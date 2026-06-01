# Increment 2 — decoupled cost addon.
# Will consume the "run finished" event emitted by the orchestrator,
# write costs.jsonl, and maintain per-issue/per-day totals.
# The core loop runs identically when this module is absent or disabled.
