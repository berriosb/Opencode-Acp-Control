#!/usr/bin/env python3
"""Manage an OpenCode ACP transport backed by a permanent FD and FIFO pair."""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

OWNER_MARKER = "opencode-acp-control-runtime-v1"
SCRIPT_DIR = Path(__file__).resolve().parent
HELPER = SCRIPT_DIR / "helper.sh"


class TransportError(RuntimeError):
    """Raised when a controller runtime is invalid or unavailable."""


def emit(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=stream)


def pid_from(path: Path) -> int | None:
    try:
        value = int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None
    return value if value > 0 else None


def pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    proc_stat = Path("/proc") / str(pid) / "stat"
    if proc_stat.exists():
        try:
            # A zombie has exited even though kill(pid, 0) still succeeds.
            # Parse state after the last ')' to tolerate spaces/parentheses in comm.
            raw_stat = proc_stat.read_text(encoding="utf-8")
            if raw_stat.rpartition(")")[2].split()[0] == "Z":
                return False
        except (OSError, IndexError):
            pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def runtime_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    owner = path / ".owner"
    try:
        marker = owner.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise TransportError(f"not an OpenCode ACP runtime: {path}") from exc
    if marker != OWNER_MARKER:
        raise TransportError(f"runtime owner marker does not match: {path}")
    return path


def read_state(runtime: Path) -> str:
    try:
        return (runtime / "state").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def process_belongs_to_runtime(pid: int, runtime: Path) -> bool:
    """Avoid signalling a reused PID that no longer belongs to helper.sh."""
    proc_cmdline = Path("/proc") / str(pid) / "cmdline"
    if proc_cmdline.exists():
        try:
            command = proc_cmdline.read_bytes().replace(b"\0", b" ")
        except OSError:
            return False
        return str(HELPER).encode() in command and str(runtime).encode() in command

    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and str(HELPER) in result.stdout and str(runtime) in result.stdout


def command_line(pid: int) -> str:
    proc_cmdline = Path("/proc") / str(pid) / "cmdline"
    if proc_cmdline.exists():
        try:
            return proc_cmdline.read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            return ""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""
    return result.stdout if result.returncode == 0 else ""


def opencode_belongs_to_runtime(pid: int, runtime: Path) -> bool:
    if not pid_alive(pid):
        return False
    try:
        executable = (runtime / "opencode.command").read_text(encoding="utf-8").strip()
        cwd = (runtime / "cwd").read_text(encoding="utf-8").strip()
    except OSError:
        return False
    command = command_line(pid)
    return bool(command and executable in command and " acp " in f" {command} " and cwd in command)


def status_payload(runtime: Path) -> dict[str, Any]:
    controller_pid = pid_from(runtime / "controller.pid")
    opencode_pid = pid_from(runtime / "opencode.pid")
    return {
        "runtimeDir": str(runtime),
        "state": read_state(runtime),
        "controllerPid": controller_pid,
        "controllerAlive": bool(
            controller_pid and process_belongs_to_runtime(controller_pid, runtime)
        ),
        "opencodePid": opencode_pid,
        "opencodeAlive": bool(
            opencode_pid and opencode_belongs_to_runtime(opencode_pid, runtime)
        ),
    }


def command_start(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).expanduser().resolve()
    if not cwd.is_dir():
        raise TransportError(f"--cwd is not a directory: {cwd}")
    if not HELPER.is_file():
        raise TransportError(f"transport helper is missing: {HELPER}")

    if args.runtime_dir:
        runtime = Path(args.runtime_dir).expanduser().resolve()
        runtime.mkdir(mode=0o700, parents=True, exist_ok=False)
    else:
        runtime = Path(tempfile.mkdtemp(prefix="opencode-acp."))
    os.chmod(runtime, 0o700)

    command = [
        "bash",
        str(HELPER),
        "start",
        "--cwd",
        str(cwd),
        "--runtime-dir",
        str(runtime),
    ]
    if args.opencode:
        command.extend(["--opencode", str(Path(args.opencode).expanduser().resolve())])

    if args.foreground:
        os.execvp(command[0], command)

    controller_log = (runtime / "controller.log").open("ab", buffering=0)
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=controller_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    controller_log.close()

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        state = read_state(runtime)
        if state == "ready":
            payload = status_payload(runtime)
            if payload["controllerAlive"] and payload["opencodeAlive"]:
                payload["nextLine"] = 0
                emit(payload)
                return 0
        if process.poll() is not None:
            break
        time.sleep(0.05)

    details = ""
    try:
        details = (runtime / "controller.log").read_text(encoding="utf-8", errors="replace")[-2000:]
    except OSError:
        pass
    raise TransportError(
        f"controller did not become ready (runtime: {runtime})"
        + (f"; log: {details.strip()}" if details.strip() else "")
    )


def load_frame(args: argparse.Namespace) -> dict[str, Any]:
    if args.frame is not None:
        raw = args.frame
    elif args.file is not None:
        raw = Path(args.file).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    if not raw.strip():
        raise TransportError("a JSON-RPC frame is required via --frame, --file, or stdin")
    try:
        frame = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TransportError(f"invalid JSON frame: {exc}") from exc
    if not isinstance(frame, dict) or frame.get("jsonrpc") != "2.0":
        raise TransportError('frame must be a JSON object with "jsonrpc":"2.0"')
    return frame


def write_nonblocking(fd: int, payload: bytes, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    view = memoryview(payload)
    while view:
        try:
            count = os.write(fd, view)
            view = view[count:]
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TransportError("timed out writing JSON-RPC frame to FIFO")
            select.select([], [fd], [], remaining)
        except BrokenPipeError as exc:
            raise TransportError("OpenCode closed its ACP stdin") from exc


def command_send(args: argparse.Namespace) -> int:
    runtime = runtime_path(args.runtime_dir)
    if read_state(runtime) != "ready":
        raise TransportError(f"transport is not ready: {read_state(runtime)}")
    frame = load_frame(args)
    payload = (json.dumps(frame, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    fifo = runtime / "stdin.fifo"
    try:
        mode = fifo.stat().st_mode
    except OSError as exc:
        raise TransportError(f"stdin FIFO is unavailable: {fifo}") from exc
    if not stat.S_ISFIFO(mode):
        raise TransportError(f"stdin endpoint is not a FIFO: {fifo}")

    lock_path = runtime / "send.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as exc:
            if exc.errno in {errno.ENXIO, errno.ENOENT}:
                raise TransportError("OpenCode has no live reader on the stdin FIFO") from exc
            raise
        try:
            write_nonblocking(fd, payload, args.timeout)
        finally:
            os.close(fd)

    emit({"sent": True, "bytes": len(payload), "runtimeDir": str(runtime)})
    return 0


def complete_lines(path: Path) -> list[str]:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return []
    if data and not data.endswith(b"\n"):
        data = data.rsplit(b"\n", 1)[0] + b"\n" if b"\n" in data else b""
    return data.decode("utf-8", errors="replace").splitlines()


def command_read(args: argparse.Namespace) -> int:
    runtime = runtime_path(args.runtime_dir)
    frames_path = runtime / "frames.ndjson"
    deadline = time.monotonic() + args.wait
    lines: list[str] = []
    while True:
        all_lines = complete_lines(frames_path)
        lines = all_lines[args.from_line :]
        if lines or args.wait <= 0 or read_state(runtime) != "ready":
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.05, remaining))

    parsed: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=args.from_line + 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            malformed.append({"line": index, "raw": line, "error": str(exc)})
            continue
        if isinstance(value, dict):
            parsed.append(value)
        else:
            malformed.append({"line": index, "raw": line, "error": "frame is not an object"})

    emit(
        {
            "runtimeDir": str(runtime),
            "state": read_state(runtime),
            "fromLine": args.from_line,
            "nextLine": args.from_line + len(lines),
            "frames": parsed,
            "malformed": malformed,
        }
    )
    return 0


def command_status(args: argparse.Namespace) -> int:
    emit(status_payload(runtime_path(args.runtime_dir)))
    return 0


def command_stop(args: argparse.Namespace) -> int:
    runtime = runtime_path(args.runtime_dir)
    controller_pid = pid_from(runtime / "controller.pid")
    controller_owned = bool(
        controller_pid and process_belongs_to_runtime(controller_pid, runtime)
    )
    if controller_owned and controller_pid:
        if not process_belongs_to_runtime(controller_pid, runtime):
            raise TransportError("refusing to signal a PID not owned by this runtime")
        os.kill(controller_pid, signal.SIGTERM)

    deadline = time.monotonic() + args.timeout
    child_signalled = False
    while time.monotonic() < deadline:
        controller_running = bool(
            controller_pid and process_belongs_to_runtime(controller_pid, runtime)
        )
        opencode_pid = pid_from(runtime / "opencode.pid")
        opencode_running = bool(
            opencode_pid and opencode_belongs_to_runtime(opencode_pid, runtime)
        )
        if not controller_running and not opencode_running:
            break
        # If the controller vanished without running its trap, the kernel has
        # closed FD 3. Give OpenCode a grace period to observe EOF, then stop
        # the exact verified child ourselves.
        if (
            not controller_running
            and opencode_running
            and not child_signalled
            and time.monotonic() + 1.0 >= deadline
            and opencode_pid
        ):
            os.kill(opencode_pid, signal.SIGTERM)
            child_signalled = True
        time.sleep(0.05)
    else:
        # Escalate to SIGKILL if processes survived the deadline.
        opencode_pid = pid_from(runtime / "opencode.pid")
        if opencode_pid and opencode_belongs_to_runtime(opencode_pid, runtime):
            try:
                os.kill(opencode_pid, signal.SIGKILL)
            except OSError:
                pass
        if controller_pid and process_belongs_to_runtime(controller_pid, runtime):
            try:
                os.kill(controller_pid, signal.SIGKILL)
            except OSError:
                pass

        kill_deadline = time.monotonic() + 1.0
        while time.monotonic() < kill_deadline:
            controller_alive = bool(
                controller_pid and process_belongs_to_runtime(controller_pid, runtime)
            )
            opencode_alive = bool(
                opencode_pid and opencode_belongs_to_runtime(opencode_pid, runtime)
            )
            if not controller_alive and not opencode_alive:
                break
            time.sleep(0.05)
        else:
            raise TransportError("controller did not stop before timeout")

    if not read_state(runtime).startswith("stopped:"):
        # SIGKILL and some process supervisors bypass EXIT traps. Once both
        # verified processes are gone, run.py safely completes the filesystem
        # half of cleanup.
        for name in ("stdin.fifo", "stdout.fifo"):
            try:
                (runtime / name).unlink()
            except FileNotFoundError:
                pass
        (runtime / "state").write_text("stopped:external\n", encoding="utf-8")

    result = status_payload(runtime)
    result["cleaned"] = not args.keep_runtime
    if not args.keep_runtime:
        shutil.rmtree(runtime)
    emit(result)
    return 0


def command_clean(args: argparse.Namespace) -> int:
    runtime = runtime_path(args.runtime_dir)
    status = status_payload(runtime)
    if status["controllerAlive"] or status["opencodeAlive"]:
        raise TransportError("refusing to clean a runtime with live processes; run stop first")
    shutil.rmtree(runtime)
    emit({"runtimeDir": str(runtime), "cleaned": True})
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="start a FIFO controller")
    start.add_argument("--cwd", required=True, help="absolute or relative project directory")
    start.add_argument("--runtime-dir", help="new directory to use instead of a secure temp directory")
    start.add_argument("--timeout", type=float, default=5.0, help="startup timeout in seconds")
    start.add_argument(
        "--foreground",
        action="store_true",
        help="remain as the controller (launch this mode with a background-process tool)",
    )
    start.add_argument("--opencode", help=argparse.SUPPRESS)
    start.set_defaults(func=command_start)

    send = subparsers.add_parser("send", help="write one JSON-RPC frame")
    send.add_argument("--runtime-dir", required=True)
    source = send.add_mutually_exclusive_group()
    source.add_argument("--frame", help="JSON-RPC object as a string")
    source.add_argument("--file", help="file containing one JSON-RPC object")
    send.add_argument("--timeout", type=float, default=5.0, help="FIFO write timeout in seconds")
    send.set_defaults(func=command_send)

    read = subparsers.add_parser("read", help="read queued frames without consuming the log")
    read.add_argument("--runtime-dir", required=True)
    read.add_argument("--from-line", type=int, default=0, help="zero-based line cursor")
    read.add_argument("--wait", type=float, default=0.0, help="wait up to this many seconds for output")
    read.set_defaults(func=command_read)

    status = subparsers.add_parser("status", help="show controller and OpenCode liveness")
    status.add_argument("--runtime-dir", required=True)
    status.set_defaults(func=command_status)

    stop = subparsers.add_parser("stop", help="close the permanent FD and stop OpenCode")
    stop.add_argument("--runtime-dir", required=True)
    stop.add_argument("--timeout", type=float, default=5.0)
    stop.add_argument("--keep-runtime", action="store_true", help="retain regular logs after stopping")
    stop.set_defaults(func=command_stop)

    clean = subparsers.add_parser("clean", help="remove an already stopped runtime")
    clean.add_argument("--runtime-dir", required=True)
    clean.set_defaults(func=command_clean)
    return result


def main() -> int:
    args = parser().parse_args()
    if getattr(args, "from_line", 0) < 0:
        raise TransportError("--from-line must be non-negative")
    if hasattr(args, "timeout") and args.timeout <= 0:
        raise TransportError("--timeout must be positive")
    if getattr(args, "wait", 0) < 0:
        raise TransportError("--wait must be non-negative")
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TransportError, OSError) as exc:
        emit({"error": str(exc)}, stream=sys.stderr)
        raise SystemExit(1) from None
