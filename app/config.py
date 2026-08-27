import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "MajdataServer"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    API3_PREFIX: str = "/api3/api"
    
    # Secret Key for sessions/tokens
    SECRET_KEY: str = os.getenv("SECRET_KEY", "majdata-super-secret-key-change-in-production")
    SESSION_EXPIRE_DAYS: int = 30
    
    # Base directory for charts and data
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))
    CHARTS_DIR: Path = Path(os.getenv("CHARTS_DIR", str(Path(__file__).resolve().parent.parent.parent / "MajdataProvider" / "charts")))
    AVATARS_DIR: Path = Path(os.getenv("AVATARS_DIR", str(Path(__file__).resolve().parent.parent / "data" / "avatars")))
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{Path(__file__).resolve().parent.parent / 'data' / 'majdata.db'}")
    
    # Cloudflare Turnstile (Optional, empty by default to allow offline/local register)
    TURNSTILE_SECRET_KEY: str = os.getenv("TURNSTILE_SECRET_KEY", "")
    REQUIRE_TURNSTILE: bool = False
    
    # Mail verification (Optional, auto-activate user if SMTP is not configured)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "noreply@majdata.net")
    AUTO_ACTIVATE_USERS: bool = True

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }

settings = Settings()

# Ensure directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.AVATARS_DIR.mkdir(parents=True, exist_ok=True)
if not settings.CHARTS_DIR.exists():
    settings.CHARTS_DIR.mkdir(parents=True, exist_ok=True)
