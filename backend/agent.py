"""The sentiment agent: collect -> score -> aggregate -> store off-chain -> publish on-chain."""
import time
import uuid

import aggregate
import db
import news
import scorer


def analyse(articles, observed_at, post=None):
    """Score and aggregate a batch of articles. Returns (signals, notes)."""
    kwargs = {"post": post} if post else {}
    signals, notes = [], []
    for token, items in news.group_by_token(articles).items():
        results, method, err = scorer.score_token(token, items, **kwargs)
        if err:
            notes.append(f"{token}: {err}")
        signals.append(aggregate.build_signal(token, results, method, observed_at))
    return signals, notes


def publish(chain, articles, signals, mode):
    """Save articles + signals, write them on-chain in one tx, log the run."""
    run_id, now = uuid.uuid4().hex, int(time.time())
    # Skip tokens whose on-chain history is already newer (contract would revert)
    fresh = [s for s in signals if s["observed_at"] > chain.last_observed(s["token"])]
    if not fresh:
        db.query("INSERT INTO runs (id, started_at, mode, status, message, tx_hash) VALUES (?,?,?,?,?,?)",
                 (run_id, now, mode, "skipped", "no new signals to publish", None))
        return None, None, []
    for a in articles:
        db.save_article(a)
    try:
        tx_hash, block = chain.publish_batch(fresh)
    except Exception as exc:
        db.query("INSERT INTO runs (id, started_at, mode, status, message, tx_hash) VALUES (?,?,?,?,?,?)",
                 (run_id, now, mode, "failed", str(exc)[:500], None))
        raise
    for s in fresh:
        db.save_signal(s, tx_hash, block, now)
    db.query("INSERT INTO runs (id, started_at, mode, status, message, tx_hash) VALUES (?,?,?,?,?,?)",
             (run_id, now, mode, "published", f"{len(fresh)} signals", tx_hash))
    return tx_hash, block, fresh


def run_live(chain, source="rss", post=None):
    """One live run. observedAt = latest block time, so it is never 'in the future' on-chain."""
    observed_at = chain.chain_time()
    errors = []
    if source == "rss":
        articles, errors = news.from_rss(now=observed_at)
        if not any(a["tokens"] for a in articles):
            errors.append("RSS returned no tagged headlines; fell back to sample dataset")
            source, articles = "sample", news.load_sample()
    else:
        articles = news.load_sample()
    if source == "sample":  # only the most recent 24h of the sample, like a live window
        articles = [a for a in articles if a["published_at"] >= observed_at - 86400]
    signals, notes = analyse(articles, observed_at, post=post)
    tx_hash, block, published = publish(chain, articles, signals, f"live:{source}")
    return {"source": source, "headlines": len(articles), "tx_hash": tx_hash, "block": block,
            "signals": published, "notes": errors + notes}


def backfill(chain, days=6, post=None):
    """Publish one batch per past day from the sample dataset, oldest first, so the trend
    chart has real on-chain history. Each window's observedAt = end of that day."""
    articles = news.load_sample()
    end = chain.chain_time() - 600
    out = []
    for k in range(days, 0, -1):
        w_end = end - (k - 1) * 86400
        window = [a for a in articles if w_end - 86400 < a["published_at"] <= w_end]
        if not window:
            continue
        signals, notes = analyse(window, w_end, post=post)
        tx_hash, block, published = publish(chain, window, signals, "backfill")
        out.append({"window_end": w_end, "tx_hash": tx_hash, "signals": len(published), "notes": notes})
    return out
