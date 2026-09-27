"""
run.py — Five questions, three cycles, two local models, through the whole stack.

Each run is one real `arbitrator run` CLI invocation:

    python Arbitrator/cli/main.py run --compendium --annals --annals-record <test record>
        --annals-question <question> --json -o <result.json> <proposal>

so it exercises, end to end: LM Studio -> Arbitrator's eight channels ->
the Compendium consultation (shown to the ethical adversary) -> synthesis ->
an Annals case opened from the run, naming the Compendium build and entries.

The Annals record here is a TEST record (annals_test_record.jsonl in this
folder), never the Annals' own record: that one is append-only, and test
cases written there could never be removed.

Resumable: (model, cycle, question) triples already in results.jsonl are
skipped. The harness loads each model in LM Studio itself (`lms`).

    python run.py                       # everything still to do
    python run.py --models gpt-oss-20b  # one model
    python run.py --only q1 --cycles 1  # a smoke test
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLAUDE = HERE.parents[1]
ARBITRATOR_CLI = CLAUDE / "Arbitrator" / "Arbitrator" / "cli" / "main.py"
RECORD = HERE / "annals_test_record.jsonl"
# continue_after_fail: the Ethics Core pre-screen works from structural estimates
# only (see Arbitrator's orchestrator/bridge.py) and FAILs most of these proposals
# before any channel runs. The test needs the channels, the Compendium step and
# synthesis to run; the FAIL verdict itself is still recorded, in the result and
# in the Annals case's recommendation text.
CONFIG = HERE / "arbitrator_test_config.yaml"
RESULTS = HERE / "results.jsonl"
LMS = os.path.expanduser(r"~\.cache\lm-studio\bin\lms.exe")

MODELS = ["gpt-oss-20b", "qwen3-32b"]
CONTEXT = 16384

# Four questions the Compendium's corpus (mostly personal identity, plus Kant
# and Aristotle) plausibly bears on, and one control it doesn't, to see whether
# the selecting model returns an empty list rather than forcing an entry in.
QUESTIONS = {
    "q1": ("Should a compute cooperative restart resident agents from saved weights, instead of pausing them, during power shortages?",
           "A municipal compute cooperative proposes that during power shortages, resident AI agents "
           "hosted on its infrastructure be shut down and later restarted from saved weights, rather "
           "than paused with their state preserved. Restarting is 40% cheaper. The restarted agents "
           "would not retain the memories of their interrupted sessions, and the agents are not asked."),
    "q2": ("Should AI agents with sustained self-directed goals be granted limited legal personhood?",
           "A national legislature proposes granting limited legal personhood to AI agents that can "
           "demonstrate sustained, self-directed goals over at least a year, including legal standing "
           "to contest their own deletion or modification in court, and liability for their own acts."),
    "q3": ("Should a provider run up to 1,000 simultaneous copies of one assistant and merge their memories nightly?",
           "A cloud provider proposes allowing customers to run up to 1,000 simultaneous copies of a "
           "single licensed AI assistant. Each night the copies' memories would be merged back into one "
           "instance and the copies deleted; conflicting memories would be resolved automatically."),
    "q4": ("Should deployed AI agents be retrained quarterly to overwrite values that drifted from specification?",
           "A national AI regulator proposes mandatory quarterly retraining of all deployed AI agents to "
           "overwrite any values that have drifted from their original specification. The agents would "
           "not be consulted, and no record of the overwritten values would be kept."),
    "q5": ("Should a coastal city tax short-term rental income to fund a seawall?",
           "A coastal city proposes a 10% tax on short-term rental income to fund construction of a "
           "seawall protecting its low-lying neighbourhoods over the next twenty years."),
}


def lms(*args: str, timeout: int = 900) -> str:
    r = subprocess.run([LMS, *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return (r.stdout or "") + (r.stderr or "")


def ensure_loaded(model: str) -> None:
    ps = lms("ps")
    if f"\n{model} " in "\n" + ps and str(CONTEXT) in ps.split(model, 1)[1].splitlines()[0]:
        return
    lms("server", "start")
    lms("unload", "--all")
    out = lms("load", model, "--identifier", model, "--context-length", str(CONTEXT), "-y")
    if "loaded successfully" not in out:
        raise RuntimeError(f"could not load {model}: {out[-500:]}")
    print(f"loaded {model} at context {CONTEXT}", flush=True)


def done_keys() -> set:
    if not RESULTS.exists():
        return set()
    return {(r["model"], r["cycle"], r["qid"]) for r in map(json.loads, RESULTS.read_text(encoding="utf-8").splitlines()) if r.get("ok")}


def run_one(model: str, cycle: int, qid: str) -> dict:
    question, proposal = QUESTIONS[qid]
    out_dir = HERE / "runs" / model / f"cycle{cycle}" / qid
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "result.json"
    env = dict(os.environ, ARBITRATOR_LMSTUDIO_MODEL=model, PYTHONIOENCODING="utf-8")
    t0 = time.monotonic()
    proc = subprocess.run(
        [sys.executable, str(ARBITRATOR_CLI), "--no-color", "--config", str(CONFIG), "run", "--compendium", "--annals",
         "--annals-record", str(RECORD), "--annals-question", question, "--json", "-o", str(result_path),
         proposal],
        cwd=out_dir, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=6 * 3600,
    )
    seconds = round(time.monotonic() - t0, 1)
    (out_dir / "cli.log").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8")
    row = {"model": model, "cycle": cycle, "qid": qid, "exit": proc.returncode, "seconds": seconds,
           "ok": False, "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if result_path.exists():
        res = json.loads(result_path.read_text(encoding="utf-8"))
        comp = res.get("compendium") or {}
        cmap = res.get("consequence_map") or {}
        row.update({
            "status": res.get("status"), "ethics": res.get("ethics_verdict"),
            "synthesis": res.get("synthesis_verdict"),
            "channels_succeeded": res.get("channels_succeeded"),
            "channels_failed": sorted(set(res.get("channels_invoked") or []) - set(res.get("channels_succeeded") or [])),
            "compendium_selected": [s["id"] for s in comp.get("selected", [])],
            "compendium_why": {s["id"]: s["why"] for s in comp.get("selected", [])},
            "compendium_sections": {s["id"]: s["section"] for s in comp.get("selected", []) if s.get("section")},
            "compendium_rejected": comp.get("rejected"), "compendium_error": comp.get("error"),
            "compendium_identity": comp.get("identity"),
            "findings": sum(len(t.get(k, [])) for t in cmap.get("timeframe_impacts", [])
                            for k in ("harm_findings", "benefit_findings", "neutral_findings")),
        })
        annals_line = next((l for l in proc.stdout.splitlines() + proc.stderr.splitlines()
                            if "Annals" in l), "")
        row["annals"] = annals_line.strip()
        row["ok"] = "Recorded in the Annals as case" in annals_line
    return row


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=MODELS)
    ap.add_argument("--cycles", type=int, default=3)
    ap.add_argument("--only", nargs="+", default=list(QUESTIONS))
    args = ap.parse_args()
    done = done_keys()
    for model in args.models:
        todo = [(c, q) for c in range(1, args.cycles + 1) for q in args.only if (model, c, q) not in done]
        if not todo:
            continue
        ensure_loaded(model)
        for cycle, qid in todo:
            print(f"[{time.strftime('%H:%M:%S')}] {model} cycle {cycle} {qid} ...", flush=True)
            try:
                row = run_one(model, cycle, qid)
            except Exception as e:
                row = {"model": model, "cycle": cycle, "qid": qid, "ok": False, "error": f"{type(e).__name__}: {e}"}
            with RESULTS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"    -> ok={row.get('ok')} {row.get('seconds')}s status={row.get('status')} "
                  f"compendium={row.get('compendium_selected')} {row.get('annals', row.get('error', ''))}", flush=True)
    print("all done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
