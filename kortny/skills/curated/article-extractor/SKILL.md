---
name: article-extractor
description: Use when asked to extract, summarize, or pull the main content from a web article, blog post, or online document — producing a clean text version, key takeaways, or a structured brief ready to share in Slack.
metadata:
  version: 1.0.0
  display_name: Article Extractor
  tags: article, web, extract, url, scrape, summarize, content, read, brief, link
---

## Goal

Pull the real content from a URL and turn it into something useful — clean text, a summary, or a Slack-ready brief — without the navigation chrome, ads, or boilerplate.

## Steps

1. **Receive the URL**. If none is provided, ask for it.
2. **Run the extraction script** (`scripts/extract_article.py`) with the URL to retrieve clean article text via `trafilatura`. The script outputs JSON: `{title, author, date, url, text, word_count}`.
3. **Choose the output mode** based on the request:
   - *Full clean text* → post the extracted text as a Slack file upload (preferred for articles > 500 words).
   - *Key takeaways* → 3-5 bullets, each one sentence, covering the main argument, supporting evidence, and conclusion.
   - *Slack brief* → one-paragraph summary (3-4 sentences: what it covers, the core claim, why it matters) + 3 bullet takeaways.
4. **Include the metadata header** in all outputs: title, author (if found), publication date (if found), source URL.
5. **Note extraction quality**: if `trafilatura` returns less than 200 words, flag that the page may be paywalled, JavaScript-heavy, or extraction-resistant.

## Rules

- Never fabricate content. If extraction fails, say so and provide the URL for the user to read directly.
- Do not summarize from the URL slug or title alone — always extract first.
- Respect the extraction result: if the article is short, the summary is short. Do not pad.
- No Whisper or audio transcription — this skill is text-only. For audio/video content use `youtube-transcript`.
