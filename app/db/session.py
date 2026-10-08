from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base


def make_session_factory(database_url: str) -> sessionmaker:
    kwargs = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(database_url, **kwargs)
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(session_factory: sessionmaker) -> None:
    """Membuat tabel jika belum ada. Penyederhanaan: belum memakai migration (Alembic)."""
    Base.metadata.create_all(session_factory.kw["bind"])
