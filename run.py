"""Run the stimuli in stimuli.py against one LM Studio decision model; every answer is appended to results/<model>.jsonl.

A decision model answers through POST /v1/systemone, not through /v1/chat/completions: one forward pass
returns probabilities and no tokens. Identical requests give identical answers, so the paper's repeated chats
are replaced by the prompt variants in stimuli.py.

    python3 run.py --list
    python3 run.py --model pplx-decider-27b-artemis --determinism
    python3 run.py --model pplx-decider-27b-artemis --sample 60      # pilot: an even spread over all requests
    python3 run.py --model pplx-decider-27b-artemis --workers 4      # resumes: requests already in the file are skipped
"""
import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import stimuli

URL = "http://localhost:1234"
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
        raise ServerError(f"run.py: cannot reach {URL}{path} ({e.reason}); is the LM Studio server running?") from None


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


def ask(model, req):
    started = time.perf_counter()
    res = call("/v1/systemone", {"model": model, "state": req["state"], "questions": req["questions"]})
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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list the models of the LM Studio server and write results/models.json")
    ap.add_argument("--model")
    ap.add_argument("--studies", default="1,2ab,2c,2d")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--sample", type=int, help="send only about this many requests, evenly spread")
    ap.add_argument("--determinism", action="store_true", help="repeat a sample of requests, serially and in parallel, and record the largest difference")
    args = ap.parse_args()

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
