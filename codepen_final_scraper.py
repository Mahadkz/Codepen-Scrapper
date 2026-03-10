#!/usr/bin/env python3
"""
CodePen Scraper using Playwright.
Properly extracts code from CodeMirror editors.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


def extract_pen_id(url: str) -> Optional[tuple[str, str]]:
    """Return (username, pen_id) from a CodePen URL, or None."""
    url = url.strip().rstrip("/")
    m = re.search(
        r"codepen\.io/([^/]+)/(?:pen|full|debug|details)/([A-Za-z0-9]+)",
        url,
        re.IGNORECASE,
    )
    return (m.group(1), m.group(2)) if m else None


async def scrape_pen_playwright(url: str, browser) -> dict:
    """Scrape a single CodePen URL using Playwright."""
    result = {"url": url, "name": "", "html": "", "css": "", "js": "", "error": ""}

    ids = extract_pen_id(url)
    if not ids:
        result["error"] = "Could not parse pen URL"
        return result

    username, pen_id = ids

    context = None
    page = None

    try:
        # Create browser context with stealth mode
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ignore_https_errors=True,
        )

        page = await context.new_page()
        page.set_default_timeout(20000)

        # Add stealth script
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
              get: () => false,
            });
            window.chrome = { runtime: {} };
        """)

        # Navigate to the pen
        pen_url = f"https://codepen.io/{username}/pen/{pen_id}"
        try:
            await page.goto(pen_url, wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(2000)  # Extra wait for React
        except PlaywrightTimeoutError:
            result["error"] = "Page load timeout"
            return result
        except Exception as e:
            result["error"] = f"Navigation error: {str(e)}"
            return result

        # Extract pen name
        try:
            title = await page.title()
            result["name"] = re.sub(r"\s+on\s+CodePen.*$", "", title, flags=re.IGNORECASE).strip()
        except Exception:
            pass

        # Extract code from page
        code_data = await page.evaluate("""
            () => {
                let html = '', css = '', js = '';

                // Strategy 1: Look for CodeMirror editor content
                // CodeMirror stores content in div.cm-s-* with class cm-s-
                // The text is in spans with class cm-atom, cm-string, etc.
                const editors = document.querySelectorAll('.CodeMirror');
                console.log(`Found ${editors.length} CodeMirror editors`);

                if (editors.length >= 3) {
                    // Typically: HTML, CSS, JS in order
                    try {
                        // Get content from CodeMirror divs
                        // Each editor has a .CodeMirror-lines div containing the code
                        let editorIndex = 0;

                        editors.forEach(editor => {
                            // Get all text content from the editor
                            const content = editor.innerText || editor.textContent || '';

                            if (editorIndex === 0) {
                                html = content;
                            } else if (editorIndex === 1) {
                                css = content;
                            } else if (editorIndex === 2) {
                                js = content;
                            }
                            editorIndex++;
                        });
                    } catch (e) {
                        console.log('Error extracting from CodeMirror:', e);
                    }
                }

                // Strategy 2: Try to get from data attributes or hidden inputs
                if (!html) {
                    const dataElements = document.querySelectorAll('[data-html], [data-css], [data-js]');
                    dataElements.forEach(el => {
                        if (el.hasAttribute('data-html')) html = el.getAttribute('data-html');
                        if (el.hasAttribute('data-css')) css = el.getAttribute('data-css');
                        if (el.hasAttribute('data-js')) js = el.getAttribute('data-js');
                    });
                }

                // Strategy 3: Check for textarea elements with code
                if (!html) {
                    const textareas = document.querySelectorAll('textarea');
                    if (textareas.length >= 3) {
                        html = textareas[0].value || '';
                        css = textareas[1].value || '';
                        js = textareas[2].value || '';
                    }
                }

                return { html, css, js };
            }
        """)

        # Use extracted code
        if code_data.get("html") or code_data.get("css") or code_data.get("js"):
            result["html"] = code_data.get("html", "")
            result["css"] = code_data.get("css", "")
            result["js"] = code_data.get("js", "")
            return result

        # Fallback: Try to scrape the result iframe
        try:
            result_frame = await page.evaluate("""
                () => {
                    const iframe = document.querySelector('iframe[title*="result"], iframe[name*="result"], [data-name="result"]');
                    if (!iframe) return null;

                    try {
                        const doc = iframe.contentDocument || iframe.contentWindow.document;
                        if (!doc) return null;

                        const html = doc.documentElement.innerHTML;
                        const styles = Array.from(doc.querySelectorAll('style')).map(s => s.textContent).join('\\n');
                        const scripts = Array.from(doc.querySelectorAll('script')).map(s => s.textContent).join('\\n');

                        return { html, css: styles, js: scripts };
                    } catch (e) {
                        return null;
                    }
                }
            """)

            if result_frame and result_frame.get("html"):
                result["html"] = result_frame.get("html", "")
                result["css"] = result_frame.get("css", "")
                result["js"] = result_frame.get("js", "")
                return result
        except Exception as e:
            pass

        result["error"] = "Could not extract code from page"
        return result

    except Exception as e:
        result["error"] = str(e)
        return result

    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass


async def scrape_urls(urls: list[str], output_file: str = "codepen_output.json"):
    """Scrape multiple CodePen URLs."""
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )

        try:
            for i, url in enumerate(urls, 1):
                print(f"\n[{i}/{len(urls)}] {url}")
                result = await scrape_pen_playwright(url, browser)
                results.append(result)

                # Print status
                if result["error"]:
                    print(f"  [ERROR] {result['error']}")
                else:
                    code_summary = []
                    if result["html"]:
                        code_summary.append(f"HTML:{len(result['html'])} chars")
                    if result["css"]:
                        code_summary.append(f"CSS:{len(result['css'])} chars")
                    if result["js"]:
                        code_summary.append(f"JS:{len(result['js'])} chars")
                    summary = ", ".join(code_summary) if code_summary else "No code"
                    pen_name = result["name"].encode('ascii', 'ignore').decode('ascii') or "[No Name]"
                    print(f"  [OK] {pen_name} | {summary}")

                # Small delay between requests
                await asyncio.sleep(0.3)

        finally:
            await browser.close()

    # Save results
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Summary
    successes = sum(1 for r in results if not r["error"])
    errors = len(results) - successes
    print(f"\n{'='*60}")
    print(f"Completed: {successes}/{len(results)} successful")
    if errors:
        print(f"Errors: {errors}")
    print(f"Saved to: {output_file}")
    print(f"{'='*60}")

    return results


async def main():
    """Load URLs from urls.txt and scrape them."""
    urls_file = Path(__file__).parent / "urls.txt"

    if not urls_file.exists():
        print(f"Error: {urls_file} not found")
        return

    # Read URLs
    urls = []
    with open(urls_file, "r") as f:
        for line in f:
            url = line.strip()
            if url and not url.startswith("#"):
                urls.append(url)

    # Remove duplicates
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    print(f"Loaded {len(unique_urls)} unique URLs from {urls_file}")
    if len(urls) > len(unique_urls):
        print(f"(Removed {len(urls) - len(unique_urls)} duplicates)")

    if not unique_urls:
        print("No URLs to scrape")
        return

    # Scrape
    await scrape_urls(unique_urls, output_file="codepen_output.json")


if __name__ == "__main__":
    asyncio.run(main())
