---
name: slack-gif-creator
description: Use when asked to create an animated GIF — a looping animation, reaction GIF, progress indicator, or short visual clip — for posting in Slack.
metadata:
  version: 1.0.0
  display_name: Slack GIF Creator
  tags: gif, animation, animated, image, loop, reaction, visual, pillow, video
---

## Goal

Produce a GIF ready to upload to Slack — small file size, correct loop, transparent background where appropriate.

## Steps

1. **Clarify the request**: what should the GIF show? (Text animation, icon spin, progress bar, frame sequence?) What dimensions and duration? Default: 400×200px, 2s loop, 15fps.
2. **Choose the creation path**:
   - *Frame-based animation* (text, shapes, icons) → run `scripts/create_gif.py` with a JSON spec describing each frame.
   - *Video-to-GIF* → run `scripts/video_to_gif.py` with the input video file path (uses ffmpeg).
3. **Review the output**: check file size is under 2MB (Slack's upload limit for GIFs in most workspaces). If over, reduce fps or dimensions.
4. **Upload to Slack**: post the GIF file to the channel with a one-line caption. The file upload happens via the tool result.

## Script specs

- `scripts/create_gif.py` — inputs: `--spec frames.json` (list of frame configs: background color, text, font size, duration_ms), `--output out.gif`. Deps: Pillow. No network.
- `scripts/video_to_gif.py` — inputs: `--input video.mp4`, `--output out.gif`, optional `--fps 12`, `--width 400`, `--start 0`, `--duration 5`. Deps: ffmpeg (subprocess call). No network.

## Rules

- Output must be a valid GIF87a or GIF89a. Use Pillow's `save(..., loop=0)` for infinite loop.
- Palette: max 256 colors per frame. Dither if the source has gradients.
- Never include audio — GIFs are silent by definition.
- If the requested content is not achievable within the sandbox (e.g., live webcam capture), say so.
