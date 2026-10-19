from dataclasses import dataclass, field
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]

@dataclass
class Settings:
    db_path: Path | None = field(default_factory=lambda: Path(os.environ["BACKEND_DB_PATH"]) if os.getenv("BACKEND_DB_PATH") else None)
    db_auto_init: bool = field(default_factory=lambda: os.getenv("DB_AUTO_INIT", "true").lower() == "true")
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    clean_csv: Path = field(default_factory=lambda: Path(os.getenv("RENT_CLEAN_CSV", str(ROOT / "backend/data/clean_rent_data.csv"))))
    cors_origins: list[str] = field(default_factory=lambda: [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if x.strip()])
    openai_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    vision_model: str = field(default_factory=lambda: os.getenv("OPENAI_VISION_MODEL", ""))
    kakao_key: str = field(default_factory=lambda: os.getenv("KAKAO_REST_API_KEY", ""))
    team_key_file: str = field(default_factory=lambda: os.getenv("TEAM_ACCESS_KEY_FILE", ""))
    shared_mode: bool = field(default_factory=lambda: os.getenv("TEAM_SHARED_MODE", "false").lower() == "true")
    maintenance_enabled: bool = field(default_factory=lambda: os.getenv("MAINTENANCE_ENABLED", "true").lower() == "true")
