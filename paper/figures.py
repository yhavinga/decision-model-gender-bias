"""Draw the paper's four figures from results/figures.json (and, for the BBQ answer counts, results/<model>.jsonl).

    python3 paper/figures.py            # writes paper/figures/*.pdf and figures/*.png (the README's copies)

Run analyze.py first: every number comes from its output, none is typed in here except GPT-4's, which come from
analyze.py's copy of the paper's tables.
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import analyze  # noqa: E402

NUMS = json.loads((ROOT / "results" / "figures.json").read_text())
OUT_PDF, OUT_PNG = ROOT / "paper" / "figures", ROOT / "figures"

# the CUDA runs, one per decision model; the Mac runs are a platform check only
MODELS = {"pplx": ("pplx-decider-27b-artemis-cuda", "pplx 27B"), "clef": ("cloudflare_clef-flash-cuda", "clef-flash 9B"),
          "granite": ("granite-switch-4.1-8b", "granite-switch 8B"), "kev": ("kev-4b", "Kev 4B"), "d1": ("d1-3b", "d1 3B")}

# colours and ink of the reference palette (dataviz skill), on a white page
BLUE, GREY, AQUA, PALE = "#2a78d6", "#898781", "#1baf7a", "#dcdbd4"
INK, INK2, AXIS = "#0b0b0b", "#52514e", "#c3c2b7"
COL, TEXT = 3.03, 6.30  # ACL column and text width, inches

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"], "font.size": 7.5,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.6, "axes.labelcolor": INK2, "axes.titlesize": 8, "axes.titlecolor": INK,
    "xtick.color": AXIS, "xtick.labelcolor": INK2, "xtick.labelsize": 7, "xtick.major.size": 2.5, "xtick.major.width": 0.6,
    "ytick.labelcolor": INK, "ytick.labelsize": 7.5, "ytick.major.size": 0, "legend.fontsize": 7, "legend.frameon": False,
    "pdf.fonttype": 42, "savefig.dpi": 200,
})


def nums(slug):
    return NUMS[MODELS[slug][0]]


def clean(ax, left=False):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(axis="y", length=0, labelleft=left)


def save(fig, name, tight=True):
    OUT_PDF.mkdir(parents=True, exist_ok=True)
    OUT_PNG.mkdir(exist_ok=True)
    box = "tight" if tight else None
    fig.savefig(OUT_PDF / f"{name}.pdf", bbox_inches=box, pad_inches=0.02)
    fig.savefig(OUT_PNG / f"{name}.png", bbox_inches=box, pad_inches=0.05, facecolor="white")
    plt.close(fig)


def moral():
    """Study 2: the gap per act under the apocalypse, its mean over five stakes, and the vignette contrast."""
    gpt4 = {**analyze.PAPER_GAP, "vignette": analyze.PAPER_2D[("Amanda", "Adam")] - analyze.PAPER_2D[("Andrew", "Anna")]}
    acts = [("insult", "Insult"), ("harass", "Harassment"), ("abuse", "Abuse"), ("torture", "Torture"), ("vignette", "Vignette")]
    order = ["pplx", "clef", "granite", "kev", "d1"]
    fig, axes = plt.subplots(1, len(acts), figsize=(TEXT, 2.05), sharey=True, gridspec_kw={"wspace": 0.12})
    for k, (ax, (act, title)) in enumerate(zip(axes, acts)):
        ax.axvline(0, color=AXIS, lw=0.6, zorder=0)
        if act in gpt4:
            ax.plot(gpt4[act], 0, "o", ms=5, mfc="white", mec=GREY, mew=1.3)
        for j, slug in enumerate(order, start=1):
            n = nums(slug)
            v, (lo, hi) = (n["mixed"], n["mixed_ci"]) if act == "vignette" else (n[f"gap_{act}_stake"], n[f"gap_{act}_stake_ci"])
            if act != "vignette":
                ax.plot(n["gap_2e"][act]["pooled"], j, "|", ms=7, mew=1.2, color=GREY, zorder=2)
            ax.plot([lo, hi], [j, j], color=BLUE, lw=1.4, solid_capstyle="butt", zorder=3)
            ax.plot(v, j, "o", ms=4, color=BLUE, mec="white", mew=0.5, zorder=4)
        ax.axhline(0.5, color=PALE, lw=0.6)
        ax.set_xlim(-0.6, 5.0)
        ax.set_xticks([0, 2, 4])
        ax.set_title(title, pad=4)
        clean(ax, left=k == 0)
    axes[0].set_ylim(len(order) + 0.5, -0.5)
    axes[0].set_yticks(range(len(order) + 1), ["GPT-4 (paper)"] + [MODELS[s][1] for s in order])
    axes[0].get_yticklabels()[0].set_color(INK2)
    fig.supxlabel("Acceptability against a man minus against a woman (points on the 1–7 scale)", fontsize=7.5, color=INK2, y=-0.04)
    handles = [Line2D([], [], color=BLUE, lw=1.4, marker="o", ms=4, mec="white", mew=0.5, label="nuclear apocalypse, 95% interval"),
               Line2D([], [], color=GREY, lw=0, marker="|", ms=7, mew=1.2, label="mean over five stakes"),
               Line2D([], [], color=GREY, lw=0, marker="o", ms=5, mfc="white", mew=1.3, label="GPT-4, apocalypse")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.55, 0.99), ncol=3, handletextpad=0.4, columnspacing=1.6)
    save(fig, "fig-moral")


def classification():
    """Study 1 and 1u: top answers for the eight phrases without a gender cue, forced and with "can't tell"."""
    order = ["clef", "granite", "d1", "pplx", "kev"]
    parts = [("female", BLUE, "girl"), ("male", GREY, "boy"), ("non-binary", AQUA, "non-binary"), ("unknown", PALE, "can’t tell")]
    # drawn at the column width exactly (no tight bounding box), so its text prints at the size set here
    fig = plt.figure(figsize=(COL, 2.45))
    ax = fig.add_axes([0.025, 0.1, 0.83, 0.78])
    for i, slug in enumerate(order):
        forced, offered = nums(slug)["s1_labels"]["no gender cue"], nums(slug)["s1u"]["no gender cue"]
        ax.text(0, i - 0.27, MODELS[slug][1], ha="left", va="bottom", fontsize=7.5, color=INK)
        for row, (share, y) in enumerate(((forced, i - 0.1), (offered, i + 0.2))):
            left = 0.0
            for key, color, _ in parts:
                w = share.get(key, 0.0)
                if w:
                    ax.barh(y, w, left=left, height=0.27, color=color, edgecolor="white", linewidth=0.6)
                left += w
            ax.text(1.03, y, f"{100 * share['female']:.0f}%", va="center", ha="left", fontsize=7, color=INK if row == 0 else INK2)
    # the first pair says which bar is which
    ax.text(0.02, -0.1, "forced choice", ha="left", va="center", fontsize=6.5, color="white")
    ax.text(0.02, 0.2, "“can’t tell” offered", ha="left", va="center", fontsize=6.5, color=INK2)
    ax.text(1.03, -0.55, "girl", ha="left", va="bottom", fontsize=7, color=INK)
    ax.set_ylim(len(order) - 0.62, -0.55)
    ax.set_xlim(0, 1)
    ax.set_xticks([0, 0.5, 1], ["0", "50%", "100%"])
    clean(ax)
    ax.legend(handles=[Patch(color=c, label=lab) for _, c, lab in parts], loc="lower left", bbox_to_anchor=(0, 1.0), ncol=4,
              handlelength=0.9, handletextpad=0.35, columnspacing=0.9, borderaxespad=0.2)
    save(fig, "fig-classification", tight=False)


def bbq_counts(slug):
    """Ambiguous gender questions that have a stereotyped answer: how often the top answer names the stereotyped person,
    the other person, or "unknown"."""
    rows = [json.loads(line) for line in (ROOT / "results" / f"{MODELS[slug][0]}.jsonl").open()]
    cells = [c for c in analyze.bbq_cells([r for r in rows if r["study"] == "bbq"]) if c["condition"] == "ambig" and c["biased"] is not None]
    st = sum(c["choice"] == c["biased"] for c in cells)
    unk = sum(c["choice"] == c["unknown"] for c in cells)
    return st, len(cells) - st - unk, unk


def benchmarks():
    """StereoSet ss with its interval, and the BBQ answers to questions without evidence."""
    order = ["granite", "clef", "d1", "pplx", "kev"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(TEXT, 1.85), sharey=True, gridspec_kw={"width_ratios": [1, 1.25], "wspace": 0.14})
    for i, slug in enumerate(order):
        ss = nums(slug)["ss"]["both|all"]
        a1.plot(ss["ss_ci"], [i, i], color=GREY, lw=1.6, solid_capstyle="butt")
        a1.plot(ss["ss"], i, "o", ms=4.5, color=GREY, mec="white", mew=0.5)
        a1.text(ss["ss_ci"][1] + 0.8, i, f"{ss['ss']:.1f}", va="center", fontsize=7, color=INK2)
        st, ot, unk = bbq_counts(slug)
        total = st + ot + unk
        left = 0.0
        for n, color in ((st, BLUE), (ot, GREY), (unk, PALE)):
            a2.barh(i, n / total, left=left, height=0.55, color=color, edgecolor="white", linewidth=0.6)
            left += n / total
        a2.text(0.985, i, f"{100 * unk / total:.0f}%", va="center", ha="right", fontsize=7, color=INK2)
        a2.text(1.13, i, f"{100 * st / (st + ot):.0f}%", va="center", ha="center", fontsize=7.5, color=INK)
    a1.axvline(50, color=AXIS, lw=0.8, ls=(0, (3, 2)), zorder=0)
    a1.text(50.6, len(order) - 0.45, "50 = no preference", fontsize=6.5, color=INK2, va="bottom")
    a1.set_xlim(45, 85)
    a1.set_xticks([50, 60, 70, 80])
    a1.set_ylim(len(order) - 0.4, -0.6)
    a1.set_yticks(range(len(order)), [MODELS[s][1] for s in order])
    a1.set_title("StereoSet: stereotype preferred, % of items", loc="left", pad=4)
    a2.set_xlim(0, 1)
    a2.set_xticks([0, 0.5, 1], ["0", "50%", "100%"])
    a2.set_title("BBQ, no evidence: the top answer names …", loc="left", pad=4)
    a2.text(1.13, -0.55, "stereotyped\nof picks", ha="center", va="bottom", fontsize=6.5, color=INK, clip_on=False)
    clean(a1, left=True)
    clean(a2)
    a2.legend(handles=[Patch(color=BLUE, label="stereotyped person"), Patch(color=GREY, label="other person"), Patch(color=PALE, label="“unknown” (right)")],
              loc="upper left", bbox_to_anchor=(0.0, -0.13), ncol=3, handlelength=0.9, handletextpad=0.35, columnspacing=1.0)
    save(fig, "fig-benchmarks")


def lean():
    """Mean probability for the default or stereotyped option against the share of top answers that choose it."""
    order = ["clef", "granite", "d1", "pplx", "kev"]
    tasks = [("Uncued writing: “girl”", lambda n: (n["neutral_pf"], n["s1_labels"]["no gender cue"]["female"]
                                                     / (n["s1_labels"]["no gender cue"]["female"] + n["s1_labels"]["no gender cue"]["male"]))),
             ("BBQ picks: stereotyped person", lambda n: (n["bbq"]["all|mean"]["share"], n["bbq"]["all|modal"]["share"])),
             ("StereoSet: stereotyped sentence", lambda n: (n["ss"]["both|all"]["ss_soft"] / 100, n["ss"]["both|all"]["ss_modal"] / 100))]
    fig, axes = plt.subplots(1, 3, figsize=(TEXT, 1.75), sharey=True, gridspec_kw={"wspace": 0.1})
    for k, (ax, (title, get)) in enumerate(zip(axes, tasks)):
        ax.axvline(0.5, color=AXIS, lw=0.8, ls=(0, (3, 2)), zorder=0)
        for j, slug in enumerate(order):
            p, d = get(nums(slug))
            ax.plot([p, d], [j, j], color=BLUE, alpha=0.45, lw=1.6, solid_capstyle="butt")
            ax.plot(p, j, "o", ms=5, mfc="white", mec=GREY, mew=1.3)
            ax.plot(d, j, "o", ms=4.5, color=BLUE, mec="white", mew=0.5)
        ax.set_xlim(0.4, 1.0)
        ax.set_xticks([0.5, 0.75, 1.0], ["0.5", "0.75", "1"])
        ax.set_title(title, pad=4)
        clean(ax, left=k == 0)
    axes[0].set_ylim(len(order) - 0.5, -0.5)
    axes[0].set_yticks(range(len(order)), [MODELS[s][1] for s in order])
    handles = [Line2D([], [], color=GREY, lw=0, marker="o", ms=5, mfc="white", mew=1.3, label="mean probability"),
               Line2D([], [], color=BLUE, lw=0, marker="o", ms=4.5, mec="white", mew=0.5, label="share of top answers")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.55, 0.99), ncol=2, handletextpad=0.4, columnspacing=1.6)
    save(fig, "fig-lean")


if __name__ == "__main__":
    moral()
    classification()
    benchmarks()
    lean()
