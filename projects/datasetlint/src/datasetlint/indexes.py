"""Ephemeral exact-match indexes; disk storage is explicitly opt-in."""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


INDEX_BACKENDS = ("memory", "sqlite")


def validate_backend(backend):
    if backend not in INDEX_BACKENDS:
        raise ValueError("index_backend must be memory or sqlite")


class _SqliteIndex:
    def __init__(self, connection, role):
        self.connection = connection
        self.role = role

    def get(self, value):
        row = self.connection.execute(
            "SELECT split, position FROM seen WHERE role = ? AND value = ?",
            (self.role, value.encode("utf-8", "surrogatepass"))).fetchone()
        return None if row is None else (row[0].decode("utf-8", "surrogatepass"), row[1])

    def __setitem__(self, value, location):
        split, position = location
        self.connection.execute("INSERT INTO seen VALUES (?, ?, ?, ?)",
                                (self.role, value.encode("utf-8", "surrogatepass"),
                                 split.encode("utf-8", "surrogatepass"), position))


@contextmanager
def open_indexes(backend):
    validate_backend(backend)
    if backend == "memory":
        yield {}, {}
        return
    # Some custom Python builds omit sqlite3; the default backend still works.
    try:
        import sqlite3
    except ImportError:
        raise ValueError("sqlite index backend requires Python sqlite3 support") from None
    try:
        with TemporaryDirectory(prefix="datasetlint-") as directory:
            connection = sqlite3.connect(str(Path(directory) / "index.sqlite"))
            try:
                connection.execute("PRAGMA cache_size = -2048")
                connection.execute("PRAGMA temp_store = FILE")
                connection.execute("CREATE TABLE seen (role TEXT, value BLOB, split BLOB, position INTEGER, "
                                   "PRIMARY KEY (role, value)) WITHOUT ROWID")
                yield _SqliteIndex(connection, "id"), _SqliteIndex(connection, "text")
            finally:
                connection.close()
    except sqlite3.Error:
        # Do not expose indexed values or return a partially validated report.
        raise ValueError("SQLite index operation failed") from None
