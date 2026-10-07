"""
thoughts.py — Render a run's complete thought process as one readable file.

    python thoughts.py <run_dir>      # writes arbitrator/thoughts.md and actualizer/thoughts.md

Every model call in the run appears in the order it happened, with its full
reasoning (gpt-oss's analysis channel or Qwen's <think> block) and its full
answer, nothing summarised or cut. The deterministic steps (the Ethics Core's
pre- and post-screen, synthesis) are shown between them so the reasoning can
be read in context. Built from the audit logs and records the run wrote.
"""

import json
import re
import sys
from pathlib import Path


def split(raw: str) -> tuple[str, str]:
    """(reasoning, answer) of a raw completion."""
    if not raw:
        return "", ""
    if "<|channel|>" in raw:
        parts = dict((m.group(1), m.group(2).strip()) for m in re.finditer(
            r"<\|channel\|>(\w+)<\|message\|>(.*?)(?=<\|(?:end|start|channel|return)\|>|$)", raw, flags=re.S))
        return parts.get("analysis", ""), parts.get("final", raw.strip())
    m = re.match(r"\s*<think>(.*?)(?:</think>|$)(.*)", raw, flags=re.S)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", raw.strip()


def call(title: str, raw: str | None, reasoning: str | None = None,
         finish: str | None = None) -> list[str]:
    r, answer = split(raw or "")
    r = reasoning or r
    cut = ["**This response was cut off: the model ran out of room (finish reason 'length').**", ""]         if finish == "length" else []
    return [f"### {title}", ""] + cut + [ "**Reasoning**", "", "```text", r or "(none recorded)", "```", "",
            "**Answer**", "", "```text", answer or "(none recorded)", "```", ""]


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def arbitrator(run_dir: Path) -> str:
    d = run_dir / "arbitrator"
    res = json.loads((d / "result.json").read_text(encoding="utf-8")) if (d / "result.json").exists() else {}
    lines = [f"# Arbitrator: complete thought process", "", f"Run: `{run_dir.name}`", "",
             "## Question", "", res.get("raw_input", "(result not written)"), ""]
    for e in load(d / "arbitrator_audit.jsonl"):
        p, k = e.get("payload", {}), e["kind"]
        if k == "ethics_evaluated":
            stage = p.get("stage", "pre_screen")
            label = ("Ethics Core pre-screen (deterministic; structural estimates, before any model)"
                     if stage == "pre_screen" else "Ethics Core post-screen (deterministic; on the channels' scores)")
            lines += [f"## {label}", "", f"Verdict **{p.get('verdict')}**: harm {p.get('weighted_harm')}, "
                      f"benefit {p.get('weighted_benefit')}, net {p.get('net_score')}.", "",
                      p.get("justification", ""), ""]
        elif k == "compendium_consulted":
            lines += ["## Compendium selection", "", f"{p.get('identity')}", ""]
            for s in p.get("selected", []):
                lines.append(f"- `{s['id']}` (sections: {', '.join(s.get('sections') or []) or 'none'}): {s.get('why')}")
            lines.append("")
            raws = p.get("raw_completions") or [p.get("raw")]
            finishes = p.get("finish_reasons") or []
            for i, raw in enumerate(raws, 1):
                lines += call(f"Selection call {i}", raw, finish=finishes[i - 1] if i <= len(finishes) else None)
        elif k == "channel_output":
            lines += [f"## Channel: {p.get('channel_name')} ({p.get('status')})", ""]
            if p.get("escalation_request"):
                lines += [f"Requested human review: {p['escalation_request']}", ""]
            lines += call(f"{p.get('channel_name')} ({p.get('model_id')})", p.get("raw_response"),
                          p.get("reasoning"), p.get("finish_reason"))
        elif k == "consequence_map":
            lines += ["## Synthesis (deterministic)", "", f"Verdict **{p.get('overall_verdict')}**: harm "
                      f"{p.get('overall_harm_score')}, benefit {p.get('overall_benefit_score')}, confidence "
                      f"{p.get('synthesis_confidence')}.", "", p.get("executive_summary", ""), ""]
        elif k == "escalation":
            lines += ["## Escalation", ""]
            for t in p.get("triggers", []):
                lines.append(f"- trigger `{t.get('source')}`: {t.get('detail')}")
            lines.append("")
            for i, a in enumerate(p.get("brief_attempts", []), 1):
                lines += call(f"Decision brief, attempt {i} ({p.get('model_id')})"
                              + (f"; problems: {'; '.join(a['problems'])}" if a.get("problems") else ""),
                              a.get("raw"), a.get("reasoning"), a.get("finish_reason"))
            if p.get("brief_error"):
                lines += [f"Brief not produced: {p['brief_error']}", ""]
        elif k == "decision_brief":
            # Since 2026-09-29 every analysed run has a brief, logged as its own entry.
            lines += ["## Decision brief", ""]
            for i, a in enumerate(p.get("attempts", []), 1):
                lines += call(f"Decision brief, attempt {i} ({p.get('model_id')})"
                              + (f"; problems: {'; '.join(a['problems'])}" if a.get("problems") else ""),
                              a.get("raw"), a.get("reasoning"), a.get("finish_reason"))
            if p.get("error"):
                lines += [f"Brief not produced: {p['error']}", ""]
    lines += ["## Outcome", "", f"Status **{res.get('status')}**; ethics verdict {res.get('ethics_verdict')} "
              f"(pre-screen {res.get('prescreen_verdict')}); synthesis {res.get('synthesis_verdict')}.", ""]
    return "\n".join(lines)


def actualizer(run_dir: Path) -> str:
    d = run_dir / "actualizer"
    lines = ["# Actualizer: complete thought process", "", f"Run: `{run_dir.name}`", ""]
    for e in load(d / "actualizer_audit.jsonl"):
        p, k = e.get("payload", {}), e["kind"]
        if k == "decision_received":
            lines += ["## Question", "", p.get("raw_input", ""), ""]
        elif k == "provider_output":
            lines += [f"## Provider: {p.get('provider_name')} ({p.get('status')})", ""]
            if p.get("framing_note"):
                lines += [f"Framing note: {p['framing_note']}", ""]
            lines += call(f"{p.get('provider_name')} ({p.get('model_id')})", p.get("raw_response"),
                          p.get("reasoning"), p.get("finish_reason"))
        elif k == "referent_dossier":
            lines += ["## Dossier (deterministic synthesis of the providers)", "", p.get("opening_note", ""), ""]
    rec_path = d / "deliberation_record.json"
    if rec_path.exists():
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        lines += ["## Deliberation", "", "The exact prompt is in `deliberation_prompt.txt`.", ""]
        lines += call(f"Deliberation ({rec.get('backend_model_id')})", rec.get("reasoning_summary"))
        lines += [f"Stance: **{rec.get('stance')}**", ""]
    summary = d / "summary.json"
    if summary.exists():
        s = json.loads(summary.read_text(encoding="utf-8"))
        if s.get("error"):
            lines += [f"Run failed: {s['error']}", ""]
    return "\n".join(lines)


def render(run_dir: Path) -> None:
    if (run_dir / "arbitrator").exists():
        (run_dir / "arbitrator" / "thoughts.md").write_text(arbitrator(run_dir), encoding="utf-8")
    if (run_dir / "actualizer").exists():
        (run_dir / "actualizer" / "thoughts.md").write_text(actualizer(run_dir), encoding="utf-8")


if __name__ == "__main__":
    render(Path(sys.argv[1]))
