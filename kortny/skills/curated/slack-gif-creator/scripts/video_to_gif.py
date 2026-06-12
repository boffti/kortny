"""
video_to_gif.py — convert a video clip to an animated GIF using ffmpeg.

Usage:
    python video_to_gif.py --input clip.mp4 --output animation.gif
    python video_to_gif.py --input clip.mp4 --output animation.gif \\
        --fps 12 --width 400 --start 5 --duration 8

Requirements:
    ffmpeg must be installed and on PATH.

Output: GIF89a, infinite loop, palette-optimized.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _check_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        sys.stderr.write(
            "ffmpeg not found on PATH. Install it via your package manager "
            "(e.g. apt install ffmpeg).\n"
        )
        sys.exit(1)


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(f"ffmpeg error:\n{result.stderr}\n")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a video clip to an animated GIF.")
    parser.add_argument("--input", required=True, help="Path to input video file.")
    parser.add_argument("--output", required=True, help="Path to write output GIF.")
    parser.add_argument("--fps", type=int, default=12, help="Output frames per second (default 12).")
    parser.add_argument("--width", type=int, default=400, help="Output width in pixels (default 400).")
    parser.add_argument("--start", type=float, default=0.0, help="Start time in seconds (default 0).")
    parser.add_argument("--duration", type=float, default=None, help="Duration in seconds (default: full clip).")
    args = parser.parse_args()

    _check_ffmpeg()

    in_path = Path(args.input)
    if not in_path.exists():
        sys.stderr.write(f"Input file not found: {args.input}\n")
        sys.exit(1)

    out_path = Path(args.output)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as pf:
        palette_path = pf.name

    # Build the palette filter
    time_args = ["-ss", str(args.start)]
    if args.duration is not None:
        time_args += ["-t", str(args.duration)]

    scale_filter = f"fps={args.fps},scale={args.width}:-1:flags=lanczos"

    # Step 1: generate palette for better color fidelity
    _run([
        "ffmpeg", "-y",
        *time_args,
        "-i", str(in_path),
        "-vf", f"{scale_filter},palettegen",
        palette_path,
    ])

    # Step 2: apply palette and output GIF
    _run([
        "ffmpeg", "-y",
        *time_args,
        "-i", str(in_path),
        "-i", palette_path,
        "-lavfi", f"{scale_filter} [x]; [x][1:v] paletteuse",
        str(out_path),
    ])

    Path(palette_path).unlink(missing_ok=True)

    size_kb = out_path.stat().st_size / 1024
    sys.stdout.write(
        f"GIF written: {out_path} ({size_kb:.1f} KB, {args.fps} fps, width={args.width}px)\n"
    )
    if size_kb > 2048:
        sys.stderr.write(
            f"Warning: GIF is {size_kb:.0f} KB — over Slack's 2 MB limit. "
            "Try reducing --fps, --width, or --duration.\n"
        )


if __name__ == "__main__":
    main()
