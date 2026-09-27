"""End-to-end tests for the permanent-FD FIFO controller."""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / "skills" / "opencode-acp-control"
RUNNER = SKILL_DIR / "scripts" / "run.py"
HELPER = SKILL_DIR / "scripts" / "helper.sh"
FAKE_OPENCODE = Path(__file__).with_name("fake_opencode.py")


def run_cli(*args: str, check: bool = True) -> tuple[subprocess.CompletedProcess[str], dict]:
    process = subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = process.stdout if process.returncode == 0 else process.stderr
    payload = json.loads(output.strip().splitlines()[-1])
    if check:
        assert process.returncode == 0, process.stderr
    return process, payload


@pytest.fixture
def controller(tmp_path: Path):
    runtime = tmp_path / "runtime"
    _, started = run_cli(
        "start",
        "--cwd",
        str(tmp_path),
        "--runtime-dir",
        str(runtime),
        "--opencode",
        str(FAKE_OPENCODE),
    )
    try:
        yield runtime, started
    finally:
        if runtime.exists():
            _, status = run_cli("status", "--runtime-dir", str(runtime), check=False)
            if status.get("controllerAlive"):
                run_cli("stop", "--runtime-dir", str(runtime), check=False)
            elif runtime.exists():
                run_cli("clean", "--runtime-dir", str(runtime), check=False)


def test_skill_has_requested_bundle_layout():
    expected = [
        SKILL_DIR / "SKILL.md",
        SKILL_DIR / "scripts" / "run.py",
        SKILL_DIR / "scripts" / "helper.sh",
        SKILL_DIR / "references" / "api.md",
        SKILL_DIR / "references" / "guidelines.md",
        SKILL_DIR / "assets" / "template.md",
        SKILL_DIR / "assets" / "example.json",
    ]
    assert all(path.is_file() for path in expected)
    assert not (REPO_ROOT / "SKILL.md").exists()


def test_helper_is_valid_bash():
    result = subprocess.run(["bash", "-n", str(HELPER)], check=False, capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_controller_creates_private_fifo_pair(controller):
    runtime, started = controller
    assert started["state"] == "ready"
    assert started["controllerAlive"] is True
    assert started["opencodeAlive"] is True
    assert stat.S_ISFIFO((runtime / "stdin.fifo").stat().st_mode)
    assert stat.S_ISFIFO((runtime / "stdout.fifo").stat().st_mode)
    assert stat.S_IMODE(runtime.stat().st_mode) == 0o700
    assert stat.S_IMODE((runtime / "stdin.fifo").stat().st_mode) == 0o600


def test_one_shot_sends_do_not_deliver_eof(controller):
    runtime, _ = controller
    initialize = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {"protocolVersion": 1, "clientCapabilities": {}},
    }
    run_cli("send", "--runtime-dir", str(runtime), "--frame", json.dumps(initialize))
    _, first_read = run_cli(
        "read", "--runtime-dir", str(runtime), "--from-line", "0", "--wait", "2"
    )
    assert first_read["frames"][0]["id"] == 0
    cursor = first_read["nextLine"]

    # send exited and closed its one-shot FIFO writer. The permanent FD must
    # keep fake OpenCode alive and able to answer a second independent send.
    time.sleep(0.1)
    _, middle = run_cli("status", "--runtime-dir", str(runtime))
    assert middle["state"] == "ready"
    assert middle["opencodeAlive"] is True

    new_session = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "session/new",
        "params": {"cwd": str(runtime.parent), "mcpServers": []},
    }
    run_cli("send", "--runtime-dir", str(runtime), "--frame", json.dumps(new_session))
    _, second_read = run_cli(
        "read",
        "--runtime-dir",
        str(runtime),
        "--from-line",
        str(cursor),
        "--wait",
        "2",
    )
    assert second_read["frames"][0]["result"]["sessionId"] == "fake-session"
    assert second_read["nextLine"] == cursor + 1


def test_primary_foreground_mode_survives_closed_background_stdin(tmp_path: Path):
    runtime = tmp_path / "foreground-runtime"
    process = subprocess.Popen(
        [
            sys.executable,
            str(RUNNER),
            "start",
            "--foreground",
            "--cwd",
            str(tmp_path),
            "--runtime-dir",
            str(runtime),
            "--opencode",
            str(FAKE_OPENCODE),
        ],
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,  # Simulate background=true closing stdin.
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if (runtime / "state").exists() and (runtime / "state").read_text().strip() == "ready":
                break
            assert process.poll() is None, process.stderr.read()
            time.sleep(0.05)
        else:
            pytest.fail("foreground controller did not become ready")

        _, status = run_cli("status", "--runtime-dir", str(runtime))
        assert status["controllerAlive"] is True
        assert status["opencodeAlive"] is True
    finally:
        if runtime.exists():
            run_cli("stop", "--runtime-dir", str(runtime), check=False)
        process.wait(timeout=2)


def test_stop_closes_transport_and_removes_runtime(controller):
    runtime, _ = controller
    _, stopped = run_cli("stop", "--runtime-dir", str(runtime))
    assert stopped["state"].startswith("stopped:")
    assert stopped["controllerAlive"] is False
    assert stopped["opencodeAlive"] is False
    assert stopped["cleaned"] is True
    assert not runtime.exists()


def test_send_rejects_non_json_rpc_object(controller):
    runtime, _ = controller
    process, payload = run_cli(
        "send", "--runtime-dir", str(runtime), "--frame", '{"hello":"world"}', check=False
    )
    assert process.returncode == 1
    assert "jsonrpc" in payload["error"]


def test_stop_repairs_runtime_when_controller_cannot_trap(controller):
    runtime, started = controller
    os.kill(started["controllerPid"], signal.SIGKILL)

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        _, status = run_cli("status", "--runtime-dir", str(runtime))
        if not status["controllerAlive"] and not status["opencodeAlive"]:
            break
        time.sleep(0.05)
    else:
        pytest.fail("controller or fake OpenCode survived SIGKILL/EOF")

    _, stopped = run_cli("stop", "--runtime-dir", str(runtime))
    assert stopped["state"] == "stopped:external"
    assert stopped["cleaned"] is True
    assert not runtime.exists()


def test_child_preserves_caller_umask(controller):
    runtime, _ = controller
    query = {"jsonrpc": "2.0", "id": 10, "method": "get_umask"}
    run_cli("send", "--runtime-dir", str(runtime), "--frame", json.dumps(query))
    _, result = run_cli("read", "--runtime-dir", str(runtime), "--from-line", "0", "--wait", "2")
    child_umask = result["frames"][0]["result"]["umask"]
    # Controller uses umask 077 internally, but child must not be constrained by 077
    assert child_umask != oct(0o77)


def test_stop_escalates_to_sigkill_when_child_ignores_sigterm(controller):
    runtime, _ = controller
    # Tell fake_opencode to ignore SIGTERM
    query = {"jsonrpc": "2.0", "id": 20, "method": "ignore_sigterm"}
    run_cli("send", "--runtime-dir", str(runtime), "--frame", json.dumps(query))
    run_cli("read", "--runtime-dir", str(runtime), "--from-line", "0", "--wait", "2")

    # Stop should escalate to SIGKILL and terminate cleanly
    _, stopped = run_cli("stop", "--runtime-dir", str(runtime), "--timeout", "1.0")
    assert stopped["opencodeAlive"] is False
    assert stopped["cleaned"] is True
    assert not runtime.exists()


def test_pid_alive_handles_process_names_with_spaces(monkeypatch):
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    import run  # type: ignore

    fake_stat = "12345 (fake opencode process) Z 1 12345 0 0 -1 0 0 0 0\n"
    monkeypatch.setattr(run.Path, "exists", lambda self: True)
    monkeypatch.setattr(run.Path, "read_text", lambda self, encoding="utf-8": fake_stat)

    # Process is a zombie ("Z"), so pid_alive must return False
    assert run.pid_alive(12345) is False
