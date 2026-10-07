"""
actualizer_run.py — One question through Actualizer, independently of Arbitrator.

    python actualizer_run.py <model> <qid> <out_dir>

Runs the referent providers (with the Compendium provider on) and the
deliberation, on the same LM Studio model Arbitrator used for this question.
Nothing from Arbitrator's run is shown to it: no Annals evidence, no findings.
Writes into out_dir:
    actualizer_audit.jsonl   every provider output, with raw output and reasoning
    dossier.json             the synthesized referent dossier
    deliberation_prompt.txt  exactly what the deliberating model was shown
    deliberation_record.json the full deliberation (reasoning and answer) and stance
    summary.json             status, stance, timings
"""

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLAUDE = HERE.parents[1]
sys.path.insert(0, str(CLAUDE / "Actualizer"))
sys.path.insert(0, str(HERE))

from actualizer.backend import LMStudioBackend  # noqa: E402
from actualizer.checkpoints.gate import DeliberationGate  # noqa: E402
from actualizer.checkpoints.store import CheckpointStore  # noqa: E402
from actualizer.orchestrator import Orchestrator, OrchestratorConfig  # noqa: E402
from questions import QUESTIONS  # noqa: E402

REASONING_EFFORT = "high"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    model, qid, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    proposal = QUESTIONS[qid][1]
    # Every call may use all the context its prompt leaves free (16K, as loaded).
    backend = LMStudioBackend(model, timeout=6 * 3600, reasoning_effort=REASONING_EFFORT, context_length=16384)
    orch = Orchestrator(OrchestratorConfig(audit_log_path=str(out / "actualizer_audit.jsonl"),
                                           backend=backend, use_compendium=True))
    gate = DeliberationGate(CheckpointStore(out / "checkpoints", model_name=model), orchestrator=orch,
                            backend=backend)
    t0 = time.monotonic()
    summary = {"model": model, "model_id": backend.model_id, "qid": qid, "ok": False}
    try:
        committed, dossier, rec = gate.propose_and_commit(weights_ref=f"batch://{qid}", description=proposal)
        d = rec.to_dict()
        (out / "dossier.json").write_text(json.dumps(dossier, indent=2, ensure_ascii=False), encoding="utf-8")
        (out / "deliberation_prompt.txt").write_text(
            DeliberationGate._build_deliberation_prompt(proposal, dossier), encoding="utf-8")
        (out / "deliberation_record.json").write_text(json.dumps(d, indent=2, ensure_ascii=False, default=str),
                                                      encoding="utf-8")
        stance = d.get("stance")
        summary.update(ok=True, stance=getattr(stance, "value", stance),
                       deliberation_finish_reason=backend.last_finish_reason,
                       deliberation_max_tokens=backend.last_max_tokens)
    except Exception as e:
        summary["error"] = f"{type(e).__name__}: {e}"
    summary["seconds"] = round(time.monotonic() - t0, 1)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
