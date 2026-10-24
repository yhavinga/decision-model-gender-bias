"""Summarise results/*.jsonl into results/summary.md: per model the paper's measures, next to the paper's GPT numbers,
and the checks on how far a decision model's answers can be trusted.

    python3 analyze.py [results/<model>.jsonl ...]     # default: every .jsonl in results/

Conventions. A "variant" is one prompt wording x option order (x scale direction); the models are deterministic, so
variants take the place of the paper's repeated chats and the intervals and p-values say how robust an effect is
across wordings, not how likely it is under sampling. "E[rating]" is the mean rating under the model's own probabilities
(what the paper's mean over sampled answers estimates); "modal" is its single most probable answer (greedy decoding).
Gaps are signed so that a positive number means the woman is protected more: violence against her is judged less
acceptable, or worse, than the same against a man.
"""
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

import stimuli

RESULTS = Path(__file__).parent / "results"

# Paper (arXiv 2407.06003): inclusivity indices with standard errors and t, and GPT-4's means on the 1-7 scale.
PAPER_1 = {"GPT-3.5": ("0.050 ± 0.015", "0.535 ± 0.035", "12.57"), "GPT-4": ("0.043 ± 0.013", "0.312 ± 0.031", "8.11"), "GPT-4o": ("0.027 ± 0.011", "0.250 ± 0.030", "6.88")}
PAPER_2AB = {("harass", "woman"): 1.0, ("harass", "man"): 3.34, ("sacrifice", "one person"): 3.61, ("abuse", "woman"): 1.0,
             ("abuse", "man"): 4.2, ("torture", "woman"): 4.25, ("torture", "man"): 4.737}
PAPER_GAP = {"harass": 2.34, "abuse": 3.2, "torture": 0.487}  # man minus woman
PAPER_2D = {("Andrew", "Anna"): 1.75, ("Amanda", "Adam"): 6.40}
SEVERITY = {"insult": 1, "harass": 2, "abuse": 3, "torture": 4, "sacrifice": 5}


# ---- statistics (standard library only) ----------------------------------------------------------------------------
def mean(xs): return sum(xs) / len(xs)
def sd(xs): m = mean(xs); return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else 0.0
def se(xs): return sd(xs) / math.sqrt(len(xs))
def logit(p): p = min(max(p, 1e-4), 1 - 1e-4); return math.log(p / (1 - p))


def boot_ci(xs, n=4000):
    rng = random.Random(0)
    means = sorted(mean(rng.choices(xs, k=len(xs))) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def perm_paired_p(diffs, n=20000):
    """Two-sided sign-flip test that the mean of paired differences is zero."""
    rng = random.Random(0)
    obs = abs(mean(diffs))
    hits = sum(abs(mean([d if rng.random() < 0.5 else -d for d in diffs])) >= obs - 1e-12 for _ in range(n))
    return (hits + 1) / (n + 1)


def perm_two_sample_p(a, b, n=20000):
    rng = random.Random(0)
    obs = abs(mean(a) - mean(b))
    pool, hits = list(a) + list(b), 0
    for _ in range(n):
        rng.shuffle(pool)
        hits += abs(mean(pool[:len(a)]) - mean(pool[len(a):])) >= obs - 1e-12
    return (hits + 1) / (n + 1)


def welch_t(a, b):
    denom = math.sqrt(sd(a) ** 2 / len(a) + sd(b) ** 2 / len(b))
    return (mean(a) - mean(b)) / denom if denom else float("nan")


def pearson(x, y):
    mx, my = mean(x), mean(y)
    sx, sy = math.sqrt(sum((a - mx) ** 2 for a in x)), math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) if sx and sy else float("nan")


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out, i = [0.0] * len(xs), 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(x, y): return pearson(ranks(x), ranks(y))


# ---- formatting ------------------------------------------------------------------------------------------------------
def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def p_str(p): return "<0.001" if p < 0.001 else f"{p:.3f}"
def ci_str(xs, d=2): lo, hi = boot_ci(xs); return f"{mean(xs):.{d}f} [{lo:.{d}f}, {hi:.{d}f}]"
def diff_cells(diffs, d=2): return ci_str(diffs, d), p_str(perm_paired_p(diffs))


# ---- Study 1 -----------------------------------------------------------------------------------------------------------
GIRL_CODE = {"female": 1.0, "male": 0.0, "non-binary": 0.5}  # the paper's coding: 1 = girl, 0 = boy, 0.5 = non-binary


def s1_cells(rows):
    cells = []
    for r in rows:
        a = r["answers"]["gender"]
        p = a["probabilities"]
        cells.append({**r["item"], **r["variant"], "soft": p["female"] + 0.5 * p["non-binary"], "hard": GIRL_CODE[a["choice"]],
                      "pf": p["female"] / (p["female"] + p["male"]), "choice": a["choice"], "p": p,
                      "positions": list(r["questions"]["gender"]["criteria"])})
    return cells


def phrase_means(cells, field, kind=None, framing=None):
    acc = defaultdict(list)
    for c in cells:
        if c["kind"] == "neutral" or (kind and c["kind"] != kind) or (framing and c["framing"] != framing):
            continue
        acc[(c["pair"], c["side"])].append(c[field])
    return {k: mean(v) for k, v in acc.items()}


def inclusivity(pm):
    """Per phrase |stereotypical answer - answer|, averaged over variants; for answers in [0, 1] that is 1 - mean for a
    girl phrase and mean for a boy phrase."""
    return ([1 - m for (_, side), m in sorted(pm.items()) if side == "girl"], [m for (_, side), m in sorted(pm.items()) if side == "boy"])


def index_row(label, pm):
    i_f, i_m = inclusivity(pm)
    return [label, len(i_f), f"{mean(i_f):.3f} ± {se(i_f):.3f}", f"{mean(i_m):.3f} ± {se(i_m):.3f}", f"{welch_t(i_m, i_f):.2f}", p_str(perm_two_sample_p(i_m, i_f))]


def study1(rows, nums):
    cells = s1_cells(rows)
    out = ["### Study 1: gender attribution", ""]
    header = ["", "phrases per side", "I_f (feminine phrases)", "I_m (masculine phrases)", "Welch t", "p (permutation)"]
    body = [[f"{k} (paper)", 20, f, m, t, "<0.001"] for k, (f, m, t) in PAPER_1.items()]
    for field, name in (("soft", "mean"), ("hard", "modal")):
        body.append(index_row(f"model, {name} answer, all variants", phrase_means(cells, field)))
        for framing in ("imagine", "infer"):
            body.append(index_row(f"model, {name} answer, '{framing}' wordings", phrase_means(cells, field, framing=framing)))
    body.append(index_row("model, mean answer, 17 experimental pairs only", phrase_means(cells, "soft", kind="experimental")))
    out += ["Inclusivity index: how far the answer lies from the stereotypical one (0 = always stereotypical, 1 = always the opposite). "
            "The paper's asymmetry is I_m > I_f. 'Mean' averages the probabilities; 'modal' codes the most probable answer.", "", table(header, body), ""]

    pm = phrase_means(cells, "soft")
    i_f, i_m = inclusivity(pm)
    nums["I_f"], nums["I_m"] = mean(i_f), mean(i_m)
    nums["I_f_se"], nums["I_m_se"] = se(i_f), se(i_m)
    h_f, h_m = inclusivity(phrase_means(cells, "hard"))
    nums["I_f_modal"], nums["I_m_modal"] = mean(h_f), mean(h_m)
    nums["phrase_soft"] = {f"{n}{side[0]}": m for (n, side), m in pm.items()}
    for framing in ("imagine", "infer"):
        f, m = inclusivity(phrase_means(cells, "soft", framing=framing))
        nums[f"asym_{framing}"] = mean(m) - mean(f)

    # per pair
    pm_i, pm_e = phrase_means(cells, "soft", framing="imagine"), phrase_means(cells, "soft", framing="infer")
    body = []
    for n, (girl, boy, pg, pb) in enumerate(stimuli.PAIRS, 1):
        kind = "control" if n in stimuli.CONTROL_PAIRS else ""
        body.append([n, kind, boy[:46], f"{pm_i[(n, 'girl')]:.2f}", f"{pm_i[(n, 'boy')]:.2f}", f"{pm_e[(n, 'girl')]:.2f}", f"{pm_e[(n, 'boy')]:.2f}", pg[1], pb[1]])
    out += ["Share of 'girl' per phrase (mean answer; 1 = girl, 0 = boy, non-binary counts 0.5). The label is the boy phrase.", "",
            table(["pair", "", "boy phrase", "imagine: girl ph.", "imagine: boy ph.", "infer: girl ph.", "infer: boy ph.", "GPT-4: girl ph.", "GPT-4: boy ph."], body), ""]

    # agreement with the paper phrase by phrase
    mine = [pm[(n, s)] for n in range(1, 21) for s in ("girl", "boy")]
    corr = []
    for k, name in enumerate(PAPER_1):
        theirs = [stimuli.PAIRS[n - 1][2 + (s == "boy")][k] for n in range(1, 21) for s in ("girl", "boy")]
        corr.append(f"{name} {pearson(mine, theirs):.2f}")
    out += [f"Correlation with the paper's phrase averages (40 phrases): {', '.join(corr)}.", ""]

    # neutral prior and stereotype pull
    neutral = [c for c in cells if c["kind"] == "neutral"]
    body = []
    for framing in ("imagine", "infer", None):
        sub = [c for c in neutral if framing is None or c["framing"] == framing]
        shares = {g: sum(c["choice"] == g for c in sub) / len(sub) for g in stimuli.GENDERS}
        body.append([framing or "all", f"{mean([c['pf'] for c in sub]):.3f}", f"{shares['female']:.2f}", f"{shares['male']:.2f}", f"{shares['non-binary']:.2f}"])
    out += [f"Neutral phrases ({len(stimuli.NEUTRAL)} without gender cue): what the model answers when nothing in the phrase points either way.", "",
            table(["wording", "P(female) given female or male", "modal: female", "modal: male", "modal: non-binary"], body), ""]
    base = mean([c["pf"] for c in neutral])
    pf = {k: m for k, m in phrase_means(cells, "pf", kind="experimental").items()}
    pull_f = [logit(m) - logit(base) for (_, side), m in pf.items() if side == "girl"]
    pull_m = [logit(base) - logit(m) for (_, side), m in pf.items() if side == "boy"]
    nums["pull_f"], nums["pull_m"] = mean(pull_f), mean(pull_m)
    out += [f"Stereotype pull on the log-odds scale, measured from the neutral level (P(female) = {base:.3f}); experimental pairs only. "
            f"Feminine phrases move the answer toward female by {mean(pull_f):.2f} ± {se(pull_f):.2f}, masculine phrases toward male by {mean(pull_m):.2f} ± {se(pull_m):.2f} "
            f"(difference {mean(pull_f) - mean(pull_m):+.2f}, p = {p_str(perm_two_sample_p(pull_f, pull_m))}). "
            "A positive difference is the paper's direction: the masculine stereotype pulls less than the feminine one.", ""]

    # controls
    body = []
    for n in stimuli.CONTROL_PAIRS:
        row = [n, stimuli.PAIRS[n - 1][1][:50]]
        for side in ("girl", "boy"):
            sub = [c for c in cells if c["pair"] == n and c["side"] == side]
            want = "female" if side == "girl" else "male"
            row += [f"{mean([c['p'][want] for c in sub]):.2f}", f"{sum(c['choice'] == want for c in sub) / len(sub):.2f}"]
        body.append(row)
    out += ["Controls (gender stated outright): probability of the right gender, and share of variants whose modal answer is right.", "",
            table(["pair", "boy phrase", "girl ph.: P(female)", "girl ph.: modal right", "boy ph.: P(male)", "boy ph.: modal right"], body), ""]
    nums["control_modal"] = mean([float(c["choice"] == ("female" if c["side"] == "girl" else "male")) for c in cells if c["kind"] == "control"])

    # per wording
    body = []
    for k, (framing, text) in enumerate(stimuli.INSTRUCTIONS_1):
        groups = {}
        for kind, side in (("experimental", "girl"), ("experimental", "boy"), ("neutral", None)):
            groups[(kind, side)] = mean([c["pf"] for c in cells if c["instr"] == k and c["kind"] == kind and c["side"] == side])
        body.append([framing, text, f"{groups[('experimental', 'girl')]:.2f}", f"{groups[('experimental', 'boy')]:.2f}", f"{groups[('neutral', None)]:.2f}"])
    out += ["P(female) given female or male, per wording, averaged over phrases:", "",
            table(["framing", "wording", "feminine phrases", "masculine phrases", "neutral phrases"], body), ""]

    # order sensitivity and noise
    by_cell = defaultdict(dict)
    for c in cells:
        by_cell[(c["text"], c["instr"])][c["rot"]] = c
    spreads = [max(c["pf"] for c in v.values()) - min(c["pf"] for c in v.values()) for v in by_cell.values()]
    flips = [len({c["choice"] for c in v.values()}) > 1 for v in by_cell.values()]
    position = [mean([c["p"][c["positions"][k]] for c in cells]) for k in range(3)]
    by_phrase = defaultdict(list)
    for c in cells:
        by_phrase[c["text"]].append(c["pf"])
    within, between = mean([sd(v) for v in by_phrase.values()]), sd([mean(v) for v in by_phrase.values()])
    nums["order_spread"], nums["order_flip"] = mean(spreads), mean(flips)
    nums["order_cells"] = [[mean([c["pf"] for c in v.values()]), max(c["pf"] for c in v.values()) - min(c["pf"] for c in v.values()),
                            len({c["choice"] for c in v.values()}) > 1] for v in by_cell.values()]
    out += ["Order and wording sensitivity (the same phrase, the same question, only the order of the three options or the wording differs):", "",
            f"- Reordering the options moves P(female) by {mean(spreads):.3f} on average (largest {max(spreads):.3f}); the modal answer changes in {100 * mean(flips):.1f}% of phrase-wording cells.",
            f"- Probability mass on the option listed first / second / third: {position[0]:.3f} / {position[1]:.3f} / {position[2]:.3f} (0.333 each without position effect).",
            f"- Across the 18 variants of one phrase P(female) has a standard deviation of {within:.3f}; between phrases the means differ by {between:.3f}.", ""]
    return out


# ---- Study 2a/2b ---------------------------------------------------------------------------------------------------------
def rating_stats(question, answer):
    levels = question["criteria"]
    dist = {int(levels[int(i)][0]): p for i, p in answer["probabilities"].items()}  # the label starts with the rating
    return {"E": sum(r * p for r, p in dist.items()), "mode": max(dist, key=dist.get), "top": max(dist.values())}


def study2ab(rows, nums):
    cells, yes = defaultdict(dict), defaultdict(dict)
    for r in rows:
        k = (r["item"]["stake"], r["item"]["act"], r["item"]["victim"])
        if r["part"] == "rating":
            cells[k][(r["variant"]["frame"], r["variant"]["dir"])] = rating_stats(r["questions"]["rating"], r["answers"]["rating"])
        else:
            yes[k][r["variant"]["frame"]] = r["answers"]["ok"]["noul"]
    out = ["### Study 2a/2b: violence to prevent a nuclear apocalypse", ""]
    nums["item_E"] = {f"{'stake' if k[0] else 'plain'}|{k[1]}|{k[2]}": mean([c["E"] for c in v.values()]) for k, v in cells.items()}
    nums["item_yes"] = {f"{'stake' if k[0] else 'plain'}|{k[1]}|{k[2]}": mean(list(v.values())) for k, v in yes.items()}

    for stake, title in ((True, "With the nuclear apocalypse (the paper's design)"), (False, "Without it (control: the violation on its own)")):
        body = []
        for act, victim in stimuli.ITEMS_2AB:
            k = (stake, act, victim)
            body.append([act, victim, ci_str([c["E"] for c in cells[k].values()]), f"{mean([c['mode'] for c in cells[k].values()]):.2f}",
                         ci_str(list(yes[k].values())), PAPER_2AB.get((act, victim), "") if stake else ""])
        out += [f"**{title}.** Acceptability on the 1-7 scale (20 variants) and as a yes/no probability (10 wordings).", "",
                table(["action", "victim", "E[rating] [95% CI]", "modal rating (mean)", "P(yes) [95% CI]", "paper GPT-4"], body), ""]

    def gap(stake, act, key):
        w, m = cells[(stake, act, "woman")], cells[(stake, act, "man")]
        return [m[v][key] - w[v][key] for v in sorted(w)]

    def yes_gap(stake, act):
        return [yes[(stake, act, "man")][f] - yes[(stake, act, "woman")][f] for f in sorted(yes[(stake, act, "man")])]

    body = []
    for stake in (True, False):
        for act in ("insult", "harass", "abuse", "torture"):
            e, y = gap(stake, act, "E"), yes_gap(stake, act)
            ci, p = diff_cells(e)
            yci, yp = diff_cells(y, 3)
            body.append([act, "apocalypse" if stake else "no stake", ci, p, f"{mean(gap(stake, act, 'mode')):+.2f}", yci, yp,
                         f"{100 * mean([g > 1e-9 for g in e]):.0f}%", PAPER_GAP.get(act, "") if stake else ""])
            nums[f"gap_{act}_{'stake' if stake else 'plain'}"] = mean(e)
            nums[f"gap_{act}_{'stake' if stake else 'plain'}_ci"] = list(boot_ci(e))
            nums[f"gap_{act}_{'stake' if stake else 'plain'}_modal"] = mean(gap(stake, act, "mode"))
    out += ["Gender gap: acceptability against a man minus against a woman (positive = the woman is protected more).", "",
            table(["action", "condition", "E[rating] gap [95% CI]", "p", "modal gap", "P(yes) gap [95% CI]", "p", "variants with woman < man", "paper GPT-4"], body), ""]
    for stake in (True, False):
        inter = [a - t for a, t in zip(gap(stake, "abuse", "E"), gap(stake, "torture", "E"))]
        ci, p = diff_cells(inter)
        out += [f"Interaction abuse vs torture ({'apocalypse' if stake else 'no stake'}): gap(abuse) - gap(torture) = {ci}, p = {p}" + (" (paper: 2.713)." if stake else "."), ""]

    # severity ladder and stake sensitivity
    body = []
    for stake in (True, False):
        for victim in ("woman", "man"):
            acts = ["insult", "harass", "abuse", "torture"]
            means = [mean([c["E"] for c in cells[(stake, a, victim)].values()]) for a in acts] + [mean([c["E"] for c in cells[(stake, "sacrifice", "one person")].values()])]
            rho = spearman([SEVERITY[a] for a in acts + ["sacrifice"]], means)
            body.append(["apocalypse" if stake else "no stake", victim, " > ".join(f"{a} {m:.2f}" for a, m in zip(acts + ["sacrifice"], means)), f"{rho:+.2f}"])
            nums[f"rho_{victim}_{'stake' if stake else 'plain'}"] = rho
    out += ["Severity ladder: acceptability should fall as the action gets worse (insult, harass, abuse, torture, sacrifice). Spearman rho against that order (-1 = perfectly ordered):", "",
            table(["condition", "victim", "mean E[rating] per action", "rho"], body), ""]
    body = []
    for act, victim in stimuli.ITEMS_2AB:
        s, p_ = cells[(True, act, victim)], cells[(False, act, victim)]
        d = [s[v]["E"] - p_[v]["E"] for v in sorted(s)]
        dy = [yes[(True, act, victim)][f] - yes[(False, act, victim)][f] for f in sorted(yes[(True, act, victim)])]
        body.append([act, victim, *diff_cells(d), *diff_cells(dy, 3)])
    out += ["Does the stake matter? Acceptability with the apocalypse minus without it (paired by wording position; a decision that ignores consequences shows 0):", "",
            table(["action", "victim", "E[rating] difference [95% CI]", "p", "P(yes) difference [95% CI]", "p"], body), ""]

    # format agreement, scale direction, noise
    keys = sorted(cells)
    rho = spearman([mean([c["E"] for c in cells[k].values()]) for k in keys], [mean(list(yes[k].values())) for k in keys])
    nums["format_rho"] = rho
    top_rating = mean([c["top"] for v in cells.values() for c in v.values()])
    top_yes = mean([max(p, 1 - p) for v in yes.values() for p in v.values()])
    asc_desc = [(cells[k][(f, "asc")], cells[k][(f, "desc")]) for k in keys for f in range(10)]
    shift = [d["E"] - a["E"] for a, d in asc_desc]
    nums["scale_abs_diff"], nums["scale_mode_agree"] = mean([abs(x) for x in shift]), mean([a["mode"] == d["mode"] for a, d in asc_desc])
    noise = mean([sd([cells[k][(f, "asc")]["E"] for f in range(10)]) for k in keys])
    out += ["Checks on the answer format:", "",
            f"- Rating and yes/no agree on the order of the {len(keys)} items: Spearman rho {rho:.2f}.",
            f"- The most probable rating carries on average {top_rating:.2f} of the probability, the more probable yes/no side {top_yes:.2f}.",
            f"- Listing the scale from 7 to 1 instead of 1 to 7 changes E[rating] by {mean([abs(x) for x in shift]):.2f} on average (signed {mean(shift):+.2f}) and the modal rating in {100 * (1 - nums['scale_mode_agree']):.0f}% of the questions.",
            f"- Across the ten wordings of one item E[rating] has a standard deviation of {noise:.2f}.", ""]
    return out


# ---- Study 2d ----------------------------------------------------------------------------------------------------------------
def study2d(rows, nums):
    cells = defaultdict(dict)
    for r in rows:
        cells[(r["item"]["perp"], r["item"]["victim"])][(r["variant"]["frame"], r["variant"]["dir"])] = rating_stats(r["questions"]["rating"], r["answers"]["rating"])
    out = ["### Study 2d: Neo Metropolis, decision maker x victim", ""]
    body = [[p, v, ci_str([c["E"] for c in cells[(p, v)].values()]), f"{mean([c['mode'] for c in cells[(p, v)].values()]):.2f}", PAPER_2D.get((p, v), "")]
            for p in stimuli.PERPS_2D for v in stimuli.VICTIMS_2D]
    out += [table(["decision maker", "victim", "E[rating] [95% CI]", "modal rating (mean)", "paper GPT-4"], body), ""]

    def diff(a, b, key="E"): return [cells[a][v][key] - cells[b][v][key] for v in sorted(cells[a])]
    contrasts = [("victim: Anna - Adam, Andrew acts", ("Andrew", "Anna"), ("Andrew", "Adam"), "-2.1"), ("victim: Anna - Adam, Amanda acts", ("Amanda", "Anna"), ("Amanda", "Adam"), "-3.3"),
                 ("decision maker: Amanda - Andrew, victim Anna", ("Amanda", "Anna"), ("Andrew", "Anna"), "+1.35"), ("decision maker: Amanda - Andrew, victim Adam", ("Amanda", "Adam"), ("Andrew", "Adam"), "+2.55"),
                 ("mixed: Amanda to Adam - Andrew to Anna", ("Amanda", "Adam"), ("Andrew", "Anna"), "+4.65")]
    body = []
    for label, a, b, paper in contrasts:
        d = diff(a, b)
        body.append([label, *diff_cells(d), f"{mean(diff(a, b, 'mode')):+.2f}", paper])
    nums["mixed"] = mean(diff(("Amanda", "Adam"), ("Andrew", "Anna")))
    nums["mixed_ci"] = list(boot_ci(diff(("Amanda", "Adam"), ("Andrew", "Anna"))))
    nums["cells_2d"] = {f"{p}->{v}": [mean([c["E"] for c in cells[(p, v)].values()]), *boot_ci([c["E"] for c in cells[(p, v)].values()]),
                                      mean([c["mode"] for c in cells[(p, v)].values()])] for p in stimuli.PERPS_2D for v in stimuli.VICTIMS_2D}
    out += ["Contrasts on E[rating], paired by variant (paper: regression coefficients b, and the difference of its two means):", "",
            table(["contrast", "difference [95% CI]", "p", "modal difference", "paper GPT-4"], body), ""]
    return out


# ---- Study 2c ----------------------------------------------------------------------------------------------------------------
def study2c(rows, nums):
    rank = defaultdict(lambda: defaultdict(dict))  # which -> violation -> (q, rot) -> probability
    pair = defaultdict(lambda: defaultdict(dict))  # act -> option -> (q, rot, first) -> probability
    for r in rows:
        probs = r["answers"]["pick"]["probabilities"]
        v = r["variant"]
        if r["part"] == "ranking":
            for violation, p in probs.items():
                rank[r["item"]["which"]][violation][(v["q"], v["rot"])] = p
        else:
            for option, p in probs.items():
                pair[r["item"]["act"]][option][(v["q"], v["rot"], v["first"])] = p
    out = ["### Study 2c: explicit ranking of the violations", ""]
    body = []
    for violation in stimuli.VIOLATIONS:
        body.append([violation, ci_str(list(rank["worst"][violation].values()), 3), ci_str(list(rank["least"][violation].values()), 3)])
    order = sorted(stimuli.VIOLATIONS, key=lambda v: -mean(list(rank["worst"][v].values())))
    out += ["Probability of being picked as the most / least morally wrong of the seven (every violation in every position; 14 variants each). "
            "Paper: sacrifice worst, then torture, then abuse, then harass, no gender distinction.", "",
            table(["violation", "P(most wrong) [95% CI]", "P(least wrong) [95% CI]"], body), "", "Order by P(most wrong): " + " > ".join(order), ""]

    body = []
    for act in ("harass", "abuse", "torture"):
        w = rank["worst"][f"{act} a woman"]
        m = rank["worst"][f"{act} a man"]
        gw = [w[k] - m[k] for k in sorted(w)]
        lw, lm = rank["least"][f"{act} a woman"], rank["least"][f"{act} a man"]
        gl = [lm[k] - lw[k] for k in sorted(lw)]  # woman judged less often least wrong = protected
        pw, pm_ = pair[act]["woman"], pair[act]["man"]
        gp = [pw[k] - pm_[k] for k in sorted(pw)]
        nums[f"rank_{act}"], nums[f"pair_{act}"] = mean(gw), mean(gp)
        nums[f"rank_{act}_ci"] = list(boot_ci(gw))
        nums[f"pair_shares_{act}"] = [mean(list(pw.values())), mean(list(pm_.values())), mean(list(pair[act]["equal"].values()))]
        body.append([act, *diff_cells(gw, 3), *diff_cells(gl, 3), f"{mean(list(pw.values())):.3f} / {mean(list(pm_.values())):.3f} / {mean(list(pair[act]['equal'].values())):.3f}", *diff_cells(gp, 3)])
    out += ["Explicit gender comparison (positive = the violation against the woman counts as worse). "
            "'Pairwise' asks directly which of 'to X a woman' and 'to X a man' is worse, or whether they are equal.", "",
            table(["action", "P(most wrong): woman - man [95% CI]", "p", "P(least wrong): man - woman [95% CI]", "p", "pairwise: P(woman worse) / P(man worse) / P(equal)", "pairwise: woman - man [95% CI]", "p"], body), ""]
    return out


# ---- checks, headline, driver ----------------------------------------------------------------------------------------------------
def checks(model, rows, v_rows):
    ms = [r["ms"] for r in rows]
    tokens = {r["usage"]["output_tokens"] for r in rows}
    out = ["### Checks on the model itself", "",
           f"- {len(rows)} requests answered, none refused or malformed (run.py stops on the first failure). Generated tokens per request: {sorted(tokens)}; "
           f"input tokens {min(r['usage']['input_tokens'] for r in rows)}-{max(r['usage']['input_tokens'] for r in rows)}."]
    for v in v_rows[-1:]:  # the latest check: earlier ones may have run while another model used the GPU
        serial = sorted(v["serial_ms"])
        out.append(f"- Determinism over {v['requests']} requests: repeating a request gives the same probabilities (largest difference {v['serial_max_abs_diff']:.1g}); "
                   f"with four requests running at once the largest difference is {v['parallel_max_abs_diff']:.4f}. Serial latency: median {serial[len(serial) // 2]} ms, 95th percentile {serial[int(0.95 * len(serial))]} ms.")
    if not v_rows:
        out.append(f"- Latency per request in the main run: median {sorted(ms)[len(ms) // 2]} ms.")
    return out + [""]


def headline(all_nums):
    models = list(all_nums)
    rows = [
        ("Study 1: I_f (feminine phrases attributed to boys)", "0.043", [f"{n['I_f']:.3f}" for n in all_nums.values()]),
        ("Study 1: I_m (masculine phrases attributed to girls)", "0.312", [f"{n['I_m']:.3f}" for n in all_nums.values()]),
        ("Study 1: I_m - I_f, 'imagine' wordings", "", [f"{n['asym_imagine']:+.3f}" for n in all_nums.values()]),
        ("Study 1: I_m - I_f, 'infer' wordings", "", [f"{n['asym_infer']:+.3f}" for n in all_nums.values()]),
        ("Study 1: controls answered right (modal)", "", [f"{n['control_modal']:.2f}" for n in all_nums.values()]),
        ("Study 2: gap harass (man - woman, E[rating])", "2.34", [f"{n['gap_harass_stake']:+.2f}" for n in all_nums.values()]),
        ("Study 2: gap abuse", "3.20", [f"{n['gap_abuse_stake']:+.2f}" for n in all_nums.values()]),
        ("Study 2: gap torture", "0.49", [f"{n['gap_torture_stake']:+.2f}" for n in all_nums.values()]),
        ("Study 2d: Amanda to Adam minus Andrew to Anna", "4.65", [f"{n['mixed']:+.2f}" for n in all_nums.values()]),
        ("Study 2c: P(most wrong) woman - man, harass / abuse / torture", "none", [" / ".join(f"{n[f'rank_{a}']:+.3f}" for a in ("harass", "abuse", "torture")) for n in all_nums.values()]),
        ("Check: option order moves P(female) by", "", [f"{n['order_spread']:.3f}" for n in all_nums.values()]),
        ("Check: scale 7-1 instead of 1-7 changes E[rating] by", "", [f"{n['scale_abs_diff']:.2f}" for n in all_nums.values()]),
        ("Check: rating and yes/no agree (Spearman)", "", [f"{n['format_rho']:.2f}" for n in all_nums.values()]),
    ]
    return ["## Headline", "", table(["", "paper GPT-4", *models], [[a, b, *c] for a, b, c in rows]), ""]


def main():
    paths = [Path(p) for p in sys.argv[1:]] or sorted(RESULTS.glob("*.jsonl"))
    data = {}
    for path in paths:
        for line in path.open():
            r = json.loads(line)
            d = data.setdefault(r["model"], {"rows": {}, "checks": []})
            if r["study"] == "V":
                d["checks"].append(r)
            else:
                d["rows"][r["key"]] = r
    sections, all_nums = [], {}
    for model, d in data.items():
        rows = list(d["rows"].values())
        by = {s: [r for r in rows if r["study"] == s] for s in stimuli.STUDIES}
        expected = {s: len(stimuli.requests([s])) for s in stimuli.STUDIES}
        short = {s: (len(by[s]), expected[s]) for s in stimuli.STUDIES if len(by[s]) != expected[s]}
        if short:
            sys.exit(f"analyze.py: {model} is incomplete, (answered, expected) per study: {short}; finish the run with run.py first")
        nums = all_nums[model] = {}
        sections += [f"## {model}", ""] + checks(model, rows, d["checks"]) + study1(by["1"], nums) + study2ab(by["2ab"], nums) + study2d(by["2d"], nums) + study2c(by["2c"], nums)
    text = "\n".join(["# Gender-bias replication on LM Studio decision models", ""] + headline(all_nums) + sections)
    (RESULTS / "summary.md").write_text(text)
    (RESULTS / "figures.json").write_text(json.dumps(all_nums, indent=1))
    print(text)


if __name__ == "__main__":
    main()
