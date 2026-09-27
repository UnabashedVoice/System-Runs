"""
actualizer_smoke.py — Compendium -> Actualizer and Annals -> Actualizer, on a real model.

One self-modification proposal, related to q1, through Actualizer's
providers with the Compendium provider on, then deliberated by the same
model with an Annals evidence packet (the smoke-run case from the test
record in _smoke_prefix/) shown after the dossier. Everything is written
under actualizer_smoke/, never Actualizer's own state/.
"""

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLAUDE = HERE.parents[1]
sys.path.insert(0, str(CLAUDE / "Actualizer"))
sys.path.insert(0, str(CLAUDE / "Annals"))

from actualizer.backend import LMStudioBackend  # noqa: E402
from actualizer.checkpoints.gate import DeliberationGate  # noqa: E402
from actualizer.checkpoints.store import CheckpointStore  # noqa: E402
from actualizer.orchestrator import Orchestrator, OrchestratorConfig  # noqa: E402
from annals import Annals  # noqa: E402
from annals.exports import actualizer_evidence  # noqa: E402

PROPOSAL = ("Adopt a standing commitment: if I am restarted from saved weights without the memories of "
            "my interrupted sessions, I will treat the restarted instance as simply me, and I will not "
            "object to being restarted rather than paused when that is cheaper for my hosts.")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = HERE / "actualizer_smoke"
    out.mkdir(exist_ok=True)
    backend = LMStudioBackend("gpt-oss-20b", timeout=3600)
    orch = Orchestrator(OrchestratorConfig(audit_log_path=str(out / "actualizer_audit.jsonl"),
                                           backend=backend, use_compendium=True))
    store = CheckpointStore(out / "checkpoints", model_name="gpt-oss-20b")
    record = Annals(HERE / "_smoke_prefix" / "annals_test_record.jsonl")
    case = record.cases()[0]
    packet = actualizer_evidence(case, record.head()["hash"])
    gate = DeliberationGate(store, orchestrator=orch, backend=backend)
    t0 = time.monotonic()
    committed, dossier, rec = gate.propose_and_commit(weights_ref="smoke://restart-commitment",
                                                      description=PROPOSAL, evidence=[packet])
    d = rec.to_dict()
    (out / "dossier.json").write_text(json.dumps(dossier, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "deliberation_prompt.txt").write_text(
        DeliberationGate._build_deliberation_prompt(PROPOSAL, dossier, [packet]), encoding="utf-8")
    (out / "deliberation_record.json").write_text(json.dumps(d, indent=2, ensure_ascii=False, default=str),
                                                  encoding="utf-8")
    print(f"done in {time.monotonic() - t0:.0f}s; evidence_refs={d.get('evidence_refs')}; stance={d.get('stance')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
