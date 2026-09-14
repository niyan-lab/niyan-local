"""Vector store providers: Qdrant (REST) and Postgres + pgvector."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List, Optional, Protocol

import httpx
import psycopg
from psycopg.rows import dict_row

from app.settings import settings

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _validate_collection(name: str) -> str:
    if not _SAFE_NAME.match(name):
        raise ValueError("collection name must be 1-64 chars of [a-zA-Z0-9_-]")
    return name


class VectorStore(Protocol):
    async def health(self) -> Dict[str, Any]: ...

    async def list_collections(self) -> List[Dict[str, Any]]: ...

    async def create_collection(self, name: str, size: int) -> Dict[str, Any]: ...

    async def delete_collection(self, name: str) -> Dict[str, Any]: ...

    async def upsert(self, collection: str, points: List[Dict[str, Any]]) -> Dict[str, Any]: ...

    async def search(
        self, collection: str, vector: List[float], limit: int = 5
    ) -> List[Dict[str, Any]]: ...


class QdrantStore:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base = (base_url or settings.qdrant_url).rstrip("/")

    async def health(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base}/readyz")
                ok = r.status_code < 500
                return {"ok": ok, "provider": "qdrant", "detail": r.text[:200]}
        except Exception as exc:
            return {"ok": False, "provider": "qdrant", "detail": str(exc)}

    async def list_collections(self) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{self.base}/collections")
            r.raise_for_status()
            result = r.json().get("result", {})
            cols = result.get("collections", [])
            out: List[Dict[str, Any]] = []
            for c in cols:
                name = c.get("name", "")
                info = await client.get(f"{self.base}/collections/{name}")
                size = None
                points = None
                if info.status_code < 400:
                    cfg = info.json().get("result", {})
                    points = cfg.get("points_count")
                    vectors = cfg.get("config", {}).get("params", {}).get("vectors", {})
                    if isinstance(vectors, dict):
                        size = vectors.get("size")
                out.append({"name": name, "size": size, "points": points})
            return out

    async def create_collection(self, name: str, size: int) -> Dict[str, Any]:
        name = _validate_collection(name)
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.put(
                f"{self.base}/collections/{name}",
                json={"vectors": {"size": size, "distance": "Cosine"}},
            )
            if r.status_code >= 400:
                raise RuntimeError(r.text)
            return {"ok": True, "name": name, "size": size, "provider": "qdrant"}

    async def delete_collection(self, name: str) -> Dict[str, Any]:
        name = _validate_collection(name)
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.delete(f"{self.base}/collections/{name}")
            if r.status_code >= 400:
                raise RuntimeError(r.text)
            return {"ok": True, "name": name, "deleted": True}

    async def upsert(self, collection: str, points: List[Dict[str, Any]]) -> Dict[str, Any]:
        collection = _validate_collection(collection)
        payload = {"points": []}
        for p in points:
            original = str(p["id"])
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"niyan:{collection}:{original}"))
            payload["points"].append(
                {
                    "id": point_id,
                    "vector": p["vector"],
                    "payload": {**(p.get("payload") or {}), "_niyan_id": original},
                }
            )

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.put(
                f"{self.base}/collections/{collection}/points",
                params={"wait": "true"},
                json=payload,
            )
            if r.status_code >= 400:
                raise RuntimeError(r.text)
            return {"ok": True, "upserted": len(points), "result": r.json().get("result")}

    async def search(
        self, collection: str, vector: List[float], limit: int = 5
    ) -> List[Dict[str, Any]]:
        collection = _validate_collection(collection)
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base}/collections/{collection}/points/search",
                json={"vector": vector, "limit": limit, "with_payload": True},
            )
            if r.status_code >= 400:
                raise RuntimeError(r.text)
            hits = r.json().get("result", [])
            out = []
            for h in hits:
                payload = h.get("payload") or {}
                point_id = payload.get("_niyan_id", h.get("id"))
                out.append(
                    {
                        "id": point_id,
                        "score": h.get("score"),
                        "payload": {k: v for k, v in payload.items() if k != "_niyan_id"},
                    }
                )
            return out


class PgvectorStore:
    def __init__(self, dsn: Optional[str] = None) -> None:
        self.dsn = dsn or settings.pgvector_dsn

    def _connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def ensure_schema(self) -> None:
        """Create meta table + extension. Safe to call repeatedly."""
        # Connect to target DB; if missing, create via maintenance DB
        try:
            with self._connect() as conn:
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS niyan_collections (
                        name TEXT PRIMARY KEY,
                        dimensions INT NOT NULL
                    )
                    """
                )
                conn.commit()
        except psycopg.OperationalError as exc:
            if "does not exist" not in str(exc):
                raise
            self._create_database()
            with self._connect() as conn:
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS niyan_collections (
                        name TEXT PRIMARY KEY,
                        dimensions INT NOT NULL
                    )
                    """
                )
                conn.commit()

    def _create_database(self) -> None:
        # postgresql://user:pass@host:port/dbname → connect to postgres
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(self.dsn)
        dbname = (parsed.path or "/niyan_vectors").lstrip("/") or "niyan_vectors"
        admin = urlunparse(parsed._replace(path="/postgres"))
        with psycopg.connect(admin, autocommit=True) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{dbname}"')

    async def health(self) -> Dict[str, Any]:
        try:
            self.ensure_schema()
            with self._connect() as conn:
                row = conn.execute("SELECT extname FROM pg_extension WHERE extname='vector'").fetchone()
            return {
                "ok": bool(row),
                "provider": "pgvector",
                "detail": "extension ready" if row else "vector extension missing",
            }
        except Exception as exc:
            return {"ok": False, "provider": "pgvector", "detail": str(exc)}

    def _table(self, name: str) -> str:
        name = _validate_collection(name)
        return f"c_{name}"

    async def list_collections(self) -> List[Dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute("SELECT name, dimensions FROM niyan_collections ORDER BY name").fetchall()
            out = []
            for row in rows:
                table = self._table(row["name"])
                try:
                    count_row = conn.execute(f'SELECT COUNT(*) AS n FROM "{table}"').fetchone()
                    points = count_row["n"] if count_row else 0
                except Exception:
                    points = 0
                out.append({"name": row["name"], "size": row["dimensions"], "points": points})
            return out

    async def create_collection(self, name: str, size: int) -> Dict[str, Any]:
        name = _validate_collection(name)
        table = self._table(name)
        self.ensure_schema()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO niyan_collections (name, dimensions) VALUES (%s, %s) "
                "ON CONFLICT (name) DO UPDATE SET dimensions = EXCLUDED.dimensions",
                (name, size),
            )
            conn.execute(
                f'''
                CREATE TABLE IF NOT EXISTS "{table}" (
                    id TEXT PRIMARY KEY,
                    embedding vector({int(size)}) NOT NULL,
                    payload JSONB NOT NULL DEFAULT '{{}}'::jsonb
                )
                '''
            )
            conn.commit()
        return {"ok": True, "name": name, "size": size, "provider": "pgvector"}

    async def delete_collection(self, name: str) -> Dict[str, Any]:
        name = _validate_collection(name)
        table = self._table(name)
        self.ensure_schema()
        with self._connect() as conn:
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            conn.execute("DELETE FROM niyan_collections WHERE name = %s", (name,))
            conn.commit()
        return {"ok": True, "name": name, "deleted": True}

    async def upsert(self, collection: str, points: List[Dict[str, Any]]) -> Dict[str, Any]:
        collection = _validate_collection(collection)
        table = self._table(collection)
        self.ensure_schema()
        with self._connect() as conn:
            for p in points:
                vec = p["vector"]
                vec_literal = "[" + ",".join(str(float(x)) for x in vec) + "]"
                conn.execute(
                    f'''
                    INSERT INTO "{table}" (id, embedding, payload)
                    VALUES (%s, %s::vector, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE
                      SET embedding = EXCLUDED.embedding,
                          payload = EXCLUDED.payload
                    ''',
                    (str(p["id"]), vec_literal, json.dumps(p.get("payload") or {})),
                )
            conn.commit()
        return {"ok": True, "upserted": len(points)}

    async def search(
        self, collection: str, vector: List[float], limit: int = 5
    ) -> List[Dict[str, Any]]:
        collection = _validate_collection(collection)
        table = self._table(collection)
        self.ensure_schema()
        vec_literal = "[" + ",".join(str(float(x)) for x in vector) + "]"
        with self._connect() as conn:
            rows = conn.execute(
                f'''
                SELECT id, payload,
                       1 - (embedding <=> %s::vector) AS score
                FROM "{table}"
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                ''',
                (vec_literal, vec_literal, limit),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "score": float(r["score"]) if r["score"] is not None else None,
                "payload": r["payload"] if isinstance(r["payload"], dict) else {},
            }
            for r in rows
        ]


def get_store() -> VectorStore:
    provider = (settings.vector_provider or "qdrant").lower()
    if provider == "pgvector":
        return PgvectorStore()
    return QdrantStore()
