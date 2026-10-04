"""Draw the deployed carry workflow as an editable, vector scientific figure.

Keeps the received Figure 1's four-colour topology, not its unimplemented
projection/guarantee claims. This script does not import or contact robot code.
"""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures"
W, H = 482.0, 550.0  # 170 mm wide; 9.6 pt becomes 9.03 pt at 160 mm width
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.2,
                     "pdf.fonttype": 42, "ps.fonttype": 42,
                     "mathtext.fontset": "dejavusans"})
fig = plt.figure(figsize=(W / 72, H / 72), facecolor="white")
ax = fig.add_axes([0, 0, 1, 1])
ax.set(xlim=(0, W), ylim=(H, 0))
ax.set_axis_off()
texts = []
COL = {"blue": ("#2E6EAB", "#EBF3FA"),
       "purple": ("#7555AA", "#F2EDF8"),
       "orange": ("#C26530", "#FCF1E9"),
       "green": ("#2F8060", "#EAF4EF")}


def yy(y):
    """Compact whitespace vertically without scaling typography or arrows."""
    old = (0, 8, 196, 210, 390, 404, 578, 596)
    new = (0, 8, 170, 184, 351, 365, 531, 550)
    for a, b, c, d in zip(old, old[1:], new, new[1:]):
        if a <= y <= b:
            return c + (y - a) * (d - c) / (b - a)
    raise ValueError(y)


def txt(x, y, text, *, size=9.2, bold=False, color="#202B35", ha="center"):
    obj = ax.text(x, yy(y), text, va="center", ha=ha, fontsize=max(9.6, size),
                  fontweight="bold" if bold else "normal", color=color,
                  linespacing=1.28)
    texts.append(obj)
    return obj


def panel(x, y, w, h, color, title):
    edge, fill = COL[color]
    ax.add_patch(Rectangle((x, yy(y)), w, yy(y+h)-yy(y), facecolor=fill,
                           edgecolor=edge, linewidth=0.8))
    ax.add_patch(Rectangle((x, yy(y)), 4, yy(y+h)-yy(y), facecolor=edge, edgecolor="none"))
    txt(x + 13, y + 14, title, size=10, bold=True, color=edge, ha="left")


def box(x, y, w, h, color, text=None, *, bold=False):
    edge = COL[color][0] if color in COL else color
    ax.add_patch(FancyBboxPatch((x, yy(y)), w, yy(y+h)-yy(y), boxstyle="round,pad=0,rounding_size=3",
                               linewidth=0.75, edgecolor=edge, facecolor="white"))
    if text:
        txt(x + w / 2, y + h / 2, text, bold=bold)


def arrow(x1, y1, x2, y2, color="#52616E", width=1):
    ax.add_patch(FancyArrowPatch((x1, yy(y1)), (x2, yy(y2)), arrowstyle="-|>",
                                mutation_scale=9, linewidth=width, color=color,
                                shrinkA=0, shrinkB=0))


# Camera geometry and semantic inference: parallel paths, not synchronous frames.
panel(8, 8, 228, 188, "blue", "A  RGB-D geometry")
panel(246, 8, 228, 188, "purple", "B  Asynchronous VLM")
box(21, 39, 202, 36, "blue", "RealSense D435i\nFixed camera; RGB + depth")
box(21, 89, 202, 39, "blue", "Foreground + depth support\nTask-object and robot masks")
box(21, 142, 202, 40, "blue", "Table homography + tracker\nSelected disc: centre c, radius r")
arrow(122, 75, 122, 89, COL["blue"][0])
arrow(122, 128, 122, 142, COL["blue"][0])
box(259, 39, 202, 36, "purple", "FastVLM-0.5B on laptop\nCount visible human hands")
box(259, 89, 202, 39, "purple", "Parsed count: 0 = OBJECT\nCount >= 1 = HUMAN")
box(259, 142, 202, 40, "purple", "Atomic frame-verdict bundle\nFrame ID; proxy; inference times")
arrow(223, 57, 259, 57, "#303A44")
arrow(360, 75, 360, 89, COL["purple"][0])
arrow(360, 128, 360, 142, COL["purple"][0])
arrow(122, 196, 122, 210, COL["blue"][0])
arrow(360, 196, 360, 210, COL["purple"][0])

# The exact stored-anchor implementation, not the redesigned offline recurrence.
panel(8, 210, 466, 180, "orange", "C  AEGIS: evidence age, score and margin")
box(21, 239, 215, 135, "orange")
box(246, 239, 215, 135, "orange")
txt(128.5, 252, "Evidence-linked score", bold=True)
txt(128.5, 273, r"$\tau=t-\widetilde{t}_{\mathrm{cap}}$", size=10)
txt(128.5, 294, r"$h_k=(1-\eta)h_{k-1}+\eta y_k$", size=10)
txt(128.5, 317, r"$p=P_0+(h_k-P_0)e^{-\max(0,\tau)/T_d}$", size=9.3)
txt(128.5, 340, r"$P_0=0.65,\ \eta=0.95,\ T_d=0.40\ \mathrm{s}$", size=9.2)
txt(128.5, 360, r"$y_k=1$ for HUMAN; 0 for OBJECT", size=9)
txt(353.5, 252, "Present-hazard intervention", bold=True)
txt(353.5, 273, r"$m=\beta+p(R-d)$", size=10)
txt(353.5, 293, r"$R=60,\ d=12,\ \beta=12\ \mathrm{mm}$", size=9.2)
txt(353.5, 313, r"AEGIS hold when $p\geq0.50$", size=9.2)
txt(353.5, 337, "Blob jump >50 mm: reset anchor;\ncached semantic verdict is retained", size=9)
txt(353.5, 360, "No detected hazard: score/margin = 0", size=9)
txt(241, 382, "Proxy = host request time - server-reported frame age", size=9,
    color=COL["orange"][0])
arrow(241, 390, 241, 404, COL["orange"][0])

# Shared planner and holds; output represents requested commands, not TCP sensing.
panel(8, 404, 466, 174, "green", "D  Shared carry controller: motion or hold")
box(21, 434, 215, 81, "green")
box(246, 434, 215, 81, "green")
txt(128.5, 446, "Shared hold checks", bold=True)
txt(128.5, 465, "Absent / invalid evidence or HUMAN", size=9)
txt(128.5, 482, "Geometric frame age >0.6 s", size=9)
txt(128.5, 499, "Confirmed depth-only / blocked goal", size=9)
txt(353.5, 446, "Otherwise: object-labelled route", bold=True, size=9.2)
txt(353.5, 465, r"Disc $r+m$; straight or cached detour", size=9)
txt(353.5, 482, "Planner: +35/70 mm; +18 mm padding", size=9)
txt(353.5, 499, "Per-step check: permit or HOLD", size=9)
arrow(236, 474, 246, 474, COL["green"][0], width=0.8)
box(21, 529, 215, 29, "#B34C43", "HOLD: no next carry increment", bold=True)
box(246, 529, 215, 29, "green", "If permitted: jog / pose command", bold=True)
arrow(128.5, 515, 128.5, 529, "#B34C43")
arrow(353.5, 515, 353.5, 529, COL["green"][0])
txt(241, 568, "Log: frame + evidence, age, score, command-state and decision", size=9)
txt(241, 590, "Monitored carry only; command-state is not a measured TCP trajectory.", size=9)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fig.canvas.draw()
    # Check for accidental page-edge clipping; visual QA is still required.
    renderer = fig.canvas.get_renderer()
    bounds = fig.bbox
    for text in texts:
        b = text.get_window_extent(renderer=renderer)
        assert b.x0 >= bounds.x0 and b.y0 >= bounds.y0, text.get_text()
        assert b.x1 <= bounds.x1 and b.y1 <= bounds.y1, text.get_text()
        assert text.get_fontsize() >= 9.6, text.get_text()
    pdf = OUT / "aegis_workflow.pdf"
    png = OUT / "aegis_workflow.png"
    fig.savefig(pdf, metadata={"Title": "Deployed AEGIS carry workflow",
                              "Subject": "Corrected hardware-only Figure 1"})
    fig.savefig(png, dpi=250)
    print(pdf)
    print(png)
    print(f"Native figure width: {W / 72 * 25.4:.2f} mm; minimum text: 9.6 pt")


if __name__ == "__main__":
    main()
