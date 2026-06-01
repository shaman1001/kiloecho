from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class LabelsConfig:
    plan: str = "plan"
    planned: str = "planned"
    build: str = "build"
    approved: str = "approved"
    building: str = "building"
    done: str = "done"
    failed: str = "failed"
    revise: str = "revise"
    automerge: str = "automerge"
    claude: str = "claude"
    aider: str = "aider"


@dataclass
class EngineConfig:
    kind: str
    model: str = ""


@dataclass
class PricingConfig:
    input: float = 0.0
    output: float = 0.0


@dataclass
class KiloEchoConfig:
    repo: str
    workdir: str
    poll_seconds: int = 60
    base_branch: str = "main"
    branch_prefix: str = "ke/"
    default_engine: str = "aider"
    parallel: bool = False
    dry_run: bool = False
    labels: LabelsConfig = field(default_factory=LabelsConfig)
    engines: dict[str, EngineConfig] = field(default_factory=dict)
    pricing: dict[str, PricingConfig] = field(default_factory=dict)


def load_config(path: Path | str = "kiloecho.toml") -> KiloEchoConfig:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    ke = raw.get("kiloecho", {})

    labels_raw = ke.get("labels", {})
    valid_label_fields = {f.name for f in fields(LabelsConfig)}
    labels = LabelsConfig(**{k: v for k, v in labels_raw.items() if k in valid_label_fields})

    engines: dict[str, EngineConfig] = {}
    for name, eng in raw.get("engines", {}).items():
        engines[name] = EngineConfig(kind=eng.get("kind", name), model=eng.get("model", ""))

    pricing: dict[str, PricingConfig] = {}
    for name, p in raw.get("pricing", {}).items():
        pricing[name] = PricingConfig(input=float(p.get("input", 0.0)), output=float(p.get("output", 0.0)))

    repo = ke.get("repo", "")
    workdir = ke.get("workdir", ".")
    if not repo:
        raise ValueError("kiloecho.toml: [kiloecho] repo is required")
    if not workdir:
        raise ValueError("kiloecho.toml: [kiloecho] workdir is required")

    return KiloEchoConfig(
        repo=repo,
        workdir=workdir,
        poll_seconds=int(ke.get("poll_seconds", 60)),
        base_branch=ke.get("base_branch", "main"),
        branch_prefix=ke.get("branch_prefix", "ke/"),
        default_engine=ke.get("default_engine", "aider"),
        parallel=bool(ke.get("parallel", False)),
        dry_run=bool(ke.get("dry_run", False)),
        labels=labels,
        engines=engines,
        pricing=pricing,
    )
