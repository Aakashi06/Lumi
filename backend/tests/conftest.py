import os
import tempfile
from pathlib import Path

import pytest

TEST_DIR = tempfile.TemporaryDirectory(prefix="lumi-tests-")
os.environ["LUMI_DATABASE_URL"] = f"sqlite:///{TEST_DIR.name}/test.db"
from lumi.db import Base, Session, Source, engine  # noqa: E402 — isolate settings first


@pytest.fixture(autouse=True)
def database():
    with engine.begin() as connection:
        for trigger in ("chunks_ai", "chunks_ad", "chunks_au"):
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger}")
        connection.exec_driver_sql("DROP TABLE IF EXISTS chunk_fts")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from lumi.indexing import initialize_search

    initialize_search()
    yield
    # Test-generated PDF uploads are disposable; never touch the user's database.
    with Session() as session:
        for source in session.query(Source).all():
            if source.file_path:
                path = Path(source.file_path)
                if path.parent == Path("data/uploads").resolve():
                    path.unlink(missing_ok=True)
