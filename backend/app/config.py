import os

from dotenv import load_dotenv

load_dotenv()


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
    return url


def user_agent() -> str:
    ua = os.environ.get("USER_AGENT", "").strip()
    if not ua or "you@yourdomain.com" in ua:
        raise RuntimeError("Set USER_AGENT with a real contact address (see .env.example)")
    return ua
