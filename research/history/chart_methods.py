# Draws methods_per_year.png from methods_summary.csv (run from the repo root).
import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
t = pd.read_csv("research/history/methods_summary.csv")
short = {
 "Hold SPY (benchmark)": "Hold SPY (benchmark)", "Hold QQQ (Nasdaq 100)": "Hold QQQ",
 "Hold RSP (equal-weight S&P 500)": "Hold RSP (equal-weight S&P 500)",
 "SPY trend, daily 200-day rule": "SPY 200-day trend rule", "QQQ trend, daily 200-day rule": "QQQ 200-day trend rule",
 "SPY trend, monthly 10-month rule": "SPY 10-month trend rule", "Dual momentum (SPY / world / bonds)": "Dual momentum (SPY/world/bonds)",
 "Sector rotation, top 3": "Sector rotation, top 3", "Sector rotation, top 3 + trend filter": "Sector rotation + trend filter",
 "SPY dip-buying (RSI 2)": "SPY dip-buying (RSI 2)", "Fund momentum, top 3 of all funds": "Fund momentum, top 3",
 "Fund momentum, top 3 + trend filter": "Fund momentum + trend filter",
 "All stocks in the list, equal weight (survivor yardstick)": "All listed stocks, equal weight (yardstick)",
 "Stock momentum, top 10": "Stock momentum, top 10", "Stock momentum, top 20": "Stock momentum, top 20",
 "Stock momentum, top 10 + trend filter": "Stock momentum + trend filter",
 "Stock momentum, top 10, without the 10 biggest winners": "Stock momentum, minus 10 biggest winners",
 "Stock momentum, top 10, without the 25 biggest winners": "Stock momentum, minus 25 biggest winners",
 "Low-volatility stocks, 20": "Low-volatility stocks",
 "Bot trend rule, its watchlist": "BOT NOW: trend rule, its watchlist", "Bot dip rule, its watchlist": "BOT NOW: dip rule, its watchlist",
 "Bot trend rule, all stocks": "Bot trend rule, all stocks", "Bot dip rule, all stocks": "Bot dip rule, all stocks",
}
t["label"] = t["method"].map(short)
t["grp"] = t["kind"].map({"fund": 0, "stocks": 1, "fund+stocks": 2})
t = t.sort_values(["grp", "per_year_%"], ascending=[False, True]).reset_index(drop=True)
BLUE, ORANGE, INK, MUTED, SURF = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#fcfcfb"
n = len(t)
fig, ax = plt.subplots(figsize=(10, 9.2), dpi=150)
fig.patch.set_facecolor(SURF); ax.set_facecolor(SURF)
spy = float(t.loc[t["method"] == "Hold SPY (benchmark)", "per_year_%"].iloc[0])
ax.axvline(spy, color=MUTED, lw=1, ls="--", zorder=1)
ax.axvline(15.8, color=INK, lw=1, ls=":", zorder=1)
for i, row in t.iterrows():
    trusted = row["kind"] != "stocks"
    ax.barh(i, row["per_year_%"], height=0.72, color=BLUE if trusted else ORANGE,
            hatch=None if trusted else "///", edgecolor=SURF, linewidth=0, zorder=2)
    ax.text(row["per_year_%"] + 0.4, i, f'{row["per_year_%"]:.1f}%', va="center", fontsize=8.5, color=INK, zorder=3,
            bbox=dict(facecolor=SURF, edgecolor="none", pad=0.6))
ax.set_yticks(range(n)); ax.set_yticklabels(t["label"], fontsize=9, color=INK)
for lbl in ax.get_yticklabels():
    if lbl.get_text().startswith("BOT NOW"):
        lbl.set_fontweight("bold")
top = n - 0.2
ax.text(spy - 0.3, top, f"Hold SPY {spy:.1f}%/yr", color=MUTED, fontsize=8.5, ha="right", va="bottom")
ax.text(15.8 + 0.3, top, "Real momentum fund (MTUM) ≈16%/yr since 2013", color=INK, fontsize=8.5, ha="left", va="bottom")
ax.set_xlim(0, 46); ax.set_ylim(-0.7, n + 0.5)
ax.set_xlabel("Average % per year, Jan 2011 – Sep 2026 ($1,000 account, costs included)", color=MUTED, fontsize=9)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color("#cfcfcb"); ax.tick_params(axis="x", colors=MUTED, labelsize=8.5); ax.tick_params(axis="y", length=0)
ax.grid(axis="x", color="#e6e6e2", lw=0.6); ax.set_axisbelow(True)
ax.legend(handles=[Patch(color=BLUE, label="Funds, or the bot's own watchlist: trustworthy"),
                   Patch(facecolor=ORANGE, hatch="///", edgecolor=SURF, label="Picking stocks from today's survivors: flattered")],
          loc="upper right", bbox_to_anchor=(1.0, 0.93), frameon=False, fontsize=9)
ax.set_title("Which methods worked, 2011–2026", loc="left", fontsize=13, color=INK, fontweight="bold", pad=14)
fig.tight_layout(); fig.savefig("research/history/methods_per_year.png", facecolor=SURF)
