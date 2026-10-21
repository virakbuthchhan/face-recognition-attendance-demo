"""Print PostgreSQL schema from the same ORM metadata used by the API."""
from sqlalchemy import create_mock_engine
from backend.db import Base


def emit(sql, *args, **kwargs):
    statement = str(sql.compile(dialect=engine.dialect)).strip()
    print('\n'.join(line.rstrip() for line in statement.splitlines()) + ';')


engine = create_mock_engine('postgresql+psycopg://', emit)
Base.metadata.create_all(engine)
