"""
extract_article.py — pull clean article text from a URL using trafilatura.

Usage:
    python extract_article.py --url https://example.com/article
    python extract_article.py --url https://example.com/article --output article.json

Output (stdout or file): JSON object with keys:
    title, author, date, url, text, word_count

Exit codes:
    0 — success
    1 — extraction failed or returned < 50 chars
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract article text from a URL.")
    parser.add_argument("--url", required=True, help="URL of the article to extract.")
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write JSON output. Defaults to stdout.",
    )
    args = parser.parse_args()

    try:
        import trafilatura  # type: ignore[import-untyped]
    except ImportError:
        sys.stderr.write(
            "trafilatura not installed. Run: pip install trafilatura\n"
        )
        sys.exit(1)

    downloaded = trafilatura.fetch_url(args.url)
    if not downloaded:
        sys.stderr.write(f"Could not fetch URL: {args.url}\n")
        sys.exit(1)

    result = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=True,
        output_format="python",
        with_metadata=True,
        favor_precision=True,
    )

    if result is None:
        sys.stderr.write(
            "trafilatura returned no content. Page may be paywalled or JS-heavy.\n"
        )
        sys.exit(1)

    # trafilatura returns a dict when output_format="python" with with_metadata=True
    if isinstance(result, dict):
        text: str = result.get("text") or ""
        title: str = result.get("title") or ""
        author: str = result.get("author") or ""
        pub_date: str = result.get("date") or ""
    else:
        # plain text string (older trafilatura versions)
        text = str(result)
        title = ""
        author = ""
        pub_date = ""

    if len(text) < 50:
        sys.stderr.write(
            f"Extraction returned very little text ({len(text)} chars). "
            "Page may be paywalled or extraction-resistant.\n"
        )
        sys.exit(1)

    output: dict[str, str | int] = {
        "title": title,
        "author": author,
        "date": pub_date,
        "url": args.url,
        "text": text,
        "word_count": len(text.split()),
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
