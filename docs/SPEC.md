# Kilo Echo — Specification (v1)

> Drive a local AI coding agent from your phone, through GitHub Issues.
> Self-hosted, local-model-first, zero inbound network exposure.

**Name:** Kilo Echo (NATO phonetic for **K E**). CLI command: `ke` (full name
`kiloecho`). Package/repo: `kiloecho`.

---

## 1. Purpose & principles

Kilo Echo turns GitHub Issues into the control plane for an AI development agent
running on your own always-on machine. You file work from anywhere (the GitHub
mobile app); Kilo Echo plans it, and on your explicit approval, implements it on
a branch and opens a PR. Engines are local (Aider + Ollama) or Claude Code,
selected per issue.

Guiding principles:

- **Safe by construction.** Nothing inbound ever reaches the PC (polling only,
  outbound calls). Code is only written after a two-key approval and always
  lands on a throwaway branch behind a PR — never on `main`.
- **Simple & fluent.** Capture and review happen entirely in the GitHub mobile
  app. Polling at 60s plus an instant acknowledgment reaction makes it feel live.
- **Local-first.** Your code and (optionally) your models stay on your hardware.
  The only required external calls are to the GitHub API via `gh`.
- **Open source.** MIT. Small, hackable, engine-agnostic.

---

## 2. Core concepts

### 2.1 Lifecycle

```
            ┌────────── you, on your phone ──────────┐
            │                                         │
   file issue (template)                       review PR / plan
            │                                         ▲
            ▼                                         │
  ┌───────────────┐   plan    ┌───────────────┐  build+approved  ┌──────────────┐
  │   new issue   │──label───►│  PLAN phase   │──── labels ──────►│  BUILD phase │
  │  (any intent) │           │ spec comment  │                   │ branch→PR    │
  └───────────────┘           └───────────────┘                   └──────────────┘
                                      │                                  │
                                  planned                          done / failed
```

### 2.2 Phases

- **PLAN** — engine reads the issue and writes a *spec only*: approach, affected
  files, step-by-step plan, risks, estimate. No files changed, no code. Posted
  as an issue comment. A proposal to read on the phone.
- **BUILD** — engine implements against the issue (and the approved plan if
  present). Kilo Echo creates a branch off `base_branch`, lets the engine edit,
  commits, pushes that branch only, and opens a PR with a result summary.

### 2.3 The two-key build gate

Build never runs on the `build` label alone. The issue must **also** carry
`approved`. `build` = "this should be implemented"; `approved` = "I authorize
writing and pushing code now." This prevents a single accidental label-tap from
launching an agent that pushes code. On successful build, `approved` is removed
so any re-run requires fresh authorization.

---

## 3. Labels (the entire control surface)

| Label        | Meaning / effect                                                        |
|--------------|-------------------------------------------------------------------------|
| `plan`       | Generate a spec (no code). Consumed → replaced with `planned`.          |
| `planned`    | Plan has been posted.                                                   |
| `build`      | Intent to implement. Inert without `approved`.                          |
| `approved`   | Authorizes build. Required alongside `build`. Removed after build.      |
| `building`   | Build in progress (set by Kilo Echo).                                   |
| `done`       | PR opened.                                                              |
| `failed`     | Plan or build errored / produced no diff (after retry).                 |
| `revise`     | Re-run build using revision notes (see §7).                             |
| `claude`     | Engine selector: use Claude Code.                                       |
| `aider`      | Engine selector: use Aider + Ollama. (Default if neither present.)      |
| `automerge`  | Opt-in: auto-merge the PR when CI passes (see §6).                      |
| `idea`,`bug` | User categorization only; Kilo Echo ignores them for routing.           |

---

## 4. Issue template (light structure)

A single GitHub issue template, all fields optional but encouraged. Lowers
ambiguity for the engine without adding much phone friction.

```markdown
## Intent
<what you want, in a sentence or two>

## Acceptance criteria
- <observable outcome 1>
- <observable outcome 2>

## Constraints / notes
<tech constraints, files to touch or avoid, links, anything else>
```

If the issue is freeform (fields missing), the engine interprets the body as-is.

---

## 5. Triggering & transport

- **Polling only.** Kilo Echo polls GitHub every `poll_seconds` (default **60**,
  user-configurable). No webhooks, no tunnels, no open ports — the PC makes
  outbound calls exclusively, so there is no inbound attack surface.
- **Instant acknowledgment.** On pickup, Kilo Echo adds a reaction to the issue
  (👀 for plan, 🚀 for build) so the phone shows life within the poll window.
- **Order of work each tick:** `build`+`approved` first, then `plan`, then
  `revise`.

---

## 6. Concurrency & merging

- **Concurrency.** Sequential by default (one issue fully processed at a time —
  safest with a single working tree). A global config flag `parallel = true`
  enables parallel processing using separate git worktrees. v1 ships sequential
  working; parallel is implemented behind the flag.
- **Merging.** Human-by-default: Kilo Echo opens the PR and stops; you merge
  from the phone. Per-issue opt-in: an `automerge` label enables GitHub
  auto-merge on that PR so it merges itself once CI is green. No issue is ever
  auto-merged without the explicit label.

---

## 7. Revise-on-PR loop

After reviewing a PR you can request changes without starting over:

1. Add the `revise` label to the **issue**, and add a comment beginning with
   `REVISE:` containing your notes.
2. Kilo Echo reads the latest `REVISE:` note, checks out the existing branch for
   that issue, and re-runs the engine with the original context **plus** the
   revision notes.
3. It amends the branch (new commit), pushes, updates the PR, and comments a
   fresh summary. `revise` is consumed.

---

## 8. Failure handling

- On build error or **no diff produced**, retry once with the same engine and
  same prompt.
- If the retry also fails, label `failed` and comment what happened.
- _Future:_ self-healing — feed error/test output back into the prompt on retry,
  optionally fall back to the stronger engine. Out of scope for v1; the retry
  hook is structured to allow it.

---

## 9. Cost & consumption visibility (decoupled addon)

**Independent addon.** The core loop ships and runs without it. If disabled or
absent, the orchestrator behaves identically and skips writing cost records.
Nothing in the core code path depends on it.

### 9.1 How cost data is obtained (verified)

Both engines expose exact figures — no estimation needed:

- **Aider:** run with `--analytics-log <runfile>`; reads the `message_send`
  event carrying `prompt_tokens`, `completion_tokens`, `total_tokens`, `cost`,
  `total_cost`. Local Ollama models report ~0 cost (correct).
- **Claude Code:** run with `--output-format json`; parses `total_cost_usd` and
  the `usage` token object from the same JSON used for the result text.

`[pricing.*]` config is only a fallback for engines/models that don't
self-report.

### 9.2 What gets surfaced

- **Per-run:** in the result comment on the issue/PR.
- **Running totals:** per issue and per day, in a `costs.jsonl` ledger and the
  status view.

### 9.3 Interface to the core

The core emits one neutral "run finished" event (engine, model, tokens, cost,
issue, phase, timestamp, duration). The cost addon consumes it. The core does
not import the cost module; the event is a no-op if nothing listens. This is what
makes the addon shippable separately.

---

## 10. Observability

- **Run log (source of truth).** Append-only JSONL on the PC, one record per run:
  timestamp, issue #, phase, engine, outcome, tokens, cost, branch, PR URL,
  duration.
- **GitHub (smart, low-noise).** State is communicated through what the mobile
  app already shows: labels (status), reactions (instant ack), and a single
  updated result comment per phase (keeps issues readable). No extra surface.
- **Local status view.** Localhost-only. v1: a terminal status line in the
  service/tmux session showing queue, current run, recent outcomes, and running
  cost totals (reads the JSONL log/ledger). Never faces the internet. A minimal
  localhost web page is a later option.

---

## 11. Installation

Kilo Echo is a Python CLI. Installation uses **uv** (the 2026 standard for Python
CLI tools), with **pipx** as a fallback. Not npm — npm is for the *Fearless* app,
not for this tool.

### 11.1 Prerequisites (on the always-on machine)

- `gh` (GitHub CLI), authenticated once: `gh auth login`.
- For the **aider** engine: `aider` installed + a running Ollama with your model.
- For the **claude** engine: Claude Code CLI installed. **Pin/verify the
  version** — v2.1.83 has a bug where `-p` print mode returns an empty result
  (tokens still billed); v2.1.78 works. `ke doctor` checks this.

### 11.2 Install uv (once, ever)

Windows (PowerShell):
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```
Linux/macOS:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 11.3 Install Kilo Echo

```bash
uv tool install git+https://github.com/<org>/kiloecho
ke --version
```
uv creates an isolated environment and puts `ke` on PATH. Update later with
`uv tool upgrade kiloecho`. pipx fallback: `pipx install git+https://...`.

### 11.4 Configure & verify

```bash
ke init            # writes a starter kiloecho.toml
$EDITOR kiloecho.toml
ke doctor          # checks gh auth, engines on PATH, Claude Code version, repo reachable
bash scripts/init-labels.sh <org>/<repo>   # create all labels
```

---

## 12. Running

### 12.1 Quickstart (try it now)

```bash
ke run             # runs in the foreground in this terminal
```
Or inside tmux so it survives disconnects:
```bash
tmux new -s ke
ke run
# detach: Ctrl-b then d ; reattach: tmux attach -t ke
```

### 12.2 As a service (recommended, auto-start + restart)

**Linux (systemd user unit):** ship `packaging/kiloecho.service`; enable with
```bash
systemctl --user enable --now kiloecho
```

**Windows (Scheduled Task):** ship `packaging/windows-task.ps1`; run it once to
register "KiloEcho" to start at logon and restart on failure:
```powershell
.\packaging\windows-task.ps1
```

tmux remains the zero-setup path; systemd/Task is the professional default.

---

## 13. Configuration (kiloecho.toml)

```toml
[kiloecho]
repo          = "owner/repo"
workdir       = "~/code/project"     # the git checkout engines operate in
poll_seconds  = 60
base_branch   = "main"
branch_prefix = "ke/"
default_engine = "aider"
parallel      = false                # true → worktree-based parallel builds
dry_run       = false                # log decisions, call no engine, never push

[kiloecho.labels]
plan="plan"; planned="planned"; build="build"; approved="approved"
building="building"; done="done"; failed="failed"; revise="revise"; automerge="automerge"

[engines.aider]
kind  = "aider"
model = "ollama/qwen2.5-coder:14b"

[engines.claude]
kind  = "claude"

# pricing fallback only (per 1M tokens); engines self-report when possible
[pricing.claude]
input = 3.0
output = 15.0
[pricing.aider]
input = 0.0
output = 0.0
```

One Kilo Echo instance watches one repo. Multiple projects = multiple instances
(separate configs/services).

---

## 14. Architecture / modules

```
kiloecho/
  __main__.py      CLI: run | once | init | doctor | status
  config.py        TOML loading, dataclasses, pricing
  github.py        gh + git wrapper: issues, comments, reactions, labels, PRs, worktrees
  engines.py       plan/build/revise prompt builders + Claude & Aider drivers; token capture
  orchestrator.py  tick loop: routing, two-key gate, retry, revise, automerge
  cost.py          (addon) token→cost, per-issue & per-day rollups, costs.jsonl
  log.py           JSONL run log read/write
  status.py        localhost status view (terminal; web later)
  doctor.py        preflight checks (gh auth, engines, Claude Code version, repo)
scripts/
  init-labels.sh   create/repair all labels on a repo
packaging/
  kiloecho.service     systemd user unit (Linux)
  windows-task.ps1     Scheduled Task registration (Windows)
tests/
  test_logic.py    routing, gate, slugging, prompt construction (no engines needed)
docs/
  SPEC.md          this document
README.md  LICENSE  pyproject.toml  kiloecho.example.toml
```

---

## 15. Security model (explicit)

- **No inbound connections.** Polling = outbound only. Nothing listens publicly.
  Status view is localhost-only.
- **No code without two keys.** `build` + `approved`; `approved` cleared after
  each build.
- **Isolated writes.** Engines operate in a dedicated `workdir`; changes go to a
  fresh `ke/<issue>-<slug>` branch; pushes are `--force-with-lease` to that
  branch only; `main` is never written directly.
- **No secrets in repo.** Auth via `gh auth login` (token in gh's store).
  `kiloecho.toml` is gitignored. No API keys in code.
- **dry_run** validates routing/labels with zero side effects.

---

## 16. v1 scope (in) vs later (out)

**In v1:** plan phase; two-key gated build; engine selection; polling + ack;
issue template; sequential + flag-gated parallel; retry-once; cost addon
(per-run + running totals); revise-via-label loop; JSONL log; terminal status
view; automerge opt-in label; `ke doctor`; install via uv/pipx; systemd + Windows
Task + tmux; label init script; logic tests.

**Later:** self-healing retries; localhost web dashboard; webhook transport
option; multi-repo from one instance; CI-result-aware build reports.

---

## 17. Build order (shippable increments)

1. **Core loop** — plan → two-key gated build → branch → PR, polling + ack,
   engine selection, retry-once, revise, sequential. Usable on its own; gets the
   workflow into daily use fastest.
2. **Cost addon** — `cost.py` + `costs.jsonl`, consuming the run-finished event.
   Added without touching the orchestrator.
3. **Status view** — reads the run log / cost ledger; localhost only.
4. **Parallel** (behind flag) and **automerge** polish.
5. **Packaging** — `ke doctor`, service files, label script finalized for release.

---

## 18. Open items

1. Confirm GitHub org `kiloecho` is free (manual eyeball; API was rate-limited).
2. ~~Token capture~~ Resolved (Aider `--analytics-log`, Claude `--output-format
   json`).
3. ~~Claude Code version~~ Noted: avoid v2.1.83 for the `claude` engine; `ke
   doctor` checks it.
