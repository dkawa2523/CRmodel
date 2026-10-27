"""Draw the implemented OESCR preparation, inverse loop, and result workflow."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.path import Path as MplPath

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs" / "oescr_paper" / "figures"
FONT = Path("C:/Windows/Fonts/YuGothM.ttc")
BOLD_FONT = Path("C:/Windows/Fonts/YuGothB.ttc")

BLUE = "#315e83"
BLUE_LIGHT = "#edf4fa"
GRAY = "#697b88"
BORDER = "#b9c5ce"
BACKGROUND = "#f7f9fb"
TEXT = "#203443"


def main() -> None:
    if not FONT.exists() or not BOLD_FONT.exists():
        raise FileNotFoundError("The diagram uses the Windows Yu Gothic fonts.")
    normal = font_manager.FontProperties(fname=str(FONT))
    bold = font_manager.FontProperties(fname=str(BOLD_FONT))
    plt.rcParams.update({
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "mathtext.fontset": "dejavusans",
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    })
    fig = plt.figure(figsize=(7.0, 7.95))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.set_axis_off()

    def text(x, y, label, *, size=10.8, weight="normal", color=TEXT, **kwargs):
        kwargs.setdefault("ha", "center")
        kwargs.setdefault("va", "center")
        return ax.text(x, y, label, fontsize=size,
                       fontproperties=bold if weight == "bold" else normal,
                       color=color, linespacing=1.35, **kwargs)

    def region(y, height, label):
        ax.add_patch(FancyBboxPatch((0.02, y), 0.96, height,
                                   boxstyle="round,pad=0,rounding_size=0.008",
                                   facecolor=BACKGROUND, edgecolor=BORDER,
                                   linewidth=0.9, zorder=0))
        text(0.045, y + height - 0.019, label, size=10.5, weight="bold",
             color=GRAY, ha="left")

    def box(x, y, width, height, label, *, highlight=False, size=10.8):
        ax.add_patch(FancyBboxPatch((x, y), width, height,
                                   boxstyle="round,pad=0,rounding_size=0.006",
                                   facecolor=BLUE_LIGHT if highlight else "white",
                                   edgecolor=BLUE if highlight else GRAY,
                                   linewidth=0.95, zorder=2))
        text(x + width / 2, y + height / 2, label, size=size, zorder=3)

    def arrow(points, *, color=BLUE, width=1.05):
        codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(points) - 1)
        ax.add_patch(FancyArrowPatch(path=MplPath(points, codes),
                                     arrowstyle="-|>", mutation_scale=10,
                                     linewidth=width, color=color, zorder=1))

    region(0.742, 0.249, "事前に一度準備")
    region(0.216, 0.511, "反復評価")
    region(0.014, 0.190, "最終出力・診断")

    box(0.06, 0.877, 0.41, 0.074,
        "物理・装置の入力\nプラズマ状態／反応データ／観測条件", highlight=True, size=10.5)
    box(0.53, 0.877, 0.41, 0.074,
        "測定・推定の入力\n測定スペクトル／推定対象・範囲", highlight=True, size=10.5)
    box(0.06, 0.758, 0.41, 0.095,
        "固定構造の準備\n状態・反応／格子・固有線形状\n視線・観測計画", size=10.5)
    box(0.53, 0.758, 0.41, 0.095,
        "測定の準備\nQC／fit窓／共分散", size=10.8)
    arrow([(0.265, 0.877), (0.265, 0.853)])
    arrow([(0.735, 0.877), (0.735, 0.853)])

    stages = [
        (0.653, "状態量の設定・更新"),
        (0.575, r"EEDF・速度係数 $k$ の計算"),
        (0.497, "定常CR・固有発光"),
        (0.419, "視線積分・装置応答・画素平均"),
        (0.341, r"重み付き残差 $\mathbf{r}$ の計算"),
        (0.263, "最適化：パラメータ更新"),
    ]
    height = 0.052
    for cy, label in stages:
        box(0.20, cy - height / 2, 0.58, height, label,
            highlight=cy in (0.653, 0.263))
    for (upper, _), (lower, _) in zip(stages, stages[1:]):
        arrow([(0.49, upper - height / 2), (0.49, lower + height / 2)])

    arrow([(0.265, 0.758), (0.265, 0.694), (0.49, 0.694), (0.49, 0.679)])
    arrow([(0.735, 0.758), (0.735, 0.741), (0.94, 0.741),
           (0.94, 0.341), (0.78, 0.341)], color=GRAY)
    text(0.855, 0.538, "測定値\n誤差モデル", size=10.5, color=GRAY)

    arrow([(0.20, 0.263), (0.065, 0.263), (0.065, 0.653), (0.20, 0.653)])
    text(0.113, 0.461, "未収束：状態量を更新", size=10.5, color=BLUE, rotation=90)

    arrow([(0.49, 0.237), (0.49, 0.167)])
    text(0.555, 0.228, "収束", size=10.5, color=BLUE)
    box(0.16, 0.112, 0.66, 0.055,
        "標準結果：物理量・予測・残差", highlight=True)
    arrow([(0.49, 0.112), (0.49, 0.087)])
    box(0.06, 0.022, 0.88, 0.065,
        "任意の最終診断\nSVD／profile／局所曲率／順解析品質", size=10.5)

    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "computation_flow.pdf")
    fig.savefig(OUT / "computation_flow.png", dpi=240)
    plt.close(fig)
    print(OUT / "computation_flow.pdf")


if __name__ == "__main__":
    main()
