#!/usr/bin/env python3
"""Subset the self-hosted InterVariable fonts to the Latin range.

The full InterVariable woff2 from rsms.me is ~344 KB because it covers 2,852
codepoints (Latin, Cyrillic, Greek, IPA, arrows, symbols, …). The fomo.nyc UI
only renders Latin text — any non-Latin venue/event names already fall back to
the system font (Inter has no CJK glyphs). Trimming to Latin + Latin-Extended +
common punctuation/currency/symbols cuts the file dramatically, which frees
bandwidth for the event-data JSON during the initial load on slow connections.

Both variable axes (wght 100-900, opsz 14-32) and OpenType features (kern, liga,
calt) are preserved, so weights and ligatures render exactly as before.

Re-run whenever the pinned Inter version changes:

    ./venv/bin/python scripts/subset_inter.py

Outputs overwrite src/fonts/inter/InterVariable*.woff2 (the build copies those).
"""
import subprocess
import sys
import urllib.request
from pathlib import Path

# Source (matches the ?v= in src/css/fonts.css / the vendored files)
INTER_VERSION = "4.1"
SOURCES = {
    "InterVariable.woff2": f"https://rsms.me/inter/font-files/InterVariable.woff2?v={INTER_VERSION}",
    "InterVariable-Italic.woff2": f"https://rsms.me/inter/font-files/InterVariable-Italic.woff2?v={INTER_VERSION}",
}

OUT_DIR = Path(__file__).resolve().parent.parent / "src" / "fonts" / "inter"

# Google Fonts "latin" + "latin-ext" ranges, plus arrows/math operators the UI
# may surface. Generous on purpose — a few extra glyphs cost little, a missing
# one shows tofu.
UNICODES = ",".join([
    "U+0000-00FF",   # Basic Latin + Latin-1 Supplement
    "U+0100-024F",   # Latin Extended-A + B
    "U+0259",        # schwa
    "U+02BB-02BC", "U+02C6", "U+02DA", "U+02DC",  # spacing modifiers
    "U+0300-036F",   # combining diacritics
    "U+1E00-1EFF",   # Latin Extended Additional
    "U+2000-206F",   # General Punctuation (quotes, dashes, ellipsis, bullet)
    "U+2070-209F",   # super/subscripts
    "U+20A0-20CF",   # currency symbols (€, etc.)
    "U+2100-214F",   # letterlike (™, ℠, №)
    "U+2190-21FF",   # arrows
    "U+2212", "U+2215",  # minus, division slash
    "U+2C60-2C7F",   # Latin Extended-C
    "U+A720-A7FF",   # Latin Extended-D
    "U+FB00-FB06",   # ff/fi/fl ligatures
    "U+FEFF", "U+FFFD",
])


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        full = OUT_DIR / (name + ".full")
        out = OUT_DIR / name
        print(f"↓ {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            full.write_bytes(resp.read())
        before = full.stat().st_size
        cmd = [
            sys.executable, "-m", "fontTools.subset", str(full),
            f"--unicodes={UNICODES}",
            "--layout-features=*",   # keep kern/liga/calt
            "--flavor=woff2",
            "--output-file=" + str(out),
            # keep variable axes — do NOT instance
            "--name-IDs=*",
        ]
        subprocess.run(cmd, check=True)
        after = out.stat().st_size
        full.unlink()
        print(f"  {name}: {before/1024:.0f} KB → {after/1024:.0f} KB "
              f"({100*(1-after/before):.0f}% smaller)")


if __name__ == "__main__":
    main()
