"""
create_gif.py — generate an animated GIF from a JSON frame specification.

Usage:
    python create_gif.py --spec frames.json --output animation.gif

Frame spec format (frames.json):
    [
        {
            "width": 400,           # px (optional, defaults to first frame size or 400)
            "height": 200,          # px (optional, defaults to first frame size or 200)
            "bg": "#1a1a2e",        # background color (hex or named color)
            "text": "Hello!",       # text to draw (optional)
            "text_color": "#ffffff",
            "font_size": 32,
            "duration_ms": 500      # how long this frame shows (ms)
        },
        ...
    ]

Output: valid GIF89a, infinite loop, max 256 colors per frame.

Dependencies: Pillow (PIL)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _parse_color(color: str) -> tuple[int, int, int]:
    """Parse hex color string to RGB tuple."""
    color = color.strip().lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    if len(color) != 6:
        raise ValueError(f"Invalid color: #{color}")
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    return (r, g, b)


def _make_frame(
    spec: dict[str, Any],
    default_width: int,
    default_height: int,
) -> "Image":  # type: ignore[name-defined]
    from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-untyped]

    width = int(spec.get("width", default_width))
    height = int(spec.get("height", default_height))
    bg_raw = spec.get("bg", "#ffffff")
    bg_color = _parse_color(bg_raw) if bg_raw.startswith("#") else bg_raw  # type: ignore[assignment]

    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    text = spec.get("text", "")
    if text:
        text_color_raw = spec.get("text_color", "#000000")
        text_color = _parse_color(text_color_raw) if text_color_raw.startswith("#") else text_color_raw  # type: ignore[assignment]
        font_size = int(spec.get("font_size", 24))
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except (IOError, OSError):
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (width - text_w) // 2
        y = (height - text_h) // 2
        draw.text((x, y), text, fill=text_color, font=font)

    return img


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an animated GIF from a frame spec.")
    parser.add_argument("--spec", required=True, help="Path to JSON frame spec file.")
    parser.add_argument("--output", required=True, help="Path to write output GIF.")
    args = parser.parse_args()

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        sys.stderr.write("Pillow not installed. Run: pip install Pillow\n")
        sys.exit(1)

    spec_path = Path(args.spec)
    if not spec_path.exists():
        sys.stderr.write(f"Spec file not found: {args.spec}\n")
        sys.exit(1)

    frames_spec: list[dict[str, Any]] = json.loads(spec_path.read_text(encoding="utf-8"))
    if not frames_spec:
        sys.stderr.write("Frame spec is empty.\n")
        sys.exit(1)

    default_width = int(frames_spec[0].get("width", 400))
    default_height = int(frames_spec[0].get("height", 200))

    frames = []
    durations = []
    for i, spec in enumerate(frames_spec):
        try:
            frame = _make_frame(spec, default_width, default_height)
            frames.append(frame)
            durations.append(int(spec.get("duration_ms", 500)))
        except Exception as exc:
            sys.stderr.write(f"Error rendering frame {i}: {exc}\n")
            sys.exit(1)

    out_path = Path(args.output)
    frames[0].save(
        out_path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )

    size_kb = out_path.stat().st_size / 1024
    sys.stdout.write(
        f"GIF written: {out_path} ({len(frames)} frames, {size_kb:.1f} KB)\n"
    )
    if size_kb > 2048:
        sys.stderr.write(
            f"Warning: GIF is {size_kb:.0f} KB — over Slack's 2 MB limit. "
            "Reduce fps or dimensions.\n"
        )


if __name__ == "__main__":
    main()
