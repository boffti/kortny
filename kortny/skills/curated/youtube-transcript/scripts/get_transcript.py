"""
get_transcript.py — fetch subtitle/caption tracks from a YouTube video using yt-dlp.

Usage:
    python get_transcript.py --url https://www.youtube.com/watch?v=XXXXXXXXXXX
    python get_transcript.py --url https://youtu.be/XXXXXXXXXXX --output transcript.json

Output (stdout or file): JSON object with keys:
    title, channel, duration_seconds, transcript_text, language, auto_generated, url

Notes:
- Prefers manually-uploaded English subtitles; falls back to auto-generated captions.
- No audio download or Whisper transcription — subtitle tracks only.
- If no subtitles exist, exits with code 1 and an explanatory message.

Exit codes:
    0 — success
    1 — no subtitles available or yt-dlp error
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def _run_yt_dlp(url: str, tmpdir: str) -> dict[str, object]:
    """Download best available subtitle track and video metadata."""
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", "en",
        "--sub-format", "vtt",
        "--print-json",
        "--no-playlist",
        "-o", f"{tmpdir}/%(id)s.%(ext)s",
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed:\n{result.stderr.strip()}")

    # yt-dlp --print-json emits one JSON line per video
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)

    raise RuntimeError("yt-dlp produced no JSON output.")


def _find_vtt_file(tmpdir: str, video_id: str) -> tuple[Path, bool]:
    """
    Return (path, auto_generated) for the best subtitle file found.
    Prefers manual (.en.vtt) over auto-generated (.en-orig.vtt / .en.auto.vtt).
    """
    base = Path(tmpdir)
    candidates = sorted(base.glob(f"{video_id}*.vtt"))
    if not candidates:
        raise FileNotFoundError("No subtitle file written by yt-dlp.")

    # Prefer non-auto tracks
    manual = [p for p in candidates if "auto" not in p.name.lower() and "orig" not in p.name.lower()]
    if manual:
        return manual[0], False
    return candidates[0], True


def _parse_vtt(vtt_text: str) -> str:
    """Strip VTT timing lines and metadata, returning plain transcript text."""
    lines = vtt_text.splitlines()
    text_lines: list[str] = []
    prev = ""
    for line in lines:
        line = line.strip()
        # Skip WEBVTT header, NOTE blocks, timestamps, and blank lines
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("NOTE") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3} --> ", line):
            continue
        if re.match(r"^\d+$", line):
            continue
        # Strip VTT tags like <00:00:01.000><c> and </c>
        line = re.sub(r"<[^>]+>", "", line)
        if line and line != prev:
            text_lines.append(line)
            prev = line

    return " ".join(text_lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch YouTube transcript via yt-dlp.")
    parser.add_argument("--url", required=True, help="YouTube video URL.")
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write JSON output. Defaults to stdout.",
    )
    args = parser.parse_args()

    try:
        import yt_dlp  # noqa: F401 — just check it's installed
    except ImportError:
        sys.stderr.write("yt-dlp not installed. Run: pip install yt-dlp\n")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            meta = _run_yt_dlp(args.url, tmpdir)
        except RuntimeError as exc:
            sys.stderr.write(str(exc) + "\n")
            sys.exit(1)

        video_id: str = str(meta.get("id", "unknown"))
        title: str = str(meta.get("title", ""))
        channel: str = str(meta.get("channel", meta.get("uploader", "")))
        duration: int = int(meta.get("duration") or 0)

        try:
            vtt_path, auto_generated = _find_vtt_file(tmpdir, video_id)
        except FileNotFoundError:
            sys.stderr.write(
                "No subtitle tracks found for this video. "
                "The video may lack captions or be private/geo-restricted.\n"
            )
            sys.exit(1)

        vtt_text = vtt_path.read_text(encoding="utf-8", errors="replace")
        transcript_text = _parse_vtt(vtt_text)
        language = "en"

    output: dict[str, object] = {
        "title": title,
        "channel": channel,
        "duration_seconds": duration,
        "transcript_text": transcript_text,
        "language": language,
        "auto_generated": auto_generated,
        "url": args.url,
    }

    payload = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload)
        sys.stdout.write(f"Written to {args.output}\n")
    else:
        sys.stdout.write(payload)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
