from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _run(cmd: list[str], cwd: str | Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nstderr: {result.stderr.strip()}")
    return result


# ── Issues ──────────────────────────────────────────────────────────────────

def list_issues(repo: str, label: str) -> list[dict]:
    result = _run([
        "gh", "issue", "list",
        "--repo", repo,
        "--label", label,
        "--state", "open",
        "--json", "number,title,body,labels,url",
        "--limit", "100",
    ])
    return json.loads(result.stdout) if result.stdout.strip() else []


def get_issue(repo: str, number: int) -> dict:
    result = _run([
        "gh", "issue", "view", str(number),
        "--repo", repo,
        "--json", "number,title,body,labels,url,comments",
    ])
    return json.loads(result.stdout)


# ── Labels ───────────────────────────────────────────────────────────────────

def add_label(repo: str, issue_num: int, label: str) -> None:
    _run(["gh", "issue", "edit", str(issue_num), "--repo", repo, "--add-label", label])


def remove_label(repo: str, issue_num: int, label: str) -> None:
    # check=False: silently ok if label is already absent
    _run(["gh", "issue", "edit", str(issue_num), "--repo", repo, "--remove-label", label], check=False)


# ── Comments & reactions ─────────────────────────────────────────────────────

def add_comment(repo: str, issue_num: int, body: str) -> None:
    _run(["gh", "issue", "comment", str(issue_num), "--repo", repo, "--body", body])


def add_reaction(repo: str, issue_num: int, reaction: str) -> None:
    # reaction: "eyes" (👀) or "rocket" (🚀)
    _run([
        "gh", "api",
        f"repos/{repo}/issues/{issue_num}/reactions",
        "--method", "POST",
        "-f", f"content={reaction}",
    ])


# ── Git / branches ───────────────────────────────────────────────────────────

def create_branch(workdir: str | Path, branch_name: str, base_branch: str) -> None:
    _run(["git", "fetch", "origin"], cwd=workdir)
    _run(["git", "checkout", base_branch], cwd=workdir)
    _run(["git", "merge", "--ff-only", f"origin/{base_branch}"], cwd=workdir)
    _run(["git", "checkout", "-b", branch_name], cwd=workdir)


def checkout_branch(workdir: str | Path, branch_name: str) -> None:
    _run(["git", "fetch", "origin"], cwd=workdir)
    # Try local branch; fall back to creating from remote tracking branch
    r = _run(["git", "checkout", branch_name], cwd=workdir, check=False)
    if r.returncode != 0:
        _run(["git", "checkout", "-b", branch_name, f"origin/{branch_name}"], cwd=workdir)


def commit_and_push(workdir: str | Path, branch_name: str, base_branch: str, message: str) -> bool:
    """Commit any uncommitted changes, push, and return True if the branch has commits ahead of base."""
    status = _run(["git", "status", "--porcelain"], cwd=workdir)
    if status.stdout.strip():
        _run(["git", "add", "-A"], cwd=workdir)
        _run(["git", "commit", "-m", message], cwd=workdir)

    ahead = _run(["git", "log", f"{base_branch}..HEAD", "--oneline"], cwd=workdir, check=False)
    has_diff = bool(ahead.stdout.strip())
    if has_diff:
        _run(["git", "push", "--force-with-lease", "origin", branch_name], cwd=workdir)
    return has_diff


def get_branch_for_issue(workdir: str | Path, issue_num: int, prefix: str) -> str | None:
    """Return the local branch name for an issue if one exists, else None."""
    _run(["git", "fetch", "origin", "--prune"], cwd=workdir, check=False)
    result = _run(["git", "branch", "--list", f"{prefix}{issue_num}-*", f"{prefix}{issue_num}"], cwd=workdir)
    for line in result.stdout.splitlines():
        branch = line.strip().lstrip("* ")
        if branch:
            return branch
    # Also check remote tracking branches
    result = _run(["git", "branch", "-r", "--list", f"origin/{prefix}{issue_num}-*"], cwd=workdir)
    for line in result.stdout.splitlines():
        branch = line.strip().removeprefix("origin/")
        if branch:
            return branch
    return None


# ── Pull requests ────────────────────────────────────────────────────────────

def create_pr(repo: str, branch: str, base: str, title: str, body: str) -> str:
    """Create a PR and return its URL."""
    result = _run([
        "gh", "pr", "create",
        "--repo", repo,
        "--head", branch,
        "--base", base,
        "--title", title,
        "--body", body,
    ])
    return result.stdout.strip()
