#!/usr/bin/env python3
"""
CodePen Advanced Scraper - CLI Version
Robust scraping with retry logic and multiple output formats.
"""

import asyncio
import json
import yaml
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from codepen_advanced_scraper import scrape_urls_with_retry, extract_pen_id, ScrapedPen


def load_urls(file_path: str) -> list[str]:
    """Load URLs from file."""
    try:
        with open(file_path, "r") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        return urls
    except FileNotFoundError:
        print(f"Error: File {file_path} not found")
        sys.exit(1)


def format_output(results: list[ScrapedPen], fmt: str) -> str:
    """Format results in specified format."""
    data = [r.to_dict() for r in results]

    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)

    elif fmt == "yaml":
        return yaml.dump(data, default_flow_style=False, allow_unicode=True)

    elif fmt == "markdown":
        md = "# CodePen Scraping Results\n\n"
        md += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        successes = sum(1 for r in results if r.success)
        md += f"## Summary\n- **Total:** {len(results)} pens\n- **Successful:** {successes}\n- **Failed:** {len(results) - successes}\n\n"

        md += "## Details\n\n"

        for r in results:
            status = "✓" if r.success else "✗"
            md += f"### {status} {r.name or 'Untitled'}\n\n"
            md += f"**URL:** {r.url}\n\n"

            if r.error:
                md += f"**Error:** {r.error}\n"
                if r.retries > 0:
                    md += f"**Retries:** {r.retries}\n"
            else:
                md += f"**Extracted:**\n"
                md += f"- HTML: {len(r.html):,} characters\n"
                md += f"- CSS: {len(r.css):,} characters\n"
                md += f"- JS: {len(r.js):,} characters\n"

            md += "\n"

        return md

    else:
        return str(data)


def progress_callback(msg: str):
    """Print progress messages."""
    print(f"  {msg}")


async def main():
    """CLI main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="CodePen Advanced Scraper - Extract code from CodePen projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python codepen_cli.py urls.txt --format json --output results.json
  python codepen_cli.py urls.txt --format yaml --output results.yaml
  python codepen_cli.py urls.txt --format markdown --output results.md --retries 3
        """,
    )

    parser.add_argument(
        "urls_file",
        help="File containing CodePen URLs (one per line)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["json", "yaml", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--retries",
        "-r",
        type=int,
        default=2,
        help="Max retries for failed URLs (default: 2)",
    )

    args = parser.parse_args()

    # Load URLs
    print(f"\nLoading URLs from {args.urls_file}...")
    urls = load_urls(args.urls_file)

    if not urls:
        print("No URLs found in file")
        sys.exit(1)

    # Remove duplicates
    unique_urls = list(dict.fromkeys(urls))
    removed = len(urls) - len(unique_urls)

    print(f"Loaded {len(unique_urls)} unique URLs" + (f" (removed {removed} duplicates)" if removed else ""))
    print(f"Output format: {args.format}")
    print(f"Max retries: {args.retries}")
    print("\nStarting scrape...\n")

    # Scrape
    try:
        results = await scrape_urls_with_retry(
            unique_urls,
            max_retries=args.retries,
            progress_callback=progress_callback,
        )
    except KeyboardInterrupt:
        print("\n\nScraping cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError during scraping: {e}")
        sys.exit(1)

    # Summary
    successes = sum(1 for r in results if r.success)
    print(f"\n{'='*60}")
    print(f"Complete: {successes}/{len(results)} successful ({successes/len(results)*100:.1f}%)")
    print(f"{'='*60}\n")

    # Format output
    output = format_output(results, args.format)

    # Save or print
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Results saved to: {args.output}")
        except Exception as e:
            print(f"Error saving file: {e}")
            sys.exit(1)
    else:
        print(output)


if __name__ == "__main__":
    asyncio.run(main())
