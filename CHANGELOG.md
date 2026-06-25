# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-06-25

### Changed

- README rewritten to surface traction (1.1K+ downloads on ClawHub), add hero badges, "Why it matters" section, traction table, and author block. No functional change to the skill itself.
- Bumped `SKILL.md` frontmatter version and `clientInfo.version` in the `initialize` example from `0.2.0` to `0.3.0` to stay in sync with the registry `_meta.json`.

## [0.2.0] - 2026-06-06

### Fixed

- `SKILL.md` `initialize` example identified itself as `clawdbot`/`Clawdbot` v1.0.0; corrected to `opencode-acp-control` / `OpenCode ACP Control` v0.2.0.
- `SKILL.md` release-check URL pointed at `anomalyco/opencode` (404). Corrected to `sst/opencode`.
- `SKILL.md` `updateOpenCode()` example also pointed at `anomalyco/opencode`; corrected to `sst/opencode`.
- `SKILL.md` install URL was `opencode.dev`. Corrected to `opencode.ai`.
- Added safety note alongside the `curl | bash` install command.
- `README.md` referenced a non-existent `hermes skill install` subcommand. Replaced with the two real copy-into-skills-dir patterns.
- Version drift: `_meta.json` said `0.1.0`, `SKILL.md` frontmatter said `1.0.2`. Aligned both to `0.2.0`.

### Added

- `examples/acp_demo.py` — runnable Python script that talks to a live `opencode acp` process over stdio JSON-RPC. Sends `initialize` + `session/new` and (optionally) a `session/prompt`, then streams `session/update` notifications until completion. Uses newline-delimited JSON framing (not LSP `Content-Length`) — matches OpenCode's actual transport. Includes `--dry-run` and `--no-prompt` modes for environments without an LLM provider configured.
- `.github/workflows/ci.yml` — CI that runs `markdownlint-cli` on every `.md`, fails if any of the URLs documented in `SKILL.md` / `README.md` / `CHANGELOG.md` return a non-2xx status (via `lychee`), and byte-compiles the demo script with Python 3.11.
- This `CHANGELOG.md`.

## [0.1.0] - 2026-01-29

### Added

- Initial public release: `SKILL.md` describing the OpenCode ACP workflow (initialize, session/new, session/prompt, session/cancel, session/load, update detection).
- `_meta.json` registry metadata.
- `README.md` with quick-start, tool mapping, and license.
- `LICENSE` (MIT).
