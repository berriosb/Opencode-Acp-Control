# ACP v1 quick reference

OpenCode's ACP server uses JSON-RPC 2.0 over stdin/stdout with one JSON object
per line. The stable protocol version exchanged during initialization is `1`.

Authoritative references:

- [OpenCode CLI: `opencode acp`](https://opencode.ai/docs/cli/#acp)
- [ACP v1 initialization](https://agentclientprotocol.com/protocol/v1/initialization)
- [ACP v1 session setup](https://agentclientprotocol.com/protocol/v1/session-setup)
- [ACP v1 prompt turn](https://agentclientprotocol.com/protocol/v1/prompt-turn)
- [ACP v1 tool calls and permission requests](https://agentclientprotocol.com/protocol/v1/tool-calls)

## Client requests

### Initialize

```json
{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{},"clientInfo":{"name":"opencode-acp-control","title":"OpenCode ACP Control","version":"0.4.1"}}}
```

All client capability fields are optional. Omitted capabilities are
unsupported. Do not claim file-system or terminal support without implementing
the related client handlers.

### New session

```json
{"jsonrpc":"2.0","id":1,"method":"session/new","params":{"cwd":"/absolute/project","mcpServers":[]}}
```

### Load session

Requires `agentCapabilities.loadSession: true` in the initialize response.

```json
{"jsonrpc":"2.0","id":2,"method":"session/load","params":{"sessionId":"sess_abc123","cwd":"/absolute/project","mcpServers":[]}}
```

### Prompt

```json
{"jsonrpc":"2.0","id":3,"method":"session/prompt","params":{"sessionId":"sess_abc123","prompt":[{"type":"text","text":"Explain the project."}]}}
```

The matching response ends the turn:

```json
{"jsonrpc":"2.0","id":3,"result":{"stopReason":"end_turn"}}
```

### Cancel

This is a notification: omit `id` and expect no direct response.

```json
{"jsonrpc":"2.0","method":"session/cancel","params":{"sessionId":"sess_abc123"}}
```

## Agent messages

### Session update notification

```json
{"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"sess_abc123","update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"Working..."}}}}
```

### Permission request

The agent chooses the offered option IDs. Do not invent legacy `reply` values.

```json
{"jsonrpc":"2.0","id":5,"method":"session/request_permission","params":{"sessionId":"sess_abc123","toolCall":{"toolCallId":"call_1"},"options":[{"optionId":"allow-once","name":"Allow once","kind":"allow_once"},{"optionId":"reject-once","name":"Reject","kind":"reject_once"}]}}
```

Selected response:

```json
{"jsonrpc":"2.0","id":5,"result":{"outcome":{"outcome":"selected","optionId":"allow-once"}}}
```

Cancelled response:

```json
{"jsonrpc":"2.0","id":5,"result":{"outcome":{"outcome":"cancelled"}}}
```

## JSON-RPC errors

Use `-32601` when OpenCode calls a client method the caller does not implement:

```json
{"jsonrpc":"2.0","id":9,"error":{"code":-32601,"message":"Method not found"}}
```
