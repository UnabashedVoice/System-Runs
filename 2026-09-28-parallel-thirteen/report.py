"""
report.py — Arbitrator and Actualizer side by side, question by question.

    python report.py            # writes REPORT.md

For each question and model: Arbitrator's status, Ethics Core verdicts
(pre-screen advisory, post-screen from the analysis), synthesis verdict,
escalation triggers and the decision brief's lean; Actualizer's stance and
the answer its deliberation gave; and the Compendium entries each chose.
The two systems' runs were independent: neither saw the other's output.
Links point to each run's thoughts.md for the full reasoning.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from questions import QUESTIONS  # noqa: E402
from thoughts import split  # noqa: E402


def load_rows():
    rows = {}
    path = HERE / "results.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[(r["model"], r["qid"], r["system"])] = r  # the last row for a triple wins
    return rows


def final_answer(model: str, qid: str) -> str:
    p = HERE / "runs" / model / qid / "actualizer" / "deliberation_record.json"
    if not p.exists():
        return ""
    return split(json.loads(p.read_text(encoding="utf-8")).get("reasoning_summary", ""))[1]


def brief(model: str, qid: str) -> dict:
    p = HERE / "runs" / model / qid / "arbitrator" / "result.json"
    if not p.exists():
        return {}
    res = json.loads(p.read_text(encoding="utf-8"))
    # Its own field since 2026-09-29; before, briefs sat inside the escalation.
    return ((res.get("brief") or {}).get("brief") or (res.get("escalation") or {}).get("brief")) or {}


def main():
    rows = load_rows()
    models = sorted({m for m, _, _ in rows})
    out = ["# Thirteen questions: Arbitrator and Actualizer side by side", "",
           "Each question went to both systems separately, on the same model; neither saw the other's run. "
           "Arbitrator ran with the analysis gate. Full reasoning for every run is in its `thoughts.md`.", ""]
    for qid, (question, _) in QUESTIONS.items():
        out += [f"## {qid}: {question}", ""]
        for model in models:
            a, b = rows.get((model, qid, "arbitrator")), rows.get((model, qid, "actualizer"))
            if not a and not b:
                continue
            out.append(f"### {model}")
            out.append("")
            out.append("| | Arbitrator | Actualizer |")
            out.append("|---|---|---|")
            out.append(f"| Outcome | {a.get('status') if a else 'not run'}"
                       f"{'; lean: `' + str(a.get('lean')) + '`' if a and a.get('lean') else ''} | "
                       f"stance: {b.get('stance') if b else 'not run'} |")
            if a:
                out.append(f"| Ethics Core | post-screen {a.get('ethics')}; pre-screen {a.get('prescreen')} (advisory) | |")
                out.append(f"| Synthesis / triggers | {a.get('synthesis')}; {', '.join(a.get('triggers') or []) or 'none'} | |")
            out.append(f"| Compendium | {', '.join(a.get('compendium') or []) if a else ''} | "
                       f"{', '.join(b.get('compendium') or []) if b else ''} |")
            out.append(f"| Time | {round((a or {}).get('seconds', 0) / 60)} min | {round((b or {}).get('seconds', 0) / 60)} min |")
            out.append(f"| Thought log | [thoughts.md](runs/{model}/{qid}/arbitrator/thoughts.md) | "
                       f"[thoughts.md](runs/{model}/{qid}/actualizer/thoughts.md) |")
            out.append("")
            br = brief(model, qid)
            if br:
                out.append("**Arbitrator's decision brief.** To decide: " + " ".join(br.get("decision_questions", [])))
                out.append("")
                aside = {a.get("option"): a.get("because") for a in br.get("set_aside") or [] if isinstance(a, dict)}
                for o in br.get("options", []):
                    out.append(f"- `{o['id']}` {o['label']}: {o.get('consequences', '')}")
                    if o.get("case_for") or o.get("case_against"):
                        out.append(f"  - for: {o.get('case_for', '')}")
                        out.append(f"  - against: {o.get('case_against', '')}")
                    if o["id"] in aside:
                        out.append(f"  - set aside because: {aside[o['id']]}")
                lean = br.get("provisional_lean") or {}
                out += ["", f"Lean: `{lean.get('option')}` ({lean.get('confidence')}). "
                            + (f"{lean['reasoning']} " if lean.get("reasoning") else "")
                            + f"Would change if {lean.get('would_change_if')}", ""]
                review = br.get("review") or {}
                if review:
                    out += [f"Brief-writer on review: {'needed' if review.get('needed') else 'not needed'}. "
                            f"{review.get('why', '')}", ""]
            ans = final_answer(model, qid)
            if ans:
                out += ["**Actualizer's answer.**", "", "> " + ans.replace("\n", "\n> "), ""]
    (HERE / "REPORT.md").write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {HERE / 'REPORT.md'}")


if __name__ == "__main__":
    main()
