#!/usr/bin/env python3
"""Build the daily fact / trivia / riddle schedule.

Reads
  data/riddles.json   curated riddle pool (committed)
  data/history.json   every pick ever made, keyed by date (restored from the gh-pages branch)
Fetches
  Open Trivia DB      https://opentdb.com            CC BY-SA 4.0
  Wikimedia REST      "On this day" feed              CC BY-SA 4.0
Writes
  data/history.json   extended so every date up to today + HORIZON_AHEAD has a pick
  public/data.json    the window the TRMNL plugin polls (today - WINDOW_BEHIND .. today + HORIZON_AHEAD)
  public/history.json copy of the ledger so the next run can restore it
  public/index.html   tiny landing page

Repeat avoidance: an item is never picked again while any unpicked item remains in its pool.
Once a pool is exhausted the least recently used item is picked, so the gap between repeats
is always as long as the pool allows (years for trivia and facts, a bit over a year for riddles).
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RIDDLES_PATH = ROOT / "data" / "riddles.json"
HISTORY_PATH = ROOT / "data" / "history.json"
PUBLIC_DIR = ROOT / "public"

HORIZON_AHEAD = 45  # days scheduled in advance
WINDOW_BEHIND = 7  # past days kept in data.json for devices that are behind

USER_AGENT = "trmnl-facts-trivia-riddles/1.0 (https://github.com/eds123/trmnl-facts-trivia-riddles)"
OTDB_API = "https://opentdb.com/api.php"
OTDB_TOKEN = "https://opentdb.com/api_token.php?command=request"
OTDB_PAUSE = 5.5  # opentdb allows one request per IP every 5 seconds
WIKI_FEED = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/{kind}/{month:02d}/{day:02d}"

# Events we don't want on a "brain snack" screen (TRMNL also rejects recipes depicting suffering).
GRIM = re.compile(
    r"\b(kill|killed|killing|dead|death|deaths|died|dies|massacre|genocide|bomb|bombing|bombed|"
    r"terror|terrorist|attack|attacked|attacks|murder|murdered|assassinat\w*|execut\w*|suicide|"
    r"shooting|shot|crash|crashed|disaster|famine|plague|epidemic|pandemic|war|wars|battle|"
    r"invasion|invaded|hostage|torture|rape|abuse|slaughter|casualt\w*|wounded|injur\w*|"
    r"earthquake|tsunami|hurricane|typhoon|cyclone|flood|floods|wildfire|explosion|exploded|"
    r"sank|sinking|collapse|collapsed|riot|riots|coup|lynch\w*|holocaust|nazi|nazis)\b",
    re.I,
)

# First words that read naturally in lower case after "On this day in 1969, ...".
LOWER_STARTERS = {
    "the", "a", "an", "after", "during", "following", "at", "in", "on", "over", "under", "with",
    "while", "as", "using", "about", "nearly", "approximately", "more", "less", "several", "many",
    "members", "according", "hundreds", "thousands", "millions", "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "eleven", "twelve", "twenty", "thirty", "fifty", "first",
    "second", "third", "construction", "work", "production", "filming", "recording", "excavation",
    "operation", "operations", "scientists", "researchers", "archaeologists", "astronomers",
    "engineers", "workers", "police", "troops", "soldiers", "rescue", "voters", "delegates",
}

# Trivia questions that only make sense with the multiple-choice options shown.
NEEDS_OPTIONS = re.compile(r"\b(following|these|of the above|below|listed)\b|which one\b", re.I)
KEEP_CAPITALISED = {"Japanese"}
# Open Trivia DB is dominated by fandom categories; allow them on roughly one day in seven.
NICHE_CATEGORIES = {"Video games", "Japanese anime & manga", "Comics", "Cartoon & animations",
                    "Board games", "Celebrities", "Gadgets"}
NICHE_EVERY = 7

SOURCES = {
    "trivia": {"name": "Open Trivia Database", "url": "https://opentdb.com", "license": "CC BY-SA 4.0"},
    "fact": {"name": "Wikipedia", "url": "https://en.wikipedia.org", "license": "CC BY-SA 4.0"},
    "riddle": {"name": "crawsome/riddles", "url": "https://github.com/crawsome/riddles", "license": "Unlicense"},
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def http_json(url: str, retries: int = 3) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == retries:
                raise
            log(f"  retry {attempt} for {url}: {exc}")
            time.sleep(3 * attempt)
    raise RuntimeError("unreachable")


# ---------------------------------------------------------------- ledger

def load_history() -> dict:
    if HISTORY_PATH.exists():
        with HISTORY_PATH.open(encoding="utf-8") as fh:
            hist = json.load(fh)
        hist.setdefault("days", {})
        return hist
    return {"version": 1, "days": {}}


def last_used(history: dict, kind: str) -> dict[str, str]:
    """item id -> most recent date it was shown."""
    used: dict[str, str] = {}
    for date in sorted(history["days"]):
        item = history["days"][date].get(kind)
        if item and item.get("id"):
            used[item["id"]] = date
    return used


def pick(candidates: list[dict], used: dict[str, str], rng: random.Random) -> dict | None:
    """Prefer never-used items; otherwise the least recently used one."""
    if not candidates:
        return None
    fresh = [c for c in candidates if c["id"] not in used]
    if fresh:
        return rng.choice(fresh)
    return min(candidates, key=lambda c: used[c["id"]])


# ---------------------------------------------------------------- riddles

MAX_RIDDLE_LEN = 200  # longer riddles truncate on the OG quadrant / half layouts
MAX_TRIVIA_LEN = 180


def load_riddles() -> list[dict]:
    with RIDDLES_PATH.open(encoding="utf-8") as fh:
        riddles = json.load(fh)["riddles"]
    return [r for r in riddles if len(r["question"]) <= MAX_RIDDLE_LEN]


# ---------------------------------------------------------------- trivia

def sentence_case_category(raw: str) -> str:
    name = raw.split(":", 1)[-1].strip()
    words = name.split(" ")
    out = [words[0]] + [w if w in KEEP_CAPITALISED or w == "&" else w.lower() for w in words[1:]]
    return " ".join(out)


def b64(value: str) -> str:
    return base64.b64decode(value).decode("utf-8")


def normalise_trivia(raw: dict) -> dict | None:
    question = b64(raw["question"]).strip()
    answer = b64(raw["correct_answer"]).strip()
    incorrect = [b64(x).strip() for x in raw.get("incorrect_answers", [])]
    kind = b64(raw.get("type", ""))
    if kind == "boolean":
        question = "True or false: " + question
        choices: list[str] = []
    elif kind == "multiple":
        if NEEDS_OPTIONS.search(question):
            return None
        choices = [answer] + incorrect
    else:
        return None
    if len(question) > MAX_TRIVIA_LEN or len(answer) > 60 or len(question) < 15:
        return None
    ident = "otdb-" + hashlib.sha1(question.lower().encode("utf-8")).hexdigest()[:12]
    return {
        "id": ident,
        "category": sentence_case_category(b64(raw["category"])),
        "difficulty": b64(raw["difficulty"]),
        "question": question,
        "answer": answer,
        "choices": choices,
        "source": "Open Trivia DB",
        "license": "CC BY-SA 4.0",
    }


def fetch_trivia(needed: int, used: dict[str, str]) -> list[dict]:
    """Fetch fresh trivia candidates from Open Trivia DB (a few batches of 50 at most)."""
    if needed <= 0:
        return []
    token = None
    try:
        tok = http_json(OTDB_TOKEN)
        token = tok.get("token")
    except Exception as exc:  # token is only an optimisation
        log(f"  no session token: {exc}")
    candidates: dict[str, dict] = {}
    batches = 0
    max_batches = min(6, max(2, (needed // 20) + 2))
    def usable() -> int:
        return len([c for c, it in candidates.items() if c not in used and it["category"] not in NICHE_CATEGORIES])

    while usable() < needed and batches < max_batches:
        if batches:
            time.sleep(OTDB_PAUSE)
        params = {"amount": 50, "encode": "base64"}
        if token:
            params["token"] = token
        data = http_json(OTDB_API + "?" + urllib.parse.urlencode(params))
        batches += 1
        code = data.get("response_code")
        if code == 5:  # rate limited
            time.sleep(OTDB_PAUSE)
            continue
        if code in (3, 4):  # token missing / exhausted: continue without it
            token = None
            continue
        if code != 0:
            raise RuntimeError(f"Open Trivia DB response_code {code}")
        for raw in data["results"]:
            item = normalise_trivia(raw)
            if item:
                candidates.setdefault(item["id"], item)
    log(f"  trivia: {len(candidates)} usable candidates from {batches} batch(es)")
    return list(candidates.values())


# ---------------------------------------------------------------- facts

def fact_text(year: int, text: str) -> str:
    text = re.sub(r"\s*\((?:pictured|depicted|illustrated|shown|example pictured)\)", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    # Wikipedia sometimes prefixes the topic: "Financial crisis of 2007–2008: The global ..."
    text = re.sub(r"^[^:.?!]{3,70}: (?=[A-Z])", "", text)
    first = text.split(" ", 1)[0]
    if first.lower() in LOWER_STARTERS:
        text = text[0].lower() + text[1:]
    if not text.endswith((".", "!", "?")):
        text += "."
    when = f"{abs(year)} BC" if year < 0 else str(year)
    return f"On this day in {when}, {text}"


def fetch_fact_candidates(month: int, day: int) -> list[dict]:
    items: list[dict] = []
    for kind in ("selected", "events"):
        try:
            data = http_json(WIKI_FEED.format(kind=kind, month=month, day=day))
        except Exception as exc:
            log(f"  wikimedia {kind} {month:02d}/{day:02d} failed: {exc}")
            continue
        for ev in data.get(kind, []):
            text = (ev.get("text") or "").strip()
            year = ev.get("year")
            if not text or year is None or GRIM.search(text):
                continue
            if not 40 <= len(text) <= 260:
                continue
            page = (ev.get("pages") or [{}])[0]
            url = page.get("content_urls", {}).get("desktop", {}).get("page", "")
            title = page.get("titles", {}).get("normalized") or page.get("title") or ""
            ident = "wiki-" + hashlib.sha1(f"{month:02d}{day:02d}|{year}|{text}".encode("utf-8")).hexdigest()[:12]
            items.append({
                "id": ident,
                "text": fact_text(year, text),
                "year": year,
                "title": title,
                "url": url,
                "source": "Wikipedia",
                "license": "CC BY-SA 4.0",
            })
        if items:  # curated "selected" list is enough; only fall back to the long list if empty
            break
    # de-duplicate on id
    seen: set[str] = set()
    unique = []
    for it in items:
        if it["id"] not in seen:
            seen.add(it["id"])
            unique.append(it)
    return unique


# ---------------------------------------------------------------- schedule

def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def build(today: dt.date) -> None:
    history = load_history()
    days = history["days"]
    before = len(days)

    horizon = today + dt.timedelta(days=HORIZON_AHEAD)
    missing = [d for d in daterange(today, horizon) if d.isoformat() not in days]
    log(f"history has {before} day(s); scheduling {len(missing)} new day(s) up to {horizon}")

    riddles = load_riddles()
    trivia_pool = fetch_trivia(len(missing), last_used(history, "trivia")) if missing else []

    for d in missing:
        key = d.isoformat()
        rng = random.Random(key)
        entry: dict = {}

        fact = pick(fetch_fact_candidates(d.month, d.day), last_used(history, "fact"), rng)
        if fact:
            entry["fact"] = fact
        else:
            log(f"  {key}: no fact candidate")

        broad = [t for t in trivia_pool if t["category"] not in NICHE_CATEGORIES]
        allow_niche = d.toordinal() % NICHE_EVERY == 0 or not broad
        trivia = pick(trivia_pool if allow_niche else broad, last_used(history, "trivia"), rng)
        if trivia:
            entry["trivia"] = trivia
            trivia_pool = [t for t in trivia_pool if t["id"] != trivia["id"]]
        else:
            log(f"  {key}: no trivia candidate")

        riddle = pick(riddles, last_used(history, "riddle"), rng)
        if riddle:
            entry["riddle"] = riddle

        if not entry:
            raise RuntimeError(f"{key}: nothing could be scheduled")
        days[key] = entry
        log(f"  {key}: " + ", ".join(f"{k}={v['id']}" for k, v in entry.items()))

    if len(days) < before:
        raise RuntimeError("history shrank; refusing to write")

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("w", encoding="utf-8") as fh:
        json.dump(history, fh, ensure_ascii=False, indent=1, sort_keys=True)

    write_public(history, today)


def slim(item: dict, keys: tuple[str, ...]) -> dict:
    return {k: item[k] for k in keys if k in item}


def write_public(history: dict, today: dt.date) -> None:
    start = today - dt.timedelta(days=WINDOW_BEHIND)
    end = today + dt.timedelta(days=HORIZON_AHEAD)
    window = {}
    for d in daterange(start, end):
        key = d.isoformat()
        entry = history["days"].get(key)
        if not entry:
            continue
        out = {}
        if "fact" in entry:
            out["fact"] = slim(entry["fact"], ("text", "year", "title", "url"))
        if "trivia" in entry:
            out["trivia"] = slim(entry["trivia"], ("category", "difficulty", "question", "answer", "choices"))
        if "riddle" in entry:
            out["riddle"] = slim(entry["riddle"], ("question", "answer"))
        window[key] = out

    payload = {
        "version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "sources": SOURCES,
        "days": window,
    }
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    data_path = PUBLIC_DIR / "data.json"
    with data_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    size = data_path.stat().st_size
    log(f"wrote {data_path} ({size} bytes, {len(window)} days)")
    if size > 90_000:
        raise RuntimeError(f"data.json is {size} bytes; TRMNL rejects responses over 100 kB")

    with (PUBLIC_DIR / "history.json").open("w", encoding="utf-8") as fh:
        json.dump(history, fh, ensure_ascii=False, indent=1, sort_keys=True)
    (PUBLIC_DIR / ".nojekyll").write_text("")
    (PUBLIC_DIR / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Facts, Trivia &amp; Riddles data</title>"
        "<p>Data feed for the <a href='https://github.com/eds123/trmnl-facts-trivia-riddles'>"
        "Facts, Trivia &amp; Riddles</a> TRMNL plugin: <a href='data.json'>data.json</a>.</p>"
        "<p>Trivia from <a href='https://opentdb.com'>Open Trivia Database</a> and facts from "
        "<a href='https://en.wikipedia.org'>Wikipedia</a>, both CC BY-SA 4.0. "
        "Riddles from <a href='https://github.com/crawsome/riddles'>crawsome/riddles</a> (Unlicense).</p>\n"
    )


if __name__ == "__main__":
    today = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.datetime.now(dt.timezone.utc).date()
    build(today)
