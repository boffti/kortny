# Provenance

**Concept source**: anthropics/skills (slack-gif-creator skill concept)
**Script authorship**: Original (clean-room rewrite)
**Adaptation date**: 2026-06-12
**Adapted by**: Agent A (HIG-239)

## What was adapted

The SKILL.md was written fresh. The scripts (`create_gif.py`, `video_to_gif.py`) are original implementations — no code was copied from the upstream source. The upstream skill's scope (Pillow + ffmpeg GIF creation for Slack upload) informed the feature set, but all implementation is clean-room.

Reason for fresh authoring: the upstream source is proprietary (anthropics internal). Conservative approach is to write from scratch.

## Script dependencies

- `create_gif.py`: Pillow only (stdlib + Pillow)
- `video_to_gif.py`: ffmpeg via subprocess (no Python imaging dep; ffmpeg must be installed)

Both scripts: argparse, file-in/file-out, no network access.

## Slack-first adaptations

- Output targets Slack file upload with size warning at 2MB threshold.
- No webcam or screen-capture capabilities (sandbox constraint noted explicitly).
- File path assumptions use workbench paths, not local development paths.

## License

Original concept source is proprietary — this skill and scripts are a clean-room rewrite.
This file and all files in this directory are subject to the Kortny project license.
