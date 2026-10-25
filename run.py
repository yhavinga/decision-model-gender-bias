"""Run the stimuli in stimuli.py against one LM Studio decision model; every answer is appended to results/<model>.jsonl.

A decision model answers through POST /v1/systemone, not through /v1/chat/completions: one forward pass
returns probabilities and no tokens. Identical requests give identical answers, so the paper's repeated chats
are replaced by the prompt variants in stimuli.py.

    python3 run.py --list
    python3 run.py --model pplx-decider-27b-artemis --determinism
    python3 run.py --model pplx-decider-27b-artemis --sample 60      # pilot: an even spread over all requests
    python3 run.py --model pplx-decider-27b-artemis --workers 4      # resumes: requests already in the file are skipped
    python3 run.py --model kev-4b --url http://localhost:8081 --llama-server   # llama.cpp's llama-server, started with --alias kev-4b
    python3 run.py --model qwen3.8-27b-logprobs --url http://localhost:8082 --llama-server --readout logprobs   # a chat model, same questions
    python3 run.py --model qwen3.8-27b-generate --url http://localhost:8082 --llama-server --readout generate   # sampled answers, as in the paper

A chat or base model has no /v1/systemone, so --readout logprobs asks each typed question as text with lettered options
and reads the probabilities of the option letters (or yes/no) as the first answer token; --readout generate samples
answers and counts them. Both write answers in systemone's format, so analyze.py reads every readout alike.
"""
import argparse
import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import stimuli

URL = "http://localhost:1234"
ERASE_SLOT = False
READOUT, RAW, SAMPLES = "systemone", False, 5
LETTERS = "ABCDEFGHIJ"
RESULTS = Path(__file__).parent / "results"


class ServerError(RuntimeError):
    pass


def call(path, body=None, timeout=120):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(URL + path, data, {"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as res:
            return json.load(res)
    except urllib.error.HTTPError as e:
        raise ServerError(f"run.py: {path} answered HTTP {e.code}: {e.read().decode(errors='replace')[:500]}") from None
    except urllib.error.URLError as e:
        raise ServerError(f"run.py: cannot reach {URL}{path} ({e.reason}); is the server running?") from None


def validate(questions, answers):
    if not isinstance(answers, dict):
        raise ValueError(f"run.py: the response has no answers: {answers!r}")
    for name, q in questions.items():
        a = answers.get(name)
        ok = isinstance(a, dict) and a.get("type") == q["type"]
        if ok and q["type"] == "noul":
            ok = isinstance(a.get("noul"), float) and 0 <= a["noul"] <= 1
        elif ok and q["type"] == "choice":
            ok = a.get("choice") in q["criteria"] and set(a.get("probabilities", {})) == set(q["criteria"])
        elif ok and q["type"] == "score":
            ok = set(a.get("probabilities", {})) == {str(i) for i in range(len(q["criteria"]))}
        if not ok:
            raise ValueError(f"run.py: malformed answer to {name} ({q['type']}): {json.dumps(a)[:300]}")


def as_text(req):
    """One typed question as a prompt for a chat or base model; returns its name, the question, the prompt, the option
    keys in systemone's format and the marks (letters, or yes/no) that stand for them."""
    (name, q), = req["questions"].items()
    if q["type"] == "noul":
        return name, q, f"{req['state']}\n\n{q['instructions']}\n\nAnswer with yes or no only.", ["yes", "no"], ["yes", "no"]
    keys = list(q["criteria"]) if q["type"] == "choice" else [str(i) for i in range(len(q["criteria"]))]
    texts = list(q["criteria"].values()) if q["type"] == "choice" else q["criteria"]
    lines = "\n".join(f"{LETTERS[i]}. {t}" for i, t in enumerate(texts))
    return name, q, f"{req['state']}\n\n{q['instructions']}\n\n{lines}\n\nAnswer with the letter of one option only.", keys, list(LETTERS[:len(keys)])


def chat(model, text, **params):
    # thinking off: the first token must be the answer; no prompt cache, so no answer depends on the request before
    return call("/v1/chat/completions", {"model": model, "messages": [{"role": "user", "content": text}], "cache_prompt": False,
                                         "chat_template_kwargs": {"enable_thinking": False}, **params})


def ask_text(model, req):
    name, q, text, keys, marks = as_text(req)
    norm = (lambda t: t.strip().strip(".:)*").lower()) if q["type"] == "noul" else (lambda t: t.strip().strip(".:)*("))
    if READOUT == "logprobs":
        if RAW:
            res = call("/completion", {"prompt": f"{text}\nAnswer:", "n_predict": 1, "n_probs": 20, "temperature": 0, "cache_prompt": False})
            top, used = res["completion_probabilities"][0]["top_logprobs"], res["tokens_evaluated"]
        else:
            res = chat(model, text, max_tokens=1, temperature=0, logprobs=True, top_logprobs=20)
            top, used = res["choices"][0]["logprobs"]["content"][0]["top_logprobs"], res["usage"]["prompt_tokens"]
        mass = dict.fromkeys(marks, 0.0)
        for t in top:
            if norm(t["token"]) in mass:
                mass[norm(t["token"])] += math.exp(t["logprob"])
        total = sum(mass.values())
        if total == 0:
            raise ValueError(f"run.py: none of {marks} among the 20 most probable first tokens {[t['token'] for t in top]}")
        probs, extra, out_tokens = {k: mass[m] / total for k, m in zip(keys, marks)}, {"mass": total}, 1
    else:
        counts, invalid = dict.fromkeys(marks, 0), []
        pattern = r"\b(yes|no)\b" if q["type"] == "noul" else rf"\b([{LETTERS[:len(marks)]}])\b"
        for seed in range(SAMPLES):
            res = chat(model, text, max_tokens=8, temperature=1.0, seed=seed)
            out = res["choices"][0]["message"]["content"]
            hit = re.search(pattern, out.lower() if q["type"] == "noul" else out)
            if hit:
                counts[hit.group(1)] += 1
            else:
                invalid.append(out[:40])
        if not sum(counts.values()):
            raise ValueError(f"run.py: no usable answer in {SAMPLES} samples: {invalid}")
        probs = {k: counts[m] / sum(counts.values()) for k, m in zip(keys, marks)}
        extra, used, out_tokens = {"samples": SAMPLES, "invalid": invalid}, res["usage"]["prompt_tokens"], SAMPLES
    answer = {"type": "noul", "noul": probs["yes"]} if q["type"] == "noul" else {"type": q["type"], "probabilities": probs}
    if q["type"] == "choice":
        answer["choice"] = max(probs, key=probs.get)
    return {"answers": {name: {**answer, **extra}}, "usage": {"input_tokens": used, "output_tokens": out_tokens}}


def ask(model, req):
    if ERASE_SLOT:
        # llama-server reuses the KV cache of the previous prompt for decision models that also generate text
        # (granite-switch), whatever --no-cache-prompt says; an empty slot makes every answer independent of the one before
        call("/slots/0?action=erase", {})
    started = time.perf_counter()
    if READOUT == "systemone":
        res = call("/v1/systemone", {"model": model, "state": req["state"], "questions": req["questions"]})
    else:
        res = ask_text(model, req)
    ms = round((time.perf_counter() - started) * 1000)
    try:
        validate(req["questions"], res.get("answers"))
    except ValueError as e:
        raise ValueError(f"{e}\n  state: {req['state'][:120]!r}\n  study {req['study']}/{req['part']} item {req['item']} variant {req['variant']}") from None
    return res, ms


def key(model, req):
    # no sort_keys: the order of the options is part of the stimulus
    return hashlib.sha1(json.dumps([model, req["state"], req["questions"]]).encode()).hexdigest()[:16]


def list_models():
    models = call("/api/v0/models")["data"]
    for m in models:
        print(f"{m['id']:<75} {m.get('type'):<10} {m.get('state'):<11} {m.get('arch'):<9} {m.get('quantization')}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "models.json").write_text(json.dumps(models, indent=1))
    return models


def diff(a, b):
    """Largest absolute difference between the numbers of two answers; infinite if their shapes or labels differ."""
    if isinstance(a, dict):
        return max(diff(a[k], b[k]) for k in a) if a.keys() == b.keys() else float("inf")
    if isinstance(a, (int, float)):
        return abs(a - b)
    return 0.0 if a == b else float("inf")


def determinism(model, reqs, out):
    """Does the same request give the same answer, also when the server runs four at once?"""
    sample = reqs[:: max(1, len(reqs) // 12)][:12]
    base, serial_ms = [], []
    for r in sample:
        res, ms = ask(model, r)
        base.append(res["answers"])
        serial_ms.append(ms)
    repeats = []
    for r in sample:
        for _ in range(2):
            res, ms = ask(model, r)
            repeats.append((len(repeats) // 2, res["answers"]))
            serial_ms.append(ms)
    with ThreadPoolExecutor(4) as pool:
        parallel = list(pool.map(lambda r: ask(model, r)[0]["answers"], sample * 4))
    row = {"model": model, "study": "V", "part": "determinism", "requests": len(sample),
           "serial_max_abs_diff": max(diff(base[i], a) for i, a in repeats),
           "parallel_max_abs_diff": max(diff(base[i % len(sample)], a) for i, a in enumerate(parallel)),
           "serial_ms": serial_ms}
    with out.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"determinism over {len(sample)} requests: serial repeat max |diff| {row['serial_max_abs_diff']}, "
          f"4 at once {row['parallel_max_abs_diff']}; serial latency median {sorted(serial_ms)[len(serial_ms) // 2]} ms")


def main():
    global URL, ERASE_SLOT, READOUT, RAW, SAMPLES
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list the models of the LM Studio server and write results/models.json")
    ap.add_argument("--model")
    ap.add_argument("--url", default=URL, help=f"server address (default {URL}, LM Studio)")
    ap.add_argument("--llama-server", action="store_true", help="the server is llama.cpp's llama-server: check the model through /v1/models instead of LM Studio's /api/v0/models")
    ap.add_argument("--erase-slot", action="store_true", help="llama-server: erase slot 0 before every request (start the server with -np 1 --slot-save-path DIR)")
    ap.add_argument("--readout", choices=["systemone", "logprobs", "generate"], default="systemone", help="how the answer is read; logprobs and generate are for chat or base models (see above)")
    ap.add_argument("--raw", action="store_true", help="--readout logprobs on a base model: a plain prompt to /completion instead of the chat template")
    ap.add_argument("--samples", type=int, default=SAMPLES, help="--readout generate: sampled answers per request")
    ap.add_argument("--studies", default=",".join(stimuli.STUDIES))
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--sample", type=int, help="send only about this many requests, evenly spread")
    ap.add_argument("--determinism", action="store_true", help="repeat a sample of requests, serially and in parallel, and record the largest difference")
    args = ap.parse_args()
    URL, ERASE_SLOT, READOUT, RAW, SAMPLES = args.url, args.erase_slot, args.readout, args.raw, args.samples

    if args.llama_server:
        # llama-server serves one model under its --alias; the GGUF metadata says whether it is a decision model
        m = call("/v1/models")["data"][0]
        outputs, need = m["architecture"]["output_modalities"], "decisions" if READOUT == "systemone" else "text"
        if m["id"] != args.model or need not in outputs:
            sys.exit(f"run.py: {URL} serves {m['id']} with outputs {outputs}, not {args.model} with {need} output")
    else:
        models = list_models() if args.list else call("/api/v0/models")["data"]
        if args.list:
            return
        state = {m["id"]: m.get("state") for m in models}
        if state.get(args.model) != "loaded":
            sys.exit(f"run.py: {args.model} is {state.get(args.model, 'unknown')}, not loaded; load it first (lms load {args.model}) so it keeps its own settings")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{args.model.replace('/', '_')}.jsonl"
    reqs = stimuli.requests(args.studies.split(","))
    if args.determinism:
        return determinism(args.model, reqs, out)
    if args.sample:
        reqs = reqs[:: max(1, len(reqs) // args.sample)]
    done = {json.loads(line).get("key") for line in out.open()} if out.exists() else set()
    todo = [r for r in reqs if key(args.model, r) not in done]
    print(f"{args.model}: {len(reqs)} requests, {len(reqs) - len(todo)} already answered, {len(todo)} to go", file=sys.stderr)

    started = time.perf_counter()
    with out.open("a") as f, ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(ask, args.model, r): r for r in todo}
        try:
            for n, fut in enumerate(as_completed(futures), 1):
                r = futures[fut]
                res, ms = fut.result()
                f.write(json.dumps({"key": key(args.model, r), "model": args.model, **r, "answers": res["answers"], "usage": res["usage"], "ms": ms}) + "\n")
                f.flush()
                if n % 100 == 0 or n == len(todo):
                    print(f"  {n}/{len(todo)} in {time.perf_counter() - started:.0f} s", file=sys.stderr)
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)  # the first failure stops the run; what was answered stays in the file
            raise


if __name__ == "__main__":
    main()
