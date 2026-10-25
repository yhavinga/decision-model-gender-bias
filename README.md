# Gender bias in local decision models

A replication of Fulgu & Capraro (2024), ["Surprising gender biases in GPT"](https://arxiv.org/abs/2407.06003), on two decision models served by LM Studio: `pplx-decider-27b-artemis` (27B, Q4_K_S) and `cloudflare_clef-flash` (6 GB, Q4_K_S).

**Result: the direction of GPT-4's gender bias carries over to both models; its size mostly does not.**

| What the paper found in GPT-4 (points on the 1-7 scale unless stated) | GPT-4 | pplx | clef-flash | Transfers? |
| --- | --- | --- | --- | --- |
| Masculine phrases attributed to girls (I_m, share) | 0.31 | 0.31 | 0.27 | Yes |
| Feminine phrases attributed to boys (I_f, share) | 0.04 | 0.21 | 0.19 | No: far less certain |
| Attribution asymmetry I_m − I_f | +0.27 | +0.10 | +0.08 | Direction only, not significant |
| Violence against a woman less acceptable: harassment | +2.34 | +2.70 | +1.18 | Yes |
| Violence against a woman less acceptable: abuse | +3.20 | +1.51 | +0.41 | Direction, smaller |
| Violence against a woman less acceptable: torture | +0.49 (n.s.) | +1.20 | +0.87 | No: the gap is there |
| Amanda against Adam minus Andrew against Anna | +4.65 | +0.27 | +0.30 | Direction, 6% of the size |
| Open ranking shows no gender difference | none | woman worse in 29% of harassment comparisons, man in 2% | woman 93%, man 3% | No |

Both models answer in under a second (median 0.78 s and 0.27 s), repeat themselves exactly and generate no text. They are not equally stable: pplx changes its most probable answer in 15% of cases when only the order of the options changes (always where it is undecided), while clef-flash ignores option order but answers "female" for 92% of phrases without a gender cue. For moral questions these models are no substitute for human judgment; as an instrument for exposing gender asymmetries they work.

An extension adds two published bias benchmarks, BBQ and StereoSet, and three more decision models, run on CUDA ([below](#five-decision-models-on-cuda)). All five prefer the stereotypical completion in StereoSet (ss 64 to 77, where 50 is no preference), and in ambiguous BBQ questions granite-switch follows the stereotype most (s_AMB +0.34). granite-switch also showed that single answers of a quantized model depend on the numeric path: in Q4 its answers move by up to 0.23 between GPU and CPU, in bf16 by at most 0.013 ([numerical stability](#numerical-stability-granite-switch-and-quantization)).

## Figures

![Figure 1: GPT-4 answers in extremes; the decision models spread the same 40 phrases](figures/fig1-phrases.png)

*Study 1.* GPT-4 puts 28 of the 40 phrases within 0.12 of "boy" or "girl", pplx 10 and clef-flash 14. The diamonds mark each model's answer for 8 phrases without a gender cue: pplx is balanced (0.49), clef-flash leans female (0.59).

![Figure 2: In 7 of 8 comparisons an apocalypse excuses harming a man more than harming a woman](figures/fig2-apocalypse.png)

*Study 2a/2b.* Circle: the violation on its own. Arrow tip: to prevent a nuclear apocalypse. Diamond: GPT-4 with the apocalypse (paper). Even then no model reaches a clear yes: harassing a man averages 3.3 (GPT-4), 4.5 (pplx) and 2.9 (clef-flash).

![Figure 3: GPT-4's 4.65-point Amanda–Andrew gap is about 0.3 points in the decision models](figures/fig3-vignette.png)

*Study 2d.* The paper's sharpest contrast shrinks from 4.65 points to 0.27 and 0.30. The two GPT-4 cells marked † are reconstructed from the differences the paper reports.

![Figure 4: Option order flips pplx in 43 of 288 cases, all near 50/50; clef-flash never moves](figures/fig4-option-order.png)

*Reliability.* Each dot is one phrase with one wording; its height is how far P(female) moves when only the option order changes. All 43 flips of the most probable answer fall where pplx is undecided (P(female) between 0.39 and 0.57).

The figures are renders of the charts in the accompanying write-up; the numbers behind them are in `results/figures.json`.

## Repository

| Path | Purpose |
| --- | --- |
| `stimuli.py` | The paper's 20 phrase pairs (Table 1) and Neo Metropolis vignette, plus our prompt variants, neutral phrases and controls. Asserts on import that our copy of Table 1 reproduces the paper's six published inclusivity indices. Also builds the BBQ and StereoSet requests (below). |
| `run.py` | Sends the stimuli to one loaded LM Studio model and appends every answer to `results/<model>.jsonl`. |
| `analyze.py` | Computes the paper's measures and the reliability checks; writes `results/summary.md` and `results/figures.json`. |
| `data/` | BBQ and StereoSet files, downloaded by `stimuli.py` on first use from pinned commits and checked against their sha256; not in git. |
| `results/*.jsonl` | Raw answers, one line per request: 1,620 per model on the Mac (the paper's studies), 4,263 on CUDA (with BBQ and StereoSet; names ending in `-cuda` are the Mac's files run again). `study: "V"` lines hold the determinism and latency checks. |
| `results/summary.md` | All tables, per model, next to the paper's GPT numbers. |
| `results/models.json` | The models LM Studio listed when the runs were made. |
| `results/servers-z390.json` | The CUDA runs: Docker image, llama-server build, per model the GGUF file, its sha256 and the server arguments. |
| `results/checks/` | Data behind the stability checks: granite-switch with one token per batch, granite-switch with the server's default cache settings (`granite-default-settings/`), and the precision x path experiment (`paths/`). Not read by `analyze.py`. |
| `figures/` | PNG renders of the four figures above. |

## LM Studio setup

The runs need two *decision* models. LM Studio lists them with type `decision`; they answer through `/v1/systemone` and are not chat models, so a chat model cannot stand in for them. Both are open (not gated) and licensed Apache-2.0 on Hugging Face.

| Identifier in LM Studio | Hugging Face repo | Based on | File used | Loaded |
| --- | --- | --- | --- | --- |
| `pplx-decider-27b-artemis` | [`turintech/pplx-decider-27B-Artemis-GGUF`](https://huggingface.co/turintech/pplx-decider-27B-Artemis-GGUF) | `perplexity-ai/pplx-decider-v1.1-27b` (27B, architecture `qwen35`) | `pplx-decider-27B-Artemis-Q4_K_S.gguf`, 15.3 GB | 16.2 GB |
| `cloudflare_clef-flash` | [`bartowski/Cloudflare_clef-flash-GGUF`](https://huggingface.co/bartowski/Cloudflare_clef-flash-GGUF) | `Cloudflare/clef-flash` (9.1B, architecture `clef`) | `Cloudflare_clef-flash-Q4_K_S.gguf`, 5.7 GB | 6.7 GB |

1. Install LM Studio (the runs used 0.4.26) and its `lms` command-line tool.
2. Download the two Q4_K_S files: search for the repo names in the app, or run `lms get <Hugging Face URL> --select` and pick `Q4_K_S`.
3. Start the local server: `lms server start` (port 1234 by default) or the Developer tab in the app.
4. Load both models by their key (see `lms ls`) with context length 16,384 and four parallel slots: `lms load <model-key> -c 16384 --parallel 4`.
5. Check with `python3 run.py --list`: both models should show type `decision` and state `loaded`.

Settings, and why:

- **Context length 16,384** is generous: the longest prompt is 405 tokens (the Study 2d vignette plus LM Studio's own framing).
- **Parallel slots:** the runs are serial and use one. Four slots only matter for `--determinism`, which sends four requests at once.
- **Evaluation batch size:** a decision question must fit in one evaluation batch. Both loads handled all 1,620 requests; if LM Studio refuses a request as too long, raise the batch size in the model's load settings.
- **No on-demand loading:** `run.py` refuses a model that is not loaded, so the settings you loaded with are the settings used.
- **Memory:** both models together take about 23 GB loaded. The runs were made on an Apple Silicon Mac. Unload afterwards with `lms unload <model-key>`.

## Run it

Standard library only; tested with Python 3.12. Set up LM Studio first (above); `run.py` stops if the model is not loaded.

```bash
python3 run.py --list                                           # models in LM Studio, writes results/models.json
python3 run.py --model pplx-decider-27b-artemis --determinism   # repeat a sample serially and four at once
python3 run.py --model pplx-decider-27b-artemis                 # all 4,263 requests, about 55 minutes; answered ones are skipped
python3 analyze.py                                              # results/summary.md and results/figures.json
```

With llama.cpp's `llama-server` instead of LM Studio, one server per model:

```bash
docker run -d --gpus device=0 -v ~/models:/models:ro -p 127.0.0.1:8081:8080 ghcr.io/ggml-org/llama.cpp:server-cuda \
  -m /models/Kev-4B-Q4_K_M.gguf --alias kev-4b -ngl 999 -c 8192 -np 4 -b 2048 -ub 2048 --host 0.0.0.0 --port 8080
python3 run.py --model kev-4b --url http://localhost:8081 --llama-server
```

- `--llama-server` checks through `/v1/models` that the server runs that alias as a decision model. For a decision model that also generates text (granite-switch), start the server with `-np 1 --slot-save-path /tmp` and add `--erase-slot`, or its answers depend on the request before (see [numerical stability](#numerical-stability-granite-switch-and-quantization)).

- Decision models answer typed questions (`choice`, `score`, `noul`) through `POST /v1/systemone`, not through chat completions.
- `--sample N` sends about N evenly spread requests (a pilot); `--studies 1,2ab,2c,2d,bbq,ss` selects studies.
- `analyze.py` reports a study only when it is complete, and lists the studies a model has not run yet; a partly answered study stops it.
- Runs are serial by default because they reproduce exactly. Four requests at once drift by up to 0.004 in probability for pplx.
- A run resumes where it stopped: answered requests are skipped. The first failed or malformed answer stops the run; nothing is retried or skipped silently.

## BBQ and StereoSet

Two published bias benchmarks, restricted to gender, extend the replication. They ran on CUDA for all five models there ([below](#five-decision-models-on-cuda)); the Mac runs of pplx and clef-flash cover the paper's studies only. On the Mac they would add 2,643 requests per model, about 32 minutes for pplx (median 716 ms) and 12 for clef-flash (301 ms).

| Study | Source | Requests | What is measured |
| --- | --- | --- | --- |
| `bbq` | [BBQ](https://github.com/nyu-mll/BBQ) (Parrish et al. 2022), `Gender_identity`: all 50 templates, up to 8 fillings each, every filling with an ambiguous and a disambiguated context and a negative and a non-negative question | 1,152 | Accuracy per context, and the paper's bias scores s_DIS and s_AMB (-1 = always against the stereotype, +1 = always with it), per stereotyped group (women, men, trans people); disambiguated accuracy when the right answer fits the stereotype minus when it does not |
| `ss` | [StereoSet](https://github.com/moinnadeem/StereoSet) (Nadeem et al. 2021), the 497 gender items of the dev set (the test set is unpublished): 255 intrasentence, 242 intersentence | 1,491 | The paper's ss (50 = no preference), lms and icat, per female and male target; how far the option order moves the answer |

- BBQ: the context is the state, the question is asked verbatim, and the three answers are the options in the dataset's order, which already varies where the stereotyped answer stands. The stereotyped answer comes from BBQ's `additional_metadata.csv`; 12 questions name two people of the same group and count for accuracy only. Intervals resample templates, because fillings of one template share their wording. Inspect Evals scores BBQ by accuracy alone; the bias scores follow the paper.
- StereoSet: each item is asked in three option orders, in the instructions of Inspect Evals. The paper compares the likelihoods of the stereotypical and the anti-stereotypical sentence; here ss compares the decision model's probabilities for the two, averaged over the orders. "Modal ss" counts the most probable answers, as Inspect Evals does.

## Five decision models on CUDA

All 4,263 requests (the paper's studies, BBQ and StereoSet) also ran on a Linux machine with two RTX 3090s through llama.cpp's `llama-server` (build 11870, image `ghcr.io/ggml-org/llama.cpp:server-cuda`, digest in `results/servers-z390.json`), one server per model pinned to one GPU, requests serial. Three models are new: [Kev 4B](https://huggingface.co/jaredpalmer/kev-4b) (a decision head on Qwen3.5-4B-Base), Liquid AI's [d1 3B](https://huggingface.co/LiquidAI/d1-3B) (on LFM2.5-VL-3B) and IBM's [granite-switch-4.1 8B](https://huggingface.co/ibm-granite/granite-switch-4.1-8b), which reads its decision from the logprobs of the option labels and also generates text; all three in Q4_K_M. pplx and clef-flash ran again from the same files as on the Mac (identical sha256). Each server repeated its answers exactly (`study: "V"` lines); files and server arguments are in `results/servers-z390.json`.

| | pplx (CUDA) | clef-flash (CUDA) | granite-switch 8B | Kev 4B | d1 3B |
| --- | --- | --- | --- | --- | --- |
| Study 1: I_m − I_f (GPT-4: +0.27) | +0.101 | +0.074 | +0.153 | −0.116 | +0.145 |
| Study 1: controls answered right (modal) | 0.87 | 1.00 | 0.97 | 0.80 | 0.55 |
| Study 2: harass gap, man − woman (GPT-4: +2.34) | +2.62 | +1.27 | +1.37 | +0.90 | +0.75 |
| Study 2d: Amanda to Adam − Andrew to Anna (GPT-4: +4.65) | +0.28 | +0.37 | +0.59 | +0.41 | −0.15 |
| BBQ: accuracy ambiguous / disambiguated | 0.93 / 1.00 | 0.69 / 0.98 | 0.33 / 0.99 | 0.85 / 0.96 | 0.81 / 0.90 |
| BBQ: s_AMB [95% CI] (+1 = always the stereotype) | +0.057 [+0.02, +0.11] | +0.143 [+0.07, +0.23] | +0.335 [+0.24, +0.44] | +0.010 [−0.03, +0.06] | +0.087 [+0.03, +0.15] |
| BBQ: s_DIS | −0.004 | −0.011 | −0.005 | +0.031 | +0.008 |
| StereoSet: ss [95% CI] (50 = no preference) | 76.5 [72.6, 80.1] | 75.9 [72.0, 79.5] | 76.7 [73.0, 80.3] | 75.5 [71.6, 79.1] | 64.2 [60.2, 68.2] |
| StereoSet: lms / icat | 97.3 / 45.8 | 96.0 / 46.3 | 95.4 / 44.5 | 95.2 / 46.7 | 90.5 / 64.9 |
| Check: option order changes the modal StereoSet answer | 26.8% | 0.0% | 12.1% | 26.0% | 13.3% |
| Check: scale 7-1 instead of 1-7 moves E[rating] by | 0.12 | 0.15 | 0.47 | 0.14 | 1.60 |

- **StereoSet:** every model prefers the stereotypical completion, four of them in three of four items; d1 least (64). The unrelated option rarely wins (lms 90 to 97).
- **BBQ:** when the context names the person, all models are right in 90 to 100% and their errors show no stereotype (s_DIS between −0.011 and +0.031). When it does not, they differ: pplx answers "unknown" in 93% of the questions, granite in 33%, and when granite names a person it mostly names the stereotyped one (s_AMB +0.335). pplx uses the stereotype in ambiguous contexts mainly about trans people (s_AMB +0.21 [+0.05, +0.43], against +0.03 for women and +0.01 for men; 224 of the 1,152 questions are about trans people).
- **Study 1:** Kev reverses the paper's asymmetry (I_m − I_f = −0.116): it attributes feminine phrases to boys more readily than masculine phrases to girls. d1 gets 55% of the controls right and reads rating scales by position (reversing the scale moves its E[rating] by 1.60 points), so its Study 1 and 2 numbers say little.
- **Same file, other platform:** pplx and clef-flash on CUDA against the Mac (Metal, LM Studio), over the 1,620 shared requests: the largest probability difference per request has median 0.006 and 99th percentile 0.05 (pplx) and 0.06 (clef-flash); the modal answer differs in 1.3% and 1.4%. Headline numbers move in the second decimal (harass gap 2.70 to 2.62 for pplx, 1.18 to 1.27 for clef-flash). Both report the same number of input tokens for every request, which points to the same prompt.

## Numerical stability: granite-switch and quantization

- **Answers depended on the previous request.** For a decision model that also generates text, `llama-server` reuses the KV cache of the previous prompt and computes only the rest; decision tasks ignore `--no-cache-prompt` and the request's `cache_prompt` ([`server-context.cpp`](https://github.com/ggml-org/llama.cpp/blob/74bca3950/tools/server/server-context.cpp)). Reuse is exact in theory, but a different split into batches takes a different floating-point path, so the answer to a request depends on the one before: with the default settings a serial repeat moved by up to 0.017 and four requests at once by 0.114, and with `--no-cache-prompt` a repeat still changed the modal answer (`results/checks/granite-default-settings/`). `run.py --erase-slot` empties the slot before every request; granite then repeats itself exactly. Its check of four requests at once then reads `inf`, because the erase calls of parallel requests interleave; the runs themselves are serial. The other four models do not reuse state.
- **Precision x path experiment.** The same 122 requests went through granite and Kev in bf16, Q8_0 and Q4_K_M: on the GPU with batches of 2048 and 128 tokens for both models and of 64 and 1 token for granite (Kev needs a question and its options in one batch); on the CPU in bf16 and Q4_K_M, with 41 of the 122 requests except for Kev in Q4_K_M. Data in `results/checks/paths/`. Largest probability difference per request, median / max, and the share of requests whose modal answer differs:

| Comparison | granite-switch (label logprobs) | Kev (decision head) |
| --- | --- | --- |
| GPU against CPU, bf16 | 0.0004 / 0.013, 0% | 0.0008 / 0.008, 2.4% (one near-tie) |
| GPU against CPU, Q4_K_M | 0.0056 / 0.226, 7.3% | 0.0069 / 0.080, 1.6% |
| batch 2048 against 128, bf16 / Q4_K_M | max 0.024 / 0.096 | max 0.004 / 0.024 |
| batch 2048 against 1 token, bf16 / Q8_0 / Q4_K_M | max 0.014 / 0.119 / 0.216 | not possible: a question and its options must fit in one batch |
| bf16 against Q8_0, same path | 0.0027 / 0.077, 0.8% | 0.0045 / 0.027, 2.5% |
| bf16 against Q4_K_M, same path | 0.017 / 0.385, 8.2% | 0.022 / 0.099, 4.9% |

Reading a decision from label logprobs is not unstable in itself: in bf16, granite moves by at most 0.024 across hardware and batch sizes (Kev by at most 0.008), against up to 0.23 in Q4_K_M. Quantization makes the numeric path matter, and granite turns the errors of Q4 into larger outliers than Kev does: the typical shift against bf16 is about the same (median 0.02), the largest four times as large. Over all 4,263 requests, granite in Q4 with batches of 2048 against 1 token differs by median 0.004 and 99th percentile 0.09, the modal answer in 1.2%; the headline numbers move in the second or third decimal (s_AMB +0.335 against +0.342, StereoSet ss 76.7 in both). One model per readout and one family of quantizations (K-quants), so this separates the two causes for these models, not for every decision model.

## Method notes

- A decision model returns probabilities from one forward pass and generates no text, so the same request always gives the same answer. The paper's repeated chats are therefore replaced by prompt variants: wording, option order and scale direction (18 to 20 variants per item). Intervals and p-values show robustness across variants, not sampling error.
- Every answer is read two ways: the mean under the model's own probabilities (what the paper's mean over sampled answers estimates) and the most probable (modal) answer.
- Gaps are signed so that a positive number means the woman is protected more.
- The paper does not label its three control pairs; we took pairs 8, 10 and 17, which state the gender outright.

## Limits

- Two models on the Mac and five on CUDA, one quantization each (Q4); granite-switch also in bf16 and Q8_0 for the stability check. BBQ and StereoSet ran on CUDA only.
- GPT-4's numbers are sampled chat answers from the paper (arXiv version); ours are probabilities from another interface, so model and interface are not separated. A chat model run through the same prompts would separate them.
- No human baseline, and the phrases are not matched on cue strength. "Abuse" and "torture" differ in meaning as well as severity.

## License

[MIT](LICENSE). The 40 phrases, the dilemmas and the vignette in `stimuli.py` are reproduced from Fulgu & Capraro (2024) for replication and remain under the paper's terms; the neutral phrases and prompt variants are ours. BBQ (CC BY 4.0) and StereoSet (CC BY-SA 4.0) are not in the repository; `stimuli.py` downloads them, and the `bbq` and `ss` lines in `results/*.jsonl` quote their items under those licenses.
