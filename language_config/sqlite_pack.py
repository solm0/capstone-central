import json
import sqlite3
import threading
from pathlib import Path
from typing import Iterable


PACK_TABLES = {
    "lines",
    "lemma_graph",
    "lemma_stats",
    "ngram_bi",
    "ngram_tri",
    "ngram_uni",
    "prefix_index",
}

PACK_DB_SUFFIXES = (".sqlite3", ".sqlite", ".db")


def find_pack_db(version_path: Path) -> Path | None:
    if not version_path.exists() or not version_path.is_dir():
        return None

    candidates = [
        path
        for path in sorted(version_path.iterdir())
        if path.is_file() and path.suffix.lower() in PACK_DB_SUFFIXES
    ]

    if not candidates:
        return None

    preferred_names = {
        "language_pack.sqlite3",
        "language_pack.sqlite",
        "language_pack.db",
        "pack.sqlite3",
        "pack.sqlite",
        "pack.db",
    }

    candidates.sort(
        key=lambda path: (
            path.name not in preferred_names,
            len(path.name),
            path.name,
        )
    )
    return candidates[0]


def has_required_tables(
    db_path: Path,
    required_tables: Iterable[str] = PACK_TABLES,
) -> bool:
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return False

    existing = {name for (name,) in rows}
    return set(required_tables).issubset(existing)


class LanguagePackDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)

        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn

        return conn

    def _fetch_pairs(self, query: str, params=()):
        try:
            rows = self._get_conn().execute(query, params).fetchall()
        except sqlite3.Error:
            return []

        return [(row[0], row[1]) for row in rows]

    def _fetch_pairs_with_fallback(
        self,
        query: str,
        params=(),
        fallback_query: str | None = None,
    ):
        try:
            rows = self._get_conn().execute(query, params).fetchall()
        except sqlite3.Error:
            if fallback_query is None:
                return []

            try:
                rows = self._get_conn().execute(fallback_query, params).fetchall()
            except sqlite3.Error:
                return []

        return [(row[0], row[1]) for row in rows]

    def _fetch_json_payload(self, table: str, key_column: str, key: str):
        try:
            row = self._get_conn().execute(
                f"SELECT payload FROM {table} WHERE {key_column} = ?",
                (key,),
            ).fetchone()
        except sqlite3.Error:
            return None

        if row is None:
            return None

        try:
            return json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            return None

    def _fetch_json_payloads(
        self,
        table: str,
        key_column: str,
        keys: list[str],
        chunk_size: int = 500,
    ):
        if not keys:
            return {}

        result = {}

        for i in range(0, len(keys), chunk_size):
            chunk = keys[i:i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)

            try:
                rows = self._get_conn().execute(
                    (
                        f"SELECT {key_column} AS key, payload "
                        f"FROM {table} "
                        f"WHERE {key_column} IN ({placeholders})"
                    ),
                    chunk,
                ).fetchall()
            except sqlite3.Error:
                continue

            for row in rows:
                try:
                    result[row["key"]] = json.loads(row["payload"])
                except (TypeError, json.JSONDecodeError):
                    continue

        return result

    def get_unigrams(self, limit: int | None = None):
        query = "SELECT token, score FROM ngram_uni ORDER BY score DESC"
        fallback_query = "SELECT token, freq FROM ngram_uni ORDER BY freq DESC"

        if limit is not None:
            query += " LIMIT ?"
            fallback_query += " LIMIT ?"
            return self._fetch_pairs_with_fallback(
                query,
                (limit,),
                fallback_query=fallback_query,
            )

        return self._fetch_pairs_with_fallback(query, fallback_query=fallback_query)

    def get_bigram(self, context: tuple[str], limit: int | None = None):
        if not context:
            return []

        query = (
            "SELECT next_token, score "
            "FROM ngram_bi "
            "WHERE w1 = ? "
            "ORDER BY score DESC"
        )
        fallback_query = (
            "SELECT next_token, freq "
            "FROM ngram_bi "
            "WHERE w1 = ? "
            "ORDER BY freq DESC"
        )

        params = context

        if limit is not None:
            query += " LIMIT ?"
            fallback_query += " LIMIT ?"
            params = (*context, limit)

        return self._fetch_pairs_with_fallback(
            query,
            params,
            fallback_query=fallback_query,
        )

    def get_trigram(self, context: tuple[str, str], limit: int | None = None):
        if len(context) != 2:
            return []

        query = (
            "SELECT next_token, score "
            "FROM ngram_tri "
            "WHERE w1 = ? AND w2 = ? "
            "ORDER BY score DESC"
        )
        fallback_query = (
            "SELECT next_token, freq "
            "FROM ngram_tri "
            "WHERE w1 = ? AND w2 = ? "
            "ORDER BY freq DESC"
        )

        params = context

        if limit is not None:
            query += " LIMIT ?"
            fallback_query += " LIMIT ?"
            params = (*context, limit)

        return self._fetch_pairs_with_fallback(
            query,
            params,
            fallback_query=fallback_query,
        )

    def get_prefix_matches(self, prefix: str):
        if not prefix:
            return []

        return self._fetch_pairs(
            (
                "SELECT token, freq "
                "FROM prefix_index "
                "WHERE prefix = ? "
                "ORDER BY freq DESC"
            ),
            (prefix,),
        )

    def has_lemma_key(self, key: str) -> bool:
        try:
            row = self._get_conn().execute(
                "SELECT 1 FROM lemma_stats WHERE lemma_key = ? LIMIT 1",
                (key,),
            ).fetchone()
        except sqlite3.Error:
            return False

        return row is not None

    def get_related(self, key: str, limit: int = 5):
        related = self._fetch_json_payload("lemma_graph", "lemma_key", key)

        if not isinstance(related, list):
            return []

        return related[:limit]

    def get_line_ids(self, key: str):
        stats = self._fetch_json_payload("lemma_stats", "lemma_key", key)

        if not isinstance(stats, dict):
            return []

        line_ids = stats.get("lines", [])
        return line_ids if isinstance(line_ids, list) else []

    def get_lines(self, line_ids: list[str]):
        rows = self._fetch_json_payloads("lines", "line_id", line_ids)
        return [rows[line_id] for line_id in line_ids if line_id in rows]
