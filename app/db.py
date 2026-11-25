import json
import sqlite3
import time
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS policies (
  id TEXT PRIMARY KEY, phone TEXT, language TEXT, quote_json TEXT, terms_hash TEXT,
  status TEXT,            -- quoted | active | held | settled
  pay_link TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, policy_id TEXT, kind TEXT, detail_json TEXT, at REAL
);
CREATE TABLE IF NOT EXISTS oracle (
  id INTEGER PRIMARY KEY CHECK (id = 1), last_seen REAL, last_obs_json TEXT
);
"""


@contextmanager
def conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)


def log_event(policy_id: str | None, kind: str, detail: dict):
    with conn() as c:
        c.execute("INSERT INTO events (policy_id, kind, detail_json, at) VALUES (?,?,?,?)",
                  (policy_id, kind, json.dumps(detail), time.time()))


def save_policy(pid: str, phone: str, language: str, quote: dict, terms_hash: str, status: str, pay_link: str = ""):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO policies VALUES (?,?,?,?,?,?,?,?)",
                  (pid, phone, language, json.dumps(quote), terms_hash, status, pay_link, time.time()))


def set_status(pid: str, status: str):
    with conn() as c:
        c.execute("UPDATE policies SET status=? WHERE id=?", (status, pid))


def get_policy(pid: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM policies WHERE id=?", (pid,)).fetchone()
    return _policy(r) if r else None


def list_policies() -> list[dict]:
    with conn() as c:
        return [_policy(r) for r in c.execute("SELECT * FROM policies ORDER BY created_at DESC")]


def events(pid: str | None = None, limit: int = 60) -> list[dict]:
    with conn() as c:
        q = "SELECT * FROM events " + ("WHERE policy_id=? " if pid else "") + "ORDER BY id DESC LIMIT ?"
        rows = c.execute(q, ((pid, limit) if pid else (limit,))).fetchall()
    return [{**dict(r), "detail": json.loads(r["detail_json"])} for r in rows]


def oracle_seen(obs: dict):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO oracle VALUES (1, ?, ?)", (time.time(), json.dumps(obs)))


def oracle_status() -> dict:
    with conn() as c:
        r = c.execute("SELECT * FROM oracle WHERE id=1").fetchone()
    if not r:
        return {"healthy": False, "age": None, "last": None}
    age = time.time() - r["last_seen"]
    return {"healthy": age <= config.ORACLE_STALE_SECONDS, "age": int(age), "last": json.loads(r["last_obs_json"])}


def _policy(r) -> dict:
    d = dict(r)
    d["quote"] = json.loads(d.pop("quote_json"))
    return d
