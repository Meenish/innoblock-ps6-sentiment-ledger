"""Flask API (app factory) for the PS6 sentiment agent.

Public:
  GET  /health                         backend, chain and wallet status
  POST /run-batch                      run the agent once (cooldown-limited, admin token skips it)
  GET  /signals?token=BTC&limit=50     off-chain details for signals (headlines, reasons, tx links)
  GET  /analysis/<analysis_hash>       exact JSON whose keccak256 is stored on-chain
  GET  /runs                           recent agent runs
Admin (header X-Admin-Token):
  POST /backfill                       publish past days from the sample dataset
The dashboard reads scores/trends straight from the contract; this API adds the 'why'.
"""
import hmac
import json
import threading
import time
from collections import defaultdict, deque

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import agent
import config
import db
from chain import Chain


def create_app(chain=None, post=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024            # requests here are tiny; refuse big bodies
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)          # Render sits behind one proxy: real client IP
    CORS(app, origins=[config.FRONTEND_ORIGIN], methods=["GET", "POST", "OPTIONS"],
         allow_headers=["Content-Type", "X-Admin-Token"], max_age=600)
    chain = chain or Chain.from_env()
    db.init()
    lock = threading.Lock()          # one run at a time (avoids nonce clashes)
    state = {"last_run": 0}

    hits = defaultdict(deque)        # ip -> recent request times (in-memory, per worker)

    def is_admin():
        sent = request.headers.get("X-Admin-Token", "")
        # constant-time compare so the token cannot be guessed from response timing
        return bool(config.ADMIN_TOKEN) and hmac.compare_digest(sent.encode(), config.ADMIN_TOKEN.encode())

    def int_arg(raw, default, lo, hi):
        try:
            return max(lo, min(hi, int(raw)))
        except (TypeError, ValueError):
            return default

    @app.before_request
    def rate_limit():
        """Per-IP cap on every route (the agent run has its own, stricter cooldown)."""
        if request.method == "OPTIONS":
            return None
        now = time.time()
        q = hits[request.remote_addr or "?"]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= config.RATE_LIMIT_PER_MINUTE:
            return jsonify(error="Too many requests. Slow down."), 429
        q.append(now)
        if len(hits) > 5000:         # keep memory bounded
            for ip in [k for k, v in hits.items() if not v or v[-1] < now - 60]:
                hits.pop(ip, None)
        return None

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def with_links(row):
        row = dict(row)
        row["explorer_url"] = chain.tx_url(row["tx_hash"]) if row.get("tx_hash") else None
        return row

    @app.get("/health")
    def health():
        w3 = chain.w3
        return jsonify(ok=True, chainId=w3.eth.chain_id, contract=chain.contract.address,
                       backendWallet=chain.account.address,
                       balanceEth=float(w3.from_wei(w3.eth.get_balance(chain.account.address), "ether")),
                       isPublisher=chain.is_publisher(), tokens=config.TOKENS,
                       ai="on" if (config.AI_API_KEY and config.AI_MODEL) else "fallback (no API key)",
                       database="postgres" if config.DATABASE_URL else "sqlite")

    @app.post("/run-batch")
    def run_batch():
        source = (request.get_json(silent=True) or {}).get("source", "rss")
        if source not in ("rss", "sample"):
            return jsonify(error="source must be 'rss' or 'sample'"), 400
        wait = state["last_run"] + config.RUN_COOLDOWN_SECONDS - time.time()
        if wait > 0 and not is_admin():
            return jsonify(error=f"Agent ran recently. Try again in {int(wait) + 1}s."), 429
        if not lock.acquire(blocking=False):
            return jsonify(error="A run is already in progress."), 409
        try:
            state["last_run"] = time.time()
            result = agent.run_live(chain, source=source, post=post)
        finally:
            lock.release()
        result["explorer_url"] = chain.tx_url(result["tx_hash"]) if result["tx_hash"] else None
        result["signals"] = [{k: v for k, v in s.items() if k != "analysis_json"} for s in result["signals"]]
        return jsonify(result)

    @app.post("/backfill")
    def backfill():
        if not is_admin():
            return jsonify(error="admin token required"), 403
        days = int_arg((request.get_json(silent=True) or {}).get("days", 6), 6, 1, 14)
        if not lock.acquire(blocking=False):
            return jsonify(error="A run is already in progress."), 409
        try:
            out = agent.backfill(chain, days=days, post=post)
        finally:
            lock.release()
        return jsonify(windows=out)

    @app.get("/signals")
    def signals():
        token = (request.args.get("token") or "").upper()
        limit = int_arg(request.args.get("limit", 50), 50, 1, 200)
        if token and (len(token) > 12 or not token.isalnum()):
            return jsonify(error="invalid token"), 400
        cols = ("analysis_hash, token, score, confidence, source_count, observed_at, label, "
                "method, analysis_json, tx_hash, block_number")
        if token:
            rows = db.query(f"SELECT {cols} FROM signals WHERE token = ? "
                            "ORDER BY observed_at DESC LIMIT ?", (token, limit))
        else:
            rows = db.query(f"SELECT {cols} FROM signals ORDER BY observed_at DESC LIMIT ?", (limit,))
        out = []
        for r in rows:
            a = json.loads(r.pop("analysis_json"))
            top = set(a.get("topHeadlineIds", []))
            heads = sorted(a["headlines"], key=lambda h: -abs(h["score"]) * h["confidence"])
            r["top_headlines"] = heads[:len(top) or 3]
            out.append(with_links(r))
        return jsonify(signals=out)

    @app.get("/analysis/<analysis_hash>")
    def analysis(analysis_hash):
        rows = db.query("SELECT analysis_json, tx_hash FROM signals WHERE analysis_hash = ?",
                        (analysis_hash.lower(),))
        if not rows:
            return jsonify(error="unknown analysis hash"), 404
        # returned as raw text so the browser can keccak256 the exact bytes
        return jsonify(analysis_json=rows[0]["analysis_json"], tx_hash=rows[0]["tx_hash"])

    @app.get("/runs")
    def runs():
        rows = db.query("SELECT * FROM runs ORDER BY started_at DESC LIMIT 20")
        return jsonify(runs=[with_links(r) for r in rows])

    @app.errorhandler(Exception)
    def handle_error(e):
        if isinstance(e, HTTPException):
            return jsonify(error=e.description), e.code
        msg = str(e)
        if "insufficient funds" in msg.lower():
            msg = f"Backend wallet {chain.account.address} is out of test ETH. Use a faucet."
        elif "not an authorized publisher" in msg:
            msg = (f"Backend wallet {chain.account.address} is not a publisher. "
                   "Use the deployer's key, or call setPublisher from the owner wallet.")
        else:
            # never echo internal exception text (paths, SQL, library details) to the public
            msg = "Something went wrong on the server. Please try again."
        app.logger.exception(e)
        return jsonify(error=msg), 500

    return app