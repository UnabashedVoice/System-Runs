"""
check_annals.py — After the batch: is everything in the Annals, and correctly?

Checks, against the TEST record only:
  1. The hash chain verifies.
  2. Every successful run in results.jsonl has exactly one case, found by its
     Arbitrator session id.
  3. Nothing was lost in intake: each case's predictions plus its listed
     unknown-certainty findings account for every channel finding in the run.
  4. The recommender identity is right: the model the run used, and the
     Compendium build and entries the run's consultation reports.
  5. The export paths work on a real case: a Palaestra draft (which Palaestra
     must refuse to load) and an Actualizer evidence packet. The Compendium
     challenge listing runs too, but has nothing to list without a review.
Writes annals_check.json and prints a summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLAUDE = HERE.parents[1]
sys.path.insert(0, str(CLAUDE / "Annals"))
sys.path.insert(0, str(CLAUDE / "Palaestra"))

from annals import Annals  # noqa: E402
from annals.exports import actualizer_evidence, compendium_challenges, palaestra_draft  # noqa: E402

RECORD = HERE / "annals_test_record.jsonl"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = Annals(RECORD)
    report = {"record": str(RECORD), "chain_problems": a.problems, "runs": [], "exports": {}}
    rows = [json.loads(l) for l in (HERE / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    cases = {c.body["source"]["session_id"]: c for c in a.cases()}

    for row in rows:
        rdir = HERE / "runs" / row["model"] / f"cycle{row['cycle']}" / row["qid"]
        res_path = rdir / "result.json"
        entry = {"model": row["model"], "cycle": row["cycle"], "qid": row["qid"], "ok": row.get("ok")}
        if not res_path.exists():
            entry["problem"] = "no result.json"
            report["runs"].append(entry)
            continue
        res = json.loads(res_path.read_text(encoding="utf-8"))
        case = cases.get(res["session_id"])
        entry["case"] = case.case_id if case else None
        if case is None:
            entry["problem"] = "no case in the record for this run"
            report["runs"].append(entry)
            continue
        cmap = res["consequence_map"]
        findings = [f for c in cmap["channel_outputs"] for f in c.get("findings", [])]
        scored = [f for f in findings if f["certainty"] in ("high", "moderate", "low")]
        unknown = [f for f in findings if f not in scored]
        preds = case.predictions
        entry.update({
            "findings": len(findings), "predictions": len(preds), "unknown_certainty": len(unknown),
            "nothing_lost": len(preds) == len(scored)
                            and all(f["summary"] in case.body["recommendation"] for f in unknown),
        })
        rec = case.body["recommender"]
        comp = res.get("compendium") or {}
        entry["identity_ok"] = (row["model"] in rec["model"]
                                and rec["compendium_version"] == comp.get("identity")
                                and rec["palaestra_lineage"] == "none")
        entry["compendium_version"] = rec["compendium_version"]
        entry["source_entries_ok"] = case.body["source"].get("compendium_entries") == [s["id"] for s in comp.get("selected", [])]
        report["runs"].append(entry)

    # Export paths, on the first recorded case.
    first = next((c for c in a.cases()), None)
    if first is not None:
        head = a.head()["hash"]
        draft = palaestra_draft(first, head)
        from palaestra.schema import load_perspectives, validate_family
        persp = load_perspectives(CLAUDE / "Palaestra" / "perspectives.json")
        errs = validate_family(draft, persp)
        report["exports"]["palaestra_draft_refused"] = bool(errs) and "draft from the Annals" in errs[0]
        report["exports"]["palaestra_todo"] = draft["_authoring"]["todo"]
        ev = actualizer_evidence(first, head)
        report["exports"]["actualizer_ref"] = ev["ref"]
        report["exports"]["actualizer_text_starts"] = ev["text"][:120]

        # No review is written here: a review looks back on a recorded decision, and
        # none exists for a test run. The challenge listing is run anyway (it should
        # be empty); the review -> challenge path itself is covered by Annals' tests.
        sys.path.insert(0, str(CLAUDE / "Compendium"))
        from compendium_access import Compendium
        ids = set(Compendium(CLAUDE / "Compendium" / "dist" / "compendium.jsonl").ids)
        report["exports"]["compendium_challenges"] = compendium_challenges(a.cases(), ids)

    (HERE / "annals_check.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    runs = report["runs"]
    print(f"record: {len(a.cases())} cases; chain problems: {report['chain_problems'] or 'none'}")
    print(f"runs: {len(runs)}; with a case: {sum(1 for r in runs if r.get('case'))}; "
          f"nothing lost: {sum(1 for r in runs if r.get('nothing_lost'))}; "
          f"identity ok: {sum(1 for r in runs if r.get('identity_ok'))}; "
          f"source entries ok: {sum(1 for r in runs if r.get('source_entries_ok'))}")
    for r in runs:
        if r.get("problem") or not (r.get("nothing_lost") and r.get("identity_ok")):
            print("  ", r)
    print("exports:", json.dumps({k: v for k, v in report["exports"].items() if k != "palaestra_todo"},
                                 ensure_ascii=False)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
