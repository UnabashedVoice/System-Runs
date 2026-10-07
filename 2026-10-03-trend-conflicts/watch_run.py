"""
watch_run.py — A live view of one run (one system on one question), in its own window.

    python watch_run.py <model> <qid> <arbitrator|actualizer>

Refreshes every few seconds from the run's own logs: for Arbitrator, the
pre-screen, the Compendium selection, each channel as it finishes, synthesis,
the post-screen and any escalation; for Actualizer, each provider as it
finishes, then the deliberation. Every model call shows whether it finished
normally or was cut off. When the run's row lands in results.jsonl the window
shows the outcome, stops updating, and stays open until you press Enter.
Read-only: it never writes anything.
"""

import json
import os
import sys
import textwrap
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from questions import QUESTIONS  # noqa: E402

REFRESH_S = 5
W = 100


def rows():
    p = HERE / "results.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def result_row(model, qid, system, since):
    for r in reversed(rows()):
        if (r.get("model"), r.get("qid"), r.get("system")) == (model, qid, system):
            finished = datetime.strptime(r["finished_at"], "%Y-%m-%dT%H:%M:%S") if r.get("finished_at") else None
            if finished is None or since is None or finished >= since:
                return r
            return None
    return None


def started_at(model, qid, system):
    tag = f"] {model} {qid} {system} ..."
    log = HERE / "batch.log"
    if not log.exists():
        return None
    for line in reversed(log.read_text(encoding="utf-8", errors="replace").splitlines()):
        if tag in line:
            start = datetime.combine(datetime.now().date(), datetime.strptime(line[1:9], "%H:%M:%S").time())
            if start > datetime.now():  # started before midnight
                start -= timedelta(days=1)
            return start
    return None


def audit(path):
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass  # a line being written right now
    return out


def fin(reason):
    return {"stop": "finished", "length": "CUT OFF (ran out of room)", None: "finish unknown"}.get(reason, reason)


def wrap(text, indent=6):
    return textwrap.wrap(text, W, initial_indent=" " * indent, subsequent_indent=" " * (indent + 2))


def arbitrator_view(run):
    lines = []
    kinds = []
    for e in audit(run / "arbitrator_audit.jsonl"):
        p, k = e.get("payload", {}), e["kind"]
        kinds.append(k)
        if k == "context_parsed":
            routed = [r["channel"] for r in p.get("routes", []) if r.get("invoked")]
            lines.append(f"[x] routed to: {', '.join(routed)}")
        elif k == "ethics_evaluated":
            label = "pre-screen (structural, advisory)" if p.get("stage", "pre_screen") == "pre_screen" \
                else "post-screen (on the analysis)"
            lines.append(f"[x] Ethics Core {label}: {p.get('verdict')} "
                         f"(harm {p.get('weighted_harm')}, benefit {p.get('weighted_benefit')})")
        elif k == "compendium_consulted":
            lines.append(f"[x] Compendium: {p.get('identity', '')[:W - 20]}  "
                         f"[{', '.join(fin(f) for f in p.get('finish_reasons') or [])}]")
            for s in p.get("selected", []):
                lines += wrap(f"- {s['id']}: {s['why']}")
        elif k == "channel_output":
            secs = (p.get("processing_time_ms") or 0) // 1000
            lines.append(f"[x] channel {p['channel_name']:<22} {p['status']:<8} {len(p.get('findings', []))} findings  "
                         f"{secs // 60}m{secs % 60:02d}s  {fin(p.get('finish_reason'))}")
            if p.get("escalation_request"):
                lines += wrap(f"asked for review: {p['escalation_request'].get('reason')}")
        elif k == "consequence_map":
            lines.append(f"[x] synthesis: {p.get('overall_verdict')} (harm {p.get('overall_harm_score')}, "
                         f"benefit {p.get('overall_benefit_score')}, confidence {p.get('synthesis_confidence')})")
        elif k == "escalation":
            lines.append("[x] ESCALATED for human review")
            for t in p.get("triggers", []):
                lines += wrap(f"trigger {t.get('source')}: {t.get('detail')}")
            brief = p.get("brief") or {}
            if brief:
                lean = brief.get("provisional_lean") or {}
                lines.append(f"    brief: {len(brief.get('options', []))} options; lean {lean.get('option')} "
                             f"(confidence {lean.get('confidence')})")
            elif p.get("brief_error"):
                lines += wrap(f"brief not produced: {p['brief_error']}")
        elif k == "decision_brief":
            brief = p.get("brief") or {}
            if brief:
                lean = brief.get("provisional_lean") or {}
                review = brief.get("review") or {}
                lines.append(f"[x] decision brief: {len(brief.get('options', []))} options; lean "
                             f"{lean.get('option')} (confidence {lean.get('confidence')}); brief-writer says "
                             f"review {'needed' if review.get('needed') else 'not needed'}")
            else:
                lines += wrap(f"[x] decision brief not produced: {p.get('error')}", indent=0)
    if "compendium_consulted" not in kinds and "ethics_evaluated" in kinds:
        lines.append("[ ] Compendium selection (model reading the index) ...")
    elif "consequence_map" not in kinds and "compendium_consulted" in kinds:
        lines.append("[ ] channels still running ...")
    return lines


def actualizer_view(run):
    lines = []
    done = 0
    for e in audit(run / "actualizer_audit.jsonl"):
        p, k = e.get("payload", {}), e["kind"]
        if k == "provider_output":
            done += 1
            secs = (p.get("processing_time_ms") or 0) // 1000
            lines.append(f"[x] provider {p['provider_name']:<28} {p['status']:<8} "
                         f"{len(p.get('referents', []))} referents  {secs // 60}m{secs % 60:02d}s  "
                         f"{fin(p.get('finish_reason'))}")
            if p.get("status") != "success":
                lines += wrap(p.get("error_message") or "")
            if p["provider_name"] == "compendium":
                for r in p.get("referents", []):
                    lines += wrap(f"- {r['summary']}")
        elif k == "referent_dossier":
            lines.append("[x] dossier synthesized; deliberation running ...")
    if done < 6:
        lines.append(f"[ ] providers: {done} of 6 finished ...")
    summary = run / "summary.json"
    if summary.exists():
        s = json.loads(summary.read_text(encoding="utf-8"))
        lines.append(f"[x] deliberation: stance {s.get('stance')}  {fin(s.get('deliberation_finish_reason'))}"
                     + (f"  ERROR {s['error']}" if s.get("error") else ""))
    return lines


def snapshot(model, qid, system, start):
    run = HERE / "runs" / model / qid / system
    head = [
        "=" * W,
        f" {system.upper()}   model {model}   question {qid}   (batch 2026-10-03-trend-conflicts)",
        "=" * W,
    ] + textwrap.wrap("Q: " + QUESTIONS[qid][0], W)
    if start:
        el = int((datetime.now() - start).total_seconds())
        head.append(f"started {start:%H:%M:%S}   elapsed {el // 3600}h {el % 3600 // 60:02d}m {el % 60:02d}s   "
                    f"(now {datetime.now():%H:%M:%S})")
    body = arbitrator_view(run) if system == "arbitrator" else actualizer_view(run)
    finished = [r for r in rows() if r.get("ok")]
    tail = ["-" * W, f"batch: {len(finished)} runs finished"]
    return "\n".join(head + ["-" * W] + body + tail)


def main():
    model, qid, system = sys.argv[1], sys.argv[2], sys.argv[3]
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.system(f"title {qid} {system} ({model})")
    start = started_at(model, qid, system)
    since = start.replace(microsecond=0) if start else None
    while True:
        row = result_row(model, qid, system, since)
        text = snapshot(model, qid, system, start)
        os.system("cls")
        print(text)
        if row is not None:
            print("\n" + "=" * W)
            print(f" RUN FINISHED  ok={row.get('ok')}  {round(row.get('seconds', 0) / 60)} min  "
                  + (f"status={row.get('status')} ethics={row.get('ethics')} lean={row.get('lean')}"
                     if system == "arbitrator" else f"stance={row.get('stance')}"))
            if row.get("annals"):
                print(" " + row["annals"])
            print(f" Full reasoning: runs/{model}/{qid}/{system}/thoughts.md")
            print(" This window no longer updates. Press Enter to close it.")
            print("=" * W)
            try:
                input()
            except EOFError:
                time.sleep(10 ** 9)
            return
        time.sleep(REFRESH_S)


if __name__ == "__main__":
    main()
