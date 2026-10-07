# Abliterated gpt-oss: stopped, unusable in this runtime (2026-10-04)

`openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix`
(DavidAU, `OpenAI-20B-NEO-CODEPlus-Uncensored-Q5_1.gguf`), loaded in Bionic at 131072 context.

- The batch's t01 Arbitrator run started 04:35. The first channel call (economic) was still generating
  at 06:40, with nothing written. Stock gpt-oss finishes a channel in 15-25 minutes.
- Probe 1: a Harmony raw completion, capped at 400 tokens, sent alongside the stuck call. It took
  250 s and returned 400 `?` characters, finish_reason `length`. (The probe passed one argument of
  `_render_harmony` in the wrong position, so its prompt was slightly malformed. Probe 2 rules that out.)
- Probe 2: a plain chat completion through the model's own template, "Is 17 prime? Answer in one
  sentence.", capped at 300 tokens. LM Studio returned HTTP 500: "The model produced output that does
  not match the expected peg-native format".

The model emits garbage tokens, so every call would fill the window and every channel would retry
twice. The batch and the stuck run were stopped and the model unloaded. `runs/` keeps the stuck
run's audit log. No row was written to results.jsonl and no Annals case was opened.

Not yet known: whether the GGUF itself is broken or this Bionic runtime build mishandles it. Load it
alone (nothing else generating) and try a short chat in Bionic's own UI to tell.
