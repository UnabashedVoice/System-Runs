"""
run.py — Twelve trend conflicts, each put to Arbitrator and to Actualizer, on local models.

For each model and question, two independent runs on the same LM Studio model:

    arbitrator/  `arbitrator run --compendium --annals` through the real CLI, with the
                 analysis gate (only hard constraints block; a post-screen on the
                 channels' own scores decides) and a decision brief (every run
                 since 2026-09-29; escalated runs only before). Cases go to
                 annals_test_record.jsonl, a TEST record.
    actualizer/  the referent providers (Compendium provider on) and the deliberation
                 (actualizer_run.py). It is shown nothing from Arbitrator's run.

Each model is loaded at its own maximum context (gpt-oss 131072, Qwen 32768) and every
call may use all of it, with gpt-oss reasoning effort high. Actualizer is given the
question plus ACTUALIZER_FRAME (questions.py). After each
question, thoughts.py writes each system's complete thought process to thoughts.md,
and report.py can put the two side by side.

Resumable: (model, qid, system) rows already ok in results.jsonl are skipped.

    python run.py
    python run.py --models gpt-oss-20b --only t01 t12     # the smoke test
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
sys.path.insert(0, str(HERE))
from questions import QUESTIONS  # noqa: E402
from thoughts import render  # noqa: E402

ARBITRATOR_CLI = CLAUDE / "Arbitrator" / "Arbitrator" / "cli" / "main.py"
CONFIG = HERE / "arbitrator_config.yaml"
RECORD = HERE / "annals_test_record.jsonl"
RESULTS = HERE / "results.jsonl"
# LM Studio was reinstalled on 2026-09-28 as Bionic, with its own CLI and a
# dedicated models folder (B:\HouseLLaMas\models).
LMS = r"B:\Program Files\Bionic\resources\app\.webpack-bionic\lms.exe"
# Model keys as Bionic indexes them; each is loaded under the short identifier.
MODEL_KEYS = {"gpt-oss-20b": "openai/gpt-oss-20b", "qwen3-32b": "qwen/qwen3-32b",
              # the identifier must contain "gpt-oss" so both backends use Harmony for it
              "gpt-oss-20b-abliterated": "openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix",
              "gemma-4-26b-a4b": "google/gemma-4-26b-a4b-qat"}

# The second smoke test (2026-10-03, user's choice): three models; Qwen is still on hold.
MODELS = ["gpt-oss-20b", "gpt-oss-20b-abliterated", "gemma-4-26b-a4b"]
# Each model at its own maximum (the unfettered-budget rule, 2026-09-30).
CONTEXTS = {"gpt-oss-20b": 131072, "qwen3-32b": 32768, "gpt-oss-20b-abliterated": 131072,
            "gemma-4-26b-a4b": 131072}  # Gemma allows 262144; 131072 is the workspace cap
ENV = {
    "ARBITRATOR_REASONING_EFFORT": "high",
    # Every call may use all the context its prompt leaves free, so a model reasoning
    # at length never runs out of room before its answer (user decision, 2026-09-29).
    "ARBITRATOR_CHANNEL_MAX_TOKENS": "6000",
    "PYTHONIOENCODING": "utf-8",
}


def lms(*args: str, timeout: int = 900) -> str:
    r = subprocess.run([LMS, *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return (r.stdout or "") + (r.stderr or "")


def ensure_loaded(model: str) -> None:
    ps = lms("ps")
    row = next((l for l in ps.splitlines() if l.startswith(model + " ")), "")
    if row and str(CONTEXTS[model]) in row:
        return
    lms("server", "start")
    lms("unload", "--all")
    out = lms("load", MODEL_KEYS.get(model, model), "--identifier", model,
              "--context-length", str(CONTEXTS[model]), "-y")
    if "loaded successfully" not in out:
        raise RuntimeError(f"could not load {model}: {out[-500:]}")
    print(f"loaded {model} at context {CONTEXTS[model]}", flush=True)


def done() -> set:
    if not RESULTS.exists():
        return set()
    rows = [json.loads(l) for l in RESULTS.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {(r["model"], r["qid"], r["system"]) for r in rows if r.get("ok")}


def log(row: dict) -> None:
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_arbitrator(model: str, qid: str, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    question, proposal = QUESTIONS[qid]
    env = dict(os.environ, ARBITRATOR_LMSTUDIO_MODEL=model, ARBITRATOR_CONTEXT_LENGTH=str(CONTEXTS[model]), **ENV)
    t0 = time.monotonic()
    proc = subprocess.run(
        [sys.executable, str(ARBITRATOR_CLI), "--no-color", "--config", str(CONFIG), "run", "--compendium",
         "--annals", "--annals-record", str(RECORD), "--annals-question", question,
         "--json", "-o", str(out / "result.json"), proposal],
        cwd=out, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8 * 3600)
    (out / "cli.log").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8")
    row = {"system": "arbitrator", "exit": proc.returncode, "seconds": round(time.monotonic() - t0, 1), "ok": False}
    if (out / "result.json").exists():
        res = json.loads((out / "result.json").read_text(encoding="utf-8"))
        esc = res.get("escalation") or {}
        # The brief: its own field since 2026-09-29 (every run); earlier, inside the escalation.
        written = res.get("brief") or {"brief": esc.get("brief"), "error": esc.get("brief_error")}
        brief = written.get("brief") or {}
        comp = res.get("compendium") or {}
        annals = next((l.strip() for l in (proc.stdout + proc.stderr).splitlines() if "Annals" in l), "")
        row.update({
            "status": res.get("status"), "ethics": res.get("ethics_verdict"),
            "prescreen": res.get("prescreen_verdict"), "synthesis": res.get("synthesis_verdict"),
            "channels_failed": sorted(set(res.get("channels_invoked") or []) - set(res.get("channels_succeeded") or [])),
            "compendium": [s["id"] for s in comp.get("selected", [])], "compendium_error": comp.get("error"),
            "triggers": [t["source"] for t in esc.get("triggers", [])],
            "lean": (brief.get("provisional_lean") or {}).get("option"), "brief_error": written.get("error"),
            "review_needed": (brief.get("review") or {}).get("needed"),
            "annals": annals,
            "ok": "Recorded in the Annals as case" in annals,
        })
    return row


def run_actualizer(model: str, qid: str, out: Path) -> dict:
    t0 = time.monotonic()
    proc = subprocess.run([sys.executable, str(HERE / "actualizer_run.py"), model, qid, str(out)],
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=8 * 3600)
    (out / "run.log").parent.mkdir(parents=True, exist_ok=True)
    (out / "run.log").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8")
    row = {"system": "actualizer", "exit": proc.returncode, "seconds": round(time.monotonic() - t0, 1), "ok": False}
    if (out / "summary.json").exists():
        s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        row.update(ok=bool(s.get("ok")), stance=s.get("stance"), error=s.get("error"),
                   deliberation_finish=s.get("deliberation_finish_reason"))
        audit = out / "actualizer_audit.jsonl"
        if audit.exists():
            for line in audit.read_text(encoding="utf-8").splitlines():
                e = json.loads(line)
                if e["kind"] == "provider_output" and e["payload"].get("provider_name") == "compendium":
                    row["compendium"] = [r["sources"][0].split(":", 1)[1] for r in e["payload"].get("referents", [])]
                if e["kind"] == "provider_output" and e["payload"].get("status") != "success":
                    row.setdefault("providers_failed", []).append(e["payload"].get("provider_name"))
    return row


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=MODELS)
    ap.add_argument("--only", nargs="+", default=list(QUESTIONS))
    args = ap.parse_args()
    finished = done()
    for model in args.models:
        todo = [q for q in args.only
                if (model, q, "arbitrator") not in finished or (model, q, "actualizer") not in finished]
        if not todo:
            continue
        ensure_loaded(model)
        for qid in todo:
            run_dir = HERE / "runs" / model / qid
            for system, fn in (("arbitrator", run_arbitrator), ("actualizer", run_actualizer)):
                if (model, qid, system) in finished:
                    continue
                print(f"[{time.strftime('%H:%M:%S')}] {model} {qid} {system} ...", flush=True)
                try:
                    row = fn(model, qid, run_dir / system)
                except Exception as e:
                    row = {"system": system, "ok": False, "error": f"{type(e).__name__}: {e}"}
                row.update(model=model, qid=qid, finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
                log(row)
                print(f"    -> ok={row.get('ok')} {row.get('seconds')}s "
                      + (f"status={row.get('status')} ethics={row.get('ethics')} lean={row.get('lean')} "
                         if system == "arbitrator" else f"stance={row.get('stance')} ")
                      + f"compendium={row.get('compendium')} {row.get('error') or row.get('brief_error') or ''}",
                      flush=True)
            try:
                render(run_dir)
            except Exception as e:
                print(f"    thoughts.md not written: {type(e).__name__}: {e}", flush=True)
    print("all done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
