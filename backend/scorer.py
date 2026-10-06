"""Step 2 of the agent: score each headline's impact on one token.
Uses an OpenAI-compatible LLM (one call per token, all its headlines at once).
If there is no API key, the call fails, or the JSON is unusable, a transparent
keyword-lexicon scorer takes over so the pipeline never stops mid-demo."""
import json
import re

import requests

import config

SYSTEM_PROMPT = (
    "You are a crypto market sentiment analyst. For each numbered headline, judge ONLY its "
    "likely short-term impact on the price sentiment of the given token. "
    "Return strict JSON, no prose, no markdown: "
    '{"results":[{"i":<headline number>,"score":<integer -100..100>,'
    '"confidence":<number 0..1>,"reason":"<max 15 words>"}]}. '
    "score > 0 = bullish, < 0 = bearish, near 0 = neutral or irrelevant. "
    "Use low confidence when a headline is ambiguous or only loosely related to the token."
)

POSITIVE = {"inflow", "inflows", "rally", "rallies", "rebound", "rebounds", "surge", "surges",
            "record", "high", "adds", "approval", "approved", "partnership", "rises", "rise",
            "climbs", "jumps", "gains", "growth", "grows", "upgrade", "successful", "successfully",
            "demand", "increases", "accumulation", "adoption", "launch", "fix", "steady", "stable"}
NEGATIVE = {"outflow", "outflows", "selloff", "sell", "selling", "slides", "slide", "drop", "drops",
            "falls", "fall", "dips", "dip", "outage", "hack", "hacked", "exploit", "lawsuit",
            "delay", "delays", "delayed", "suffers", "lower", "delisted", "delists", "ban", "warn", "warns", "worries", "worry",
            "loses", "shrink", "slips", "congestion", "low", "fades", "pulls", "back", "tougher",
            "resistance", "downside", "slowdown", "concerns", "profits"}


def lexicon_score(title):
    """Count positive vs negative words. Deliberately simple and explainable."""
    words = re.findall(r"[a-z]+", title.lower())
    pos = sum(w in POSITIVE for w in words)
    neg = sum(w in NEGATIVE for w in words)
    if pos == neg:
        return 0, 0.3, "no clear positive/negative keywords"
    score = max(-100, min(100, 35 * (pos - neg)))
    conf = min(0.6, 0.35 + 0.1 * abs(pos - neg))
    return score, conf, f"keyword match: {pos} positive, {neg} negative"


def _extract_json(text):
    text = re.sub(r"```(?:json)?", "", text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model reply")
    return json.loads(text[start:end + 1])


def _clamp_int(v, lo, hi):
    return max(lo, min(hi, int(round(float(v)))))


def ai_score(token, headlines, post=requests.post):
    """Returns list of (score, confidence, reason), aligned with `headlines`. Raises on failure."""
    numbered = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(headlines))
    resp = post(
        f"{config.AI_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.AI_API_KEY}"},
        json={"model": config.AI_MODEL, "temperature": 0,
              "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                           {"role": "user", "content": f"Token: {token}\nHeadlines:\n{numbered}"}]},
        timeout=45,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    by_i = {}
    for r in _extract_json(content).get("results", []):
        try:
            i = int(r["i"])
            if 1 <= i <= len(headlines):
                conf = max(0.0, min(1.0, float(r.get("confidence", 0.5))))
                by_i[i] = (_clamp_int(r["score"], -100, 100), conf, str(r.get("reason", ""))[:160])
        except (KeyError, TypeError, ValueError):
            continue
    if len(by_i) < len(headlines) / 2:
        raise ValueError(f"model scored only {len(by_i)} of {len(headlines)} headlines")
    # any headline the model skipped falls back to the lexicon, marked as such
    return [by_i.get(i + 1) or (*lexicon_score(h)[:2], "lexicon (model skipped)")
            for i, h in enumerate(headlines)]


def score_token(token, articles, post=requests.post):
    """Score all of a token's articles. Returns (per-article results, method used, error)."""
    titles = [a["title"] for a in articles]
    method, error = "lexicon", None
    if config.AI_API_KEY and config.AI_MODEL:
        try:
            scored = ai_score(token, titles, post=post)
            method = f"llm:{config.AI_MODEL}"
        except Exception as exc:  # noqa: BLE001 - fall back, but report why
            error = f"AI failed, used lexicon fallback: {exc}"[:300]
            scored = [lexicon_score(t) for t in titles]
    else:
        scored = [lexicon_score(t) for t in titles]
    results = [{"id": a["id"], "title": a["title"], "source": a["source"], "url": a["url"],
                "published_at": a["published_at"], "score": s, "confidence": round(c, 3),
                "reason": r} for a, (s, c, r) in zip(articles, scored)]
    return results, method, error
