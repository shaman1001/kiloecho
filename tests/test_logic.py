"""Logic tests for increment 1 — no gh/aider/claude installation required."""

from textwrap import dedent

import pytest

from kiloecho.config import LabelsConfig, load_config
from kiloecho.engines import (
    build_build_prompt,
    build_plan_prompt,
    build_revise_prompt,
    select_engine,
)
from kiloecho.orchestrator import branch_name, route, slug
from kiloecho import log


LABELS = LabelsConfig()

_MINIMAL_TOML = dedent("""\
    [kiloecho]
    repo = "owner/repo"
    workdir = "/tmp"
""")

_FULL_TOML = dedent("""\
    [kiloecho]
    repo = "owner/repo"
    workdir = "~/code/project"
    poll_seconds = 30
    base_branch = "develop"
    default_engine = "claude"
    dry_run = true

    [engines.aider]
    kind = "aider"
    model = "ollama/qwen2.5-coder:14b"

    [engines.claude]
    kind = "claude"

    [pricing.claude]
    input = 3.0
    output = 15.0
""")


# ── slug / branch name ────────────────────────────────────────────────────────

def test_slug_basic():
    assert slug("Add user authentication") == "add-user-authentication"


def test_slug_special_chars():
    assert slug("Fix: bug in parser (v2)!") == "fix-bug-in-parser-v2"


def test_slug_long_title():
    assert len(slug("a" * 100)) <= 40


def test_slug_no_trailing_dash():
    result = slug("hello world!!!")
    assert not result.endswith("-")


def test_slug_numbers_preserved():
    assert "2" in slug("Fix issue #2 now")


def test_branch_name():
    assert branch_name("ke/", 42, "Fix the bug") == "ke/42-fix-the-bug"


def test_branch_name_complex_title():
    b = branch_name("ke/", 7, "Add OAuth2 login (Google)")
    assert b.startswith("ke/7-")
    assert "google" in b


# ── route / two-key gate ──────────────────────────────────────────────────────

def test_route_plan():
    assert route({"plan"}, LABELS) == "plan"


def test_route_build_requires_approved():
    assert route({"build"}, LABELS) is None


def test_route_approved_alone_is_nothing():
    assert route({"approved"}, LABELS) is None


def test_route_build_with_approved():
    assert route({"build", "approved"}, LABELS) == "build"


def test_route_build_priority_over_plan():
    assert route({"build", "approved", "plan"}, LABELS) == "build"


def test_route_build_with_extra_labels():
    assert route({"build", "approved", "claude", "idea"}, LABELS) == "build"


def test_route_revise():
    assert route({"revise"}, LABELS) == "revise"


def test_route_none_on_terminal_labels():
    assert route({"done", "claude"}, LABELS) is None
    assert route({"failed"}, LABELS) is None
    assert route({"planned"}, LABELS) is None


def test_route_build_plan_revise_together():
    # build+approved always wins
    assert route({"build", "approved", "revise", "plan"}, LABELS) == "build"


# ── config loading ────────────────────────────────────────────────────────────

def test_config_minimal_defaults(tmp_path):
    p = tmp_path / "ke.toml"
    p.write_text(_MINIMAL_TOML)
    cfg = load_config(p)
    assert cfg.repo == "owner/repo"
    assert cfg.workdir == "/tmp"
    assert cfg.poll_seconds == 60
    assert cfg.base_branch == "main"
    assert cfg.branch_prefix == "ke/"
    assert cfg.default_engine == "aider"
    assert cfg.parallel is False
    assert cfg.dry_run is False


def test_config_full(tmp_path):
    p = tmp_path / "ke.toml"
    p.write_text(_FULL_TOML)
    cfg = load_config(p)
    assert cfg.poll_seconds == 30
    assert cfg.base_branch == "develop"
    assert cfg.default_engine == "claude"
    assert cfg.dry_run is True
    assert "aider" in cfg.engines
    assert cfg.engines["aider"].model == "ollama/qwen2.5-coder:14b"
    assert cfg.pricing["claude"].input == 3.0
    assert cfg.pricing["claude"].output == 15.0


def test_config_label_defaults(tmp_path):
    p = tmp_path / "ke.toml"
    p.write_text(_MINIMAL_TOML)
    cfg = load_config(p)
    assert cfg.labels.plan == "plan"
    assert cfg.labels.approved == "approved"
    assert cfg.labels.building == "building"
    assert cfg.labels.done == "done"
    assert cfg.labels.claude == "claude"
    assert cfg.labels.aider == "aider"


def test_config_custom_labels(tmp_path):
    p = tmp_path / "ke.toml"
    p.write_text(dedent("""\
        [kiloecho]
        repo = "x/y"
        workdir = "/tmp"

        [kiloecho.labels]
        plan = "ke-plan"
        approved = "ke-approved"
    """))
    cfg = load_config(p)
    assert cfg.labels.plan == "ke-plan"
    assert cfg.labels.approved == "ke-approved"
    assert cfg.labels.build == "build"  # default unchanged


def test_config_missing_repo_raises(tmp_path):
    p = tmp_path / "ke.toml"
    p.write_text("[kiloecho]\nworkdir = '/tmp'\n")
    with pytest.raises(ValueError, match="repo"):
        load_config(p)


# ── engine selection ──────────────────────────────────────────────────────────

def test_select_engine_claude_label():
    assert select_engine(["claude", "build", "approved"], "aider", LABELS) == "claude"


def test_select_engine_aider_label():
    assert select_engine(["aider", "build", "approved"], "claude", LABELS) == "aider"


def test_select_engine_default_aider():
    assert select_engine(["build", "approved"], "aider", LABELS) == "aider"


def test_select_engine_default_claude():
    assert select_engine(["build", "approved"], "claude", LABELS) == "claude"


def test_select_engine_claude_wins_over_aider():
    # both labels present: claude wins (checked first)
    assert select_engine(["claude", "aider"], "aider", LABELS) == "claude"


# ── prompt construction ───────────────────────────────────────────────────────

def test_plan_prompt_references_issue():
    p = build_plan_prompt(42, "Add login", "Users need to log in")
    assert "#42" in p
    assert "Add login" in p


def test_plan_prompt_says_no_code():
    p = build_plan_prompt(1, "t", "b")
    assert "PLAN" in p.upper()
    assert "no code" in p.lower() or "no file" in p.lower()


def test_build_prompt_references_issue():
    p = build_build_prompt(42, "Add login", "Users need to log in")
    assert "#42" in p
    assert "Add login" in p


def test_build_prompt_includes_plan_when_given():
    p = build_build_prompt(42, "Add login", "body", plan="Step 1: do X")
    assert "Step 1: do X" in p


def test_build_prompt_no_plan_section_when_absent():
    p = build_build_prompt(42, "Add login", "body", plan=None)
    assert "Approved plan" not in p


def test_revise_prompt_contains_notes():
    p = build_revise_prompt(42, "Add login", "body", "Make it prettier")
    assert "Make it prettier" in p
    assert "#42" in p


def test_revise_prompt_includes_plan():
    p = build_revise_prompt(42, "t", "b", "notes", plan="Original plan here")
    assert "Original plan here" in p


# ── log ───────────────────────────────────────────────────────────────────────

def test_log_append_and_read(tmp_path):
    log.set_path(tmp_path / "runs.jsonl")
    r = log.RunRecord(issue=1, phase="plan", engine="aider", outcome="success", cost_usd=0.01)
    log.append(r)
    records = log.read_all()
    assert len(records) == 1
    assert records[0].issue == 1
    assert records[0].cost_usd == pytest.approx(0.01)
    assert records[0].phase == "plan"


def test_log_multiple_records(tmp_path):
    log.set_path(tmp_path / "runs.jsonl")
    for i in range(3):
        log.append(log.RunRecord(issue=i, phase="build", engine="claude", outcome="success"))
    assert len(log.read_all()) == 3


def test_log_empty_file(tmp_path):
    log.set_path(tmp_path / "nonexistent.jsonl")
    assert log.read_all() == []


def test_log_has_timestamp(tmp_path):
    log.set_path(tmp_path / "runs.jsonl")
    log.append(log.RunRecord(issue=1, phase="plan", engine="aider", outcome="success"))
    records = log.read_all()
    assert records[0].timestamp  # non-empty ISO timestamp
