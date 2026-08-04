"""Snapshot storage — one JSON file, one entry per URL. Simple on purpose:
this is a handful of pages checked once a day/week, not a scale problem."""

import hashlib
import json
import os

from config import STORE_PATH


def _load() -> dict:
    if not os.path.exists(STORE_PATH):
        return {}
    with open(STORE_PATH) as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(STORE_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get(url: str) -> dict:
    return _load().get(url)


def put(url: str, text: str, checked_at: str, changed_at: str = None) -> None:
    data = _load()
    data[url] = {
        "hash": text_hash(text),
        "text": text,
        "last_checked": checked_at,
        "last_changed": changed_at or (data.get(url) or {}).get("last_changed") or checked_at,
    }
    _save(data)
