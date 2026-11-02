"""Cliente Supabase vía REST (urllib) — sin dependencias httpx/websockets."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


class _Result:
    def __init__(self, data: list):
        self.data = data


class _TableQuery:
    def __init__(self, client: "SupabaseHttpClient", table: str):
        self._client = client
        self._table = table
        self._cols = "*"
        self._filters: list[str] = []
        self._limit: Optional[int] = None
        self._insert_data: Any = None
        self._update_data: Any = None
        self._delete = False

    def select(self, cols: str = "*"):
        self._cols = cols
        return self

    def eq(self, col: str, val: Any):
        self._filters.append(f"{col}=eq.{urllib.parse.quote(str(val))}")
        return self

    def order(self, col: str, desc: bool = False):
        direction = ".desc" if desc else ".asc"
        self._filters.append(f"order={col}{direction}")
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def insert(self, data: Any):
        self._insert_data = data
        return self

    def update(self, data: dict):
        self._update_data = data
        return self

    def delete(self):
        self._delete = True
        return self

    def execute(self) -> _Result:
        if self._insert_data is not None:
            return self._client._request("POST", self._table, body=self._insert_data)
        if self._update_data is not None:
            return self._client._request("PATCH", self._table, qs=self._build_qs(), body=self._update_data)
        if self._delete:
            return self._client._request("DELETE", self._table, qs=self._build_qs())
        return self._client._request("GET", self._table, qs=self._build_qs())

    def _build_qs(self) -> str:
        parts = [f"select={urllib.parse.quote(self._cols, safe='*,()')}"]
        parts.extend(self._filters)
        if self._limit is not None:
            parts.append(f"limit={self._limit}")
        return "&".join(parts)


class SupabaseHttpClient:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key

    def table(self, name: str) -> _TableQuery:
        return _TableQuery(self, name)

    def _request(
        self,
        method: str,
        table: str,
        qs: str = "",
        body: Any = None,
        prefer: str = "return=representation",
    ) -> _Result:
        url = f"{self.url}/rest/v1/{table}"
        if qs:
            url += "?" + qs
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        }
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode()
                return _Result(json.loads(raw) if raw else [])
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            raise RuntimeError(err_body) from e


    def rpc(self, fn: str, params: dict | None = None):
        """Llama una función de Postgres. No lee tablas directo."""
        url = f"{self.url}/rest/v1/rpc/{urllib.parse.quote(fn)}"
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        def _json_default(valor):
            if hasattr(valor, "item"):
                return valor.item()
            raise TypeError(type(valor).__name__)

        data = json.dumps(params or {}, default=_json_default).encode()
        req = urllib.request.Request(url, data=data, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode()
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            raise RuntimeError(err_body) from e


def create_client(url: str, key: str) -> SupabaseHttpClient:
    return SupabaseHttpClient(url, key)
