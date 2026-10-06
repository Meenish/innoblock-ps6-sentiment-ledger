"""Step 3 of the agent: turn per-headline scores into one signal per token, and build the
canonical analysis JSON whose keccak256 hash goes on-chain.

Method (documented so judges can check it):
  score       = sum(score_i * conf_i) / sum(conf_i)      confidence-weighted mean, -100..100
  confidence  = sum(conf_i^2) / sum(conf_i) * agreement   weighted mean confidence, scaled by
  agreement   = |sum(sign_i * conf_i)| / sum(conf_i)      how much the headlines agree (0.5..1)
                (mapped to 0.5 + 0.5 * raw so mixed news halves confidence, never zeroes it)
  sourceCount = number of distinct headlines used
  label       = BULLISH if score >= 20, BEARISH if <= -20, else NEUTRAL (same rule as contract)
"""
import json

from web3 import Web3

THRESHOLD = 20


def classify(score):
    return "BULLISH" if score >= THRESHOLD else "BEARISH" if score <= -THRESHOLD else "NEUTRAL"


def aggregate(results):
    total_c = sum(r["confidence"] for r in results)
    if not results or total_c <= 0:
        return 0, 0
    score = sum(r["score"] * r["confidence"] for r in results) / total_c
    mean_c = sum(r["confidence"] ** 2 for r in results) / total_c
    sign = lambda s: (s > 0) - (s < 0)  # noqa: E731
    raw_agree = abs(sum(sign(r["score"]) * r["confidence"] for r in results)) / total_c
    conf = mean_c * (0.5 + 0.5 * raw_agree)
    return max(-100, min(100, round(score))), max(0, min(100, round(conf * 100)))


def build_signal(token, results, method, observed_at):
    score, confidence = aggregate(results)
    top = sorted(results, key=lambda r: -abs(r["score"]) * r["confidence"])[:3]
    analysis = {
        "version": 1, "token": token, "observedAt": observed_at, "method": method,
        "score": score, "confidence": confidence, "sourceCount": len(results),
        "label": classify(score),
        "headlines": [{k: r[k] for k in ("title", "source", "url", "published_at",
                                         "score", "confidence", "reason")} for r in results],
        "topHeadlineIds": [r["id"] for r in top],
    }
    # Canonical form: sorted keys, no spaces, UTF-8. Anyone can re-hash it and compare.
    canonical = json.dumps(analysis, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {"token": token, "score": score, "confidence": confidence,
            "source_count": len(results), "observed_at": observed_at, "label": classify(score),
            "method": method, "analysis_json": canonical,
            "analysis_hash": Web3.to_hex(Web3.keccak(text=canonical))}
