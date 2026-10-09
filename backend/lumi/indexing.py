"""SQLite full-text index. Triggers keep it in sync with indexed passages."""

from sqlalchemy import text

from .db import engine


def initialize_search():
    with engine.begin() as connection:
        exists = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE name='chunk_fts'"
        ).first()
        if exists and "porter unicode61" not in exists[0]:
            for trigger in ("chunks_ai", "chunks_ad", "chunks_au"):
                connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger}")
            connection.exec_driver_sql("DROP TABLE chunk_fts")
            exists = None
        connection.exec_driver_sql(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(text, content='chunks', content_rowid='rowid', tokenize='porter unicode61')"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN INSERT INTO chunk_fts(rowid,text) VALUES(new.rowid,new.text); END"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN INSERT INTO chunk_fts(chunk_fts,rowid,text) VALUES('delete',old.rowid,old.text); END"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE OF text ON chunks BEGIN INSERT INTO chunk_fts(chunk_fts,rowid,text) VALUES('delete',old.rowid,old.text); INSERT INTO chunk_fts(rowid,text) VALUES(new.rowid,new.text); END"
        )
        if not exists:
            connection.exec_driver_sql("INSERT INTO chunk_fts(chunk_fts) VALUES('rebuild')")


def keyword_candidates(session, terms: set[str]) -> dict[str, float]:
    if not terms:
        return {}
    match = " OR ".join('"' + term.replace('"', '""') + '"' for term in sorted(terms))
    rows = session.execute(
        text(
            "SELECT chunks.id, bm25(chunk_fts) AS rank FROM chunk_fts JOIN chunks ON chunks.rowid=chunk_fts.rowid JOIN sources ON sources.id=chunks.source_id WHERE sources.kind IN ('pdf', 'docx', 'txt') AND chunk_fts MATCH :match ORDER BY rank LIMIT 100"
        ),
        {"match": match},
    ).all()
    return {identifier: abs(rank) for identifier, rank in rows}
