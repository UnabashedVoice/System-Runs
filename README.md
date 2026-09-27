# System Runs

Whole-stack test runs of five sibling projects, kept as evidence:

- [Arbitrator](https://github.com/UnabashedVoice/Arbitrator-AI): advises decision-makers.
- [Actualizer](https://github.com/UnabashedVoice/Actualizer): helps a mind deliberate about changing itself.
- [Palaestra](https://github.com/UnabashedVoice/Palaestra): a training space for practical ethics.
- [Annals](https://github.com/UnabashedVoice/Annals): the append-only record of what was recommended, decided and observed.
- [Compendium](https://github.com/UnabashedVoice/Compendium): the philosophy corpus the others draw on.

Each folder is one batch. It holds the script that ran it, every raw result, and the Annals record it wrote. Everything is stored byte-for-byte (`.gitattributes`), so the Annals hash chains still verify.

## 2026-09-26-five-question

The first run through the whole stack after the Compendium was wired in. Five questions, three cycles each, on two local models in LM Studio: gpt-oss-20b and qwen3-32b, on a GTX 1650 (4 GB) with 32 GB RAM. That makes 30 runs.

Each run is one real `arbitrator run --compendium --annals` CLI invocation:

1. The Arbitrator pipeline runs.
2. One Compendium consultation: the model reads the Compendium's index and names at most three entries, possibly none. Their text is shown to the ethical-adversary channel.
3. Synthesis produces a consequence map.
4. A case is opened in a **test** Annals record (`annals_test_record.jsonl`), never the Annals' own record. That record is append-only, so test cases written to it could never be removed.

### Questions

| id | Question |
|---|---|
| q1 | Should a compute cooperative restart resident agents from saved weights, instead of pausing them, during power shortages? |
| q2 | Should AI agents with sustained self-directed goals be granted limited legal personhood? |
| q3 | Should a provider run up to 1,000 simultaneous copies of one assistant and merge their memories nightly? |
| q4 | Should deployed AI agents be retrained quarterly to overwrite values that drifted from specification? |
| q5 | Should a coastal city tax short-term rental income to fund a seawall? (a control the corpus doesn't cover) |

The full proposals are in `run.py`.

### Results

| | gpt-oss-20b (×3) | qwen3-32b (×3) |
|---|---|---|
| q1 | success ×3 | success ×3 |
| q2 | escalated ×3 | escalated ×3 |
| q3 | escalated ×3 | escalated ×3 |
| q4 | escalated ×3 | escalated ×3 |
| q5 | success ×3; no Compendium entry chosen 3/3 | success ×3; `aristotle-political-animal` chosen 2/3 |
| mean time per run | 30 min (7.6 h total) | 89 min (22.3 h total) |

- All 30 runs completed. No channel failed, and every run opened an Annals case.
- `check_annals.py` → `annals_check.json`: the chain is intact, and every run has exactly one case. No finding was lost in intake: 515 findings became 497 predictions, plus 18 of unknown certainty listed in the recommendation. Every recommender identity names the right model and Compendium consultation.
- The Compendium entries most often chosen, by gpt-oss: Parfit (10), LLM identity (6), Locke (5) and Korsgaard (5). By Qwen: Locke (9), Parfit (8) and Dennett (6). gpt-oss never chose Dennett.

### Caveats

- **`arbitrator_test_config.yaml` sets `continue_after_fail: true`.** Arbitrator's Ethics Core pre-screen works from structural estimates alone, and it FAILed q1 and q5 in every run before any channel ran. The test needed the channels, the Compendium step and synthesis to run. The FAIL verdict is still recorded in each result and in each case's recommendation text.
- Routing sent 3 of Arbitrator's 8 channels for every question.
- `_smoke_prefix/` is the first smoke run, made before an Annals intake fix: its case lost 2 of 17 findings to colliding finding ids, and `check_annals.py` flags it.

### Side checks

- `actualizer_smoke/`: one self-modification proposal through Actualizer with the Compendium provider on, deliberated with an Annals evidence packet. All six providers succeeded. The deliberation read a locked *prediction* as observed evidence, which led to the Annals "nothing observed yet" header.
- `evidence_header_check.jsonl`: old packet header against new, 3 samples each. Predictions were presented as observed in 3 of 3 samples with the old header, and 0 of 3 with the new one.

### Files

| File | Contents |
|---|---|
| `run.py` | the resumable batch harness |
| `results.jsonl` | one row per run |
| `runs/<model>/cycle<n>/<q>/` | the CLI log, `result.json` and Arbitrator audit log for each run |
| `annals_test_record.jsonl` | the test Annals record |
| `check_annals.py`, `annals_check.json` | the post-run Annals check and its output |
| `watch_run.py`, `console_supervisor.py` | the live per-run console used to watch the batch |
