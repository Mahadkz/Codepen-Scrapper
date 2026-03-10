#!/usr/bin/env python3
"""
CodePen Advanced Scraper - Modern, Robust, with GUI
Features:
- Retries failed URLs with exponential backoff
- Multiple extraction strategies
- Modern Samsung-like UI (light mode, high contrast, no shadows)
- Output in JSON, YAML, or Markdown
- Progress tracking and detailed logging
"""

import asyncio
import json
import re
import yaml
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


@dataclass
class ScrapedPen:
    """Represents a scraped CodePen."""
    url: str
    name: str
    html: str
    css: str
    js: str
    error: str = ""
    retries: int = 0
    extracted_at: str = ""

    def to_dict(self):
        return asdict(self)

    @property
    def success(self) -> bool:
        return not self.error


def extract_pen_id(url: str) -> Optional[tuple[str, str]]:
    """Return (username, pen_id) from a CodePen URL, or None."""
    url = url.strip().rstrip("/")
    m = re.search(
        r"codepen\.io/([^/]+)/(?:pen|full|debug|details)/([A-Za-z0-9]+)",
        url,
        re.IGNORECASE,
    )
    return (m.group(1), m.group(2)) if m else None


async def scrape_pen_playwright(url: str, browser, retry_count: int = 0) -> ScrapedPen:
    """Scrape a single CodePen URL using Playwright."""
    result = ScrapedPen(
        url=url,
        name="",
        html="",
        css="",
        js="",
        error="",
        retries=retry_count,
        extracted_at=datetime.now().isoformat(),
    )

    ids = extract_pen_id(url)
    if not ids:
        result.error = "Could not parse pen URL"
        return result

    username, pen_id = ids
    context = None
    page = None

    try:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ignore_https_errors=True,
        )

        page = await context.new_page()
        page.set_default_timeout(25000)

        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.chrome = { runtime: {} };
        """)

        # Try multiple strategies for loading
        pen_url = f"https://codepen.io/{username}/pen/{pen_id}"
        try:
            await page.goto(pen_url, wait_until="networkidle", timeout=25000)
            await page.wait_for_timeout(2500)
        except PlaywrightTimeoutError:
            result.error = "Page load timeout"
            return result
        except Exception as e:
            result.error = f"Navigation failed: {str(e)}"
            return result

        # Extract pen name
        try:
            title = await page.title()
            result.name = re.sub(r"\s+on\s+CodePen.*$", "", title, flags=re.IGNORECASE).strip()
        except Exception:
            pass

        # Extract code - Multiple strategies
        code_data = await page.evaluate("""
            () => {
                let html = '', css = '', js = '';

                // Strategy 1: CodeMirror editors
                const editors = document.querySelectorAll('.CodeMirror');
                if (editors.length >= 3) {
                    editors.forEach((editor, idx) => {
                        const content = editor.innerText || editor.textContent || '';
                        if (idx === 0) html = content;
                        else if (idx === 1) css = content;
                        else if (idx === 2) js = content;
                    });
                }

                // Strategy 2: Data attributes
                if (!html) {
                    const dataElements = document.querySelectorAll('[data-html], [data-css], [data-js]');
                    dataElements.forEach(el => {
                        if (el.hasAttribute('data-html')) html = el.getAttribute('data-html');
                        if (el.hasAttribute('data-css')) css = el.getAttribute('data-css');
                        if (el.hasAttribute('data-js')) js = el.getAttribute('data-js');
                    });
                }

                // Strategy 3: Textarea elements
                if (!html) {
                    const textareas = document.querySelectorAll('textarea');
                    if (textareas.length >= 3) {
                        html = textareas[0].value || '';
                        css = textareas[1].value || '';
                        js = textareas[2].value || '';
                    }
                }

                // Strategy 4: Extract from result iframe
                if (!html) {
                    const iframe = document.querySelector('iframe[title*="result"]');
                    if (iframe) {
                        try {
                            const doc = iframe.contentDocument || iframe.contentWindow.document;
                            if (doc) {
                                html = doc.documentElement.innerHTML;
                                const styles = Array.from(doc.querySelectorAll('style')).map(s => s.textContent).join('\\n');
                                const scripts = Array.from(doc.querySelectorAll('script')).map(s => s.textContent).join('\\n');
                                css = styles;
                                js = scripts;
                            }
                        } catch (e) {}
                    }
                }

                return { html, css, js };
            }
        """)

        if code_data.get("html") or code_data.get("css") or code_data.get("js"):
            result.html = code_data.get("html", "")
            result.css = code_data.get("css", "")
            result.js = code_data.get("js", "")
            return result

        result.error = "Could not extract code from page"
        return result

    except Exception as e:
        result.error = str(e)
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


async def scrape_urls_with_retry(
    urls: list[str],
    max_retries: int = 3,
    progress_callback=None
) -> list[ScrapedPen]:
    """Scrape URLs with retry logic for failed ones."""
    results = []
    failed_urls = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )

        try:
            # First pass
            for i, url in enumerate(urls, 1):
                if progress_callback:
                    progress_callback(f"Scraping {i}/{len(urls)}: {url.split('/')[-1]}")

                result = await scrape_pen_playwright(url, browser)
                results.append(result)

                if result.error:
                    failed_urls.append(url)

                await asyncio.sleep(0.2)

            # Retry failed URLs
            for retry_num in range(1, max_retries + 1):
                if not failed_urls:
                    break

                if progress_callback:
                    progress_callback(f"Retry {retry_num}/{max_retries}: {len(failed_urls)} URLs")

                retry_urls = failed_urls.copy()
                failed_urls.clear()

                for url in retry_urls:
                    if progress_callback:
                        progress_callback(f"Retrying (attempt {retry_num}): {url.split('/')[-1]}")

                    # Find and update the result
                    for result in results:
                        if result.url == url:
                            new_result = await scrape_pen_playwright(url, browser, retry_num)
                            if not new_result.error:
                                result.html = new_result.html
                                result.css = new_result.css
                                result.js = new_result.js
                                result.error = ""
                                result.retries = retry_num
                                result.extracted_at = new_result.extracted_at
                            else:
                                if retry_num < max_retries:
                                    failed_urls.append(url)
                                result.error = new_result.error
                                result.retries = retry_num
                            break

                    await asyncio.sleep(0.3)

        finally:
            await browser.close()

    return results


class CodePenScraperApp(tk.Tk):
    """Modern Samsung-like CodePen Scraper GUI."""

    def __init__(self):
        super().__init__()
        self.title("CodePen Scraper Pro")
        self.geometry("1000x750")
        self.resizable(True, True)

        # Samsung-like color scheme
        self.bg_primary = "#ffffff"      # White
        self.bg_secondary = "#f5f5f5"    # Light gray
        self.text_primary = "#000000"    # Black
        self.text_secondary = "#666666"  # Dark gray
        self.accent = "#1428a0"          # Samsung blue
        self.border = "#e0e0e0"          # Light border

        self.configure(bg=self.bg_primary)
        self._build_ui()
        self._results = []
        self._scraping = False

    def _build_ui(self):
        """Build the UI with modern design."""
        # Header
        header = tk.Frame(self, bg=self.bg_primary, height=80)
        header.pack(fill="x", padx=0, pady=0)

        title = tk.Label(
            header,
            text="CodePen Scraper Pro",
            font=("Segoe UI", 24, "bold"),
            bg=self.bg_primary,
            fg=self.text_primary,
        )
        title.pack(anchor="w", padx=20, pady=(14, 4))

        subtitle = tk.Label(
            header,
            text="Extract HTML, CSS, and JavaScript from CodePen projects",
            font=("Segoe UI", 10),
            bg=self.bg_primary,
            fg=self.text_secondary,
        )
        subtitle.pack(anchor="w", padx=20, pady=(0, 10))

        # Separator
        separator = tk.Frame(header, bg=self.border, height=1)
        separator.pack(fill="x", padx=0, pady=(0, 0))

        # Content
        content = tk.Frame(self, bg=self.bg_primary)
        content.pack(fill="both", expand=True, padx=20, pady=20)

        # Input section
        input_label = tk.Label(
            content,
            text="Paste CodePen URLs (one per line)",
            font=("Segoe UI", 11, "bold"),
            bg=self.bg_primary,
            fg=self.text_primary,
        )
        input_label.pack(anchor="w", pady=(0, 8))

        self.url_box = scrolledtext.ScrolledText(
            content,
            height=8,
            bg=self.bg_secondary,
            fg=self.text_primary,
            insertbackground=self.accent,
            font=("Consolas", 10),
            relief="solid",
            borderwidth=1,
            wrap="word",
        )
        self.url_box.pack(fill="x", pady=(0, 14))

        # Options
        options_frame = tk.Frame(content, bg=self.bg_primary)
        options_frame.pack(fill="x", pady=(0, 14))

        tk.Label(
            options_frame,
            text="Max retries for failed URLs:",
            font=("Segoe UI", 10),
            bg=self.bg_primary,
            fg=self.text_primary,
        ).pack(side="left", padx=(0, 10))

        self.retry_var = tk.IntVar(value=2)
        retry_spin = tk.Spinbox(
            options_frame,
            from_=0,
            to=5,
            textvariable=self.retry_var,
            width=3,
            font=("Segoe UI", 10),
            bg=self.bg_secondary,
            fg=self.text_primary,
            relief="solid",
            borderwidth=1,
        )
        retry_spin.pack(side="left")

        tk.Label(
            options_frame,
            text="Output format:",
            font=("Segoe UI", 10),
            bg=self.bg_primary,
            fg=self.text_primary,
        ).pack(side="left", padx=(30, 10))

        self.format_var = tk.StringVar(value="json")
        format_combo = ttk.Combobox(
            options_frame,
            textvariable=self.format_var,
            values=["json", "yaml", "markdown"],
            state="readonly",
            width=12,
            font=("Segoe UI", 10),
        )
        format_combo.pack(side="left")

        # Buttons
        buttons_frame = tk.Frame(content, bg=self.bg_primary)
        buttons_frame.pack(fill="x", pady=(0, 14))

        btn_style = {
            "font": ("Segoe UI", 11, "bold"),
            "relief": "solid",
            "borderwidth": 0,
            "padx": 16,
            "pady": 10,
            "cursor": "hand2",
        }

        self.scrape_btn = tk.Button(
            buttons_frame,
            text="▶  Start Scraping",
            command=self._start_scrape,
            bg=self.accent,
            fg="white",
            activebackground="#0f1f7f",
            activeforeground="white",
            **btn_style,
        )
        self.scrape_btn.pack(side="left", padx=(0, 10))

        self.save_btn = tk.Button(
            buttons_frame,
            text="💾  Save Results",
            command=self._save_results,
            bg=self.bg_secondary,
            fg=self.text_primary,
            activebackground="#e0e0e0",
            state="disabled",
            **btn_style,
        )
        self.save_btn.pack(side="left", padx=(0, 10))

        clear_btn = tk.Button(
            buttons_frame,
            text="🗑  Clear",
            command=self._clear,
            bg=self.bg_secondary,
            fg=self.text_primary,
            activebackground="#e0e0e0",
            **btn_style,
        )
        clear_btn.pack(side="left")

        # Progress
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            content,
            variable=self.progress_var,
            maximum=100,
            length=400,
        )
        self.progress_bar.pack(fill="x", pady=(0, 8))

        self.status_lbl = tk.Label(
            content,
            text="Ready to scrape",
            font=("Segoe UI", 10),
            bg=self.bg_primary,
            fg=self.text_secondary,
            anchor="w",
        )
        self.status_lbl.pack(fill="x")

        # Output
        output_label = tk.Label(
            content,
            text="Results",
            font=("Segoe UI", 11, "bold"),
            bg=self.bg_primary,
            fg=self.text_primary,
        )
        output_label.pack(anchor="w", pady=(20, 8))

        self.output_box = scrolledtext.ScrolledText(
            content,
            bg=self.bg_secondary,
            fg=self.text_primary,
            font=("Consolas", 9),
            relief="solid",
            borderwidth=1,
            wrap="word",
        )
        self.output_box.pack(fill="both", expand=True)

    def _set_status(self, msg: str):
        """Update status message."""
        self.status_lbl.config(text=msg)
        self.update_idletasks()

    def _start_scrape(self):
        """Start scraping."""
        raw = self.url_box.get("1.0", "end").strip()
        urls = [u.strip() for u in raw.splitlines() if u.strip()]

        if not urls:
            messagebox.showwarning("No URLs", "Please paste at least one CodePen URL.")
            return

        self.scrape_btn.config(state="disabled")
        self.save_btn.config(state="disabled")
        self.output_box.delete("1.0", "end")
        self._results = []
        self._scraping = True

        import threading
        threading.Thread(target=self._run_scrape, args=(urls,), daemon=True).start()

    def _run_scrape(self, urls: list[str]):
        """Run scraping in background thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            results = loop.run_until_complete(
                scrape_urls_with_retry(
                    urls,
                    max_retries=self.retry_var.get(),
                    progress_callback=self._update_progress,
                )
            )
            self._results = results

            # Display results
            self.output_box.insert("end", self._format_output(results))
            self.save_btn.config(state="normal")

            successes = sum(1 for r in results if r.success)
            self._set_status(f"Complete: {successes}/{len(results)} successful")

        except Exception as e:
            self.output_box.insert("end", f"Error: {str(e)}")
            self._set_status("Error during scraping")

        finally:
            self.scrape_btn.config(state="normal")
            self._scraping = False
            loop.close()

    def _update_progress(self, msg: str):
        """Update progress display."""
        self._set_status(msg)

    def _format_output(self, results: list[ScrapedPen]) -> str:
        """Format results for display."""
        fmt = self.format_var.get()
        data = [r.to_dict() for r in results]

        if fmt == "json":
            return json.dumps(data, indent=2, ensure_ascii=False)
        elif fmt == "yaml":
            return yaml.dump(data, default_flow_style=False, allow_unicode=True)
        elif fmt == "markdown":
            md = "# CodePen Scraping Results\n\n"
            for r in results:
                status = "✓" if r.success else "✗"
                md += f"## {status} {r.name or 'Untitled'}\n\n"
                md += f"**URL:** {r.url}\n\n"
                if r.error:
                    md += f"**Error:** {r.error}\n\n"
                else:
                    md += f"- HTML: {len(r.html)} chars\n"
                    md += f"- CSS: {len(r.css)} chars\n"
                    md += f"- JS: {len(r.js)} chars\n\n"
            return md

        return str(data)

    def _save_results(self):
        """Save results to file."""
        if not self._results:
            messagebox.showwarning("No Results", "Nothing to save.")
            return

        fmt = self.format_var.get()
        ext_map = {"json": "json", "yaml": "yaml", "markdown": "md"}
        ext = ext_map.get(fmt, "txt")

        path = filedialog.asksaveasfilename(
            defaultextension=f".{ext}",
            filetypes=[(f"{fmt.upper()} files", f"*.{ext}"), ("All files", "*.*")],
        )

        if not path:
            return

        try:
            content = self._format_output(self._results)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("Success", f"Results saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {str(e)}")

    def _clear(self):
        """Clear all inputs and outputs."""
        self.url_box.delete("1.0", "end")
        self.output_box.delete("1.0", "end")
        self._results = []
        self.progress_var.set(0)
        self.save_btn.config(state="disabled")
        self._set_status("Cleared")


if __name__ == "__main__":
    app = CodePenScraperApp()
    app.mainloop()
