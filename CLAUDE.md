# CLAUDE.md — project context for Claude Code

## What this is

**Kilo Echo** (`ke`) is a self-hosted tool that drives a local AI coding agent
from a phone, through GitHub Issues. You file work as a GitHub issue; an
always-on machine polls for labeled issues, writes a plan, and — after explicit
approval — implements it on a branch and opens a PR. Engines are Aider (+ local
Ollama) or Claude Code, selected per issue by label.

**The full design is in `docs/SPEC.md`. Read it before writing code.** It is the
source of truth. If something here and the spec conflict, the spec wins; flag the
conflict rather than guessing.

## Core principles (do not violate)

- **Safe by construction.** Polling only — the tool makes outbound calls and
  never listens on a network port. Nothing inbound.
- **Two-key build gate.** Code is written only when an issue has BOTH `build` and
  `approved` labels. `approved` is removed after a successful build.
- **Isolated writes.** Engine changes go on a fresh `ke/<issue>-<slug>` branch off
  `base_branch`; push with `--force-with-lease` to that branch only. Never write
  to `main` directly.
- **No secrets in the repo.** Auth is via `gh auth login`. `kiloecho.toml` is
  gitignored. Never embed API keys.

## Tech & conventions

- Python ≥ 3.11, standard library first; avoid heavy deps without reason.
- GitHub and git operations go through the `gh` CLI and `git`, wrapped in
  `github.py`. Do not call the GitHub REST API directly with raw tokens.
- Config is TOML (`kiloecho.toml`), loaded via `config.py` into dataclasses.
- CLI entry point is `ke` (also `kiloecho`), defined in `__main__.py`.
- Lint/format with `ruff`; tests with `pytest`. Keep `tests/test_logic.py`
  runnable WITHOUT aider/claude/gh installed (pure logic: routing, gate,
  slugging, prompt construction).
- Prefer small, focused modules matching the architecture in SPEC §14.

## Module layout (target)

```
kiloecho/  __main__.py config.py github.py engines.py orchestrator.py
           cost.py log.py status.py doctor.py
scripts/   init-labels.sh
packaging/ kiloecho.service  windows-task.ps1
tests/     test_logic.py
```

## Build order (SPEC §17) — build in this sequence

1. **Core loop first.** plan → two-key gated build → branch → PR; polling + ack
   reaction; engine selection by label; retry-once; revise-via-label; sequential
   processing; JSONL run log; `config.py`, `github.py`, `engines.py`,
   `orchestrator.py`, `__main__.py` (`run`/`once`/`init`/`doctor`), logic tests.
2. **Cost addon** (`cost.py`) — decoupled; consumes a neutral "run finished"
   event. The core must run identically if cost is disabled/absent.
3. **Status view** (`status.py`) — localhost/terminal only; reads the run log.
4. **Parallel** (behind `parallel` flag) and **automerge** polish.
5. **Packaging** — `doctor.py`, service files, label script for release.

Ship and verify increment 1 before starting 2.

## Engine specifics (verified — see SPEC §9)

- **Aider:** run with `--analytics-log <runfile>`; cost/tokens come from the
  `message_send` event (`prompt_tokens`, `completion_tokens`, `cost`,
  `total_cost`). Plan mode: read-only (`--chat-mode ask`), no edits.
- **Claude Code:** run with `--output-format json`; parse `total_cost_usd` and
  `usage`. Plan mode must not edit files. NOTE: avoid relying on Claude Code
  v2.1.83 — its `-p` mode returns an empty result (tokens still billed). v2.1.78
  works. `ke doctor` should check the version.

## Guardrails for you, the agent

- Read `docs/SPEC.md` fully before implementing a section.
- Keep changes scoped to the increment being built; don't jump ahead.
- Write tests alongside code; keep logic tests dependency-free.
- When a design decision isn't covered by the spec, ask or note it — don't
  silently invent behavior that affects safety (gating, pushing, merging).
