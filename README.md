# Kilo Echo

**Drive a local AI coding agent from your phone, through GitHub Issues.**

File a bug, backlog item, or product idea from the GitHub mobile app. Your
always-on machine picks it up, writes a plan, and — once you approve — implements
it on a branch and opens a PR. Engines run locally (Aider + Ollama) or via Claude
Code, chosen per issue with a label.

No cloud service. No exposed ports. No SaaS. Your code and your models stay on
your hardware; the only required network calls are to the GitHub API.

---

## Why

Existing "AI fixes your issues" tools are cloud products tied to hosted models.
If you run local models for cost or privacy — or you just want your own machine
doing the work while you're away from the desk — there hasn't been a clean,
hackable, self-hosted option. Kilo Echo is that: small, label-driven, and
engine-agnostic.

What makes it different: **plan → approve → build.** Most tools jump straight to
a PR. Kilo Echo plans first, waits for your explicit approval, then builds. You
stay in control, and code is never pushed on a single accidental tap.

---

## How it works

```
phone (GitHub app)              your always-on machine
─────────────────               ───────────────────────────────
 new Issue + label   ──poll──►   ke watcher
   plan   ────────────────────►  writes a spec → comments it → label: planned
   build + approved ──────────►  branch, implement, push, open PR → label: done
 review PR on phone ◄─────────   PR + result report
```

Two phases, selected by label:

- **`plan`** — engine writes a spec (no code), posted as an issue comment.
- **`build`** — engine implements on a fresh branch and opens a PR. Requires a
  second `approved` label (the two-key gate) so nothing is built without your
  go-ahead.

Engine is chosen by label too (`claude` or `aider`); omit to use the default.

---

## Quick start

Kilo Echo is a Python CLI installed with [uv](https://docs.astral.sh/uv/).

```bash
# 1. install uv (once)
curl -LsSf https://astral.sh/uv/install.sh | sh          # Windows: irm https://astral.sh/uv/install.ps1 | iex

# 2. install Kilo Echo
uv tool install git+https://github.com/<org>/kiloecho

# 3. configure and verify
ke init                 # writes kiloecho.toml
ke doctor               # checks gh auth, engines, repo
bash scripts/init-labels.sh <org>/<repo>

# 4. run (foreground, or as a service — see docs)
ke run
```

**Prerequisites:** `gh` authenticated (`gh auth login`); for local builds, Aider
+ a running Ollama; for Claude builds, the Claude Code CLI. `ke doctor` tells you
what's missing.

---

## Using it from your phone

1. GitHub mobile app → New Issue. Describe the work (a light template helps).
2. Add labels:
   - `plan` → get a spec back
   - `build` + `approved` → implement and open a PR
   - `claude` / `aider` → pick the engine (optional)
3. Watch the issue — Kilo Echo reacts on pickup and comments progress.
4. Review the PR in the app; merge it, or add `revise` with notes to iterate.

---

## Running as a service

For an always-on setup, register Kilo Echo with your OS so it starts on boot and
restarts on crash:

- **Linux:** `systemctl --user enable --now kiloecho` (unit in `packaging/`)
- **Windows:** run `packaging/windows-task.ps1` to register a Scheduled Task

tmux is fine for trying it out; the service is the recommended default.

---

## Safety

- **Nothing inbound.** Kilo Echo only polls (outbound calls). Nothing listens on
  a public interface.
- **Two-key builds.** Code is written only when an issue has both `build` and
  `approved`; approval is cleared after each build.
- **Isolated changes.** Builds happen on a throwaway `ke/<issue>` branch behind a
  PR. `main` is never touched directly.
- **`dry_run`** validates your setup with zero side effects.

---

## Status

Early but functional end to end. See [docs/SPEC.md](docs/SPEC.md) for the full
design. Issues and PRs welcome.

## License

MIT.
