from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    success: bool = True
    error: str = ""


# ── Prompt builders ──────────────────────────────────────────────────────────

def build_plan_prompt(issue_num: int, title: str, body: str) -> str:
    return f"""You are planning work for GitHub issue #{issue_num}: {title}

Issue body:
{body}

Write a PLAN ONLY — no code, no file changes. Include:
1. Approach: how you would solve this
2. Affected files: which files will likely need to change
3. Step-by-step plan: ordered implementation steps
4. Risks: potential issues or gotchas
5. Estimate: rough complexity (small / medium / large)

Be specific and concise. This plan will be reviewed before any code is written."""


def build_build_prompt(issue_num: int, title: str, body: str, plan: str | None = None) -> str:
    plan_section = f"\n\nApproved plan:\n{plan}\n" if plan else ""
    return f"""Implement GitHub issue #{issue_num}: {title}

Issue body:
{body}{plan_section}
Implement the changes described. Follow the approved plan if one is provided."""


def build_revise_prompt(
    issue_num: int, title: str, body: str, revision_notes: str, plan: str | None = None
) -> str:
    plan_section = f"\n\nOriginal approved plan:\n{plan}\n" if plan else ""
    return f"""Revise the implementation for GitHub issue #{issue_num}: {title}

Issue body:
{body}{plan_section}
Revision notes:
{revision_notes}

Apply the requested revisions to the existing branch. Make minimal targeted changes."""


# ── Engine selection ─────────────────────────────────────────────────────────

def select_engine(labels: list[str], default: str, label_names) -> str:
    label_set = set(labels)
    if label_names.claude in label_set:
        return "claude"
    if label_names.aider in label_set:
        return "aider"
    return default


# ── Drivers ──────────────────────────────────────────────────────────────────

class AiderDriver:
    def __init__(self, model: str = ""):
        self.model = model

    def run(self, prompt: str, workdir: str | Path, plan_mode: bool = False) -> RunResult:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            analytics_log = f.name

        try:
            cmd = ["aider", "--analytics-log", analytics_log, "--yes-always", "--no-pretty"]
            if self.model:
                cmd += ["--model", self.model]
            if plan_mode:
                cmd += ["--chat-mode", "ask"]
            cmd += ["--message", prompt]

            r = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir, timeout=600)
            result = RunResult(
                text=r.stdout,
                success=r.returncode == 0,
                error=r.stderr if r.returncode != 0 else "",
            )
            _parse_aider_analytics(analytics_log, result)
            return result
        except subprocess.TimeoutExpired:
            return RunResult(text="", success=False, error="aider timed out after 600s")
        finally:
            Path(analytics_log).unlink(missing_ok=True)


def _parse_aider_analytics(log_path: str, result: RunResult) -> None:
    try:
        with open(log_path) as f:
            for line in f:
                event = json.loads(line.strip())
                if event.get("event") == "message_send":
                    result.prompt_tokens = int(event.get("prompt_tokens", 0))
                    result.completion_tokens = int(event.get("completion_tokens", 0))
                    result.cost_usd = float(event.get("cost", 0.0))
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
        pass


class ClaudeDriver:
    # Plan mode restricts tools to read-only so the engine cannot edit files.
    _READ_ONLY_TOOLS = "Read,Glob,Grep,LS"

    def run(self, prompt: str, workdir: str | Path, plan_mode: bool = False) -> RunResult:
        cmd = ["claude", "--output-format", "json", "-p", prompt]
        if plan_mode:
            cmd += ["--allowedTools", self._READ_ONLY_TOOLS]

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir, timeout=600)
            if r.returncode != 0:
                return RunResult(text="", success=False, error=r.stderr.strip())
            return _parse_claude_output(r.stdout)
        except subprocess.TimeoutExpired:
            return RunResult(text="", success=False, error="claude timed out after 600s")


def _parse_claude_output(stdout: str) -> RunResult:
    try:
        data = json.loads(stdout)
        text = data.get("result", "") or data.get("content", "") or ""
        usage = data.get("usage", {})
        cost = float(data.get("total_cost_usd", 0.0))
        return RunResult(
            text=text,
            prompt_tokens=int(usage.get("input_tokens", 0)),
            completion_tokens=int(usage.get("output_tokens", 0)),
            cost_usd=cost,
            success=True,
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        # Fallback: treat raw stdout as the result text
        return RunResult(text=stdout, success=bool(stdout.strip()))
