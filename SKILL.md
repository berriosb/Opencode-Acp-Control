---
name: opencode-acp-control
description: Control OpenCode through ACP (Agent Client Protocol): start ACP processes, initialize JSON-RPC sessions, create/load conversation sessions, send prompts, stream responses, cancel runs, and perform safe version/update checks. Use this skill when an agent must operate OpenCode programmatically instead of interactive CLI chat.
---

# OpenCode ACP Skill

Control OpenCode directly via the Agent Client Protocol (ACP).

## Metadata

- ACP protocol docs (LLM-oriented): https://agentclientprotocol.com/llms.txt
- GitHub repo: https://github.com/berriosb/Opencode-Acp-Control
- Report issues: https://github.com/berriosb/Opencode-Acp-Control/issues

## Quick Reference

| Action | Command pattern |
|---|---|
| Start OpenCode ACP | `opencode acp --cwd /path/to/project` |
| Write JSON-RPC message | write line-delimited JSON (`...\n`) to process stdin |
| Poll responses | read stdout/stderr periodically until terminal response |
| Stop ACP process | terminate process |
| List resumable sessions | `opencode session list` |
| Check installed version | `opencode --version` |

> The exact host tool names for process I/O vary by platform (for example: `bash + process.write/poll`, or `exec_command + write_stdin`). Keep the ACP message flow the same.

## Protocol Rules

- Use **JSON-RPC 2.0**.
- Send **newline-delimited** JSON messages.
- Keep a monotonic `id` counter for requests that require responses.
- Treat `session/update` as notifications (no `id` expected).

---

## Standard Workflow

### 1) Start ACP process

```bash
opencode acp --cwd /path/to/project
```

Store the returned process handle/id from your runtime.

### 2) Initialize protocol

Send immediately after startup:

```json
{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{"fs":{"readTextFile":true,"writeTextFile":true},"terminal":true},"clientInfo":{"name":"acp-client","title":"ACP Client","version":"1.0.0"}}}
```

Success criteria:
- response contains `result.protocolVersion: 1`

### 3) Create new OpenCode session

```json
{"jsonrpc":"2.0","id":1,"method":"session/new","params":{"cwd":"/path/to/project","mcpServers":[]}}
```

Store `result.sessionId` (example: `ses_abc123...`).

### 4) Prompt session

```json
{"jsonrpc":"2.0","id":2,"method":"session/prompt","params":{"sessionId":"ses_abc123...","prompt":[{"type":"text","text":"Your question here"}]}}
```

Poll repeatedly until final response for `id=2` includes `result.stopReason`.

### 5) Parse stream correctly

Each poll may produce multiple JSON lines:
- `method: "session/update"` → accumulate streamed content.
- `id: <request-id>` → terminal response for that request.

### 6) Cancel running generation (optional)

```json
{"jsonrpc":"2.0","method":"session/cancel","params":{"sessionId":"ses_abc123..."}}
```

`session/cancel` is a notification, so no response is required.

---

## Resume Existing Session

### 1) List sessions

```bash
opencode session list
```

Example:

```text
ID                                  Updated              Messages
ses_451cd8ae0ffegNQsh59nuM3VVy      2026-01-11 15:30     12
ses_451a89e63ffea2TQIpnDGtJBkS      2026-01-10 09:15     5
ses_4518e90d0ffeJIpOFI3t3Jd23Q      2026-01-09 14:22     8
```

### 2) Ask user which session to resume

Request either ordinal (1/2/3) or full session id.

### 3) Load the selected session

1. Start ACP process
2. Send `initialize`
3. Send:

```json
{"jsonrpc":"2.0","id":1,"method":"session/load","params":{"sessionId":"ses_451cd8ae0ffegNQsh59nuM3VVy","cwd":"/path/to/project","mcpServers":[]}}
```

Notes:
- `session/load` requires `cwd` and `mcpServers`.
- On load, history is replayed via stream updates.

---

## Polling and Timeout Strategy

- Poll interval: **~2 seconds**.
- Recommended max wait per prompt: **5 minutes**.
- If no terminal response is received:
  1. send cancel,
  2. stop process,
  3. restart + initialize,
  4. reload session if needed.

---

## State to Track

Per ACP process:
- `processId` (host runtime handle)
- `opencodeSessionId` (from `session/new` or selected from list)
- `nextMessageId` (monotonic request id)

---

## Stop Reasons

| `stopReason` | Meaning |
|---|---|
| `end_turn` | Normal completion |
| `cancelled` | Cancelled by client/user |
| `max_tokens` | Model token limit reached |

---

## Common Failure Modes

| Issue | Mitigation |
|---|---|
| Empty poll output | Continue polling; model may still be generating |
| Malformed output line | Skip that line and keep parser alive |
| ACP process exited | Restart ACP, initialize, then `session/load` |
| Stalled beyond timeout | Cancel + restart flow |

---

## Update OpenCode Safely

### 1) Check installed version

```bash
opencode --version
```

### 2) Check latest release

Inspect latest tag from:
- `https://github.com/anomalyco/opencode/releases/latest`

### 3) Update procedure

If latest > current:
1. stop running ACP processes,
2. start ACP again (auto-update happens on restart),
3. reinitialize clients,
4. verify version.

### 4) If update fails

Inform user and suggest manual install:

```bash
curl -fsSL https://opencode.dev/install | bash
```

---

## Implementation Notes

- Prefer deterministic JSON serialization (no trailing commas, always `\n` terminated).
- Keep parser robust against mixed stdout/stderr lines.
- Normalize path handling for `cwd` (absolute path preferred).
- Do not assume session id prefix beyond treating it as opaque text (`ses_*` shown as example).
