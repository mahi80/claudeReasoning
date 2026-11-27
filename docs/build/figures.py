"""Draw the two diagrams used in the document and the README."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

NAVY, MID, GREY, GOLD = "#1F3A5F", "#3B6EA5", "#4B5563", "#C99A2E"
FILL_CORE, FILL_SIDE, FILL_EXT, FILL_ZONE = "#DCE8F5", "#EEF3F8", "#FBF1DC", "#F7F8FA"
plt.rcParams["font.family"] = "DejaVu Sans"


def box(ax, x, y, w, h, title, lines=(), fill=FILL_SIDE, edge=MID, lw=1.2,
        title_size=11.5, line_size=9.4, pitch=0.34):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=fill, ec=edge, lw=lw, zorder=2))
    top = y + h - 0.2
    ax.text(x + w / 2, top, title, ha="center", va="top", fontsize=title_size,
            fontweight="bold", color=NAVY, zorder=3)
    for i, line in enumerate(lines):
        ax.text(x + w / 2, top - 0.42 - i * pitch, line, ha="center", va="top",
                fontsize=line_size, color="#1C2733", zorder=3)


def arrow(ax, a, b, label="", both=False, offset=(0, 0.08), size=8.8):
    style = "<|-|>" if both else "-|>"
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=12, lw=1.4,
                                 color=GREY, zorder=1, shrinkA=2, shrinkB=2))
    if label:
        ax.text((a[0] + b[0]) / 2 + offset[0], (a[1] + b[1]) / 2 + offset[1], label,
                ha="center", va="bottom", fontsize=size, color=GREY, zorder=3)


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h), dpi=220)
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    return fig, ax


# ------------------------------------------------------------------ figure 1: the loop
fig, ax = canvas(9.4, 5.3)
box(ax, 0.15, 3.3, 1.3, 1.3, "User", ["task in,", "answer out"], fill=FILL_EXT, edge=GOLD)
box(ax, 1.95, 2.65, 4.25, 2.5, "Agent harness (Python)",
    ["1. build messages: rules, skills index, plan, task",
     "2. call the model with the tool schemas",
     "3. validate, approve and run each tool call",
     "4. append results, repeat until a plain answer",
     "compaction  ·  checkpoints  ·  step cap  ·  trace"],
    fill=FILL_CORE, edge=NAVY, lw=1.6)
box(ax, 7.4, 3.2, 1.85, 1.45, "Model server", ["vLLM on a GPU pod", "OpenAI-style API"],
    fill=FILL_EXT, edge=GOLD)
arrow(ax, (1.47, 3.95), (1.93, 3.95))
arrow(ax, (6.22, 4.25), (7.38, 4.25), "messages + tools", offset=(-0.03, 0.08), size=8.5)
arrow(ax, (7.38, 3.6), (6.22, 3.6), "text or tool calls", offset=(0, -0.33))

xs = [0.15, 2.45, 4.75, 7.05]
titles = ["Built-in tools", "MCP servers", "Skills", "Worker agents"]
lines = [["files and shell,", "inside a workspace"], ["your own systems", "behind one protocol"],
         ["one line each in the prompt,", "full text loaded on demand"],
         ["same loop, fresh context,", "only the report returns"]]
starts = [2.5, 3.5, 4.75, 5.7]
for x, t, ls, sx in zip(xs, titles, lines, starts):
    box(ax, x, 0.2, 2.1, 1.4, t, ls, line_size=8.9)
    arrow(ax, (sx, 2.63), (x + 1.05, 1.62), both=True)
ax.text(4.42, 2.02, "tool calls and results", ha="center", fontsize=8.8, color=GREY,
        bbox=dict(fc="white", ec="none", pad=1.5), zorder=4)
fig.savefig("docs/img/fig_loop.png", dpi=220, facecolor="white")
plt.close(fig)

# ------------------------------------------------------------------ figure 2: deployment
fig, ax = canvas(9.4, 5.3)
ax.add_patch(FancyBboxPatch((3.8, 1.6), 5.45, 3.55, boxstyle="round,pad=0.02,rounding_size=0.15",
                            fc=FILL_ZONE, ec="#9AA5B1", lw=1.1, ls=(0, (5, 3)), zorder=0))
ax.text(6.5, 5.04, "Runpod Secure Cloud data centre", ha="center", va="top", fontsize=10,
        color=GREY, style="italic")
box(ax, 0.15, 2.95, 2.65, 1.75, "Harness host",
    ["CPU pod or your own VM", "harness, chat UI, pod manager,", "sandbox workspace, traces"],
    fill=FILL_CORE, edge=NAVY, lw=1.6, line_size=9.0)
box(ax, 0.15, 0.45, 2.65, 1.4, "Users and your systems", ["tasks in, approvals,", "MCP servers"],
    fill=FILL_EXT, edge=GOLD)
box(ax, 4.0, 3.1, 2.3, 1.4, "Runpod HTTPS proxy",
    ["public URL per pod and port", "100-second idle limit"], line_size=9.0)
box(ax, 6.85, 2.95, 2.3, 1.75, "GPU pod (on-demand)",
    ["vLLM container", "port 8000, API key", "1 to 8 GPUs"], fill=FILL_CORE, edge=NAVY, lw=1.6)
box(ax, 6.85, 1.75, 2.3, 0.9, "Network volume", ["/workspace: weights, cache"], line_size=8.9)
box(ax, 6.85, 0.2, 2.3, 0.9, "Hugging Face Hub", ["first download of weights"],
    fill=FILL_EXT, edge=GOLD, line_size=8.9)
ax.text(5.2, 2.3, "GPU pods can also reach each other\nprivately at POD_ID.runpod.internal",
        ha="center", va="center", fontsize=8.5, color=GREY, style="italic", linespacing=1.5)
arrow(ax, (2.82, 3.82), (3.98, 3.82), "streamed", offset=(-0.08, 0.08))
arrow(ax, (6.32, 3.82), (6.83, 3.82))
arrow(ax, (1.47, 1.87), (1.47, 2.93), both=True)
arrow(ax, (8.0, 2.67), (8.0, 2.93), both=True)
arrow(ax, (8.0, 1.12), (8.0, 1.73))
ax.text(3.32, 3.74, "HTTPS", ha="center", va="top", fontsize=8.8, color=GREY)
fig.savefig("docs/img/fig_deploy.png", dpi=220, facecolor="white")
plt.close(fig)
print("figures written")
