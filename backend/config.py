"""All settings come from environment variables (backend/.env locally, Render's
Environment tab when deployed). Nothing secret is ever hard-coded."""
import os
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

RPC_URL = os.getenv("RPC_URL", "")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
EXPLORER_URL = os.getenv("EXPLORER_URL", "https://sepolia.etherscan.io").rstrip("/")
# Exactly one allowed website (no trailing slash). Never "*": any site could then call the API.
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://innoblock-ps6-sentiment-ledger-fron.vercel.app").rstrip("/")
DATABASE_URL = os.getenv("DATABASE_URL", "")          # empty = local SQLite file

# AI: any OpenAI-compatible chat API (Groq, Gemini, OpenRouter...). Empty key = fallback scorer.
AI_API_KEY = os.getenv("API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "")

# Admin token for /backfill and for skipping the /run-batch cooldown. Keep it secret.
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
RUN_COOLDOWN_SECONDS = int(os.getenv("RUN_COOLDOWN_SECONDS", "120"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))   # per IP, all routes

# Which tokens we track (keep the list small: every token = AI calls + gas)
TOKENS = [t.strip().upper() for t in os.getenv("TOKENS", "BTC,ETH,SOL,XRP,DOGE").split(",") if t.strip()]

# Free RSS feeds, no API key needed
RSS_FEEDS = [u.strip() for u in os.getenv(
    "RSS_FEEDS",
    "https://www.coindesk.com/arc/outboundfeeds/rss/,"
    "https://cointelegraph.com/rss,"
    "https://decrypt.co/feed",
).split(",") if u.strip()]
NEWS_WINDOW_HOURS = int(os.getenv("NEWS_WINDOW_HOURS", "24"))
MAX_HEADLINES_PER_TOKEN = int(os.getenv("MAX_HEADLINES_PER_TOKEN", "15"))