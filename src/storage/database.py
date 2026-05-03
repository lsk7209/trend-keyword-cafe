from pathlib import Path

from sqlmodel import SQLModel, create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "topic_radar.db"
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(DATABASE_URL, echo=False)


def init_db() -> None:
    """SQLite DB와 테이블을 생성합니다."""

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
