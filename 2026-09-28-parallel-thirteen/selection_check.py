"""
selection_check.py — The Compendium selection step alone, on a few questions.

    python selection_check.py q10 q13 q01 q05

Runs only the selection call (on gpt-oss-20b at high reasoning effort, the
batch's settings) and prints what was chosen and why. A cheap way to check
the selection prompt before spending hours on full runs. Writes nothing.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLAUDE = HERE.parents[1]
sys.path.insert(0, str(CLAUDE / "Arbitrator"))
sys.path.insert(0, str(HERE))

from Arbitrator.SeedCore.channels.backend import LMStudioBackend  # noqa: E402
from Arbitrator.SeedCore.orchestrator.compendium_link import consult  # noqa: E402
from questions import QUESTIONS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
backend = LMStudioBackend("gpt-oss-20b", timeout=3600, reasoning_effort="high")
for qid in sys.argv[1:]:
    record, _ = consult(QUESTIONS[qid][1], backend, max_entries=5, budget_chars=14000, max_sections=2)
    print(f"{qid}: {record.get('identity')}")
    import json
    out = Path(sys.argv[0]).resolve().parent / "selection_check_raw"
    out.mkdir(exist_ok=True)
    (out / f"{qid}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    for s in record.get("selected", []):
        print(f"    {s['id']}: {s['why']}")
    sys.stdout.flush()
