"""DB 엔진·세션·모델. DATABASE_URL 없으면 로컬 SQLite(deploy/local.db)."""
import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, UniqueConstraint, func
from sqlalchemy.orm import declarative_base, sessionmaker

_url = os.environ.get("DATABASE_URL", "sqlite:///local.db")
# Render/Heroku 스타일 postgres:// → postgresql:// 보정
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql://", 1)

engine = create_engine(_url, future=True,
                       connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, future=True)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    pw_hash = Column(String(255), nullable=False)
    created = Column(DateTime, server_default=func.now())


class UserConfig(Base):
    __tablename__ = "user_config"
    user_id = Column(Integer, primary_key=True)
    json = Column(Text, nullable=False, default="{}")


class UserData(Base):
    """kind ∈ dailyGoals/events/conditions/selfDev/fillers/overrides/habits/goals/tasks/gradTasks/plan.
    date는 날짜별 데이터용(없으면 빈문자열). plan은 kind='plan', date=YYYY-MM-DD."""
    __tablename__ = "user_data"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    kind = Column(String(40), nullable=False)
    date = Column(String(10), nullable=False, default="")
    json = Column(Text, nullable=False, default="{}")
    __table_args__ = (UniqueConstraint("user_id", "kind", "date", name="uq_user_kind_date"),)


def init_db():
    Base.metadata.create_all(engine)
