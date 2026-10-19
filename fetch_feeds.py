#!/usr/bin/env python3
"""
Ruhi screensaver — markets & world feed builder.

Fetches reputable finance / crypto / gold / geopolitics / macro RSS feeds and
writes stories.json. Everything is VERBATIM from the outlet: we pass through the
outlet's own headline + its own description. No summarizing, no AI, no rewriting.

Runs hourly in GitHub Actions (stdlib only — no pip install needed). The TV reads
the resulting stories.json on screensaver launch.
"""

import json
import re
import sys
import html
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

# category -> list of (source label, feed url). Order matters: first feeds win ties.
FEEDS = {
    "Equities": [
        ("CNBC", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
        ("MarketWatch", "http://feeds.marketwatch.com/marketwatch/topstories/"),
    ],
    "Crypto": [
        ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("Cointelegraph", "https://cointelegraph.com/rss"),
    ],
    "Gold": [
        ("Investing.com", "https://www.investing.com/rss/commodities.rss"),
        ("Kitco", "https://www.kitco.com/rss/KitcoNews.xml"),
    ],
    "Geopolitics": [
        ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ],
    "Macro": [
        ("BBC", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("Investing.com", "https://www.investing.com/rss/news_25.rss"),
    ],
    "US Politics": [
        ("The Hill", "https://thehill.com/news/feed/"),
        ("NPR", "https://feeds.npr.org/1014/rss.xml"),
    ],
    "India Politics": [
        ("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss"),
        ("Times of India", "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms"),
    ],
    "AI": [
        ("VentureBeat", "https://venturebeat.com/category/ai/feed/"),
        ("The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ],
}

PER_CATEGORY_DEFAULT = 3  # stories per category
PER_CAT = {"Gold": 2}     # reduced gold per user request
BLURB_MAX = 1000          # mechanical clip for file size (not a summary)
UA = "Mozilla/5.0 (compatible; RuhiFeed/1.0; +https://github.com/rupii/ruhi-feed)"

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean(text):
    """Strip HTML tags + entities, collapse whitespace. Keeps the outlet's words."""
    if not text:
        return ""
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = WS_RE.sub(" ", text).strip()
    if len(text) > BLURB_MAX:
        text = text[:BLURB_MAX].rsplit(" ", 1)[0].rstrip(",;:- ") + "…"
    return text


def parse_date(s):
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def strip_ns(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def parse_items(raw):
    """Return list of dicts with title, blurb, link, dt from RSS 2.0 or Atom."""
    out = []
    root = ET.fromstring(raw)
    nodes = [el for el in root.iter() if strip_ns(el.tag) in ("item", "entry")]
    for it in nodes:
        fields = {}
        link = ""
        for ch in it:
            t = strip_ns(ch.tag)
            if t == "title":
                fields["title"] = (ch.text or "").strip()
            elif t in ("description", "summary", "content"):
                if not fields.get("desc"):
                    fields["desc"] = ch.text or ""
            elif t == "link":
                href = ch.get("href")
                link = href if href else (ch.text or "").strip()
            elif t in ("pubDate", "published", "updated", "date"):
                if not fields.get("date"):
                    fields["date"] = (ch.text or "").strip()
        title = clean(fields.get("title", ""))
        if not title:
            continue
        out.append({
            "title": title,
            "blurb": clean(fields.get("desc", "")),
            "link": link,
            "dt": parse_date(fields.get("date")),
        })
    return out


def main():
    by_cat = {}
    seen = set()
    log = []
    for category, feeds in FEEDS.items():
        limit = PER_CAT.get(category, PER_CATEGORY_DEFAULT)
        picked = []
        for source, url in feeds:
            if len(picked) >= limit:
                break
            try:
                items = parse_items(fetch(url))
            except Exception as e:  # noqa: BLE001 — resilient: skip a bad feed
                log.append("  [skip] %s %s: %s" % (category, source, e))
                continue
            items.sort(key=lambda x: x["dt"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            for it in items:
                if len(picked) >= limit:
                    break
                key = it["title"].lower()[:80]
                if key in seen:
                    continue
                seen.add(key)
                picked.append({
                    "category": category,
                    "headline": it["title"],
                    "blurb": it["blurb"],
                    "source": source,
                    "ts": it["dt"].isoformat() if it["dt"] else None,
                    "url": it["link"],
                })
            log.append("  [ok]   %s %s: %d items" % (category, source, len(items)))
        by_cat[category] = picked

    # interleave categories round-robin so the TV's first ~20 cover every category
    stories = []
    rank = 0
    while True:
        added = False
        for category in FEEDS:
            lst = by_cat.get(category, [])
            if rank < len(lst):
                stories.append(lst[rank])
                added = True
        if not added:
            break
        rank += 1

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(stories),
        "stories": stories,
    }
    with open("stories.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print("\n".join(log))
    print("WROTE stories.json  (%d stories)" % len(stories))
    if not stories:
        sys.exit("ERROR: no stories fetched")


if __name__ == "__main__":
    main()
