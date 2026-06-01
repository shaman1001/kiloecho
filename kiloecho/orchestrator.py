from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import KiloEchoConfig
from . import engines, github, log

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def slug(text: str, max_len: int = 40) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_len].rstrip("-")


def branch_name(prefix: str, issue_num: int, title: str) -> str:
    return f"{prefix}{issue_num}-{slug(title)}"


def issue_labels(issue: dict) -> set[str]:
    return {lbl["name"] for lbl in issue.get("labels", [])}


def route(labels: set[str], label_cfg) -> str | None:
    """Return 'build', 'plan', 'revise', or None. Build requires both build+approved."""
    if label_cfg.build in labels and label_cfg.approved in labels:
        return "build"
    if label_cfg.plan in labels:
        return "plan"
    if label_cfg.revise in labels:
        return "revise"
    return None


def _sort_key(issue: dict, label_cfg) -> int:
    lbls = issue_labels(issue)
    action = route(lbls, label_cfg)
    return {"build": 0, "plan": 1, "revise": 2}.get(action or "", 99)


def _get_plan_comment(issue: dict) -> str | None:
    for comment in issue.get("comments", []):
        body = comment.get("body", "")
        if body.startswith("## Plan for #"):
            return body
    return None


def _get_revision_notes(issue: dict) -> str:
    for comment in reversed(issue.get("comments", [])):
        body = comment.get("body", "")
        if body.startswith("REVISE:"):
            return body[len("REVISE:"):].strip()
    return ""


def _get_driver(cfg: KiloEchoConfig, engine_name: str):
    if engine_name == "claude":
        return engines.ClaudeDriver()
    eng_cfg = cfg.engines.get(engine_name)
    model = eng_cfg.model if eng_cfg else ""
    return engines.AiderDriver(model=model)


def _cost_suffix(result: engines.RunResult) -> str:
    if result.cost_usd > 0:
        total_tokens = result.prompt_tokens + result.completion_tokens
        return f"\n\n---\n_Cost: ${result.cost_usd:.4f} | Tokens: {total_tokens:,}_"
    return ""


# ── Tick ─────────────────────────────────────────────────────────────────────

def tick(cfg: KiloEchoConfig) -> None:
    label_cfg = cfg.labels
    seen: dict[int, dict] = {}

    for label in (label_cfg.build, label_cfg.plan, label_cfg.revise):
        for issue in github.list_issues(cfg.repo, label):
            n = issue["number"]
            if n not in seen:
                seen[n] = issue

    if not seen:
        logger.debug("No actionable issues")
        return

    ordered = sorted(seen.values(), key=lambda i: _sort_key(i, label_cfg))

    for issue in ordered:
        action = route(issue_labels(issue), label_cfg)
        if action is None:
            continue
        _process(cfg, issue, action)


# ── Process ───────────────────────────────────────────────────────────────────

def _process(cfg: KiloEchoConfig, issue: dict, action: str) -> None:
    num = issue["number"]
    title = issue["title"]
    label_cfg = cfg.labels

    logger.info("issue #%d: %s — %s", num, action, title)

    if cfg.dry_run:
        logger.info("[dry_run] would %s issue #%d: %s", action, num, title)
        return

    reaction = "eyes" if action == "plan" else "rocket"
    try:
        github.add_reaction(cfg.repo, num, reaction)
    except Exception as e:
        logger.warning("reaction failed for #%d: %s", num, e)

    issue_detail = github.get_issue(cfg.repo, num)
    lbls = issue_labels(issue_detail)
    engine_name = engines.select_engine(list(lbls), cfg.default_engine, label_cfg)
    driver = _get_driver(cfg, engine_name)
    workdir = Path(cfg.workdir).expanduser()
    started = datetime.now(timezone.utc)

    if action == "plan":
        _do_plan(cfg, issue_detail, engine_name, driver, workdir, started)
    elif action == "build":
        _do_build(cfg, issue_detail, engine_name, driver, workdir, started)
    elif action == "revise":
        _do_revise(cfg, issue_detail, engine_name, driver, workdir, started)


def _do_plan(cfg, issue, engine_name, driver, workdir, started):
    num, title, body = issue["number"], issue["title"], issue.get("body") or ""
    lc = cfg.labels

    github.add_label(cfg.repo, num, lc.building)
    prompt = engines.build_plan_prompt(num, title, body)

    result = driver.run(prompt, workdir, plan_mode=True)
    if not result.success or not result.text.strip():
        result = driver.run(prompt, workdir, plan_mode=True)

    duration = (datetime.now(timezone.utc) - started).total_seconds()

    if result.success and result.text.strip():
        body_out = f"## Plan for #{num}: {title}\n\n{result.text}{_cost_suffix(result)}"
        github.add_comment(cfg.repo, num, body_out)
        github.remove_label(cfg.repo, num, lc.plan)
        github.add_label(cfg.repo, num, lc.planned)
        github.remove_label(cfg.repo, num, lc.building)
        outcome = "success"
    else:
        err = result.error or "Engine produced no output"
        github.add_comment(cfg.repo, num, f"## Plan failed\n\n{err}")
        github.remove_label(cfg.repo, num, lc.plan)
        github.remove_label(cfg.repo, num, lc.building)
        github.add_label(cfg.repo, num, lc.failed)
        outcome = "failed"

    log.append(log.RunRecord(
        issue=num, phase="plan", engine=engine_name, outcome=outcome,
        prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd, duration=duration,
    ))


def _do_build(cfg, issue, engine_name, driver, workdir, started):
    num, title, body = issue["number"], issue["title"], issue.get("body") or ""
    lc = cfg.labels
    plan = _get_plan_comment(issue)
    branch = branch_name(cfg.branch_prefix, num, title)

    github.add_label(cfg.repo, num, lc.building)

    try:
        github.create_branch(workdir, branch, cfg.base_branch)
    except Exception as e:
        logger.error("branch creation failed for #%d: %s", num, e)
        github.remove_label(cfg.repo, num, lc.building)
        github.add_label(cfg.repo, num, lc.failed)
        github.add_comment(cfg.repo, num, f"## Build failed\n\nCould not create branch: {e}")
        log.append(log.RunRecord(issue=num, phase="build", engine=engine_name, outcome="failed",
                                 duration=(datetime.now(timezone.utc) - started).total_seconds()))
        return

    prompt = engines.build_build_prompt(num, title, body, plan)
    result = driver.run(prompt, workdir, plan_mode=False)
    has_diff = False
    if result.success:
        has_diff = github.commit_and_push(workdir, branch, cfg.base_branch,
                                          f"ke: implement #{num} {title}")

    if not result.success or not has_diff:
        result = driver.run(prompt, workdir, plan_mode=False)
        if result.success:
            has_diff = github.commit_and_push(workdir, branch, cfg.base_branch,
                                              f"ke: implement #{num} {title}")

    duration = (datetime.now(timezone.utc) - started).total_seconds()

    if result.success and has_diff:
        pr_body = f"Implements #{num}: {title}\n\n{result.text}{_cost_suffix(result)}"
        pr_url = github.create_pr(cfg.repo, branch, cfg.base_branch, f"ke: {title}", pr_body)
        github.remove_label(cfg.repo, num, lc.build)
        github.remove_label(cfg.repo, num, lc.approved)
        github.remove_label(cfg.repo, num, lc.building)
        github.add_label(cfg.repo, num, lc.done)
        github.add_comment(cfg.repo, num, f"## Build complete\n\nPR: {pr_url}\n\n{result.text}")
        outcome = "success"
        log.append(log.RunRecord(issue=num, phase="build", engine=engine_name, outcome=outcome,
                                 prompt_tokens=result.prompt_tokens,
                                 completion_tokens=result.completion_tokens,
                                 cost_usd=result.cost_usd, branch=branch, pr_url=pr_url,
                                 duration=duration))
    else:
        err = result.error or ("No changes were produced" if not has_diff else "Build failed")
        github.add_comment(cfg.repo, num, f"## Build failed\n\n{err}")
        github.remove_label(cfg.repo, num, lc.building)
        github.add_label(cfg.repo, num, lc.failed)
        log.append(log.RunRecord(issue=num, phase="build", engine=engine_name, outcome="failed",
                                 prompt_tokens=result.prompt_tokens,
                                 completion_tokens=result.completion_tokens,
                                 cost_usd=result.cost_usd, branch=branch, duration=duration))


def _do_revise(cfg, issue, engine_name, driver, workdir, started):
    num, title, body = issue["number"], issue["title"], issue.get("body") or ""
    lc = cfg.labels
    revision_notes = _get_revision_notes(issue)
    plan = _get_plan_comment(issue)

    existing_branch = github.get_branch_for_issue(workdir, num, cfg.branch_prefix)
    if not existing_branch:
        github.add_comment(cfg.repo, num,
                           f"## Revise failed\n\nNo existing branch found for issue #{num}")
        github.remove_label(cfg.repo, num, lc.revise)
        github.add_label(cfg.repo, num, lc.failed)
        log.append(log.RunRecord(issue=num, phase="revise", engine=engine_name, outcome="failed",
                                 duration=(datetime.now(timezone.utc) - started).total_seconds()))
        return

    github.add_label(cfg.repo, num, lc.building)

    try:
        github.checkout_branch(workdir, existing_branch)
    except Exception as e:
        github.remove_label(cfg.repo, num, lc.building)
        github.remove_label(cfg.repo, num, lc.revise)
        github.add_label(cfg.repo, num, lc.failed)
        github.add_comment(cfg.repo, num, f"## Revise failed\n\nCould not checkout branch: {e}")
        log.append(log.RunRecord(issue=num, phase="revise", engine=engine_name, outcome="failed",
                                 duration=(datetime.now(timezone.utc) - started).total_seconds()))
        return

    prompt = engines.build_revise_prompt(num, title, body, revision_notes, plan)
    result = driver.run(prompt, workdir, plan_mode=False)
    has_diff = False
    if result.success:
        has_diff = github.commit_and_push(workdir, existing_branch, cfg.base_branch,
                                          f"ke: revise #{num}")

    if not result.success or not has_diff:
        result = driver.run(prompt, workdir, plan_mode=False)
        if result.success:
            has_diff = github.commit_and_push(workdir, existing_branch, cfg.base_branch,
                                              f"ke: revise #{num}")

    duration = (datetime.now(timezone.utc) - started).total_seconds()

    if result.success:
        comment_body = f"## Revision applied\n\n{result.text}{_cost_suffix(result)}"
        github.add_comment(cfg.repo, num, comment_body)
        github.remove_label(cfg.repo, num, lc.revise)
        github.remove_label(cfg.repo, num, lc.building)
        outcome = "success"
    else:
        err = result.error or "Engine produced no output"
        github.add_comment(cfg.repo, num, f"## Revise failed\n\n{err}")
        github.remove_label(cfg.repo, num, lc.revise)
        github.remove_label(cfg.repo, num, lc.building)
        github.add_label(cfg.repo, num, lc.failed)
        outcome = "failed"

    log.append(log.RunRecord(issue=num, phase="revise", engine=engine_name, outcome=outcome,
                             prompt_tokens=result.prompt_tokens,
                             completion_tokens=result.completion_tokens,
                             cost_usd=result.cost_usd, branch=existing_branch, duration=duration))


# ── Main loop ────────────────────────────────────────────────────────────────

def run_loop(cfg: KiloEchoConfig) -> None:
    logger.info("ke starting: repo=%s poll=%ds dry_run=%s", cfg.repo, cfg.poll_seconds, cfg.dry_run)
    while True:
        try:
            tick(cfg)
        except Exception as e:
            logger.error("tick error: %s", e, exc_info=True)
        time.sleep(cfg.poll_seconds)
