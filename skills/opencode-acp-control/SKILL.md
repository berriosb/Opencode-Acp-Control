---
name: opencode-acp-control
description: Start, drive, monitor, resume, and stop OpenCode CLI sessions over ACP. Use when an agent must control `opencode acp` programmatically through JSON-RPC, especially in runtimes whose background-process tools close stdin or that have no Python. Includes a persistent-FD FIFO controller and a standalone Bash workflow.
metadata:
  version: "0.4.0"
  license: "MIT"
---

# OpenCode ACP Control

Control OpenCode through ACP v1 over newline-delimited JSON-RPC.

## Critical transport rule

OpenCode ACP uses stdin/stdout as the transport. Its stdin writer **must remain
open for the entire ACP process lifetime**.

Never use this as the default startup recipe:

```text
terminal(command: "opencode acp --cwd ...", background: true)
process.write(processId, frame)
```

Some runtimes close a background process's stdin immediately. OpenCode then
receives EOF and exits before `initialize`. A one-shot `echo > fifo` has the
same defect when it is the FIFO's final writer.

The recommended recipe is the bundled `scripts/run.py`. It starts
`scripts/helper.sh`, whose controller owns a permanent FIFO write descriptor.
Each `send` command may open and close its own writer without causing EOF. If
Python is unavailable, `helper.sh` can run independently as the transport
controller; the calling agent must then perform sending, polling, locking, and
cleanup itself as documented below.

Only use a host's native background-process API when its documentation or a
preflight proves that writable stdin remains attached after the launch call
returns. Native support is an optimization, not a portable assumption.

## Requirements

- Unix-like runtime with Bash and `mkfifo`
- POSIX `awk` for line-cursor polling in the no-Python recipe
- Python 3.9 or newer for the recommended `run.py` interface; optional when
  using `helper.sh` directly
- `opencode` on `PATH`
- An absolute project working directory

Resolve `<skill-dir>` to the directory containing this `SKILL.md`. Do not copy
`run.py` away from `helper.sh`; it resolves the helper relative to itself.

## Primary startup recipe

### 1. Start the transport

Launch this command with the host's background-process tool:

```bash
python3 <skill-dir>/scripts/run.py start --foreground --cwd /absolute/project
```

The host may close the command's stdin; this controller does not read it. Poll
the background output until the helper prints:

```text
READY<TAB>/tmp/opencode-acp.x<TAB>100<TAB>101
```

Save the path after `READY` as `runtimeDir`; it is the transport handle. The
last two values are the controller and OpenCode PIDs, not the OpenCode session
ID. Then confirm both are alive with `run.py status`.

If a host explicitly supports detached descendants and no background-process
handle is available, omit `--foreground`:

```bash
python3 <skill-dir>/scripts/run.py start --cwd /absolute/project
```

This returns a JSON status object after detaching. Do not use detached mode in a
runtime that automatically reaps descendants when the launch command exits.

### 2. Initialize and verify the transport

Only advertise client capabilities the calling agent actually implements. This
minimal handshake advertises none:

```bash
python3 <skill-dir>/scripts/run.py send \
  --runtime-dir <runtime-dir> \
  --frame '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{},"clientInfo":{"name":"opencode-acp-control","title":"OpenCode ACP Control","version":"0.4.0"}}}'
```

Poll from line zero:

```bash
python3 <skill-dir>/scripts/run.py read \
  --runtime-dir <runtime-dir> --from-line 0 --wait 2
```

Save the returned `nextLine` as the next cursor. Do not send `session/new`
until a response with `id: 0` confirms `result.protocolVersion: 1`.

If the controller or OpenCode exits before this response, classify it as a
transport/startup failure. Inspect `<runtime-dir>/stderr.log` and
`<runtime-dir>/controller.log`; do not mislabel it as an ACP method error.

### 3. Create a session

Increment the request ID and send:

```json
{"jsonrpc":"2.0","id":1,"method":"session/new","params":{"cwd":"/absolute/project","mcpServers":[]}}
```

Poll using the saved line cursor. Save `result.sessionId` exactly as returned.

### 4. Send a prompt

```json
{"jsonrpc":"2.0","id":2,"method":"session/prompt","params":{"sessionId":"sess_abc123","prompt":[{"type":"text","text":"List the files in this project."}]}}
```

Poll repeatedly, always replacing the cursor with the newest `nextLine`.
Preserve `session/update` notifications in order. A prompt finishes only when
the response whose `id` matches the prompt request contains
`result.stopReason` or an `error`.

### 5. Stop and clean up

Always stop the transport when finished:

```bash
python3 <skill-dir>/scripts/run.py stop --runtime-dir <runtime-dir>
```

This signals the exact controller, closes permanent FD 3, lets OpenCode exit on
stdin EOF, escalates to `TERM` only if needed, removes the FIFO nodes, and then
removes the owned runtime directory. Use `--keep-runtime` only when logs are
needed; later run `clean` on the stopped runtime.

## No-Python environment: use helper.sh directly

`scripts/helper.sh` can operate without `run.py` or Python. It is a complete
transport lifecycle controller, but it is not a complete ACP client.

Used by itself, the helper still:

- creates the private runtime directory and stdin/stdout FIFO pair;
- starts the exact `opencode acp --cwd ...` child;
- permanently holds FD 3 as the stdin writer;
- continuously drains stdout through FD 4 into `frames.ndjson`;
- records controller and OpenCode PIDs;
- handles `INT`, `TERM`, `HUP`, child waiting, graceful EOF, and FIFO cleanup.

It does **not** provide `run.py`'s JSON validation, cross-process writer lock,
structured line-cursor result, PID ownership verification, stale-runtime repair,
or automatic removal of retained logs. The calling agent owns those duties.

### 1. Create and save a private runtime directory

Run:

```bash
mktemp -d "${TMPDIR:-/tmp}/opencode-acp.XXXXXX"
```

Save the exact printed path as `runtimeDir`. Substitute that literal path in
later commands; do not assume shell variables survive across agent tool calls.
The helper also forces the directory mode to `0700`.

### 2. Start helper.sh with the background-process tool

```bash
bash <skill-dir>/scripts/helper.sh start \
  --cwd /absolute/project \
  --runtime-dir /tmp/opencode-acp.ABC123
```

The command intentionally remains running. The host may close its stdin because
the helper never reads controller commands from stdin. Poll the background
output until it reports:

```text
READY<TAB>/tmp/opencode-acp.ABC123<TAB>100<TAB>101
```

Save the controller PID and OpenCode PID from this current `READY` line. At this
point the runtime contains:

```text
stdin.fifo       # write one nd-JSON request or response frame here
stdout.fifo      # owned and drained by helper FD 4; do not read directly
frames.ndjson    # append-only OpenCode stdout queue; poll this file
stderr.log       # OpenCode diagnostics
state            # starting, ready, or stopped:<exit-status>
controller.pid
opencode.pid
```

### 3. Send initialize through the stdin FIFO

Use `printf`, not `echo`, and terminate every frame with exactly one newline:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{},"clientInfo":{"name":"opencode-acp-control-shell","title":"OpenCode ACP Control Shell","version":"0.4.0"}}}' \
  >/tmp/opencode-acp.ABC123/stdin.fifo
```

This command opens and closes a one-shot FIFO writer. It does not end OpenCode,
because the controller still owns permanent FD 3.

Without `run.py` locking, send exactly one frame at a time and never run two
writers concurrently. Concurrent writers, especially with frames larger than
`PIPE_BUF`, can interleave and corrupt the nd-JSON stream. The calling agent
must also ensure that each frame is a valid, single-line JSON-RPC 2.0 object
before writing it.

### 4. Poll complete stdout frames with a line cursor

Use an integer cursor beginning at `0`. This example prints every line after
cursor zero and reports the last line it observed:

```bash
awk -v from=0 '
  NR > from { print }
  { last = NR }
  END { print "NEXT_LINE=" (last + 0) > "/dev/stderr" }
' /tmp/opencode-acp.ABC123/frames.ndjson
```

Save the reported `NEXT_LINE` value. On the next poll replace `from=0` with
that value. The `awk` invocation derives frames and the next cursor from the
same file read, avoiding a race between separate `sed` and `wc` commands.

Parse each printed line as an independent JSON-RPC object. Complete the normal
`initialize` → `session/new` → `session/prompt` workflow using the frames in
[references/api.md](references/api.md). Continue responding to server-to-client
requests such as `session/request_permission` while waiting for the prompt's
matching terminal response.

### 5. Check status and diagnostics

```bash
cat /tmp/opencode-acp.ABC123/state
kill -0 "$(cat /tmp/opencode-acp.ABC123/controller.pid)"
kill -0 "$(cat /tmp/opencode-acp.ABC123/opencode.pid)"
```

Only use these PIDs with the runtime created during the current launch. Unlike
`run.py status`, these shell checks do not protect against stale PID reuse.
Inspect `stderr.log` if either process exits before the initialize response.

### 6. Stop the standalone controller

Compare `controller.pid` with the controller PID saved from the current
`READY` line. If they match, request an ordered shutdown:

```bash
kill -TERM "$(cat /tmp/opencode-acp.ABC123/controller.pid)"
```

Poll the background output for `STOPPED` or read `state` until it starts with
`stopped:`. The helper closes FD 3, lets OpenCode exit on EOF, sends `TERM` if
the child does not exit during the grace period, closes FD 4, and unlinks both
FIFO nodes. It intentionally retains the regular logs and state for diagnosis.

After confirming a normal stopped state, remove only the exact owned runtime:

```bash
runtime_dir=/tmp/opencode-acp.ABC123
owner=$(cat "$runtime_dir/.owner")
state=$(cat "$runtime_dir/state")

if [[ "$owner" == "opencode-acp-control-runtime-v1" && "$state" == stopped:* ]]; then
  rm -r -- "$runtime_dir"
else
  printf 'Refusing to remove unverified or active runtime: %s\n' "$runtime_dir" >&2
fi
```

`SIGKILL` and host crashes cannot run the helper trap. The kernel still closes
all FDs, so OpenCode receives EOF, but FIFO nodes may remain and `state` may
still say `ready`. Without Python's ownership checks, do not automatically
remove or signal such a stale runtime; inspect the recorded PIDs and process
command lines first.

## State to track

| Field | Meaning |
|---|---|
| `runtimeDir` | Transport/controller handle created by the startup recipe |
| `controllerPid` | Shell process that owns FIFO FDs and cleanup |
| `opencodePid` | Exact OpenCode child process |
| `sessionId` | Opaque OpenCode conversation ID from `session/new` |
| `nextId` | Next client JSON-RPC request ID; start at 0 and increment |
| `nextLine` | Read cursor returned by `run.py read` or standalone `awk` |
| `pendingRequests` | Server-to-client request IDs awaiting a response |

An OpenCode `sessionId` can survive a transport restart; `runtimeDir` cannot.
Loading a conversation never proves that the old FIFO or controller is alive.

## Protocol rules

- Send one JSON object per line, terminated by `\n`. Do not use LSP
  `Content-Length` framing.
- Requests have unique IDs. Notifications have no ID and receive no response.
- Complete `initialize` before any session method.
- `cwd` in session lifecycle requests must be absolute.
- Treat stdout as protocol-only. Diagnostics belong on stderr.
- Never advertise `fs` or `terminal` client capabilities unless the caller
  implements every corresponding server-to-client method and response.
- Serialize sends through `run.py`; without Python, enforce one writer at a
  time manually so frames cannot interleave.

See [references/api.md](references/api.md) for current ACP v1 frames.

## Server-to-client requests

While waiting for a prompt response, continue processing frames. A frame with
both `method` and `id` is a request from OpenCode and must receive a response.

For `session/request_permission`, show the supplied `options` to the user. Send
back the exact selected `optionId`:

```json
{"jsonrpc":"2.0","id":5,"result":{"outcome":{"outcome":"selected","optionId":"allow-once"}}}
```

If the prompt is cancelled, answer every pending permission request with:

```json
{"jsonrpc":"2.0","id":5,"result":{"outcome":{"outcome":"cancelled"}}}
```

Never silently auto-approve a permission unless the user has already granted a
policy that covers that exact operation.

If an unimplemented server request arrives, return JSON-RPC error `-32601`
instead of ignoring it; otherwise OpenCode may wait forever.

## Cancel, load, and status

Cancel is a notification and has no response:

```json
{"jsonrpc":"2.0","method":"session/cancel","params":{"sessionId":"sess_abc123"}}
```

Only call `session/load` if the initialize response advertises
`agentCapabilities.loadSession: true`:

```json
{"jsonrpc":"2.0","id":3,"method":"session/load","params":{"sessionId":"sess_abc123","cwd":"/absolute/project","mcpServers":[]}}
```

Check transport liveness independently of session state:

```bash
python3 <skill-dir>/scripts/run.py status --runtime-dir <runtime-dir>
```

Both `controllerAlive` and `opencodeAlive` must be true before sending.

## Failure handling

| Symptom | Meaning | Action |
|---|---|---|
| Exit before initialize response | Broken stdio lifecycle or startup failure | Inspect logs; restart controller |
| `OpenCode has no live reader` | Child exited or stdin transport broke | Check status/stderr; do not retry on stale FIFO |
| Empty read with state `ready` | No complete frame is queued yet | Poll again with the same cursor |
| Malformed entry reported by `read` | Non-JSON data appeared on stdout | Preserve it for diagnosis; continue from `nextLine` |
| Prompt exceeds five minutes | Model/network stall or unanswered client request | Check pending requests, then cancel |
| `session/load` error | Unsupported, stale, or deleted session | Verify capability; fall back to `session/new` |

For FD ownership, cleanup invariants, and recovery details, read
[references/guidelines.md](references/guidelines.md).
