# Sentiment Ledger (INNOBLOCK 2.0, PS 6)

An AI agent reads crypto headlines, scores each token as bullish, bearish or neutral with a
confidence value, and publishes one record per token to a smart contract on Ethereum Sepolia.
A web dashboard draws the sentiment trend **directly from the on-chain records**.

| | |
|---|---|
| **Contract (verified)** | [`0x119cC959d84C882893468134eC0F5b78f571EF5B`](https://sepolia.etherscan.io/address/0x119cC959d84C882893468134eC0F5b78f571EF5B#code) on Ethereum Sepolia |
| **Live dashboard** | https://sentiment-ledger-api.onrender.com |
| **Backend API** | https://sentiment-ledger-api.onrender.com/health |
| **Demo video** | _add link_ |
| **Repo** | https://github.com/Meenish/innoblock-ps6-sentiment-ledger |

## Why a blockchain
Crypto sentiment is scattered across many articles and hard to track over time. A database run by
one operator can be edited after the fact. The contract is a shared, timestamped, tamper-evident log:
any trader or other contract can read exactly what the agent published and when. Only an authorized
publisher wallet can write, each token's entries must move forward in time, and history cannot be changed.

The chain proves **what was published and when**. It does not prove the AI was right.

## What is on-chain and what is off-chain
| On-chain (per token, per news window) | Off-chain (database) |
|---|---|
| token, score (-100..100), confidence (0..100), source count, observedAt, recordedAt, analysisHash | full headlines, sources, URLs, per-headline scores and AI reasons, the exact analysis JSON |

`analysisHash = keccak256(analysis JSON)`. The dashboard re-hashes the stored analysis and compares it
with the chain: change one character and verification fails.

## Architecture
```
RSS feeds / sample dataset
        |
  Backend (Flask + web3.py) -- AI scorer (OpenAI-compatible API, keyword fallback)
        |  aggregate per token, save the analysis in Postgres/SQLite
        |  sign publishBatch() with the publisher wallet
        v
  SentimentRegistry.sol on Sepolia  <-- Dashboard reads history directly (ethers.js)
                                        and asks the backend only for headlines and reasons
```

**Aggregation.** Score = confidence-weighted mean of the headline scores. Confidence = weighted mean
confidence, scaled by how much the headlines agree. Label: score >= 20 bullish, <= -20 bearish, otherwise
neutral (the same rule as the contract's `classify()`). Source count = number of headlines used.
Details in `backend/aggregate.py`.

## Repository layout
```
contracts/SentimentRegistry.sol   the contract (Solidity 0.8.24, optimizer off, EVM cancun)
backend/                          agent + API (app.py is the entry point)
frontend/                         dashboard (edit config.js only)
tests/                            contract and end-to-end backend tests
```

## Run locally
Backend (Python 3.10+):
```
cd backend
python -m venv venv
venv\Scripts\activate            # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # Mac/Linux: cp .env.example .env, then fill it in
python app.py                    # http://localhost:5000/health
```
Frontend (second terminal):
```
cd frontend
python -m http.server 8000       # open http://localhost:8000 (not as a file://)
```

## Environment variables (backend/.env, never committed)
| Name | Purpose |
|---|---|
| `PRIVATE_KEY` | burner wallet that is an authorized publisher (the deployer) |
| `RPC_URL`, `CONTRACT_ADDRESS`, `EXPLORER_URL` | network and contract |
| `DATABASE_URL` | Postgres connection string (Neon/Supabase); empty = local SQLite |
| `FRONTEND_ORIGIN` | exact frontend URL for CORS |
| `ADMIN_TOKEN` | protects `/backfill` and skips the run cooldown |
| `API_KEY`, `AI_BASE_URL`, `AI_MODEL` | AI provider; an empty key uses the keyword fallback scorer |
| `TOKENS`, `NEWS_WINDOW_HOURS`, `MAX_HEADLINES_PER_TOKEN`, `RUN_COOLDOWN_SECONDS` | agent settings |

## API
`GET /health` | `POST /run-batch {"source":"rss"|"sample"}` | `GET /signals?token=BTC` |
`GET /analysis/<hash>` | `GET /runs` | `POST /backfill` (header `X-Admin-Token`)

## How to test
1. Open the dashboard. Token tabs, the big score and the chart load from the contract.
2. Press **Run agent now**: pending, then confirmed with a block number and an Etherscan link. The chart gains a point.
3. In **Check it against the chain**, press Verify (matches), edit one character, press Verify again (fails).
4. Stop the backend and reload. Scores and the chart still load, because they come from the chain.
5. Automated: `python tests/test_contract.py` and `python tests/test_backend.py` (local EVM; needs `pip install "eth-tester[py-evm]"`).

## Security
- The publisher key lives only in `backend/.env` and in the hosting provider's environment settings. It is never committed and never sent to the browser.
- Only authorized publisher addresses can write to the contract. The owner can add or revoke publishers.
- The contract validates every input (token format, score and confidence range, non-zero sources, no future timestamps, time-ordered history).
- Burner testnet wallet only. No mainnet, no real funds.

## Honesty notes
- History before the first live run was backfilled from `backend/data/sample_headlines.json`, a **synthetic** dataset. Those records say "Sample dataset (synthetic)" inside their analysis.
- Live runs use real RSS headlines (CoinDesk, Cointelegraph, Decrypt). A feed that fails is skipped.
- Token tagging is keyword-based; the AI scores each headline's impact on the token.
- Sentiment is an information signal, not a price prediction or trading advice.

## Team
_Add names and roles._
