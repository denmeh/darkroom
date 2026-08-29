from __future__ import annotations

import threading
import time
from typing import Literal

from fastapi import HTTPException
from instagrapi.exceptions import (
    ClientThrottledError,
    FeedbackRequired,
    LoginRequired,
    PleaseWaitFewMinutes,
    RateLimitError,
)
from pydantic import BaseModel

from darkroom.crawl import (
    DELAY_RANGE,
    MAX_SOFT_BLOCKS,
    SOFT_BLOCK_WAIT_S,
    dump_user,
    error_message,
    fetch_page,
)
from darkroom.db import Database, get_db, utcnow
from darkroom.session import load_client, session_exists

# A scan is two paced crawls of the logged-in account (following, then
# followers), stored in SQLite. Unfollowers = following − followers.
# Vanished = previous scan's following − this scan's following (blocked,
# deactivated, or you unfollowed).

ScanState = Literal["idle", "running", "waiting", "done", "error"]
ScanPhase = Literal["following", "followers", "comparing"] | None
ListKind = Literal["unfollowers", "vanished", "new_following", "following", "followers"]


class AccountOut(BaseModel):
    pk: str
    username: str | None = None
    full_name: str | None = None
    is_private: bool | None = None
    is_verified: bool | None = None


class ScanStatus(BaseModel):
    state: ScanState
    phase: ScanPhase = None
    scan_id: int | None = None
    wait_seconds: int | None = None
    following_fetched: int = 0
    following_total: int | None = None
    followers_fetched: int = 0
    followers_total: int | None = None
    error: str | None = None


class ScanSummary(BaseModel):
    id: int
    started_at: str
    finished_at: str | None
    state: str
    following_fetched: int
    followers_fetched: int
    unfollowers_count: int | None = None
    vanished_count: int | None = None
    new_following_count: int | None = None


class ReportCounts(BaseModel):
    following: int = 0
    followers: int = 0
    unfollowers: int = 0
    vanished: int = 0
    new_following: int = 0


class Report(BaseModel):
    latest: ScanSummary | None = None
    previous: ScanSummary | None = None
    counts: ReportCounts = ReportCounts()


class UserPage(BaseModel):
    kind: ListKind
    total: int
    offset: int
    users: list[AccountOut]


def _row_account(row) -> AccountOut:
    return AccountOut(
        pk=row["pk"],
        username=row["username"],
        full_name=row["full_name"],
        is_private=bool(row["is_private"]) if row["is_private"] is not None else None,
        is_verified=bool(row["is_verified"]) if row["is_verified"] is not None else None,
    )


def _row_summary(row) -> ScanSummary:
    return ScanSummary(
        id=row["id"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        state=row["state"],
        following_fetched=row["following_fetched"],
        followers_fetched=row["followers_fetched"],
        unfollowers_count=row["unfollowers_count"],
        vanished_count=row["vanished_count"],
        new_following_count=row["new_following_count"],
    )


def _count(db: Database, sql: str, params: tuple = ()) -> int:
    row = db.query_one(sql, params)
    return int(row["n"]) if row else 0


def _member_pks(db: Database, scan_id: int, list_name: str) -> set[str]:
    rows = db.query(
        "SELECT pk FROM scan_members WHERE scan_id = ? AND list = ?",
        (scan_id, list_name),
    )
    return {row["pk"] for row in rows}


class ScanStore:
    """One scan at a time: crawl my following, then my followers, then diff vs last scan."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.state: ScanState = "idle"
        self.phase: ScanPhase = None
        self.scan_id: int | None = None
        self.wait_until: float | None = None
        self.following_fetched = 0
        self.following_total: int | None = None
        self.followers_fetched = 0
        self.followers_total: int | None = None
        self.error: str | None = None
        self._hydrate_from_db()

    def _hydrate_from_db(self) -> None:
        db = get_db()
        row = db.query_one("SELECT * FROM scans ORDER BY id DESC LIMIT 1")
        if row is None:
            return
        self.scan_id = row["id"]
        self.phase = row["phase"]
        self.following_fetched = row["following_fetched"]
        self.following_total = row["following_total"]
        self.followers_fetched = row["followers_fetched"]
        self.followers_total = row["followers_total"]
        self.state = "idle"
        if row["state"] == "running":
            self.error = "Interrupted. Run scan again to resume."
        else:
            self.error = row["error"]

    def snapshot(self) -> ScanStatus:
        with self._lock:
            wait_seconds = None
            if self.wait_until is not None:
                wait_seconds = max(0, int(self.wait_until - time.monotonic()))
            return ScanStatus(
                state=self.state,
                phase=self.phase,
                scan_id=self.scan_id,
                wait_seconds=wait_seconds,
                following_fetched=self.following_fetched,
                following_total=self.following_total,
                followers_fetched=self.followers_fetched,
                followers_total=self.followers_total,
                error=self.error,
            )

    def start(self) -> ScanStatus:
        if not session_exists():
            raise HTTPException(status_code=401, detail="Not logged in")
        with self._lock:
            if self.state in ("running", "waiting"):
                raise HTTPException(status_code=409, detail="A scan is already running")
            self._stop.clear()
            self.state = "running"
            self.error = None
            self.wait_until = None
        thread = threading.Thread(target=self._run, name="darkroom-scan", daemon=True)
        thread.start()
        return self.snapshot()

    def stop(self) -> ScanStatus:
        self._stop.set()
        return self.snapshot()

    def _set(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def _wait(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        self._set(state="waiting", wait_until=deadline)
        while time.monotonic() < deadline:
            if self._stop.is_set():
                return True
            self._stop.wait(timeout=min(1.0, deadline - time.monotonic()))
        self._set(state="running", wait_until=None)
        return self._stop.is_set()

    def _run(self) -> None:
        db = get_db()
        try:
            self._scan(db)
        except Exception as exc:
            self._set(state="error", error=error_message(exc), wait_until=None)
            if self.scan_id:
                db.execute(
                    "UPDATE scans SET state = 'error', error = ? WHERE id = ?",
                    (error_message(exc), self.scan_id),
                )

    def _scan(self, db: Database) -> None:
        client = load_client()
        client.delay_range = DELAY_RANGE

        me = client.account_info()
        user_id = me.pk
        info = client.user_info(user_id)
        following_total = info.following_count
        followers_total = info.follower_count

        latest_row = db.query_one("SELECT * FROM scans ORDER BY id DESC LIMIT 1")
        resume = latest_row is not None and latest_row["finished_at"] is None

        if resume and latest_row:
            scan_id = latest_row["id"]
            phase = latest_row["phase"] or "following"
            following_cursor = latest_row["following_cursor"] or ""
            followers_cursor = latest_row["followers_cursor"] or ""
            db.execute(
                """
                UPDATE scans SET state = 'running', error = NULL,
                  following_total = ?, followers_total = ?
                WHERE id = ?
                """,
                (following_total, followers_total, scan_id),
            )
        else:
            cur = db.execute(
                """
                INSERT INTO scans (started_at, state, phase, following_total, followers_total)
                VALUES (?, 'running', 'following', ?, ?)
                """,
                (utcnow(), following_total, followers_total),
            )
            scan_id = cur.lastrowid
            if scan_id is None:
                raise RuntimeError("Failed to create scan row")
            phase = "following"
            following_cursor = ""
            followers_cursor = ""

        self._set(
            scan_id=scan_id,
            following_total=following_total,
            followers_total=followers_total,
            following_fetched=_count(
                db,
                "SELECT COUNT(*) AS n FROM scan_members WHERE scan_id = ? AND list = 'following'",
                (scan_id,),
            ),
            followers_fetched=_count(
                db,
                "SELECT COUNT(*) AS n FROM scan_members WHERE scan_id = ? AND list = 'followers'",
                (scan_id,),
            ),
        )

        if phase == "following":
            if not self._crawl_list(
                db, client, scan_id, user_id, "following", following_cursor
            ):
                return
            phase = "followers"
            db.execute("UPDATE scans SET phase = 'followers' WHERE id = ?", (scan_id,))

        if phase == "followers":
            if not self._crawl_list(
                db, client, scan_id, user_id, "followers", followers_cursor
            ):
                return

        self._set(phase="comparing")
        db.execute("UPDATE scans SET phase = 'comparing' WHERE id = ?", (scan_id,))
        self._finalize(db, scan_id)
        self._set(state="done", phase=None, wait_until=None, error=None)

    def _crawl_list(
        self,
        db: Database,
        client,
        scan_id: int,
        user_id: str,
        kind: str,
        cursor: str,
    ) -> bool:
        """Return False if we should abort the whole scan (fatal / stop)."""
        self._set(phase=kind)  # type: ignore[arg-type]
        fetched_field = f"{kind}_fetched"
        cursor_field = f"{kind}_cursor"
        seen = _member_pks(db, scan_id, kind)
        soft_blocks = 0

        while not self._stop.is_set():
            try:
                chunk, next_id = fetch_page(client, kind, user_id, cursor)
            except FeedbackRequired as exc:
                msg = error_message(exc)
                db.execute(
                    "UPDATE scans SET state = 'error', error = ? WHERE id = ?",
                    (msg, scan_id),
                )
                self._set(state="error", error=msg, wait_until=None)
                return False
            except LoginRequired as exc:
                db.execute(
                    "UPDATE scans SET state = 'error', error = ? WHERE id = ?",
                    (error_message(exc), scan_id),
                )
                self._set(state="error", error=error_message(exc), wait_until=None)
                return False
            except (PleaseWaitFewMinutes, RateLimitError, ClientThrottledError):
                soft_blocks += 1
                if soft_blocks > MAX_SOFT_BLOCKS:
                    msg = (
                        "Instagram kept asking us to wait. Progress is saved; "
                        "run scan again later to resume."
                    )
                    db.execute(
                        "UPDATE scans SET state = 'error', error = ? WHERE id = ?",
                        (msg, scan_id),
                    )
                    self._set(state="error", error=msg, wait_until=None)
                    return False
                if self._wait(SOFT_BLOCK_WAIT_S):
                    break
                continue

            now = utcnow()
            added = 0
            member_rows = []
            for user in chunk:
                item = dump_user(user)
                if item["pk"] in seen:
                    continue
                seen.add(item["pk"])
                db.upsert_account(item, now)
                member_rows.append((scan_id, item["pk"], kind))
                added += 1
            if member_rows:
                db.executemany(
                    "INSERT OR IGNORE INTO scan_members (scan_id, pk, list) VALUES (?, ?, ?)",
                    member_rows,
                )

            next_cursor = next_id or ""
            exhausted = not next_cursor or next_cursor == cursor
            cursor = "" if exhausted else next_cursor
            count = len(seen)
            db.execute(
                f"UPDATE scans SET {cursor_field} = ?, {fetched_field} = ? WHERE id = ?",
                (cursor, count, scan_id),
            )
            self._set(**{fetched_field: count})

            if exhausted:
                return True

        db.execute(
            "UPDATE scans SET state = 'error', error = ? WHERE id = ?",
            ("Stopped. Run scan again to resume.", scan_id),
        )
        self._set(
            state="idle",
            error="Stopped. Run scan again to resume.",
            wait_until=None,
        )
        return False

    def _finalize(self, db: Database, scan_id: int) -> None:
        following = _member_pks(db, scan_id, "following")
        followers = _member_pks(db, scan_id, "followers")
        unfollowers = following - followers

        prev = db.query_one(
            """
            SELECT id FROM scans
            WHERE state = 'done' AND id < ?
            ORDER BY id DESC LIMIT 1
            """,
            (scan_id,),
        )
        vanished: set[str] = set()
        new_following: set[str] = set()
        if prev:
            prev_following = _member_pks(db, prev["id"], "following")
            vanished = prev_following - following
            new_following = following - prev_following

        now = utcnow()
        event_rows = (
            [(scan_id, pk, "unfollower", now) for pk in unfollowers]
            + [(scan_id, pk, "vanished", now) for pk in vanished]
            + [(scan_id, pk, "new_following", now) for pk in new_following]
        )
        if event_rows:
            db.executemany(
                "INSERT INTO events (scan_id, pk, kind, created_at) VALUES (?, ?, ?, ?)",
                event_rows,
            )
        db.execute(
            """
            UPDATE scans SET
              state = 'done',
              finished_at = ?,
              phase = NULL,
              error = NULL,
              following_fetched = ?,
              followers_fetched = ?,
              unfollowers_count = ?,
              vanished_count = ?,
              new_following_count = ?
            WHERE id = ?
            """,
            (
                now,
                len(following),
                len(followers),
                len(unfollowers),
                len(vanished),
                len(new_following),
                scan_id,
            ),
        )


def latest_report() -> Report:
    db = get_db()
    latest = db.query_one(
        "SELECT * FROM scans WHERE state = 'done' ORDER BY id DESC LIMIT 1"
    )
    if latest is None:
        return Report()
    previous = db.query_one(
        "SELECT * FROM scans WHERE state = 'done' AND id < ? ORDER BY id DESC LIMIT 1",
        (latest["id"],),
    )
    return Report(
        latest=_row_summary(latest),
        previous=_row_summary(previous) if previous else None,
        counts=ReportCounts(
            following=latest["following_fetched"],
            followers=latest["followers_fetched"],
            unfollowers=latest["unfollowers_count"] or 0,
            vanished=latest["vanished_count"] or 0,
            new_following=latest["new_following_count"] or 0,
        ),
    )


def list_scans() -> list[ScanSummary]:
    db = get_db()
    rows = db.query("SELECT * FROM scans ORDER BY id DESC LIMIT 50")
    return [_row_summary(row) for row in rows]


def list_users(kind: ListKind, offset: int = 0, limit: int = 100) -> UserPage:
    db = get_db()
    latest = db.query_one(
        "SELECT id FROM scans WHERE state = 'done' ORDER BY id DESC LIMIT 1"
    )
    if latest is None:
        return UserPage(kind=kind, total=0, offset=offset, users=[])
    scan_id = latest["id"]
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    if kind in ("unfollowers", "vanished", "new_following"):
        total = _count(
            db,
            "SELECT COUNT(*) AS n FROM events WHERE scan_id = ? AND kind = ?",
            (scan_id, kind if kind != "unfollowers" else "unfollower"),
        )
        event_kind = "unfollower" if kind == "unfollowers" else kind
        rows = db.query(
            """
            SELECT a.* FROM events e
            JOIN accounts a ON a.pk = e.pk
            WHERE e.scan_id = ? AND e.kind = ?
            ORDER BY a.username COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            (scan_id, event_kind, limit, offset),
        )
    else:
        total = _count(
            db,
            "SELECT COUNT(*) AS n FROM scan_members WHERE scan_id = ? AND list = ?",
            (scan_id, kind),
        )
        rows = db.query(
            """
            SELECT a.* FROM scan_members m
            JOIN accounts a ON a.pk = m.pk
            WHERE m.scan_id = ? AND m.list = ?
            ORDER BY a.username COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            (scan_id, kind, limit, offset),
        )
    return UserPage(
        kind=kind,
        total=total,
        offset=offset,
        users=[_row_account(row) for row in rows],
    )


store = ScanStore()
