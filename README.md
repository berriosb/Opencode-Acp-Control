# OpenCode ACP Control

> **A reusable AI agent skill that lets coding agents drive OpenCode CLI sessions over the Agent Client Protocol (ACP).**
> **1.1K+ downloads on [ClawHub](https://clawhub.ai/berriosb/skills/opencode-acp-control-3) — used in production agent workflows.**

[![ClawHub Downloads](https://img.shields.io/badge/ClawHub-1.1K%20downloads-orange?style=flat-square)](https://clawhub.ai/berriosb/skills/opencode-acp-control-3)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](./LICENSE)
[![Protocol: ACP (JSON-RPC 2.0)](https://img.shields.io/badge/Protocol-ACP%20%2F%20JSON--RPC%202.0-green?style=flat-square)](https://agentclientprotocol.com)
[![OpenCode ≥ v1.1.0](https://img.shields.io/badge/OpenCode-%E2%89%A5%20v1.1.0-black?style=flat-square)](https://opencode.ai)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![CI: markdownlint + lychee + ruff](https://img.shields.io/badge/CI-markdownlint%20%2B%20lychee%20%2B%20ruff-success?style=flat-square)](./.github/workflows/ci.yml)

---

## What it does

This repository contains a reusable **skill** (`.md`-based instruction set) that enables AI coding agents — such as [Hermes Agent](https://hermes-agent.nousresearch.com) and Clawdbot — to **start, control, and monitor [OpenCode](https://opencode.ai) CLI sessions** over the standardized [Agent Client Protocol (ACP)](https://agentclientprotocol.com), which speaks **JSON-RPC 2.0** over stdio.

In plain terms: an AI agent can spin up an OpenCode session, send it coding tasks, stream responses back, resume old conversations by ID, and shut it down — all through a documented JSON-RPC interface.

### Capabilities

- ✅ Start OpenCode in ACP background mode (`opencode acp`)
- ✅ Create, resume, and cancel sessions
- ✅ Send prompts and stream responses
- ✅ Resume past conversations from saved session IDs
- ✅ Check for and trigger OpenCode updates

---

## Why it matters

Most AI coding agents today are isolated: they can't reliably spawn, supervise, or coordinate other coding CLIs. **ACP** is the open standard (JSON-RPC 2.0 over stdio) that fixes this — but agents need explicit instructions to use it correctly (handshake order, framing, permission requests, session IDs).

This skill packages that knowledge into a drop-in instruction set any ACP-compatible agent can load. Instead of every agent author re-discovering the protocol quirks, they load `SKILL.md` and get the working workflow.

**Result:** agents become orchestrators, not isolated tools.

---

## Traction

| Metric | Value | Source |
|---|---|---|
| Downloads on ClawHub | **1.1K+** | [clawhub.ai/berriosb/skills/opencode-acp-control-3](https://clawhub.ai/berriosb/skills/opencode-acp-control-3) |
| Current version | **v0.1.1** (ClawHub) / **v0.2.0** (GitHub) | ClawHub dashboard |
| Last updated | **May 17, 2026** | ClawHub dashboard |
| Stars | 2 | GitHub |
| License | MIT | [LICENSE](./LICENSE) |

> The GitHub repo is the source of truth for development. ClawHub is the distribution channel for agent authors who install the skill with one command.

---

## Quick start

### Install the skill into your agent

```bash
# ClawHub (recommended for OpenClaw / Clawdbot users)
openclaw skills install @berriosb/opencode-acp-control-3

# Or clone and load manually
git clone https://github.com/berriosb/Opencode-Acp-Control.git
cd Opencode-Acp-Control

# Hermes Agent — copy into the active profile's skills dir
# Option A — flat file
cp SKILL.md ~/.hermes/profiles/<profile>/skills/opencode-acp-control.md

# Option B — folder (Hermes picks up any SKILL.md under the skills tree)
mkdir -p ~/.hermes/profiles/<profile>/skills/opencode-acp-control
cp SKILL.md ~/.hermes/profiles/<profile>/skills/opencode-acp-control/SKILL.md
```

### Try it locally (no LLM needed)

```bash
# Print the JSON-RPC frames the skill produces (no OpenCode required)
python3 examples/acp_demo.py --dry-run

# Spawn `opencode acp`, run initialize + session/new, and exit (no LLM call)
python3 examples/acp_demo.py --no-prompt

# Full end-to-end run against a real project (requires a configured LLM provider)
python3 examples/acp_demo.py --cwd /path/to/project --prompt "list the files in this repo"
```

---

## Requirements

- **[OpenCode](https://opencode.ai)** ≥ v1.1.0 — installed and available on `$PATH`
- **Python 3.11+** — only for running the demo script
- **An ACP-compatible agent** — Hermes Agent, Clawdbot, or any agent that loads `.md` skills
- **A terminal with background process support**

---

## How it works

A typical ACP session with OpenCode looks like this:

| Step | Action | Description |
|---|---|---|
| 1 | `opencode acp` | Start OpenCode in ACP (background) mode |
| 2 | `initialize` | Initialize JSON-RPC 2.0 connection |
| 3 | `session/new` | Create a new coding session |
| 4 | `session/prompt` | Send prompts, stream responses |
| 5 | `session/cancel` | Cancel mid-response if needed |
| 6 | `session/load` | Resume a previous session by ID |

All frames are **newline-delimited JSON** on stdout (not LSP `Content-Length` framing) — this matches OpenCode's actual transport.

---

## Tool requirements for AI agents

This skill expects the agent runtime to expose these primitives (names vary by platform):

| Generic Name | Hermes Agent | Clawdbot |
|---|---|---|
| Run command | `terminal()` | `bash()` |
| Write to process | `process.write()` | `process.write()` |
| Read process output | `process.poll()` | `process.poll()` |
| Kill process | `process.kill()` | `process.kill()` |
| Web fetch | `web_extract()` | `webfetch()` |
| User prompt | `clarify()` | `askUser()` |

---

## Repository layout

```
Opencode-Acp-Control/
├── SKILL.md              # The skill definition — load this into your agent
├── README.md             # This file
├── CHANGELOG.md          # Release notes (Keep a Changelog format)
├── _meta.json            # Registry metadata for Hermes / ClawHub
├── LICENSE               # MIT
├── examples/
│   └── acp_demo.py       # Runnable Python script — talks to a live `opencode acp` process
└── .github/
    └── workflows/
        └── ci.yml        # CI: markdownlint + lychee URL check + ruff + python -m py_compile
```

---

## CI / quality gates

Every push runs:

- **markdownlint** — enforces consistent Markdown style
- **lychee** — fails if any documented URL returns non-2xx
- **ruff** — Python lint
- **python -m py_compile** — syntax check on the demo script

---

## Contributing

Issues and PRs are welcome. Before opening a PR:

1. `ruff check examples/` passes locally
2. `markdownlint **/*.md` passes locally
3. Bump the version in both `_meta.json` and `SKILL.md` frontmatter
4. Add an entry to `CHANGELOG.md` under a new `## [x.y.z]` heading

---

## Author

**Bastián Berríos** ([@berriosb](https://github.com/berriosb))

- 🌐 Portfolio: [hakke.cl](https://hakke.cl)
- 📦 ClawHub: [@berriosb](https://clawhub.ai/berriosb)
- 🐙 GitHub: [@berriosb](https://github.com/berriosb)

Building AI agent infrastructure, RAG systems, and automation tools for production workflows.

---

## License

MIT — see [LICENSE](./LICENSE).
