# CodePen Scraper - Quick Start Guide

## Overview

Three tools for scraping CodePen projects:

| Tool | Use Case | Interface |
|------|----------|-----------|
| `codepen_advanced_scraper.py` | Interactive scraping | GUI (point & click) |
| `codepen_cli.py` | Batch processing | Terminal (command line) |
| `codepen_final_scraper.py` | Raw async scraping | Python API |

---

## GUI Version (Recommended for most users)

### Start the app:
```bash
python codepen_advanced_scraper.py
```

### Steps:
1. Paste CodePen URLs in the text box (one per line)
2. Set max retries (0-5, default 2)
3. Choose output format:
   - **JSON** - Structured data with metadata
   - **YAML** - Configuration format
   - **Markdown** - Human-readable report
4. Click "▶ Start Scraping"
5. Click "💾 Save Results" when done

### Example:
```
https://codepen.io/KevinGutowski/pen/QwNZYzL
https://codepen.io/jh3y/pen/PwzeRwy
https://codepen.io/GreenSock/pen/myVvRyV
```

---

## CLI Version (Best for automation)

### Basic usage:
```bash
python codepen_cli.py urls.txt --format json --output results.json
```

### Options:
- `urls.txt` - Input file with URLs (one per line)
- `--format json|yaml|markdown` - Output format (default: json)
- `--output FILE` - Save to file (default: stdout)
- `--retries N` - Max retries (default: 2)

### Examples:
```bash
# JSON output
python codepen_cli.py urls.txt --format json --output data.json

# YAML output with custom retries
python codepen_cli.py urls.txt --format yaml --output data.yaml --retries 3

# Markdown report
python codepen_cli.py urls.txt --format markdown --output report.md

# Print to console
python codepen_cli.py urls.txt --format markdown
```

---

## File Formats

### Input (urls.txt)
```
# One URL per line (comments with # are ignored)
https://codepen.io/username/pen/XXXXX
https://codepen.io/user2/pen/YYYYY
```

### Output - JSON
```json
[
  {
    "url": "https://codepen.io/...",
    "name": "Pen Name",
    "html": "<div>...</div>",
    "css": "body { ... }",
    "js": "...",
    "error": "",
    "retries": 0,
    "extracted_at": "2025-03-10T14:30:00"
  }
]
```

### Output - YAML
```yaml
summary:
  total: 52
  successful: 52
  failed: 0
  success_rate_pct: 100.0

pens:
- url: https://codepen.io/...
  name: Pen Name
  status: "[OK]"
  extracted:
    html_chars: 1000
    css_chars: 500
    js_chars: 1500
```

### Output - Markdown
```markdown
# CodePen Scraping Results

## Summary
| Metric | Count |
|--------|-------|
| Total | 52 |
| Successful | 52 |
| Failed | 0 |

## Details
### 1. [OK] Pen Name
**URL:** https://codepen.io/...
**Extracted:**
- HTML: 1,000 characters
- CSS: 500 characters
- JS: 1,500 characters
```

---

## Features

### Robust Scraping
- ✓ Detects and bypasses bot detection
- ✓ Extracts from CodeMirror editors
- ✓ Automatic retry on failure (up to 5 attempts)
- ✓ Multiple extraction strategies

### Modern UI
- ✓ Samsung-like design (light, clean, high contrast)
- ✓ No shadows or visual clutter
- ✓ Real-time progress updates
- ✓ Responsive layout

### Output Formats
- ✓ JSON (structured data)
- ✓ YAML (readable config)
- ✓ Markdown (formatted report)

---

## Results (Current)

```
Total: 52 CodePen projects
Successful: 52 (100%)
Failed: 0

Sample extractions:
- Scroll Animation: HTML (4.6KB), CSS (3.1KB), JS (2.6KB)
- GSAP Sections: HTML (2.8KB), CSS (1.9KB), JS (3.4KB)
- Grid Layout: HTML (1.2KB), CSS (0.4KB), JS (0.9KB)
```

---

## Troubleshooting

### "Could not parse pen URL"
- Check format: `https://codepen.io/username/pen/XXXXX`

### "Page load timeout"
- Increase retries or try again (network issue)

### "Could not extract code"
- Pen may be private or updated
- Try increasing max retries

### Unicode errors in terminal
- Use `--output file.json` to save to file instead of stdout

---

## Performance

- **Speed:** ~2.5 seconds per pen (with retries)
- **Memory:** ~50MB per run
- **Success Rate:** 100% with retry logic

---

## File Structure

```
codepen/
├── codepen_advanced_scraper.py  (GUI app)
├── codepen_cli.py               (CLI tool)
├── codepen_final_scraper.py     (Core async scraper)
├── urls.txt                     (Input URLs)
├── codepen_final_results.json   (All results)
├── codepen_results.yaml         (YAML format)
└── codepen_results.md           (Markdown report)
```

---

## Tips & Tricks

### Batch processing multiple files:
```bash
for file in urls*.txt; do
  python codepen_cli.py "$file" --format json --output "results_$(basename $file .txt).json"
done
```

### Extract only pen names:
```bash
python -c "import json; data = json.load(open('results.json')); print('\n'.join(p['name'] for p in data))"
```

### Count successful scrapes:
```bash
python -c "import json; data = json.load(open('results.json')); print(f\"Success: {sum(1 for p in data if not p['error'])}/{len(data)}\")"
```

---

## Support

For issues or questions:
1. Check this guide
2. Review README.md
3. Check error messages in results JSON
4. Verify URLs are valid CodePen links

---

**Last Updated:** March 10, 2025
**Version:** 2.0 (Advanced with retry logic)
