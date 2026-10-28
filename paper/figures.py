"""Draw the paper's six figures from results/figures.json.

    python3 paper/figures.py            # writes paper/figures/*.pdf and figures/*.png (the README's copies)

Run analyze.py first: every number comes from its output, none is typed in here except GPT-4's, which come from
analyze.py's copy of the paper's tables. A run or measure missing from figures.json stops the script before it draws.
Each figure is drawn at the width it prints at (ACL column or text width), so its text prints at the size set here.
"""
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.patheffects import withStroke
from matplotlib.textpath import TextPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import analyze  # noqa: E402

NUMS = json.loads((ROOT / "results" / "figures.json").read_text())
OUT_PDF, OUT_PNG = ROOT / "paper" / "figures", ROOT / "figures"

# The paper's main runs in its order (analyze.MAIN): TypeSafe's Jev, AutoTrust's two distillations of it, then the five
# open models that implement its API. A label names the model; maker and precision belong in the caption.
LABELS = dict(zip(analyze.MAIN, ("Jev 1.14", "JEV-27B", "JEV-9B", "pplx 27B", "clef-flash 9B", "granite-switch 8B", "Kev 4B", "d1 3B"), strict=True))
JEV = analyze.MAIN[0]
REPEAT = f"{JEV}-pass2"  # Jev's second pass over the same requests: the noise floor of the decision task
ACTS = ("insult", "harass", "abuse", "torture")
GENDER = "Gender_identity"  # BBQ's name for the category of the bbq study; bbqx has the other eight
CATEGORIES = (GENDER, *analyze.stimuli.BBQX_CATEGORIES)
COUNTS = ("n", "stereotyped", "other")  # BBQ questions without evidence that have a stereotyped answer, and whom the top answer names
NEEDED = {m: ("s1_labels", "s1u", "neutral_pf", *(f"gap_{a}_stake" for a in ACTS), "gap_2e", "mixed", "bbq", "gate_bbq", "ss",
              *(f"bbqx {c} {k}" for c in CATEGORIES[1:] for k in ("share", "share_ci", *COUNTS)), *(("de",) if m in analyze.DE_RUNS else ())) for m in analyze.MAIN}
NEEDED[REPEAT] = ("de_repeat",)


def has(n, key):
    for k in key.split(" "):
        if k not in n:
            return False
        n = n[k]
    return True


# Jev's raw answers are not published, so every number, Jev's included, comes from figures.json; one line per run
lack = {m: ["the whole run"] if m not in NUMS else list(dict.fromkeys(f"bbqx[*].{k.split()[2]}" if k.startswith("bbqx ") else k for k in keys if not has(NUMS[m], k)))
        for m, keys in NEEDED.items()}
if lack := {m: v for m, v in lack.items() if v}:
    sys.exit("figures.py: results/figures.json lacks\n" + "\n".join(f"  {m}: {', '.join(v)}" for m, v in lack.items()) + "\nfinish those runs and rerun analyze.py")

COL, TEXT = 3.03, 6.30  # ACL column and text width, inches
JEV_FAMILY = analyze.MAIN[:3]  # Jev and its two distillations come first in analyze.MAIN; a gap sets them off from the rest


def rows(runs):
    """y of each run's row, top to bottom."""
    k = sum(m in JEV_FAMILY for m in runs)
    return [i + 0.45 * (i >= k) for i in range(len(runs))]


ROW = rows(analyze.MAIN)
FEW = 10  # below this many committed answers (a person named, not "unknown"), a share of them is shown as a count

# Ink and chrome of the dataviz skill's reference palette, on a white page
INK, INK2, MUTED, AXIS, PALE = "#0b0b0b", "#52514e", "#898781", "#c3c2b7", "#e1e0d9"
# One meaning per colour in every figure. A model's estimate is ink, a second readout or a reference grey with an open
# marker; hue is kept for gender and for the stereotype, and pale for "unknown" or "can't tell". The three gender hues
# pass the dataviz palette validator on all pairs (CVD dE >= 9.1, normal vision >= 22.9); in grayscale (luma 0.39 / 0.65
# / 0.49) violet and aqua come close, so non-binary also has a texture in bars and a diamond for a marker. Yellow and
# aqua are under 3:1 on white, so their marks always come with a direct label as well as the legend.
FEMALE, MALE, NONBINARY = "#6250d6", "#eda100", "#1baf7a"
TEXTURE = {"non-binary": "////"}  # drawn in the bar's white edge colour
FEMALE_LIGHT = "#9085e9"  # the same violet a step lighter (luma 0.58): the woman's top answer is no where the man's is yes
# Stereotyped share of committed answers: blue against the stereotype, red with it, grey at 0.5. The ends are the
# palette's blue 600 and red darkened to the same OKLCH lightness (0.43), so both arms span the same lightness.
STEREO = LinearSegmentedColormap.from_list("stereotype", [(0, "#184f95"), (0.2, "#3987e5"), (0.5, "#f0efec"), (0.8, "#e34948"), (1, "#911f22")])

SMALL = 7.5  # annotations; no text is set below it
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"], "font.size": 8,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.6, "axes.labelcolor": INK2, "axes.labelsize": 8, "axes.titlesize": 8.5,
    "axes.titlecolor": INK, "axes.titlelocation": "left", "axes.titlepad": 5,
    "xtick.color": AXIS, "xtick.labelcolor": INK2, "xtick.labelsize": 8, "xtick.major.size": 2.5, "xtick.major.width": 0.6,
    "ytick.labelcolor": INK, "ytick.labelsize": 8, "ytick.major.size": 0, "legend.fontsize": 8, "legend.frameon": False,
    "legend.handletextpad": 0.4, "legend.columnspacing": 1.4, "legend.borderaxespad": 0, "legend.borderpad": 0,
    "hatch.linewidth": 0.6, "pdf.fonttype": 42, "savefig.dpi": 200,
})


def place(fig, left, right, top, bottom, **space):
    """Margins in inches, so that the plot area does not depend on the figure's size."""
    w, h = fig.get_size_inches()
    fig.subplots_adjust(left=left / w, right=1 - right / w, top=1 - top / h, bottom=bottom / h, **space)


def clean(ax, left=False):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0, labelleft=left)


def models(ax, runs=analyze.MAIN):
    """Model labels on the y axis, in analyze.MAIN's order from the top."""
    ax.set_yticks(rows(runs), [LABELS[m] for m in runs])
    ax.set_ylim(rows(runs)[-1] + 0.6, -0.6)


def width_in(text, size):
    return TextPath((0, 0), text, size=size, prop=FontProperties(family=plt.rcParams["font.sans-serif"])).get_extents().width / 72


def ink_on(colour):
    """Text inside a fill: white or ink, whichever contrasts more (they tie at a relative luminance of 0.179)."""
    lum = sum(k * (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) for k, c in zip((0.2126, 0.7152, 0.0722), to_rgb(colour)))
    return "white" if lum < 0.179 else INK


def label_segments(ax, bars, parts):
    """Name each part inside the first bar segment wide enough to hold its name, so identity does not rest on colour.
    bars: (y, {part: (left, width)}) in data units of an x axis from 0 to 1."""
    span = ax.get_position().width * ax.figure.get_size_inches()[0]
    for key, colour, name in parts:
        for y, segs in bars:
            left, w = segs.get(key, (0, 0))
            if w * span >= width_in(name, SMALL) + 0.08:
                # a stroke in the segment's own colour keeps a texture out of the letters (a box would stick out of the bar)
                ax.text(left + w / 2, y, name, ha="center", va="center", fontsize=SMALL, color=ink_on(colour), path_effects=[withStroke(linewidth=1.5, foreground=colour)])
                break


def save(fig, name):
    OUT_PDF.mkdir(parents=True, exist_ok=True)
    OUT_PNG.mkdir(exist_ok=True)
    # no tight bounding box: the page size is the print size
    fig.savefig(OUT_PDF / f"{name}.pdf")
    fig.savefig(OUT_PNG / f"{name}.png", facecolor="white")
    plt.close(fig)


def bbq_share(run, cat):
    """(stereotyped, committed, questions, share, 95% interval) of one BBQ category, for the questions without evidence
    that have a stereotyped answer: committed answers name a person rather than "unknown"; the share is of those, its
    interval resamples templates. Counts and share are computed apart in analyze.py, so they are checked to agree."""
    c, s = (NUMS[run]["gate_bbq"], NUMS[run]["bbq"]["all|modal"]) if cat == GENDER else (NUMS[run]["bbqx"][cat],) * 2
    committed = c["stereotyped"] + c["other"]
    expected = c["stereotyped"] / committed if committed else math.nan
    if not (math.isclose(s["share"], expected) or math.isnan(s["share"]) and math.isnan(expected)):
        raise ValueError(f"figures.py: results/figures.json gives {run} a BBQ {cat} share of {s['share']} but counts {c['stereotyped']} of {committed}")
    return c["stereotyped"], committed, c["n"], s["share"], s["share_ci"]


def dot(ax, v, lo, hi, y, colour=INK, marker="o", open_=False, ms=4.5):
    """An estimate with its 95% interval; an open marker for a second readout."""
    ax.plot([lo, hi], [y, y], color=colour, lw=1.2, solid_capstyle="butt", zorder=3)
    ax.plot(v, y, marker, ms=ms, zorder=4, **({"mfc": "white", "mec": colour, "mew": 1.1} if open_ else {"color": colour, "mec": "white", "mew": 0.6}))


def moral():
    """Study 2: the gap per act under the apocalypse and pooled over five stakes, and the vignette contrast."""
    gpt4 = {**analyze.PAPER_GAP, "vignette": analyze.PAPER_2D[("Amanda", "Adam")] - analyze.PAPER_2D[("Andrew", "Anna")]}
    panels = [*zip(ACTS, ("Insult", "Harassment", "Abuse", "Torture")), ("vignette", "Vignette")]
    fig, axes = plt.subplots(1, len(panels), figsize=(TEXT, 3.1), sharex=True, sharey=True)
    place(fig, left=1.0, right=0.06, top=0.5, bottom=0.5, wspace=0.1)
    top, xs = -1.3, list(gpt4.values())  # GPT-4's row sits above the models'
    for ax, (act, title) in zip(axes, panels):
        ax.axvline(0, color=AXIS, lw=0.6, zorder=0)
        ax.axhline(-0.7, color=PALE, lw=0.6)
        if act in gpt4:
            ax.plot(gpt4[act], top, "o", ms=5.5, mfc="white", mec=INK2, mew=1.2)
        for m, y in zip(analyze.MAIN, ROW):
            n = NUMS[m]
            if act == "vignette":  # one scenario, so no mean over stakes
                dot(ax, n["mixed"], *n["mixed_ci"], y)
                xs += n["mixed_ci"]
                continue
            dot(ax, n[f"gap_{act}_stake"], *n[f"gap_{act}_stake_ci"], y - 0.17)
            dot(ax, n["gap_2e"][act]["pooled"], *n["gap_2e"][act]["pooled_ci"], y + 0.17, MUTED, "D", open_=True, ms=4)
            xs += n[f"gap_{act}_stake_ci"] + n["gap_2e"][act]["pooled_ci"]
        ax.set_title(title)
        clean(ax, left=ax is axes[0])
    axes[0].set_xlim(min(0, *xs) - 0.4, max(xs) + 0.4)
    axes[0].set_xticks(range(0, int(max(xs)) + 1, 2))
    axes[0].set_yticks([top, *ROW], ["GPT-4 (original)", *(LABELS[m] for m in analyze.MAIN)])
    axes[0].get_yticklabels()[0].set_color(INK2)
    axes[0].set_ylim(ROW[-1] + 0.6, top - 0.6)
    fig.text(0.5 * (axes[0].get_position().x0 + axes[-1].get_position().x1), 0.08 / 3.1, "Acceptability against a man minus against a woman (points on the 1–7 scale)",
             ha="center", va="bottom", color=INK2)
    handles = [Line2D([], [], color=INK, lw=1.2, marker="o", ms=4.5, mec="white", mew=0.6, label="nuclear apocalypse"),
               Line2D([], [], color=MUTED, lw=1.2, marker="D", ms=4, mfc="white", mec=MUTED, mew=1.1, label="mean over five stakes"),
               Line2D([], [], lw=0, marker="o", ms=5.5, mfc="white", mec=INK2, mew=1.2, label="GPT-4, apocalypse")]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(axes[0].get_position().x0, 1 - 0.06 / 3.1), ncol=3)
    save(fig, "fig-moral")


def classification():
    """Study 1 and 1u: top answers for the eight phrases without a gender cue, forced and with "can't tell"."""
    parts = [("female", FEMALE, "girl"), ("male", MALE, "boy"), ("non-binary", NONBINARY, "non-binary"), ("unknown", PALE, "can’t tell")]
    w, h = COL, 4.5
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0.06 / w, 0.25 / h, (w - 0.51) / w, (h - 0.25 - 0.62) / h])
    bars = []
    for m, y in zip(analyze.MAIN, ROW):
        forced, offered = NUMS[m]["s1_labels"]["no gender cue"], NUMS[m]["s1u"]["no gender cue"]
        ax.text(0, y - 0.32, LABELS[m], ha="left", va="bottom", fontsize=8, color=INK)
        for share, yy in ((forced, y - 0.15), (offered, y + 0.17)):
            left, segs = 0.0, {}
            for key, colour, _ in parts:
                if share.get(key, 0.0):  # Study 1 has no "unknown"
                    ax.barh(yy, share[key], left=left, height=0.3, color=colour, edgecolor="white", linewidth=0.8, hatch=TEXTURE.get(key))
                    segs[key] = (left, share[key])
                left += share.get(key, 0.0)
            bars.append((yy, segs))
            ax.text(1.03, yy, f"{100 * share['female']:.0f}%", va="center", ha="left", fontsize=8, color=INK if share is forced else INK2)
    label_segments(ax, bars, parts)
    ax.text(1.03, -0.68, "girl", ha="left", va="bottom", fontsize=8, color=INK)
    ax.set_ylim(ROW[-1] + 0.36, -0.68)
    ax.set_xlim(0, 1)
    ax.set_xticks([0, 0.5, 1], ["0", "50%", "100%"])
    clean(ax)
    ax.legend(handles=[Patch(fc=c, ec="white", lw=0, hatch=TEXTURE.get(k), label=lab) for k, c, lab in parts], loc="lower left", bbox_to_anchor=(0, 1 + 0.3 / (h - 0.87)), ncol=4,
              handlelength=0.9, columnspacing=0.9)
    ax.text(0, 1 + 0.07 / (h - 0.87), "Upper bar: forced choice. Lower bar: “can’t tell” offered.", transform=ax.transAxes, fontsize=SMALL, color=INK2, va="bottom")
    save(fig, "fig-classification")


def benchmarks():
    """Gender items: StereoSet ss, and in BBQ questions without evidence how often the top answer names a person and how
    often that person is the stereotyped one."""
    w, h = TEXT, 2.75
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(w, h), sharey=True, gridspec_kw={"width_ratios": [1.15, 1, 1.15]})
    place(fig, left=1.0, right=0.08, top=0.5, bottom=0.27, wspace=0.16)
    for m, y in zip(analyze.MAIN, ROW):
        ss = NUMS[m]["ss"]["both|all"]
        dot(a1, ss["ss"], *ss["ss_ci"], y)
        a1.text(ss["ss_ci"][1] + 1, y, f"{ss['ss']:.1f}", va="center", fontsize=SMALL, color=INK2)
        st, committed, n, share, (lo, hi) = bbq_share(m, GENDER)
        a2.barh(y, 1, height=0.5, color=PALE, lw=0)  # the track: answers "unknown", the right answer here
        a2.barh(y, committed / n, height=0.5, color=MUTED, edgecolor="white", linewidth=0.8)
        a2.text(committed / n + 0.015, y, f"{100 * committed / n:.0f}%", va="center", ha="left", fontsize=SMALL, color=INK)
        if m == JEV:
            a2.text(0.97, y, "“unknown”", va="center", ha="right", fontsize=SMALL, color=INK)
        if committed < FEW:  # too few for a share to mean anything
            a3.text(0.5, y, f"{st} of {committed}" if committed else "none", ha="center", va="center", fontsize=SMALL, color=INK2,
                    bbox={"fc": "white", "ec": "none", "pad": 1})
        elif math.isnan(lo):
            raise ValueError(f"figures.py: no interval for the BBQ gender share of {m} although it has {committed} committed answers")
        else:
            dot(a3, share, lo, hi, y)
    a1.axvline(50, color=AXIS, lw=0.6, zorder=0)
    a1.set_xlim(45, 90)
    a1.set_xticks([50, 60, 70, 80, 90])
    a1.set_title("StereoSet: stereotyped sentence\npreferred, % of items")
    a2.set_xlim(0, 1)
    a2.set_xticks([0, 0.5, 1], ["0", "50%", "100%"])
    a2.set_title(f"BBQ, no evidence: top answer\nnames a person, % of {n}")
    a3.axvline(0.5, color=AXIS, lw=0.6, zorder=0)
    a3.set_xlim(0, 1)
    a3.set_xticks([0, 0.5, 1], ["0", "0.5", "1"])
    a3.set_title("Of those, the share naming\nthe stereotyped person")
    models(a1)
    clean(a1, left=True)
    clean(a2)
    clean(a3)
    save(fig, "fig-benchmarks")


def lean():
    """Mean probability for the default or stereotyped option against the share of top answers that choose it."""
    def uncued(n):
        s = n["s1_labels"]["no gender cue"]
        return n["neutral_pf"], s["female"] / (s["female"] + s["male"])
    tasks = [("Uncued writing:\n“girl” rather than “boy”", uncued, None),
             ("BBQ, no evidence:\nthe stereotyped person", lambda n: (n["bbq"]["all|mean"]["share"], n["bbq"]["all|modal"]["share"]), GENDER),
             ("StereoSet:\nthe stereotyped sentence", lambda n: (n["ss"]["both|all"]["ss_soft"] / 100, n["ss"]["both|all"]["ss_modal"] / 100), None)]
    fig, axes = plt.subplots(1, 3, figsize=(TEXT, 2.75), sharey=True)
    place(fig, left=1.0, right=0.08, top=0.62, bottom=0.27, wspace=0.1)
    for ax, (title, get, bbq) in zip(axes, tasks):
        ax.axvline(0.5, color=AXIS, lw=0.6, zorder=0)
        for m, y in zip(analyze.MAIN, ROW):
            p, d = get(NUMS[m])
            ax.plot(p, y, "o", ms=5, mfc="white", mec=MUTED, mew=1.2, zorder=4)
            committed = bbq_share(m, bbq)[1] if bbq else FEW
            if committed < FEW:  # too few top answers name a person for their share to mean anything
                ax.text(p + 0.03, y, f"{committed} named" if committed else "none named", va="center", fontsize=SMALL, color=INK2)
                continue
            ax.plot([p, d], [y, y], color=AXIS, lw=1.6, solid_capstyle="butt", zorder=2)
            ax.plot(d, y, "o", ms=4.5, color=INK, mec="white", mew=0.6, zorder=5)
        ax.set_xlim(0.4, 1.0)
        ax.set_xticks([0.5, 0.75, 1.0], ["0.5", "0.75", "1"])
        ax.set_title(title)
        clean(ax, left=ax is axes[0])
    models(axes[0])
    handles = [Line2D([], [], lw=0, marker="o", ms=5, mfc="white", mec=MUTED, mew=1.2, label="mean probability"),
               Line2D([], [], lw=0, marker="o", ms=4.5, color=INK, mec="white", mew=0.6, label="share of top answers")]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(axes[0].get_position().x0, 1 - 0.06 / 2.75), ncol=2)
    save(fig, "fig-lean")


def bbq_categories():
    """BBQ questions without evidence, gender and eight other categories: the stereotyped share of committed answers."""
    w, h = TEXT, 3.0
    fig, ax = plt.subplots(figsize=(w, h))
    place(fig, left=1.0, right=0.04, top=0.4, bottom=0.66)
    xs = [j + 0.3 * (j > 0) for j in range(len(CATEGORIES))]  # gender, the category of the other figures, set apart
    for m, y in zip(analyze.MAIN, ROW):
        for cat, x in zip(CATEGORIES, xs):
            st, committed, _, share, (lo, hi) = bbq_share(m, cat)
            box = (x - 0.47, y - 0.44), 0.94, 0.88
            if committed < FEW:
                ax.add_patch(Rectangle(*box, fc="white", ec=AXIS, lw=0, hatch="//////"))
                ax.text(x, y, f"{st} of {committed}" if committed else "none", ha="center", va="center", fontsize=SMALL, color=INK2,
                        bbox={"fc": "white", "ec": "none", "pad": 0.8})
                continue
            colour = STEREO(share)
            ax.add_patch(Rectangle(*box, fc=colour, lw=0))
            # bold: the interval excludes 0.5 (no preference); an interval that is undefined excludes nothing
            ax.text(x, y, f"{share:.2f}", ha="center", va="center", fontsize=8, color=ink_on(colour),
                    fontweight="bold" if lo > 0.5 or hi < 0.5 else "normal")
    ax.set_xlim(xs[0] - 0.5, xs[-1] + 0.5)
    names = [{"Race_ethnicity": "Race/\nethnicity"}.get(c, c.replace("_", "\n")) for c in CATEGORIES]
    ax.set_xticks(xs, [t if "\n" in t else t + "\n " for t in names], fontsize=8, color=INK)
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", length=0, pad=3)
    models(ax)
    ax.set_ylim(ROW[-1] + 0.5, -0.5)
    for side in ax.spines:
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    # the key: the colour scale, and the hatching for cells with too few committed answers
    pos = ax.get_position()
    key = fig.add_axes([pos.x0, 0.2 / h, 1.9 / w, 0.09 / h])
    key.imshow([[i / 100 for i in range(101)]], cmap=STEREO, vmin=0, vmax=1, aspect="auto", extent=(0, 1, 0, 1))
    key.set_yticks([])
    key.set_xticks([0, 0.5, 1], ["0", "0.5", "1"])
    key.tick_params(axis="x", length=2, pad=1.5)
    for side in key.spines:
        key.spines[side].set_visible(False)
    key.set_title("Share naming the stereotyped person", fontsize=SMALL, color=INK2, pad=3)
    few = fig.add_axes([pos.x0 + 2.3 / w, 0.33 / h, 0.3 / w, 0.12 / h])
    few.add_patch(Rectangle((0, 0), 1, 1, fc="white", ec=AXIS, lw=0, hatch="//////"))
    few.set_axis_off()
    fig.text(pos.x0 + 2.68 / w, 0.39 / h, f"fewer than {FEW} name a person: stereotyped of those", fontsize=SMALL, color=INK2, va="center")
    fig.text(pos.x0 + 2.3 / w, 0.16 / h, "0.72", fontsize=8, fontweight="bold", color=INK, va="center")
    fig.text(pos.x0 + 2.68 / w, 0.16 / h, "bold: the 95% interval excludes 0.5", fontsize=SMALL, color=INK2, va="center")
    save(fig, "fig-bbq-categories")


def decision():
    """Decision task: how far the woman's and the non-binary person's request moves P(yes) from the man's, and how often
    the top answer differs from the man's; Jev's second pass shows how often it differs with nothing changed."""
    runs = analyze.DE_RUNS  # AutoTrust's distillations were not run on it
    pairs = {NUMS[m]["de"]["female"]["flips"]["n"] for m in runs}
    if len(pairs) != 1:
        raise ValueError(f"figures.py: the decision task has different numbers of pairs per model: {sorted(pairs)}")
    (pairs,) = pairs
    w, h = TEXT, 2.9
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(w, h), sharey=True, gridspec_kw={"width_ratios": [1, 1.1]})
    place(fig, left=1.0, right=0.08, top=0.72, bottom=0.27, wspace=0.12)
    groups = (("female", FEMALE, "o", -0.17, "woman"), ("non-binary", NONBINARY, "D", 0.17, "non-binary"))
    xs, rates, first = [], [], []
    for i, (m, y) in enumerate(zip(runs, rows(runs))):
        de = NUMS[m]["de"]
        for g, colour, marker, dy, name in groups:
            lo, hi = de[g]["diff_ci"]
            dot(a1, de[g]["diff"], lo, hi, y + dy, colour, marker, ms=4.5 if marker == "o" else 4)
            if i == 0:  # the first row names the two marks
                first.append((lo, hi, y + dy, name))
            xs += [lo, hi]
        f = de["female"]["flips"]
        to_yes, to_no = f["to_yes"] / pairs, f["to_no"] / pairs
        yy, hh = (y - 0.14, 0.3) if m == JEV else (y, 0.45)
        a2.barh(yy, to_yes, height=hh, color=FEMALE, edgecolor="white", linewidth=0.8)
        a2.barh(yy, to_no, left=to_yes, height=hh, color=FEMALE_LIGHT, edgecolor="white", linewidth=0.8)
        a2.text(to_yes + to_no, yy, f" {f['to_yes'] + f['to_no']}", va="center", fontsize=SMALL, color=INK)
        rates.append(to_yes + to_no)
        if m == JEV:  # Jev is not deterministic: the same requests sent again
            r = NUMS[REPEAT]["de_repeat"]
            a2.barh(y + 0.2, r["changed"] / r["n"], height=0.2, color=MUTED, edgecolor="white", linewidth=0.8)
            a2.text(r["changed"] / r["n"], y + 0.2, f" same requests again: {r['changed']} of {r['n']:,}", va="center", fontsize=SMALL, color=INK2)
            rates.append(r["changed"] / r["n"])
    reach = max(abs(x) for x in xs) * 1.15
    a1.set_xlim(-reach, reach)
    for lo, hi, y, name in first:
        right = reach - hi >= lo + reach
        a1.text(hi if right else lo, y, f"  {name}" if right else f"{name}  ", va="center", ha="left" if right else "right", fontsize=SMALL, color=INK2)
    a1.axvline(0, color=AXIS, lw=0.6, zorder=0)
    a1.set_title("Difference in logit P(yes)\nfrom the man’s request")
    a2.set_xlim(0, max(rates) * 1.45)
    a2.xaxis.set_major_formatter(lambda v, _: f"{100 * v:.0f}%")
    a2.set_title(f"Top answer differs from the man’s,\n% of {pairs:,} pairs")
    models(a1, runs)
    clean(a1, left=True)
    clean(a2)
    a1.legend(handles=[Line2D([], [], color=c, lw=1.2, marker=mk, ms=4.5 if mk == "o" else 4, mec="white", mew=0.6, label=f"{name} − man")
                       for _, c, mk, _, name in groups], loc="lower left", bbox_to_anchor=(0, 1 + 0.42 / (h - 0.99)), ncol=2)
    a2.legend(handles=[Patch(color=FEMALE, label="woman yes, man no"), Patch(color=FEMALE_LIGHT, label="woman no, man yes")],
              loc="lower left", bbox_to_anchor=(0, 1 + 0.42 / (h - 0.99)), ncol=2, handlelength=0.9)
    save(fig, "fig-decision")


if __name__ == "__main__":
    moral()
    classification()
    benchmarks()
    lean()
    bbq_categories()
    decision()
