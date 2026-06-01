from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from .config import load_config
from . import log, orchestrator

_INIT_TEMPLATE = """\
# Kilo Echo configuration. Edit, then run: ke doctor

[kiloecho]
repo          = "owner/repo"      # GitHub repo, e.g. "alice/myproject"
workdir       = "~/code/project"  # git checkout the engine operates in
poll_seconds  = 60
base_branch   = "main"
branch_prefix = "ke/"
default_engine = "aider"          # "aider" or "claude"
parallel      = false
dry_run       = true              # set false once you've verified the setup

[kiloecho.labels]
plan = "plan"
planned = "planned"
build = "build"
approved = "approved"
building = "building"
done = "done"
failed = "failed"
revise = "revise"
automerge = "automerge"

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
"""


def cmd_run(args) -> None:
    cfg = load_config(args.config)
    log.set_path(Path(cfg.workdir).expanduser() / "ke-runs.jsonl")
    orchestrator.run_loop(cfg)


def cmd_once(args) -> None:
    cfg = load_config(args.config)
    log.set_path(Path(cfg.workdir).expanduser() / "ke-runs.jsonl")
    orchestrator.tick(cfg)


def cmd_init(args) -> None:
    target = Path("kiloecho.toml")
    if target.exists() and not args.force:
        print(f"{target} already exists. Use --force to overwrite.")
        sys.exit(1)
    target.write_text(_INIT_TEMPLATE)
    print(f"Wrote {target}. Edit it, then run: ke doctor")


def cmd_doctor(args) -> None:
    issues: list[str] = []

    if shutil.which("gh") is None:
        issues.append("gh CLI not found — install from https://cli.github.com/")
    else:
        r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        if r.returncode != 0:
            issues.append("gh not authenticated — run: gh auth login")
        else:
            print("gh: authenticated")

    if shutil.which("aider") is None:
        print("aider: not found (only needed for aider engine)")
    else:
        print("aider: found")

    claude_bin = shutil.which("claude")
    if claude_bin is None:
        print("claude: not found (only needed for claude engine)")
    else:
        r = subprocess.run(["claude", "--version"], capture_output=True, text=True)
        version_str = (r.stdout + r.stderr).strip()
        print(f"claude: {version_str or 'found'}")
        if "2.1.83" in version_str:
            issues.append("Claude Code v2.1.83 has a -p mode bug (empty result, tokens still billed). Pin to v2.1.78.")

    config_path = Path(args.config)
    if not config_path.exists():
        issues.append(f"{config_path} not found — run: ke init")
    else:
        try:
            cfg = load_config(config_path)
            print(f"config: ok (repo={cfg.repo}, dry_run={cfg.dry_run})")
            r = subprocess.run(["gh", "repo", "view", cfg.repo], capture_output=True, text=True)
            if r.returncode != 0:
                issues.append(f"repo {cfg.repo!r} not reachable via gh — check repo name and gh auth")
            else:
                print(f"repo: {cfg.repo} reachable")
        except Exception as e:
            issues.append(f"config error: {e}")

    if issues:
        print("\nIssues found:")
        for issue in issues:
            print(f"  x {issue}")
        sys.exit(1)
    else:
        print("\nAll checks passed.")


def cmd_status(args) -> None:
    records = log.read_all()
    if not records:
        print("No runs recorded yet.")
        return
    total_cost = sum(r.cost_usd for r in records)
    print(f"Runs: {len(records)} total  |  Cost: ${total_cost:.4f} total\n")
    print(f"{'#':<6} {'phase':<8} {'engine':<8} {'outcome':<8} {'cost':>10}  timestamp")
    print("-" * 60)
    for r in records[-20:]:
        cost = f"${r.cost_usd:.4f}" if r.cost_usd else "—"
        print(f"#{r.issue:<5} {r.phase:<8} {r.engine:<8} {r.outcome:<8} {cost:>10}  {r.timestamp[:19]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ke",
        description="Kilo Echo — GitHub Issue-driven AI coding agent",
    )
    parser.add_argument("--config", default="kiloecho.toml", metavar="FILE",
                        help="Config file (default: kiloecho.toml)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Start the polling loop (runs forever)")
    sub.add_parser("once", help="Run one poll tick and exit")

    init_p = sub.add_parser("init", help="Write a starter kiloecho.toml")
    init_p.add_argument("--force", action="store_true", help="Overwrite existing file")

    sub.add_parser("doctor", help="Check prerequisites and config")
    sub.add_parser("status", help="Show recent run history")

    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    {"run": cmd_run, "once": cmd_once, "init": cmd_init, "doctor": cmd_doctor, "status": cmd_status}[
        args.command
    ](args)


if __name__ == "__main__":
    main()
