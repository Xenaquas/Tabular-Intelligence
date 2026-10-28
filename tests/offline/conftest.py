"""Test-only ownership and temporary storage; production isolation is Phase 0B."""

import gc

import pytest


@pytest.fixture
def engine(monkeypatch, tmp_path):
    from core.db_engine import DatabaseEngine
    from core.metadata_store import SQLiteMetadataStore
    from core.tools.artifact_store import ArtifactStore

    # SQLite's connection context commits but does not close. Own handles here
    # so Windows can clean temporary fixture databases deterministically.
    monkeypatch.setattr(SQLiteMetadataStore, "_instance", None)
    original_connect = SQLiteMetadataStore._get_connection
    handles = []

    def connect(store):
        conn = original_connect(store)
        handles.append(conn)
        return conn

    monkeypatch.setattr(SQLiteMetadataStore, "_get_connection", connect)
    metadata = SQLiteMetadataStore(str(tmp_path / "metadata.db"))
    monkeypatch.setattr(SQLiteMetadataStore, "_instance", metadata)
    db = DatabaseEngine()
    monkeypatch.setattr(DatabaseEngine, "_instance", db)
    monkeypatch.setattr(ArtifactStore, "_instance", ArtifactStore())
    try:
        yield db
    finally:
        db._conn.close()
        for conn in handles:
            conn.close()
        gc.collect()


@pytest.fixture
def dataset(engine, monkeypatch):
    import pandas as pd
    from pathlib import Path

    from core.db_engine import DatabaseEngine
    from core.tools.artifact_store import ArtifactStore

    monkeypatch.setattr(DatabaseEngine, "_instance", engine)
    store = ArtifactStore()
    monkeypatch.setattr(ArtifactStore, "_instance", store)
    path = Path(__file__).resolve().parents[2] / "data" / "retail_sales_sample.csv"
    frame = pd.read_csv(path)
    engine.register_dataframe(frame, "retail_sales")
    return frame, engine, store
