# Claude Code build prompts (Kilo Echo)

Run these in order, in a Claude Code session started inside the repo folder.
`CLAUDE.md` is read automatically, so these prompts stay short. **Verify each
increment before sending the next.** Don't paste them all at once.

---

## 0. Orient (first message of the session)

```
Read CLAUDE.md and docs/SPEC.md in full. Then give me a short summary of the
v1 build plan and the module layout you'll create, and confirm you'll build
increment 1 (the core loop) only for now. Do not write any code yet — just
confirm your understanding and flag anything in the spec that's ambiguous or
that you'd decide differently.
```

*Why first: surfaces misreadings before any code exists. Answer any flags, then
proceed.*

---

## 1. Core loop — scaffold + config + github wrapper

```
Build the project skeleton for increment 1: the package directory `kiloecho/`
with empty-but-importable modules per SPEC §14, plus `config.py` (TOML loading
into dataclasses, per SPEC §13) and `github.py` (a wrapper over `gh` and `git`
for issues, comments, reactions, labels, branches, PRs).

Then write `tests/test_logic.py` covering config loading and any pure logic so
far, runnable with pytest WITHOUT gh/aider/claude installed. Run the tests and
show me they pass.
```

---

## 2. Core loop — engines

```
Implement `engines.py` per SPEC §9 and the engine specifics in CLAUDE.md:
plan/build/revise prompt builders, plus Aider and Claude Code drivers. Plan mode
must not edit files (aider `--chat-mode ask`; claude with edit tools disabled).
Capture tokens/cost where available (aider `--analytics-log`, claude
`--output-format json`) but expose it as a neutral result object — do NOT couple
it to cost logic yet.

Add logic tests for prompt construction and engine selection. Run tests.
```

---

## 3. Core loop — orchestrator + CLI

```
Implement `orchestrator.py` (the tick loop: routing, the two-key build gate,
instant ack reaction, retry-once, revise-via-label, sequential processing) and
`log.py` (append-only JSONL run log). Wire `__main__.py` with the `ke` commands:
`run`, `once`, `init`, and a minimal `doctor`.

Enforce the safety rules from CLAUDE.md exactly: build requires both `build` and
`approved`; `approved` is cleared after a successful build; changes go on a fresh
`ke/<issue>-<slug>` branch; never write main directly. Honor `dry_run`.

Add logic tests for the gate, routing, and branch-name slugging (no engines/gh
needed). Run tests and show the full `ke --help` output.
```

---

## 4. Verify increment 1 end to end (dry run)

```
With dry_run = true in a sample kiloecho.toml, walk me through exactly what
happens for: (a) an issue labeled `plan`, (b) an issue labeled `build` only,
(c) an issue labeled `build` + `approved`, (d) an issue labeled `revise`.
Show the decisions logged, confirming no engine calls or pushes occur in dry_run.
Fix anything that doesn't match the spec.
```

*Stop here and try it for real on a throwaway repo before continuing.*

---

## 5. Cost addon (increment 2)

```
Implement `cost.py` per SPEC §9 as a decoupled addon: consume the neutral
"run finished" event the core already emits, write a `costs.jsonl` ledger, and
maintain per-issue and per-day totals. The core must behave identically if the
cost addon is disabled or absent — verify that with a test. Surface per-run cost
in the result comment and totals for the status view to read.
```

---

## 6. Status view (increment 3)

```
Implement `status.py`: a localhost/terminal-only status view that reads the run
log and cost ledger and shows the queue, current run, recent outcomes, and
running cost totals. No network exposure. Wire it to `ke status`.
```

---

## 7. Packaging & release polish (increments 4–5)

```
Finish for release: flesh out `doctor.py` (check gh auth, engines on PATH,
Claude Code version is not 2.1.83, repo reachable); add `scripts/init-labels.sh`;
add `packaging/kiloecho.service` (systemd user unit) and
`packaging/windows-task.ps1` (Scheduled Task). Implement the `parallel` flag with
git worktrees and the `automerge` label behavior. Update README if commands
changed.
```

---

## Tips while running

- After each increment, review the diff yourself and commit before the next.
- If Claude Code drifts from the spec, point it back: "re-read SPEC §X."
- Keep `dry_run = true` until you've watched a full plan→build cycle behave.
- Test the `claude` engine path only after confirming your installed Claude Code
  version isn't 2.1.83.
