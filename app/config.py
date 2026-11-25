import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
DB_PATH = env("DB_PATH", str(ROOT / "mausam.db"))
MEDIA_DIR = ROOT / "media"
DEPLOYMENTS_FILE = ROOT / "deployments.json"

# Sarvam
SARVAM_API_KEY = env("SARVAM_API_KEY")
SARVAM_STT_MODEL = env("SARVAM_STT_MODEL", "saarika:v2.5")
SARVAM_CHAT_MODEL = env("SARVAM_CHAT_MODEL", "sarvam-105b-conversations")
SARVAM_TTS_MODEL = env("SARVAM_TTS_MODEL", "bulbul:v3")

# Twilio WhatsApp sandbox
TWILIO_ACCOUNT_SID = env("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = env("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = env("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
# Optional: authenticate with an API key (SK...) + secret instead of the auth token
TWILIO_API_KEY_SID = env("TWILIO_API_KEY_SID")
TWILIO_API_KEY_SECRET = env("TWILIO_API_KEY_SECRET")
TWILIO_AUTH = (TWILIO_API_KEY_SID, TWILIO_API_KEY_SECRET) if TWILIO_API_KEY_SID else (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Telegram bot (demo channel with two-way replies)
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")

# Razorpay (TEST MODE ONLY)
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET")

# Flagsmith
FLAGSMITH_ENV_KEY = env("FLAGSMITH_ENV_KEY")

# Chain (testnet)
CHAIN_RPC_URL = env("CHAIN_RPC_URL")
CHAIN_PRIVATE_KEY = env("CHAIN_PRIVATE_KEY")
CHAIN_EXPLORER_TX = env("CHAIN_EXPLORER_TX", "https://sepolia.basescan.org/tx/")

# Oracle worker -> app
ORACLE_TOKEN = env("ORACLE_TOKEN", "dev-oracle-token")
ORACLE_STALE_SECONDS = int(env("ORACLE_STALE_SECONDS", "90"))

if RAZORPAY_KEY_ID and not RAZORPAY_KEY_ID.startswith("rzp_test_"):
    raise SystemExit("Refusing to start: RAZORPAY_KEY_ID must be a TEST key (rzp_test_...).")
