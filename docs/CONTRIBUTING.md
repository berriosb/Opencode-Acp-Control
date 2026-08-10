# Contributing to OpenCode ACP Control

Thanks for your interest in improving this skill. Most changes here are
documentation and bundled transport scripts. The core capability is the
`skills/opencode-acp-control/` directory that an ACP-compatible agent loads.

## Quick start

```bash
git clone https://github.com/berriosb/Opencode-Acp-Control.git
cd Opencode-Acp-Control
```

Edits to the skill bundle are validated by CI:

- `markdownlint-cli` (rules in `.markdownlint.json`)
- `lychee` link checker for every URL referenced in docs
- `bash -n` on the FIFO controller
- `ruff check`, byte compilation, and pytest on the Python code

## Where to make changes

| File | What it controls |
|---|---|
| `skills/opencode-acp-control/SKILL.md` | The instruction set agents load. |
| `skills/opencode-acp-control/scripts/helper.sh` | Permanent-FD FIFO owner and cleanup controller. |
| `skills/opencode-acp-control/scripts/run.py` | User-facing transport command line. |
| `skills/opencode-acp-control/references/` | ACP and lifecycle detail loaded on demand. |
| `README.md` | Public-facing project description and quick start. |
| `docs/CHANGELOG.md` | Release notes, Keep a Changelog format. |
| `_meta.json` | Registry metadata (do not edit `ownerId`/`slug`; only bump `version`/`publishedAt` on release). |

## Style

- Markdown follows the existing tone: short sections, tables, code blocks with
  JSON-RPC frames, no marketing fluff.
- Keep the permanent-writer ownership invariant explicit: OpenCode must never
  inherit FD 3, and one-shot senders must never become the final writer.
- Bundled Python uses the standard library only (no third-party runtime deps).
- Protocol examples must match the current stable ACP v1 documentation.

## Tests

```bash
# Markdown lint
markdownlint README.md docs/*.md skills/opencode-acp-control/SKILL.md \
  skills/opencode-acp-control/references/*.md \
  skills/opencode-acp-control/assets/*.md

# Python syntax + ruff
ruff check skills/opencode-acp-control/scripts/run.py tests/
python3 -m py_compile skills/opencode-acp-control/scripts/run.py
bash -n skills/opencode-acp-control/scripts/helper.sh

# Run the fake-server transport suite (no real OpenCode/provider required)
python3 -m pytest tests/ -v
```

## Commit messages

Conventional commits in English: `feat:`, `fix:`, `docs:`, `chore:`. The
release pipeline uses standard-version to bump the version and update
`CHANGELOG.md`, so commit messages become changelog entries.

## Reporting issues

Open an issue at <https://github.com/berriosb/Opencode-Acp-Control/issues>
with:

- Which agent platform you are loading the skill into (Hermes Agent,
  Clawdbot, custom, etc.)
- The exact `opencode --version` you are running
- A minimal reproduction of the unexpected behavior

## License

By contributing, you agree that your contributions will be licensed under the
MIT License (see [`LICENSE`](../LICENSE)).
