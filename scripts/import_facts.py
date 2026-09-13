#!/usr/bin/env python3
"""One-off importer: build data/facts.json from Wikipedia "Did you know" hooks.

Source: https://huggingface.co/datasets/derenrich/enwiki-did-you-know (CC BY; the hook text
itself is Wikipedia content, CC BY-SA 4.0). Download the parquet files into a directory, then:

    python -m venv .venv && .venv/bin/pip install pyarrow
    .venv/bin/python scripts/import_facts.py /path/to/parquet-dir

Only hooks with page-view data (2017 onwards) are considered, and only the ones whose article
drew at least MIN_VIEWS views on the day, which weeds out most of the very obscure entries.
Hooks are rewritten from "... that X?" into a plain statement "X." so they read naturally
under the plugin's "Did you know?" label.
"""

from __future__ import annotations

import glob
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover
    sys.exit("pyarrow is required: pip install pyarrow")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_data import GRIM  # noqa: E402  (same taste filter as the daily build)

OUT = Path(__file__).resolve().parent.parent / "data" / "facts.json"
MIN_VIEWS = 1000
MIN_LEN, MAX_LEN = 40, 200

# Hooks that only make sense on the day they ran, or that lean on an image.
STALE = re.compile(
    r"\b(today|tonight|tomorrow|yesterday|this (week|month|year|weekend)|last (week|month|year)|"
    r"next (week|month|year)|currently|now|recently|latest|newest|upcoming|ongoing|still|"
    r"pictured|illustrated|shown|depicted|audio|video|listen|wikipedia)\b",
    re.I,
)


def to_statement(hook: str) -> str | None:
    text = re.sub(r"\s+", " ", hook).strip()
    m = re.match(r"^\.{2,}\s*that\s+(.*)$", text, re.I)
    if not m:
        return None
    text = m.group(1).strip()
    if text.endswith("?"):
        text = text[:-1].rstrip() + "."
    if not text.endswith((".", "!")):
        text += "."
    # "... that in 1919 Ethel ..." -> "In 1919 Ethel ..."
    text = text[0].upper() + text[1:]
    return text


def main(parquet_dir: str) -> None:
    files = sorted(glob.glob(str(Path(parquet_dir) / "*.parquet")))
    if not files:
        sys.exit(f"no parquet files in {parquet_dir}")
    cols = ["subject", "subject_article", "dyk_text", "timestamp", "day_of_views"]
    rows: list[dict] = []
    for f in files:
        rows += pq.read_table(f, columns=cols).to_pylist()
    print(f"{len(rows)} hooks read", file=sys.stderr)

    seen: set[str] = set()
    facts: list[dict] = []
    for r in rows:
        views = r.get("day_of_views") or 0
        if views < MIN_VIEWS:
            continue
        text = to_statement(r.get("dyk_text") or "")
        if not text or not MIN_LEN <= len(text) <= MAX_LEN:
            continue
        if GRIM.search(text) or STALE.search(text):
            continue
        if '"' in text and text.count('"') % 2:
            continue  # broken quoting
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        article = (r.get("subject_article") or r.get("subject") or "").strip()
        facts.append({
            "id": "dyk-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12],
            "text": text,
            "title": article,
            "url": "https://en.wikipedia.org/wiki/" + article.replace(" ", "_") if article else "",
            "views": int(views),
            "ran": r["timestamp"].date().isoformat() if r.get("timestamp") else None,
        })

    facts.sort(key=lambda f: -f["views"])
    payload = {
        "source": "Wikipedia Did you know hooks via huggingface.co/datasets/derenrich/enwiki-did-you-know",
        "license": "CC BY-SA 4.0",
        "min_views": MIN_VIEWS,
        "count": len(facts),
        "facts": facts,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=0)
    print(f"wrote {OUT} with {len(facts)} facts ({OUT.stat().st_size} bytes)", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
