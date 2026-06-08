# OpenCode ACP Control

**Control OpenCode directly via the Agent Client Protocol (ACP).**

This repository contains a reusable **skill** (`.md`-based instruction set) that enables AI coding agents to start, control, and monitor OpenCode sessions over the **Agent Client Protocol (ACP)**.

## What It Does

- Start OpenCode in ACP mode
- Create, resume, and cancel sessions
- Send prompts and stream responses
- Resume past conversations from saved session IDs
- Check for and trigger OpenCode updates

## Quick Start

```bash
# Clone
git clone https://github.com/berriosb/Opencode-Acp-Control.git
cd Opencode-Acp-Control

# Load as skill (Hermes Agent)
# Option A — copy into the active profile's skills dir
cp SKILL.md ~/.hermes/profiles/<profile>/skills/opencode-acp-control.md

# Option B — load from a custom path (Hermes picks up any .md under the skills tree)
mkdir -p ~/.hermes/profiles/<profile>/skills/opencode-acp-control
cp SKILL.md ~/.hermes/profiles/<profile>/skills/opencode-acp-control/SKILL.md
```

## Try It Locally

```bash
# Print the JSON-RPC frames the skill produces (no opencode needed)
python3 examples/acp_demo.py --dry-run

# Spawn opencode acp, run initialize + session/new, and exit (no LLM call)
python3 examples/acp_demo.py --no-prompt

# Full end-to-end run (requires a configured LLM provider)
python3 examples/acp_demo.py --cwd /path/to/project --prompt "list the files in this repo"
```

## Requirements

- **OpenCode** (≥ v1.1.0) — installed and available on `$PATH`
- A terminal with background process support
- An ACP-compatible agent (Hermes, Clawdbot, etc.)

## How It Works

| Step | Action | Description |
|------|--------|-------------|
| 1 | `opencode acp` | Start OpenCode in ACP (background) mode |
| 2 | `initialize` | Initialize JSON-RPC 2.0 connection |
| 3 | `session/new` | Create a new coding session |
| 4 | `session/prompt` | Send prompts, stream responses |
| 5 | `session/cancel` | Cancel mid-response if needed |
| 6 | `session/load` | Resume a previous session by ID |

## Tool Requirements for AI Agents

This skill uses these agent tools (names vary by platform):

| Generic Name | Hermes Agent | Clawdbot |
|-------------|-------------|----------|
| Run command | `terminal()` | `bash()` |
| Write to process | `process.write()` | `process.write()` |
| Read process output | `process.poll()` | `process.poll()` |
| Kill process | `process.kill()` | `process.kill()` |
| Web fetch | `web_extract()` | `webfetch()` |
| User prompt | `clarify()` | `askUser()` |

## Files

- `SKILL.md` — The skill definition (load this into your agent)
- `examples/acp_demo.py` — Runnable Python script that demonstrates the full ACP workflow against a live `opencode acp` process
- `.github/workflows/ci.yml` — CI: `markdownlint` + URL link check + Python syntax check
- `CHANGELOG.md` — Release notes
- `_meta.json` — Registry metadata (Hermes)

## License

MIT — see [LICENSE](./LICENSE).
