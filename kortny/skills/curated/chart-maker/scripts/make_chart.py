#!/usr/bin/env python3
"""Render a single clean chart to PNG with matplotlib — sandbox-only.

One chart, one job. The script encodes the chart conventions Kortny commits
to so the output is presentation-grade by default:

  * axes are always labeled; the title states the takeaway, not the metric
  * no chart junk — no 3D, no gradients, no drop shadows
  * categorical comparisons default to a bar chart, never a pie (pies are
    only produced when explicitly requested AND the series has <= 5 slices)
  * a restrained palette and a light grid on the value axis only
  * thousands separators on numeric ticks; source line in the caption

Network is never required. Input is a JSON spec (``--spec``) or stdin;
output is a PNG path under the workbench dir.

Spec shape (see references/spec-format.md):

    {
      "type": "bar",            # bar | line | hbar | pie
      "title": "Signups doubled after the referral launch",
      "x_label": "Week", "y_label": "Signups",
      "labels": ["W1", "W2", "W3", "W4"],
      "series": [
        {"name": "Signups", "values": [120, 180, 240, 360]}
      ],
      "source": "Mixpanel, Apr 2026"
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless backend — never opens a window
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

# Colorblind-friendly, restrained palette (Okabe-Ito subset).
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00"]
PIE_MAX_SLICES = 5


def _thousands(x: float, _pos: int) -> str:
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    if x == int(x):
        return f"{int(x)}"
    return f"{x:g}"


def _apply_house_style(ax: Any, spec: dict[str, Any]) -> None:
    ax.set_title(
        spec.get("title", ""), fontsize=14, fontweight="bold", loc="left", pad=12
    )
    if spec.get("x_label"):
        ax.set_xlabel(spec["x_label"], fontsize=11)
    if spec.get("y_label"):
        ax.set_ylabel(spec["y_label"], fontsize=11)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=10)


def _render(spec: dict[str, Any]) -> Any:
    chart_type = spec.get("type", "bar")
    labels: list[str] = list(spec.get("labels", []))
    series: list[dict[str, Any]] = list(spec.get("series", []))
    if not series:
        raise ValueError("spec must include at least one series")

    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=144)

    if chart_type == "pie":
        values = series[0]["values"]
        if len(values) > PIE_MAX_SLICES:
            raise ValueError(
                f"pie charts are capped at {PIE_MAX_SLICES} slices; "
                "use a bar chart for more categories"
            )
        ax.pie(
            values,
            labels=labels,
            autopct="%1.0f%%",
            colors=PALETTE[: len(values)],
            startangle=90,
            counterclock=False,
        )
        ax.axis("equal")
        ax.set_title(spec.get("title", ""), fontsize=14, fontweight="bold", pad=12)
    elif chart_type == "line":
        for i, s in enumerate(series):
            ax.plot(
                labels,
                s["values"],
                marker="o",
                linewidth=2,
                color=PALETTE[i % len(PALETTE)],
                label=s.get("name", f"Series {i + 1}"),
            )
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.yaxis.set_major_formatter(FuncFormatter(_thousands))
        _apply_house_style(ax, spec)
        if len(series) > 1:
            ax.legend(frameon=False, fontsize=10)
    elif chart_type == "hbar":
        single = series[0]
        ax.barh(labels, single["values"], color=PALETTE[0])
        ax.grid(axis="x", linestyle="--", alpha=0.4)
        ax.xaxis.set_major_formatter(FuncFormatter(_thousands))
        ax.invert_yaxis()  # first category on top
        _apply_house_style(ax, spec)
    else:  # grouped/simple vertical bar
        n = len(series)
        width = 0.8 / max(n, 1)
        x = range(len(labels))
        for i, s in enumerate(series):
            offsets = [xi + (i - (n - 1) / 2) * width for xi in x]
            ax.bar(
                offsets,
                s["values"],
                width=width,
                color=PALETTE[i % len(PALETTE)],
                label=s.get("name", f"Series {i + 1}"),
            )
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.yaxis.set_major_formatter(FuncFormatter(_thousands))
        _apply_house_style(ax, spec)
        if n > 1:
            ax.legend(frameon=False, fontsize=10)

    source = spec.get("source")
    if source:
        fig.text(0.01, 0.01, f"Source: {source}", fontsize=8, color="#6b7280")

    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def build(spec: dict[str, Any], out_path: Path) -> Path:
    fig = _render(spec)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="png", bbox_inches="tight")
    plt.close(fig)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a clean chart to PNG.")
    parser.add_argument("--spec", help="path to a JSON spec file; omit to read stdin")
    parser.add_argument("--out", required=True, help="output .png path")
    args = parser.parse_args(argv)

    raw = Path(args.spec).read_text() if args.spec else sys.stdin.read()
    spec = json.loads(raw)
    out = build(spec, Path(args.out))
    print(f"wrote chart: {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
