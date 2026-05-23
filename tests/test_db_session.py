from sqlalchemy import Engine

from kortny.db.session import make_engine, make_session_factory, normalize_database_url


def test_normalize_database_url_uses_psycopg_driver() -> None:
    assert (
        normalize_database_url("postgresql://kortny:kortny@localhost:5432/kortny")
        == "postgresql+psycopg://kortny:kortny@localhost:5432/kortny"
    )


def test_normalize_database_url_preserves_explicit_driver() -> None:
    assert (
        normalize_database_url("postgresql+psycopg://kortny:kortny@localhost/kortny")
        == "postgresql+psycopg://kortny:kortny@localhost/kortny"
    )


def test_make_engine_uses_normalized_postgres_driver() -> None:
    engine = make_engine("postgresql://kortny:kortny@localhost:5432/kortny")

    try:
        assert engine.url.drivername == "postgresql+psycopg"
    finally:
        engine.dispose()


def test_make_session_factory_accepts_existing_engine() -> None:
    engine = make_engine("postgresql://kortny:kortny@localhost:5432/kortny")

    try:
        session_factory = make_session_factory(engine=engine)
        session = session_factory()
        try:
            assert session.bind is engine
            assert isinstance(session.bind, Engine)
        finally:
            session.close()
    finally:
        engine.dispose()
