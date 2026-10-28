"""Serving-path check: a sample of requests through Kev's own reference server (github.com/jaredpalmer/kev at 2074cc4,
kev.serve, PyTorch bf16) against the answers llama.cpp's llama-server gave for the same requests (results/kev-4b-bf16.jsonl).

    uv run --extra serve python -m kev.serve --run jaredpalmer/kev-4b@6cfce5c2fa4b4bd64026336ab649c5ca78857d52 --port 8008   # in the kev repository
    python3 results/checks/kev_check.py http://127.0.0.1:8008   # writes results/checks/kev-reference.jsonl; the printout is kev-reference.txt

6cfce5c2 is the revision ggml-org/Kev-4B-GGUF was converted from (its .src_sha), so both servers read the same weights.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import analyze  # noqa: E402
import run  # noqa: E402
import stimuli  # noqa: E402

run.URL = sys.argv[1]
# kev.serve lists models as TypeSafe does ({"models": [{"name": ...}]}), with its serving details; kept next to the answers
models = run.call("/v1/models")
served = [m["name"] for m in models["models"]]
Path("results/checks").mkdir(parents=True, exist_ok=True)
Path("results/checks/kev-reference-models.json").write_text(json.dumps(models, indent=1))
reqs = stimuli.requests(list(stimuli.STUDIES))
sample = reqs[:: len(reqs) // 150]  # an even spread over all studies, as run.py --sample does
ours = {}
for line in open("results/kev-4b-bf16.jsonl"):
    r = json.loads(line)
    if r["study"] != "V":
        ours[r["key"]] = r
out = Path("results/checks/kev-reference.jsonl")
out.parent.mkdir(parents=True, exist_ok=True)
rows = []
with out.open("w") as f:
    for req in sample:
        res, ms = run.ask(served[0], req)
        row = {"key": run.key("kev-4b-reference", req), "model": "kev-4b-reference", "served_as": served[0], **req, "answers": res["answers"], "ms": ms}
        f.write(json.dumps(row) + "\n")
        mine = ours[run.key("kev-4b-bf16", req)]
        p, q = analyze.answer_dist(row), analyze.answer_dist(mine)
        rows.append({"study": req["study"], "max_abs": max(abs(p[k] - q[k]) for k in p), "same_top": max(p, key=p.get) == max(q, key=q.get), "kl": analyze.kl(p, q)})
by = {}
for r in rows:
    by.setdefault(r["study"], []).append(r)
print(f"{len(rows)} requests; served model {served[0]}")
for study, rs in sorted(by.items()) + [("all", rows)]:
    print(f"{study:>5}: n {len(rs):3d}  max |diff| {max(r['max_abs'] for r in rs):.4f}  mean |diff| {analyze.mean([r['max_abs'] for r in rs]):.4f}  "
          f"same top answer {sum(r['same_top'] for r in rs)}/{len(rs)}  mean KL(reference || llama.cpp) {analyze.mean([r['kl'] for r in rs]):.4f}")
