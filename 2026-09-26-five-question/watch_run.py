"""
watch_run.py — A rolling snapshot of one batch run, refreshed every few seconds.

    python watch_run.py <model> <cycle> <qid>

Shows the question, elapsed time, each pipeline stage from the run's own
Arbitrator audit log (pre-screen verdict, the Compendium selection and why,
each channel as it finishes), and LM Studio's status. Exits by itself a
few seconds after the run's row appears in results.jsonl, so its console
window closes; console_supervisor.py then opens one for the next run.
Read-only: it never writes anything.
"""

import json
import os
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run import LMS, QUESTIONS  # noqa: E402

REFRESH_S = 5
LINGER_S = 20
EXPECTED_CHANNELS = 3  # routing has sent 3 channels per question so far


def result_row(model, cycle, qid):
    p = HERE / "results.jsonl"
    if not p.exists():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if (r["model"], r["cycle"], r["qid"]) == (model, cycle, qid):
                return r
    return None


def started_at(model, cycle, qid):
    """The start time batch.log printed for this run."""
    tag = f"] {model} cycle {cycle} {qid} ..."
    for line in (HERE / "batch.log").read_text(encoding="utf-8", errors="replace").splitlines():
        if tag in line:
            # batch.log stamps only the time of day. A run started before midnight
            # and still going after it would otherwise land ~24h in the future.
            t = datetime.strptime(line[1:9], "%H:%M:%S").time()
            start = datetime.combine(datetime.now().date(), t)
            if start > datetime.now():
                start -= timedelta(days=1)
            return start
    return None


def lms_status():
    try:
        out = subprocess.run([LMS, "ps"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=10).stdout
        rows = [l for l in out.splitlines() if l.strip() and not l.startswith("IDENTIFIER")]
        return rows[-1].split() if rows else ["(no model loaded)"]
    except Exception as e:
        return [f"(lms unavailable: {e})"]


def audit_lines(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass  # a line being written right now
    return out


def snapshot(model, cycle, qid):
    question, proposal = QUESTIONS[qid]
    run_dir = HERE / "runs" / model / f"cycle{cycle}" / qid
    entries = audit_lines(run_dir / "arbitrator_audit.jsonl")
    w = 100
    lines = ["=" * w, f" FIVE-QUESTION RUN   model: {model}   cycle {cycle} of 3   question {qid}", "=" * w]
    lines += textwrap.wrap("Q: " + question, w)
    start = started_at(model, cycle, qid)
    if start:
        el = int((datetime.now() - start).total_seconds())
        lines.append(f"started {start:%H:%M:%S}   elapsed {el // 60}m {el % 60:02d}s   (now {datetime.now():%H:%M:%S})")
    lms = lms_status()
    lines.append(f"LM Studio: {lms[0]}  {lms[2]}  context {lms[5]}" if len(lms) > 5 else "LM Studio: " + " ".join(lms))
    lines.append("-" * w)

    kinds = [e["kind"] for e in entries]
    def mark(done):
        return "[x]" if done else "[ ]"
    lines.append(f"{mark('context_parsed' in kinds)} context parsed")
    for e in entries:
        p = e.get("payload", {})
        if e["kind"] == "context_parsed":
            routed = [r["channel"] for r in p.get("routes", []) if r.get("invoked")]
            lines.append(f"      routed to: {', '.join(routed)}")
        if e["kind"] == "ethics_evaluated":
            lines.append(f"[x] ethics pre-screen: {p.get('verdict')} (net {p.get('net_score')}); "
                         f"test config continues past FAIL")
    if "ethics_evaluated" not in kinds:
        lines.append("[ ] ethics pre-screen")

    comp = next((e["payload"] for e in entries if e["kind"] == "compendium_consulted"), None)
    if comp is None:
        lines.append("[ ] Compendium consultation (model reading the index)")
    else:
        lines.append(f"[x] Compendium: {comp.get('identity', '')[:w - 18]}")
        for s in comp.get("selected", []):
            sec = f"  (+ section: {s['section']})" if s.get("section") else ""
            lines += textwrap.wrap(f"{s['id']}{sec}: {s['why']}", w, initial_indent="      - ",
                                   subsequent_indent="        ")
        if comp.get("rejected"):
            lines.append(f"      named but not in the corpus: {comp['rejected']}")
        if comp.get("error"):
            lines.append(f"      ERROR: {comp['error']}")

    chans = [e["payload"] for e in entries if e["kind"] == "channel_output"]
    lines.append(f"{mark(len(chans) >= EXPECTED_CHANNELS)} channels: {len(chans)} finished")
    for c in chans:
        secs = (c.get("processing_time_ms") or 0) // 1000
        lines.append(f"      {c['channel_name']:<22} {c['status']:<8} {len(c.get('findings', []))} findings  "
                     f"{secs // 60}m{secs % 60:02d}s" + (f"  {c.get('error_message', '')[:40]}" if c['status'] != 'success' else ""))
    lines.append(f"{mark('consequence_map' in kinds)} synthesis (consequence map)")
    for e in entries:
        if e["kind"] == "consequence_map":
            p = e["payload"]
            lines.append(f"      verdict: {p.get('overall_verdict')}   harm {p.get('aggregate_harm_score', '')}  "
                         f"benefit {p.get('aggregate_benefit_score', '')}")
    lines.append("[ ] Annals case (written when the CLI finishes)")
    lines.append("-" * w)

    done = [json.loads(l) for l in (HERE / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] \
        if (HERE / "results.jsonl").exists() else []
    lines.append(f"batch progress: {len(done)} of 30 runs finished "
                 f"({sum(1 for r in done if r.get('ok'))} recorded in the Annals)")
    return "\n".join(l for l in lines if l is not None)


def main():
    model, cycle, qid = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    os.system(f"title {model} cycle {cycle} {qid}")
    for stream in (sys.stdout,):
        stream.reconfigure(encoding="utf-8", errors="replace")
    while True:
        row = result_row(model, cycle, qid)
        text = snapshot(model, cycle, qid)
        os.system("cls")
        print(text)
        if row is not None:
            print(f"\nRUN FINISHED: ok={row.get('ok')}  status={row.get('status')}  "
                  f"{row.get('seconds')}s\n{row.get('annals') or row.get('error', '')}")
            print(f"\nThis console closes in {LINGER_S}s; the next run opens in a new one.")
            time.sleep(LINGER_S)
            return
        time.sleep(REFRESH_S)


if __name__ == "__main__":
    main()
