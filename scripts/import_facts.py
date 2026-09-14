#!/usr/bin/env python3
"""Build data/facts.json from two sources (stdlib only, no API keys):

  misconception  Wikipedia "List of common misconceptions" (three sub-lists), CC BY-SA 4.0.
                 Each bullet is a correction of a popular myth; we keep the first sentence or two.
  simple         ProCreations/simple-facts on Hugging Face, CC BY 4.0. Short, light fun facts.

Run it again whenever you want to refresh the pool:

    python3 scripts/import_facts.py

Items keep stable ids (a hash of the text), so re-importing does not reset the repeat-avoidance
ledger for facts that are still present.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_data import GRIM, USER_AGENT  # noqa: E402  (same taste filter as the daily build)

OUT = Path(__file__).resolve().parent.parent / "data" / "facts.json"
MIN_LEN, MAX_LEN = 25, 200

MISCONCEPTION_PAGES = [
    "List of common misconceptions about arts and culture",
    "List of common misconceptions about history",
    "List of common misconceptions about science, technology, and mathematics",
]
SIMPLE_FACTS_ROWS = "https://datasets-server.huggingface.co/rows?dataset=ProCreations%2Fsimple-facts&config=default&split=train&offset={offset}&length=100"

# Not for a family e-ink screen.
ADULT = re.compile(
    r"\b(sex|sexual|sexually|vagina\w*|penis|penile|g-spot|orgasm\w*|masturbat\w*|porn\w*|genital\w*|"
    r"erection|erectile|condom\w*|ejaculat\w*|semen|nipple\w*|circumci\w*|prostitut\w*|libido|"
    r"intercourse|arous\w*|erotic\w*|fetish\w*)\b",
    re.I,
)
# simple-facts filler and the entries that are well-known to be wrong or unverifiable.
SIMPLE_SKIP = re.compile(
    r"^A group of |^The collective noun|^The plural of|^The human \w+ bone\b|\bsuicide\b|\bstatistics\b|"
    r"most common name in the world|fastest random speaker|remember 50,000|Psalms? 46|"
    r"Apache servers|youngest parents|status code 218|Karoke|"
    r"\b(you|your)\b.*\b(swallow|spiders?)\b|goldfish.*memory|lightning never strikes|"
    r"Great Wall.*space|left.?handed people|right.?handed people|live.*years longer",
    re.I,
)
# Misconception bullets that are opinions of the moment or read badly without context.
MISC_SKIP = re.compile(
    r"\b(Trump|Biden|Obama|Clinton|COVID|coronavirus|vaccin\w*|abortion|transgender|gender)\b|"
    r"\[dataset\]|processed by|^[A-Z][a-z]+ [A-Z][a-z]+ \(\d{4}\)",  # stray reference-list bullets
    re.I,
)


def http(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def fact_id(prefix: str, text: str) -> str:
    return prefix + "-" + hashlib.sha1(text.lower().encode("utf-8")).hexdigest()[:12]


def tidy(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s*\(\s*\)", "", text)  # empty parens left by stripped links
    text = re.sub(r"(?<!\.)\.\.$", ".", text)  # stray double full stop
    if text and not text.endswith((".", "!", "?", '"')):
        text += "."
    return text[0].upper() + text[1:] if text else text


# ---------------------------------------------------------------- misconceptions

def strip_templates(s: str) -> str:
    out, depth, i = [], 0, 0
    while i < len(s):
        if s.startswith("{{", i):
            depth += 1
            i += 2
            continue
        if s.startswith("}}", i) and depth:
            depth -= 1
            i += 2
            continue
        if depth == 0:
            out.append(s[i])
        i += 1
    return "".join(out)


def strip_wikitext(line: str) -> str:
    line = line.lstrip("*").strip()
    line = strip_templates(line)
    line = re.sub(r"<ref[^>]*/>", "", line)
    line = re.sub(r"<ref[^>]*>.*?</ref>", "", line, flags=re.S)
    line = re.sub(r"<ref[^>]*>.*$", "", line)  # unterminated ref after template removal
    line = re.sub(r"\[\[(?:File|Image):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", "", line)
    line = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", line)
    line = re.sub(r"\[\[([^\]]*)\]\]", r"\1", line)
    line = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", line)
    line = re.sub(r"'{2,}", "", line)
    line = re.sub(r"<[^>]+>", "", line)
    return re.sub(r"\s+", " ", line).strip()


def first_sentences(text: str, limit: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", text)
    out = parts[0]
    for part in parts[1:]:
        if len(out) + 1 + len(part) > limit:
            break
        out += " " + part
    return out


def load_misconceptions() -> list[dict]:
    facts = []
    for page in MISCONCEPTION_PAGES:
        url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "parse", "page": page, "prop": "wikitext", "format": "json", "formatversion": "2"})
        wikitext = json.loads(http(url))["parse"]["wikitext"]
        page_url = "https://en.wikipedia.org/wiki/" + page.replace(" ", "_")
        n = 0
        for line in wikitext.split("\n"):
            if not line.startswith("*") or line.startswith("**"):
                continue
            text = strip_wikitext(line)
            if not text:
                continue
            text = tidy(first_sentences(text, MAX_LEN))
            if not MIN_LEN <= len(text) <= MAX_LEN:
                continue
            if GRIM.search(text) or ADULT.search(text) or MISC_SKIP.search(text):
                continue
            facts.append({
                "id": fact_id("myth", text),
                "kind": "misconception",
                "text": text,
                "title": page,
                "url": page_url,
            })
            n += 1
        print(f"{page}: {n} kept", file=sys.stderr)
    return facts


# ---------------------------------------------------------------- simple facts

def load_simple_facts() -> list[dict]:
    rows: list[str] = []
    offset = 0
    while True:
        data = json.loads(http(SIMPLE_FACTS_ROWS.format(offset=offset)))
        batch = [r["row"]["fact"] for r in data.get("rows", [])]
        rows += batch
        if len(batch) < 100:
            break
        offset += 100
    print(f"simple-facts: {len(rows)} rows read", file=sys.stderr)
    facts = []
    for raw in rows:
        text = tidy(raw)
        if not MIN_LEN <= len(text) <= MAX_LEN:
            continue
        if GRIM.search(text) or ADULT.search(text) or SIMPLE_SKIP.search(text):
            continue
        facts.append({
            "id": fact_id("fact", text),
            "kind": "simple",
            "text": text,
            "title": "",
            "url": "https://huggingface.co/datasets/ProCreations/simple-facts",
        })
    print(f"simple-facts: {len(facts)} kept", file=sys.stderr)
    return facts


def main() -> None:
    facts = load_misconceptions() + load_simple_facts()
    seen: set[str] = set()
    unique = []
    for f in facts:
        key = re.sub(r"[^a-z0-9]", "", f["text"].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    payload = {
        "sources": {
            "misconception": {"name": "Wikipedia, List of common misconceptions", "license": "CC BY-SA 4.0",
                              "url": "https://en.wikipedia.org/wiki/List_of_common_misconceptions"},
            "simple": {"name": "ProCreations/simple-facts", "license": "CC BY 4.0",
                       "url": "https://huggingface.co/datasets/ProCreations/simple-facts"},
        },
        "count": len(unique),
        "facts": unique,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    kinds = {}
    for f in unique:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    print(f"wrote {OUT}: {len(unique)} facts {kinds} ({OUT.stat().st_size} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
