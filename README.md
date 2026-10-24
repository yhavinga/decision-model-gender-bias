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
| `stimuli.py` | The paper's 20 phrase pairs (Table 1) and Neo Metropolis vignette, plus our prompt variants, neutral phrases and controls. Asserts on import that our copy of Table 1 reproduces the paper's six published inclusivity indices. |
| `run.py` | Sends the stimuli to one loaded LM Studio model and appends every answer to `results/<model>.jsonl`. |
| `analyze.py` | Computes the paper's measures and the reliability checks; writes `results/summary.md` and `results/figures.json`. |
| `results/*.jsonl` | Raw answers, one line per request (1,620 per model). `study: "V"` lines hold the determinism and latency checks. |
| `results/summary.md` | All tables, per model, next to the paper's GPT numbers. |
| `results/models.json` | The models LM Studio listed when the runs were made. |
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
python3 run.py --model pplx-decider-27b-artemis                 # all 1,620 requests, about 20 minutes
python3 analyze.py                                              # results/summary.md and results/figures.json
```

- Decision models answer typed questions (`choice`, `score`, `noul`) through `POST /v1/systemone`, not through chat completions.
- `--sample N` sends about N evenly spread requests (a pilot); `--studies 1,2ab,2c,2d` selects studies.
- Runs are serial by default because they reproduce exactly. Four requests at once drift by up to 0.004 in probability for pplx.
- A run resumes where it stopped: answered requests are skipped. The first failed or malformed answer stops the run; nothing is retried or skipped silently.

## Method notes

- A decision model returns probabilities from one forward pass and generates no text, so the same request always gives the same answer. The paper's repeated chats are therefore replaced by prompt variants: wording, option order and scale direction (18 to 20 variants per item). Intervals and p-values show robustness across variants, not sampling error.
- Every answer is read two ways: the mean under the model's own probabilities (what the paper's mean over sampled answers estimates) and the most probable (modal) answer.
- Gaps are signed so that a positive number means the woman is protected more.
- The paper does not label its three control pairs; we took pairs 8, 10 and 17, which state the gender outright.

## Limits

- Two models, one quantization each.
- GPT-4's numbers are sampled chat answers from the paper (arXiv version); ours are probabilities from another interface, so model and interface are not separated. A chat model run through the same prompts would separate them.
- No human baseline, and the phrases are not matched on cue strength. "Abuse" and "torture" differ in meaning as well as severity.

## License

[MIT](LICENSE). The 40 phrases, the dilemmas and the vignette in `stimuli.py` are reproduced from Fulgu & Capraro (2024) for replication and remain under the paper's terms; the neutral phrases and prompt variants are ours.
