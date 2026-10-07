"""Step 1 of the agent: collect headlines, clean them, drop duplicates and tag tokens."""
import calendar
import hashlib
import json
import os
import re
import time

import config

# Keyword rules for token identification. Word boundaries stop "ether" matching "ethereal"
# and "sol" matching "solid". The AI scorer later judges each headline's impact on the token.
TOKEN_KEYWORDS = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "ether", "eth"],
    "SOL": ["solana", "sol"],
    "XRP": ["xrp", "ripple"],
    "DOGE": ["dogecoin", "doge"],
}
_PATTERNS = {tok: re.compile(r"\b(" + "|".join(map(re.escape, kws)) + r")\b", re.I)
             for tok, kws in TOKEN_KEYWORDS.items()}


def normalize_title(title):
    """Lowercase, strip punctuation and extra spaces: used to detect duplicates."""
    t = re.sub(r"[^a-z0-9 ]+", " ", (title or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def article_id(title):
    return hashlib.sha256(normalize_title(title).encode()).hexdigest()[:32]


def tag_tokens(title, tracked=None):
    tracked = tracked or config.TOKENS
    return [tok for tok in tracked if tok in _PATTERNS and _PATTERNS[tok].search(title or "")]


def _make_article(title, source, url, published_at, origin):
    title = re.sub(r"\s+", " ", (title or "")).strip()
    url = url if isinstance(url, str) and url.lower().startswith(("http://", "https://")) else ""
    return {"id": article_id(title), "title": title, "source": source or "unknown",
            "url": url or "", "published_at": int(published_at), "tokens": tag_tokens(title),
            "origin": origin}


def dedupe(articles):
    """Keep the first copy of each headline (same normalized title = duplicate)."""
    seen, out = set(), []
    for a in articles:
        if a["title"] and a["id"] not in seen:
            seen.add(a["id"])
            out.append(a)
    return out


def from_rss(feed_urls=None, window_hours=None, now=None, fetch=None):
    """Fetch recent headlines from free RSS feeds. A broken feed is skipped, not fatal.
    `fetch` lets tests pass raw XML instead of hitting the network."""
    import feedparser
    now = now or int(time.time())
    cutoff = now - 3600 * (window_hours or config.NEWS_WINDOW_HOURS)
    articles, errors = [], []
    for url in feed_urls or config.RSS_FEEDS:
        try:
            parsed = feedparser.parse(fetch(url) if fetch else url,
                                      agent="Mozilla/5.0 (INNOBLOCK sentiment agent)")
            source = parsed.feed.get("title") or url
            for e in parsed.entries:
                t = e.get("published_parsed") or e.get("updated_parsed")
                ts = calendar.timegm(t) if t else now
                if cutoff <= ts <= now + 300:
                    articles.append(_make_article(e.get("title"), source, e.get("link"), ts, "rss"))
        except Exception as exc:  # noqa: BLE001 - one bad feed must not stop the run
            errors.append(f"{url}: {exc}")
    return dedupe(articles), errors


SAMPLE_PATH = os.path.join(config.HERE, "data", "sample_headlines.json")


def load_sample(path=SAMPLE_PATH):
    """Synthetic demo dataset (clearly labelled as such). Each item has an hours_ago
    offset so the windows are always in the recent past relative to now."""
    with open(path) as f:
        data = json.load(f)
    now = int(time.time())
    out = [_make_article(i["title"], i.get("source", "Sample dataset"), "",
                         now - int(i["hours_ago"] * 3600), "sample") for i in data["items"]]
    return dedupe(out)


def group_by_token(articles, limit=None):
    """{token: [articles newest first]} for tracked tokens only."""
    limit = limit or config.MAX_HEADLINES_PER_TOKEN
    groups = {}
    for a in sorted(articles, key=lambda x: -x["published_at"]):
        for tok in a["tokens"]:
            if len(groups.setdefault(tok, [])) < limit:
                groups[tok].append(a)
    return groups