---
name: youtube-transcript
description: Use when asked to get a transcript, extract key points, or summarize a YouTube video — given a YouTube URL.
metadata:
  version: 1.0.0
  display_name: YouTube Transcript
  tags: youtube, video, transcript, summary, yt, captions, watch, talk, webinar, lecture
---

## Goal

Pull the transcript from a YouTube video and produce the most useful artifact from it — clean transcript, structured notes, or a Slack-ready summary.

## Steps

1. **Receive the YouTube URL**. If none is provided, ask for it.
2. **Run the transcript script** (`scripts/get_transcript.py`) with the URL. The script uses `yt-dlp` to fetch auto-generated or manually-uploaded subtitle tracks (prefers manual/English; falls back to auto). Output: `{title, channel, duration_seconds, transcript_text, language}`.
3. **Choose the output mode** based on the request:
   - *Full transcript* → upload as a Slack file (plain text).
   - *Summary* → 3-4 sentence paragraph: what the video covers, the core argument or demo, key takeaway.
   - *Structured notes* → sections matching the video's natural breaks, with timestamps if present in the transcript.
   - *Action items* → for talks/webinars: decisions mentioned, questions raised, next steps named.
4. **Include the metadata header**: video title, channel, duration, language, URL.
5. **Flag transcript quality**: if the transcript is auto-generated (noted in output), mention that names and technical terms may be misheard.

## Rules

- No Whisper audio transcription — use only the subtitle tracks `yt-dlp` retrieves. If no subtitles exist, say so rather than transcribing manually or refusing silently.
- Do not fabricate transcript content.
- For videos over 2 hours, default to structured notes rather than full transcript unless the user asks explicitly.
- Private or geo-restricted videos will fail extraction — report the error clearly.
