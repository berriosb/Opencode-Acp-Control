# OpenCode ACP Control

A reusable Agent Skill for controlling `opencode acp` over newline-delimited
JSON-RPC without losing the stdio transport when a host runtime closes
background stdin.

## What changed in 0.4.0

The old recipe launched `opencode acp` with a generic background tool and then
assumed `process.write()` could still reach its stdin. That is not portable.
OpenCode documents ACP as a stdin/stdout protocol, so closing stdin delivers EOF
and terminates the server.

The skill now ships a FIFO controller with an explicit ownership model:

```text
short run.py send commands ──► stdin.fifo ──► OpenCode
                                  ▲
                                  │ FD 3 stays open
                           controller shell

OpenCode ──► stdout.fifo ──► controller FD 4 ──► frames.ndjson
```

The permanent FD prevents a one-shot writer from becoming the last writer and
accidentally ending the ACP session. The controller also owns the exact child
PID, drains stdout, and performs ordered cleanup.

## Repository layout

```text
Opencode-Acp-Control/
├── README.md
├── LICENSE
├── skills/
│   └── opencode-acp-control/
│       ├── SKILL.md
│       ├── scripts/
│       │   ├── run.py
│       │   └── helper.sh
│       ├── references/
│       │   ├── api.md
│       │   └── guidelines.md
│       └── assets/
│           ├── template.md
│           └── example.json
├── docs/
└── tests/
```

The installable skill is the complete
[`skills/opencode-acp-control`](skills/opencode-acp-control/) directory. Keep
the scripts, references, and assets beside `SKILL.md`.

## Install

Clone the repository, then copy or link the skill directory into the skill root
used by your agent runtime:

```bash
git clone https://github.com/berriosb/Opencode-Acp-Control.git
cp -R Opencode-Acp-Control/skills/opencode-acp-control \
  /path/to/your/agent/skills/
```

Requirements:

- Unix-like system with Bash and `mkfifo`
- Python 3.9+
- OpenCode available as `opencode` on `PATH`

## Transport smoke test

Start the controller against a project with the command in background mode:

```bash
runtime_dir="/tmp/opencode-acp.example.$$"
python3 skills/opencode-acp-control/scripts/run.py start \
  --foreground --cwd "$PWD" --runtime-dir "$runtime_dir" &
```

Wait for its `READY` line, then send the initialize frame in
[`assets/example.json`](skills/opencode-acp-control/assets/example.json):

```bash
python3 skills/opencode-acp-control/scripts/run.py send \
  --runtime-dir "$runtime_dir" \
  --file skills/opencode-acp-control/assets/example.json

python3 skills/opencode-acp-control/scripts/run.py read \
  --runtime-dir "$runtime_dir" --from-line 0 --wait 2

python3 skills/opencode-acp-control/scripts/run.py stop \
  --runtime-dir "$runtime_dir"
```

## Controller commands

| Command | Purpose |
|---|---|
| `start --foreground --cwd DIR` | Run a controller under a background-process tool |
| `start --cwd DIR` | Detach only when the runtime preserves descendants |
| `send --runtime-dir DIR --frame JSON` | Write one validated JSON-RPC frame |
| `read --runtime-dir DIR --from-line N` | Poll complete frames using a cursor |
| `status --runtime-dir DIR` | Check controller and child liveness |
| `stop --runtime-dir DIR` | Close the permanent FD and clean the runtime |
| `clean --runtime-dir DIR` | Remove an already stopped retained runtime |

See [`SKILL.md`](skills/opencode-acp-control/SKILL.md) for the agent workflow
and [`guidelines.md`](skills/opencode-acp-control/references/guidelines.md) for
FD ownership and recovery invariants.

## Development

```bash
bash -n skills/opencode-acp-control/scripts/helper.sh
python3 -m py_compile skills/opencode-acp-control/scripts/run.py
python3 -m pytest tests/ -v
```

Project documents live under [`docs/`](docs/), including the
[`CHANGELOG`](docs/CHANGELOG.md) and
[`contribution guide`](docs/CONTRIBUTING.md).

## License

MIT — see [`LICENSE`](LICENSE).
