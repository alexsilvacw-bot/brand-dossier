"""Persistência em SQLite: marcas, posts, análises e dossiês."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import DATA_DIR, DB_PATH, IMAGES_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS brands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    products TEXT NOT NULL DEFAULT '',
    audience TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'pt-BR',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    image_path TEXT,
    original_filename TEXT,
    caption TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT 'instagram',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    effort TEXT,
    analysis_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_post_analyses_post ON post_analyses(post_id, created_at);

CREATE TABLE IF NOT EXISTS dossiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    model TEXT NOT NULL,
    effort TEXT,
    analysis_model TEXT,
    post_count INTEGER NOT NULL,
    markdown TEXT NOT NULL,
    aggregate_json TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(path: Path = DB_PATH) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    with connect(path) as con:
        con.executescript(SCHEMA)


@contextmanager
def connect(path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _rows(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


# --- Marcas -----------------------------------------------------------------

def create_brand(name: str, summary: str, products: str, audience: str = "", language: str = "pt-BR") -> int:
    with connect() as con:
        cur = con.execute(
            "INSERT INTO brands (name, summary, products, audience, language, created_at) VALUES (?,?,?,?,?,?)",
            (name.strip(), summary.strip(), products.strip(), audience.strip(), language, _now()),
        )
        return int(cur.lastrowid)


def update_brand(brand_id: int, name: str, summary: str, products: str, audience: str, language: str) -> None:
    with connect() as con:
        con.execute(
            "UPDATE brands SET name=?, summary=?, products=?, audience=?, language=? WHERE id=?",
            (name.strip(), summary.strip(), products.strip(), audience.strip(), language, brand_id),
        )


def list_brands() -> list[dict[str, Any]]:
    with connect() as con:
        return _rows(con.execute("SELECT * FROM brands ORDER BY created_at DESC"))


def get_brand(brand_id: int) -> dict[str, Any] | None:
    with connect() as con:
        row = con.execute("SELECT * FROM brands WHERE id=?", (brand_id,)).fetchone()
        return dict(row) if row else None


def delete_brand(brand_id: int) -> None:
    for p in list_posts(brand_id):
        _remove_image(p.get("image_path"))
    with connect() as con:
        con.execute("DELETE FROM brands WHERE id=?", (brand_id,))


# --- Posts ------------------------------------------------------------------

def add_post(brand_id: int, image_path: str | None, original_filename: str | None, caption: str,
             platform: str = "instagram") -> int:
    with connect() as con:
        cur = con.execute(
            "INSERT INTO posts (brand_id, image_path, original_filename, caption, platform, created_at) VALUES (?,?,?,?,?,?)",
            (brand_id, image_path, original_filename, caption.strip(), platform, _now()),
        )
        return int(cur.lastrowid)


def update_post_caption(post_id: int, caption: str) -> None:
    with connect() as con:
        con.execute("UPDATE posts SET caption=? WHERE id=?", (caption.strip(), post_id))


def list_posts(brand_id: int) -> list[dict[str, Any]]:
    with connect() as con:
        return _rows(con.execute("SELECT * FROM posts WHERE brand_id=? ORDER BY id", (brand_id,)))


def get_post(post_id: int) -> dict[str, Any] | None:
    with connect() as con:
        row = con.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        return dict(row) if row else None


def _remove_image(path: str | None) -> None:
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def delete_post(post_id: int) -> None:
    post = get_post(post_id)
    if post:
        _remove_image(post.get("image_path"))
    with connect() as con:
        con.execute("DELETE FROM posts WHERE id=?", (post_id,))


# --- Análises ---------------------------------------------------------------

def save_analysis(post_id: int, model: str, effort: str | None, analysis: dict, metrics: dict,
                  usage: dict[str, int], cost_usd: float) -> int:
    with connect() as con:
        cur = con.execute(
            """INSERT INTO post_analyses
               (post_id, model, effort, analysis_json, metrics_json, input_tokens, output_tokens,
                cache_read_tokens, cache_write_tokens, cost_usd, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                post_id, model, effort,
                json.dumps(analysis, ensure_ascii=False),
                json.dumps(metrics, ensure_ascii=False),
                usage.get("input_tokens", 0), usage.get("output_tokens", 0),
                usage.get("cache_read_input_tokens", 0), usage.get("cache_creation_input_tokens", 0),
                cost_usd, _now(),
            ),
        )
        return int(cur.lastrowid)


def latest_analyses(brand_id: int) -> dict[int, dict[str, Any]]:
    """Análise mais recente de cada post da marca, indexada por post_id."""
    with connect() as con:
        rows = _rows(con.execute(
            """SELECT a.* FROM post_analyses a
               JOIN posts p ON p.id = a.post_id
               WHERE p.brand_id = ?
               AND a.id = (SELECT MAX(id) FROM post_analyses WHERE post_id = a.post_id)""",
            (brand_id,),
        ))
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        r["analysis"] = json.loads(r.pop("analysis_json"))
        r["metrics"] = json.loads(r.pop("metrics_json"))
        out[int(r["post_id"])] = r
    return out


# --- Dossiês ----------------------------------------------------------------

def save_dossier(brand_id: int, model: str, effort: str | None, analysis_model: str | None, post_count: int,
                 markdown: str, aggregate: dict, usage: dict[str, int], cost_usd: float) -> int:
    with connect() as con:
        version = con.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM dossiers WHERE brand_id=?",
                              (brand_id,)).fetchone()[0]
        cur = con.execute(
            """INSERT INTO dossiers
               (brand_id, version, model, effort, analysis_model, post_count, markdown, aggregate_json,
                input_tokens, output_tokens, cost_usd, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (brand_id, version, model, effort, analysis_model, post_count, markdown,
             json.dumps(aggregate, ensure_ascii=False),
             usage.get("input_tokens", 0), usage.get("output_tokens", 0), cost_usd, _now()),
        )
        return int(cur.lastrowid)


def list_dossiers(brand_id: int) -> list[dict[str, Any]]:
    with connect() as con:
        rows = _rows(con.execute(
            "SELECT id, brand_id, version, model, effort, analysis_model, post_count, input_tokens, output_tokens, cost_usd, created_at "
            "FROM dossiers WHERE brand_id=? ORDER BY version DESC", (brand_id,)))
    return rows


def get_dossier(dossier_id: int) -> dict[str, Any] | None:
    with connect() as con:
        row = con.execute("SELECT * FROM dossiers WHERE id=?", (dossier_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["aggregate"] = json.loads(d.pop("aggregate_json"))
    return d


def brand_cost_summary(brand_id: int) -> dict[str, float]:
    with connect() as con:
        a = con.execute(
            "SELECT COALESCE(SUM(a.cost_usd),0) FROM post_analyses a JOIN posts p ON p.id=a.post_id WHERE p.brand_id=?",
            (brand_id,)).fetchone()[0]
        d = con.execute("SELECT COALESCE(SUM(cost_usd),0) FROM dossiers WHERE brand_id=?", (brand_id,)).fetchone()[0]
    return {"analyses_usd": float(a), "dossiers_usd": float(d), "total_usd": float(a) + float(d)}
