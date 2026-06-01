from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RunRecord:
    issue: int
    phase: str          # plan | build | revise
    engine: str
    outcome: str        # success | failed
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    branch: str = ""
    pr_url: str = ""
    duration: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_log_path: Path = Path("ke-runs.jsonl")


def set_path(path: Path | str) -> None:
    global _log_path
    _log_path = Path(path)


def append(record: RunRecord) -> None:
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(_log_path, "a") as f:
        f.write(json.dumps(asdict(record)) + "\n")


def read_all() -> list[RunRecord]:
    if not _log_path.exists():
        return []
    records = []
    with open(_log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(RunRecord(**json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                pass
    return records
