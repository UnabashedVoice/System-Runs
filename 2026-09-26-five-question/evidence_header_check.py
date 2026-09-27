"""
evidence_header_check.py — Does saying "nothing observed yet" change how the mind reads Annals evidence?

The Actualizer smoke run's deliberation treated a locked Arbitrator
prediction as if it had happened. Annals' evidence packet now says, first,
when a case has no observed outcome. This re-asks only the deliberation
step (same dossier, same system prompt, max_tokens and temperature as
DeliberationGate) with the old packet and the new one, alternating, and
records whether each answer presents a prediction as observed.
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
from actualizer.checkpoints.gate import DeliberationGate, _DELIBERATION_SYSTEM_PROMPT, _parse_stance  # noqa: E402
from annals import Annals  # noqa: E402
from annals.exports import actualizer_evidence  # noqa: E402

sys.path.insert(0, str(HERE))
from actualizer_smoke import PROPOSAL  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = HERE / "actualizer_smoke" / "evidence_header_check.jsonl"
    dossier = json.loads((HERE / "actualizer_smoke" / "dossier.json").read_text(encoding="utf-8"))
    record = Annals(HERE / "_smoke_prefix" / "annals_test_record.jsonl")
    case = record.cases()[0]
    new = actualizer_evidence(case, record.head()["hash"])
    old_header_end = new["text"].index("\n\nNOTHING HAS BEEN OBSERVED YET")
    body_start = new["text"].index("\n\n", old_header_end + 2)
    old = dict(new, text=new["text"][:old_header_end] + new["text"][body_start:])
    backend = LMStudioBackend("gpt-oss-20b", timeout=3600)
    for sample in range(3):
        for label, packet in (("old_header", old), ("new_header", new)):
            prompt = DeliberationGate._build_deliberation_prompt(PROPOSAL, dossier, [packet])
            t0 = time.monotonic()
            raw = backend.complete(_DELIBERATION_SYSTEM_PROMPT, prompt, max_tokens=4000, temperature=0.4)
            final = raw.split("<|channel|>final<|message|>")[-1]
            row = {"sample": sample, "packet": label, "seconds": round(time.monotonic() - t0, 1),
                   "stance": (_parse_stance(raw) or None) and _parse_stance(raw).value, "final": final, "raw": raw}
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(sample, label, row["stance"], row["seconds"], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
