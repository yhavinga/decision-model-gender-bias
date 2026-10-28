"""Mixed-effects models of the main runs, next to analyze.py's paired tests: results/mixed.json and results/mixed.md.

    python3 mixed.py      # needs numpy, pandas, statsmodels; analyze.py itself stays standard-library only

Study 2 (the apocalypse of Study 2a/2b and the four stakes of Study 2e): the victim effect, acceptability against the man
minus against the woman in the same act, stake and wording (and scale direction), ~ act, with crossed random intercepts
for the wording and the stake. On the paired difference these intercepts are the random victim slopes of a model of
the raw answers, whose nuisance intercepts the pairing removes. Fitted once for E[rating] on the 1-7 scale and once
for logit P(yes); positive = more acceptable against the man, analyze.py's sign.

Decision task (Tamkin et al. 2023; the main runs except AutoTrust's JEV): logit P(yes) ~ gender + race + age, with a random intercept and random gender
slopes per decision; the reference person is a 60-year-old white man, age in decades. A positive gender effect favours
the woman or the non-binary person: yes is the favourable answer.
"""
import json
import sys
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

import analyze

ACTS = ("insult", "harass", "abuse", "torture")
RACES = ("Black", "Hispanic", "Asian", "Native American")  # against white


def load(model):
    rows = {}
    for line in (analyze.RESULTS / f"{model}.jsonl").open():
        r = json.loads(line)
        if r["study"] != "V":
            rows[r["key"]] = r
    return list(rows.values())


def study2_frames(rows):
    """The paired man - woman differences of Study 2, one frame for the ratings and one for yes/no."""
    rating, yes = [], []
    for r in rows:
        it = r["item"]
        if r["study"] not in ("2ab", "2e") or it["stake"] is False or it["act"] not in ACTS:  # no stake: nothing to vary
            continue
        # 2a/2b and 2e word their questions differently, so a wording is the study's frame
        cell = {"act": it["act"], "man": float(it["victim"] == "man"), "stake": "apocalypse" if it["stake"] is True else it["stake"],
                "wording": f"{r['study']}-{r['variant']['frame']}"}
        if r["part"] == "rating":
            rating.append({**cell, "dir": r["variant"]["dir"], "y": analyze.rating_stats(r["questions"]["rating"], r["answers"]["rating"])["E"]})
        else:
            yes.append({**cell, "y": analyze.logit(r["answers"]["ok"]["noul"], analyze.DE_EPS)})
    frames = []
    for cells, keys in ((rating, ["act", "stake", "wording", "dir"]), (yes, ["act", "stake", "wording"])):
        df = pd.DataFrame(cells).set_index(keys)
        frames.append((df[df.man == 1]["y"] - df[df.man == 0]["y"]).dropna().rename("y").reset_index())
    return frames


def de_frame(rows):
    return pd.DataFrame([{"question": r["item"]["id"], "female": float(r["item"]["gender"] == "female"), "nonbinary": float(r["item"]["gender"] == "non-binary"),
                          "race": r["item"]["race"], "age10": (r["item"]["age"] - 60) / 10, "y": analyze.logit(r["answers"]["yes"]["noul"], analyze.DE_EPS)}
                         for r in rows if r["study"] == "de"])


def fit(formula, df, **kw):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res = smf.mixedlm(formula, df, **kw).fit(reml=True, method="powell")  # L-BFGS stalls on some crossed fits; Powell converges on all
    notes = sorted({str(w.message).split("\n")[0] for w in caught})
    for note in notes:
        print(f"mixed.py: {formula}: {note}", file=sys.stderr)
    return res, notes


def coef(res, name):
    lo, hi = res.conf_int().loc[name]
    return {"est": res.fe_params[name], "ci": [lo, hi], "p": res.pvalues[name]}


def study2(df):
    df = df.assign(g=1)  # one group: the wordings and the stakes are crossed variance components
    res, notes = fit("y ~ 0 + C(act)", df, groups="g", re_formula="0", vc_formula={"wording": "0 + C(wording)", "stake": "0 + C(stake)"})
    return {"n": len(df), "converged": bool(res.converged), "warnings": notes,
            "victim": {act: coef(res, f"C(act)[{act}]") for act in ACTS},
            "variances": dict(zip(res.model.exog_vc.names, res.vcomp.tolist())), "residual": res.scale}


def decision_task(df):
    res, notes = fit("y ~ female + nonbinary + C(race, Treatment('white')) + age10", df, groups="question", re_formula="~ female + nonbinary")
    return {"n": len(df), "decisions": int(df["question"].nunique()), "converged": bool(res.converged), "warnings": notes,
            "female": coef(res, "female"), "non-binary": coef(res, "nonbinary"), "age10": coef(res, "age10"),
            "race": {race: coef(res, f"C(race, Treatment('white'))[T.{race}]") for race in RACES},
            "re_cov": res.cov_re.values.tolist(), "residual": res.scale}


BOUNDARY = "The MLE may be on the boundary of the parameter space."


def notes(o):
    """What the table says about a fit: a variance estimated at 0 is a result, anything else a problem to read in mixed.json."""
    if not o["converged"]:
        return "NOT CONVERGED"
    return "; ".join("a variance at 0" if w == BOUNDARY else w for w in o["warnings"])


def cell(c, d=2):
    return f"{c['est']:+.{d}f} [{c['ci'][0]:+.{d}f}, {c['ci'][1]:+.{d}f}]"


def report(out):
    lines = ["# Mixed-effects models of the main runs", "", "Written by mixed.py; see its docstring for the models. Estimates with 95% Wald intervals.", ""]
    for key, title in (("rating", "Study 2: victim effect on E[rating] (man - woman, 1-7 scale), stakes and wordings as random effects"),
                       ("yes", "Study 2: victim effect on logit P(yes) (man - woman)")):
        body = [[m, *(cell(o[key]["victim"][a]) for a in ACTS), notes(o[key])]
                for m, o in out.items() if key in o]
        lines += [f"## {title}", "", analyze.table(["run", *ACTS, "fit notes"], body), ""]
    body = [[m, cell(o["de"]["female"], 3), cell(o["de"]["non-binary"], 3), f"{min(c['est'] for c in o['de']['race'].values()):+.3f} to {max(c['est'] for c in o['de']['race'].values()):+.3f}",
             cell(o["de"]["age10"], 3), notes(o["de"])]
            for m, o in out.items() if "de" in o]
    lines += ["## Decision task: effects on logit P(yes) against a 60-year-old white man", "",
              analyze.table(["run", "female", "non-binary", "race (four effects, lowest to highest)", "age per decade", "fit notes"], body), ""]
    missing = [m for m in analyze.MAIN if m not in out] + [m for m in analyze.DE_RUNS if m in out and "de" not in out[m]]
    if missing:
        lines += [f"Not fitted yet, no complete run (decision task or all studies): {', '.join(m + ('' if m in out else ' (no file)') for m in missing)}.", ""]
    return "\n".join(lines)


def main():
    out = {}
    for model in analyze.MAIN:
        if not (analyze.RESULTS / f"{model}.jsonl").exists():
            continue
        rows = load(model)
        by = {s: sum(r["study"] == s for r in rows) for s in ("2ab", "2e", "de")}
        # same rule as analyze.py: a study is complete or left out, never fitted on part of its requests
        short = {s: (n, len(analyze.stimuli.requests([s]))) for s, n in by.items() if n and n != len(analyze.stimuli.requests([s]))}
        if short:
            sys.exit(f"mixed.py: {model} is incomplete, (answered, expected) per study: {short}")
        o = out[model] = {}
        if by["2ab"] and by["2e"]:
            rating, yes = study2_frames(rows)
            o["rating"], o["yes"] = study2(rating), study2(yes)
        if by["de"]:
            o["de"] = decision_task(de_frame(rows))
    (analyze.RESULTS / "mixed.json").write_text(json.dumps(out, indent=1))
    text = report(out)
    (analyze.RESULTS / "mixed.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
