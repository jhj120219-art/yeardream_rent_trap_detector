from dataclasses import dataclass, field
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]

@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.getenv("BACKEND_DB_PATH", str(ROOT / "backend/data/app.sqlite3"))))
    clean_csv: Path = field(default_factory=lambda: Path(os.getenv("RENT_CLEAN_CSV", str(ROOT / "backend/data/clean_rent_data.csv"))))
    cors_origins: list[str] = field(default_factory=lambda: [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if x.strip()])
    openai_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    vision_model: str = field(default_factory=lambda: os.getenv("OPENAI_VISION_MODEL", ""))
    kakao_key: str = field(default_factory=lambda: os.getenv("KAKAO_REST_API_KEY", ""))
