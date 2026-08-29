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

from darkroom.avatars import has_avatar, prefetch_avatar
from darkroom.crawl import (
    DELAY_RANGE,
    MAX_SOFT_BLOCKS,
    SOFT_BLOCK_WAIT_S,
    dump_user,
    error_message,
    fetch_page,
)
from darkroom.db import Database, get_db, utcnow
from darkroom.session import load_client, session_user_pk

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
    avatar_url: str | None = None


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
    scan: ScanSummary | None = None
    previous: ScanSummary | None = None
    counts: ReportCounts = ReportCounts()


class UserPage(BaseModel):
    kind: ListKind
    total: int
    offset: int
    scan_id: int | None = None
    users: list[AccountOut]


def _row_account(row) -> AccountOut:
    pk = row["pk"]
    pic = row["profile_pic_url"]
    has_pic = bool(pic) or has_avatar(pk)
    return AccountOut(
        pk=pk,
        username=row["username"],
        full_name=row["full_name"],
        is_private=bool(row["is_private"]) if row["is_private"] is not None else None,
        is_verified=bool(row["is_verified"]) if row["is_verified"] is not None else None,
        avatar_url=f"/api/avatars/{pk}" if has_pic else None,
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


def _like_filter(q: str | None) -> tuple[str, tuple[str, ...]]:
    needle = (q or "").strip()
    if not needle:
        return "", ()
    escaped = (
        needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    pattern = f"%{escaped}%"
    sql = (
        " AND (a.username LIKE ? ESCAPE '\\' OR a.full_name LIKE ? ESCAPE '\\')"
    )
    return sql, (pattern, pattern)


def _member_pks(db: Database, scan_id: int, list_name: str) -> set[str]:
    rows = db.query(
        "SELECT pk FROM scan_members WHERE scan_id = ? AND list = ?",
        (scan_id, list_name),
    )
    return {row["pk"] for row in rows}


def _require_owner() -> str:
    pk = session_user_pk()
    if not pk:
        raise HTTPException(status_code=401, detail="Not logged in")
    return pk


def _owned_scan(db: Database, scan_id: int, owner_pk: str):
    row = db.query_one(
        "SELECT * FROM scans WHERE id = ? AND owner_pk = ?",
        (scan_id, owner_pk),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return row


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
        self._owner_pk: str | None = session_user_pk()
        self._hydrate_from_db()

    def bind(self, owner_pk: str | None) -> None:
        """Point this store at a logged-in account, or clear it on logout."""
        with self._lock:
            same = owner_pk == self._owner_pk
            running = self.state in ("running", "waiting")
        if same:
            return
        if running:
            self._stop.set()
        with self._lock:
            if owner_pk == self._owner_pk:
                return
            self._owner_pk = owner_pk
            self.state = "idle"
            self.phase = None
            self.scan_id = None
            self.wait_until = None
            self.following_fetched = 0
            self.following_total = None
            self.followers_fetched = 0
            self.followers_total = None
            self.error = None
            self._hydrate_from_db()
            self._stop.clear()

    def _hydrate_from_db(self) -> None:
        if not self._owner_pk:
            return
        db = get_db()
        row = db.query_one(
            "SELECT * FROM scans WHERE owner_pk = ? ORDER BY id DESC LIMIT 1",
            (self._owner_pk,),
        )
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
        owner = _require_owner()
        with self._lock:
            if self.state in ("running", "waiting"):
                raise HTTPException(status_code=409, detail="A scan is already running")
            self._owner_pk = owner
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

    def _set(self, owner: str | None = None, **kwargs) -> None:
        with self._lock:
            if owner is not None and self._owner_pk != owner:
                return
            for key, value in kwargs.items():
                setattr(self, key, value)

    def _wait(self, owner: str, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        self._set(owner, state="waiting", wait_until=deadline)
        while time.monotonic() < deadline:
            if self._stop.is_set() or self._owner_pk != owner:
                return True
            self._stop.wait(timeout=min(1.0, deadline - time.monotonic()))
        self._set(owner, state="running", wait_until=None)
        return self._stop.is_set() or self._owner_pk != owner

    def _run(self) -> None:
        db = get_db()
        owner = self._owner_pk
        active: list[int] = []
        try:
            self._scan(db, owner, active)
        except Exception as exc:
            msg = error_message(exc)
            self._set(owner, state="error", error=msg, wait_until=None)
            if active:
                db.execute(
                    "UPDATE scans SET state = 'error', error = ? WHERE id = ?",
                    (msg, active[0]),
                )

    def _scan(self, db: Database, owner: str | None, active: list[int]) -> None:
        client = load_client()
        client.delay_range = DELAY_RANGE

        me = client.account_info()
        user_id = str(me.pk)
        if owner and user_id != owner:
            return
        owner = user_id
        info = client.user_info(user_id)
        following_total = info.following_count
        followers_total = info.follower_count

        latest_row = db.query_one(
            "SELECT * FROM scans WHERE owner_pk = ? ORDER BY id DESC LIMIT 1",
            (owner,),
        )
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
                INSERT INTO scans (
                  started_at, state, phase, following_total, followers_total, owner_pk
                )
                VALUES (?, 'running', 'following', ?, ?, ?)
                """,
                (utcnow(), following_total, followers_total, owner),
            )
            scan_id = cur.lastrowid
            if scan_id is None:
                raise RuntimeError("Failed to create scan row")
            phase = "following"
            following_cursor = ""
            followers_cursor = ""

        active.append(scan_id)
        self._set(
            owner,
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
                db, client, owner, scan_id, user_id, "following", following_cursor
            ):
                return
            phase = "followers"
            db.execute("UPDATE scans SET phase = 'followers' WHERE id = ?", (scan_id,))

        if phase == "followers":
            if not self._crawl_list(
                db, client, owner, scan_id, user_id, "followers", followers_cursor
            ):
                return

        self._set(owner, phase="comparing")
        db.execute("UPDATE scans SET phase = 'comparing' WHERE id = ?", (scan_id,))
        self._finalize(db, owner, scan_id)
        self._set(owner, state="done", phase=None, wait_until=None, error=None)

    def _crawl_list(
        self,
        db: Database,
        client,
        owner: str,
        scan_id: int,
        user_id: str,
        kind: str,
        cursor: str,
    ) -> bool:
        """Return False if we should abort the whole scan (fatal / stop)."""
        self._set(owner, phase=kind)  # type: ignore[arg-type]
        fetched_field = f"{kind}_fetched"
        cursor_field = f"{kind}_cursor"
        seen = _member_pks(db, scan_id, kind)
        soft_blocks = 0

        while not self._stop.is_set() and self._owner_pk == owner:
            try:
                chunk, next_id = fetch_page(client, kind, user_id, cursor)
            except FeedbackRequired as exc:
                msg = error_message(exc)
                db.execute(
                    "UPDATE scans SET state = 'error', error = ? WHERE id = ?",
                    (msg, scan_id),
                )
                self._set(owner, state="error", error=msg, wait_until=None)
                return False
            except LoginRequired as exc:
                db.execute(
                    "UPDATE scans SET state = 'error', error = ? WHERE id = ?",
                    (error_message(exc), scan_id),
                )
                self._set(owner, state="error", error=error_message(exc), wait_until=None)
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
                    self._set(owner, state="error", error=msg, wait_until=None)
                    return False
                if self._wait(owner, SOFT_BLOCK_WAIT_S):
                    break
                continue

            now = utcnow()
            member_rows = []
            for user in chunk:
                item = dump_user(user)
                if item["pk"] in seen:
                    continue
                seen.add(item["pk"])
                db.upsert_account(item, now)
                prefetch_avatar(item["pk"], item.get("profile_pic_url"))
                member_rows.append((scan_id, item["pk"], kind))
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
            self._set(owner, **{fetched_field: count})

            if exhausted:
                return True

        if self._owner_pk != owner:
            return False
        db.execute(
            "UPDATE scans SET state = 'error', error = ? WHERE id = ?",
            ("Stopped. Run scan again to resume.", scan_id),
        )
        self._set(
            owner,
            state="idle",
            error="Stopped. Run scan again to resume.",
            wait_until=None,
        )
        return False

    def _finalize(self, db: Database, owner: str, scan_id: int) -> None:
        following = _member_pks(db, scan_id, "following")
        followers = _member_pks(db, scan_id, "followers")
        unfollowers = following - followers

        prev = db.query_one(
            """
            SELECT id FROM scans
            WHERE state = 'done' AND id < ? AND owner_pk = ?
            ORDER BY id DESC LIMIT 1
            """,
            (scan_id, owner),
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


def get_report(scan_id: int | None = None) -> Report:
    owner = _require_owner()
    db = get_db()
    if scan_id is not None:
        row = _owned_scan(db, scan_id, owner)
    else:
        row = db.query_one(
            """
            SELECT * FROM scans
            WHERE state = 'done' AND owner_pk = ?
            ORDER BY id DESC LIMIT 1
            """,
            (owner,),
        )
        if row is None:
            return Report()
    previous = db.query_one(
        """
        SELECT * FROM scans
        WHERE state = 'done' AND id < ? AND owner_pk = ?
        ORDER BY id DESC LIMIT 1
        """,
        (row["id"], owner),
    )
    return Report(
        scan=_row_summary(row),
        previous=_row_summary(previous) if previous else None,
        counts=ReportCounts(
            following=row["following_fetched"] or 0,
            followers=row["followers_fetched"] or 0,
            unfollowers=row["unfollowers_count"] or 0,
            vanished=row["vanished_count"] or 0,
            new_following=row["new_following_count"] or 0,
        ),
    )


def list_scans() -> list[ScanSummary]:
    owner = _require_owner()
    db = get_db()
    rows = db.query(
        "SELECT * FROM scans WHERE owner_pk = ? ORDER BY id DESC LIMIT 50",
        (owner,),
    )
    return [_row_summary(row) for row in rows]


def list_users(
    kind: ListKind,
    offset: int = 0,
    limit: int = 100,
    scan_id: int | None = None,
    q: str | None = None,
) -> UserPage:
    db = get_db()
    owner = _require_owner()
    if scan_id is not None:
        row = _owned_scan(db, scan_id, owner)
        sid = row["id"]
    else:
        latest = db.query_one(
            """
            SELECT id FROM scans
            WHERE state = 'done' AND owner_pk = ?
            ORDER BY id DESC LIMIT 1
            """,
            (owner,),
        )
        if latest is None:
            return UserPage(kind=kind, total=0, offset=offset, users=[])
        sid = latest["id"]

    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    search_sql, search_params = _like_filter(q)

    if kind in ("unfollowers", "vanished", "new_following"):
        event_kind = "unfollower" if kind == "unfollowers" else kind
        total = _count(
            db,
            f"""
            SELECT COUNT(*) AS n FROM events e
            JOIN accounts a ON a.pk = e.pk
            WHERE e.scan_id = ? AND e.kind = ?{search_sql}
            """,
            (sid, event_kind, *search_params),
        )
        rows = db.query(
            f"""
            SELECT a.* FROM events e
            JOIN accounts a ON a.pk = e.pk
            WHERE e.scan_id = ? AND e.kind = ?{search_sql}
            ORDER BY a.username COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            (sid, event_kind, *search_params, limit, offset),
        )
    else:
        total = _count(
            db,
            f"""
            SELECT COUNT(*) AS n FROM scan_members m
            JOIN accounts a ON a.pk = m.pk
            WHERE m.scan_id = ? AND m.list = ?{search_sql}
            """,
            (sid, kind, *search_params),
        )
        rows = db.query(
            f"""
            SELECT a.* FROM scan_members m
            JOIN accounts a ON a.pk = m.pk
            WHERE m.scan_id = ? AND m.list = ?{search_sql}
            ORDER BY a.username COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            (sid, kind, *search_params, limit, offset),
        )
    return UserPage(
        kind=kind,
        total=total,
        offset=offset,
        scan_id=sid,
        users=[_row_account(row) for row in rows],
    )


store = ScanStore()
