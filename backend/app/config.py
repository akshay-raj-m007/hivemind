import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


MIXPANEL_TOKEN = os.getenv("MIXPANEL_TOKEN", "").strip()
MIXPANEL_API_HOST = os.getenv("MIXPANEL_API_HOST", "api.mixpanel.com").strip()
ADMIN_KEY = os.getenv("ADMIN_KEY", "change-me")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
# Optional regex for extra allowed origins, e.g. Vercel preview URLs: https://hive-.*\.vercel\.app
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX", "").strip() or None
TRUST_PROXY = _bool("TRUST_PROXY")
DEV_RESOLVE_PUBLIC_IP = _bool("DEV_RESOLVE_PUBLIC_IP", True)
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "analytics.db"))

# ---- Hive tests ----
# Reading the Mind in the Eyes: Autism Research Centre allows non-commercial research use only.
ENABLE_RMET = _bool("ENABLE_RMET", True)

# NVIDIA API (build.nvidia.com). Without a key, results use the deterministic template paragraph.
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
# Chat model that rewrites verified facts into a paragraph (only when the user opts in).
# Lightning 30B writes far richer portraits than Bolt E4B; set nvidia/nemotron-3.5-bolt-e4b for speed.
NVIDIA_CHAT_MODEL = os.getenv("NVIDIA_CHAT_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
