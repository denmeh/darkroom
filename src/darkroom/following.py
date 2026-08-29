from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from instagrapi.exceptions import (
    ClientThrottledError,
    FeedbackRequired,
    InvalidTargetUser,
    LoginRequired,
    PleaseWaitFewMinutes,
    RateLimitError,
    UserNotFound,
)
from pydantic import BaseModel

from darkroom.session import APP_DIR, load_client, session_exists

# The Instagram call is a page loop. Everything else exists because the GUI
# cannot freeze for minutes: a worker thread crawls, FastAPI polls snapshot()
# for progress, and each page is written to disk so a rate-limit hit can resume.
#
# We never call user_info per following. That is a second request per account
# and is what actually burns the rate limit.

FollowingState = Literal["idle", "running", "waiting", "done", "error"]

# instagrapi sleeps a random float in this range after every private request.
# 3–7s is slower than the guide's 1–3s default; following walks are long.
DELAY_RANGE = [3, 7]
# Instagram already returns ~50–100 users per response. 100 is the high end
# of that, so we take fewer round-trips (safer), not a huge dump.
PAGE_SIZE = 100
# Guide: please_wait_a_few_minutes is a soft block — sit idle 30 minutes, then retry.
SOFT_BLOCK_WAIT_S = 30 * 60
MAX_SOFT_BLOCKS = 3
USERNAME_RE = re.compile(r"[a-z0-9._]{1,30}")


class FollowingUser(BaseModel):
    pk: str
    username: str | None = None
    full_name: str | None = None
    is_private: bool | None = None
    is_verified: bool | None = None


# Polled by the GUI. Keep this cheap: snapshot() may run every second.
class FollowingStatus(BaseModel):
    state: FollowingState
    username: str | None = None
    user_id: str | None = None
    fetched: int = 0
    total: int | None = None
    wait_seconds: int | None = None
    error: str | None = None
    path: str | None = None
    resumed: bool = False
    is_private: bool = False
    users: list[FollowingUser] = []


class FollowingRequest(BaseModel):
    username: str


# On-disk cursor + users so a killed crawl can continue from next_max_id.
class Checkpoint(BaseModel):
    username: str
    user_id: str
    following_count: int | None = None
    cursor: str = ""
    complete: bool = False
    is_private: bool = False
    users: list[FollowingUser] = []


def normalize_username(raw: str) -> str:
    return raw.strip().lstrip("@").strip().lower()


def following_dir() -> Path:
    path = APP_DIR / "following"
    path.mkdir(parents=True, exist_ok=True)
    return path


def checkpoint_path(username: str) -> Path:
    safe = "".join(c for c in username if c.isalnum() or c in "._")
    return following_dir() / f"{safe}.json"


def _dump_user(user) -> FollowingUser:
    # Skip profile_pic_url: Instagram CDN links expire within hours.
    return FollowingUser(
        pk=str(user.pk),
        username=user.username,
        full_name=user.full_name or "",
        is_private=user.is_private,
        is_verified=user.is_verified,
    )


def _save(path: Path, checkpoint: Checkpoint) -> None:
    # Write-then-rename so a crash mid-write cannot leave a truncated JSON.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(checkpoint.model_dump_json())
    tmp.replace(path)


def _load(path: Path) -> Checkpoint | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
        return Checkpoint.model_validate(data)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _message(exc: Exception) -> str:
    if isinstance(exc, FeedbackRequired):
        return (
            "Instagram flagged unusual activity (feedback_required). "
            "Wait several hours and sign in from the official app before retrying."
        )
    if isinstance(exc, LoginRequired):
        return "Session expired. Sign in again from the Login tab."
    if isinstance(exc, (UserNotFound, InvalidTargetUser)):
        return "No Instagram account with that username."
    if isinstance(exc, PleaseWaitFewMinutes):
        return "Instagram asked us to wait a few minutes."
    if isinstance(exc, (RateLimitError, ClientThrottledError)):
        return "Instagram is rate-limiting this session."
    return str(exc) or exc.__class__.__name__


class FollowingStore:
    """One crawl at a time. Worker thread talks to Instagram; HTTP handlers only read."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Event, not a bool: _wait() can wake immediately when Stop is clicked.
        self._stop = threading.Event()
        self.state: FollowingState = "idle"
        self.username: str | None = None
        self.user_id: str | None = None
        self.fetched = 0
        self.total: int | None = None
        self.wait_until: float | None = None
        self.error: str | None = None
        self.path: str | None = None
        self.resumed = False
        self.is_private = False
        self.users: list[FollowingUser] = []

    def snapshot(self) -> FollowingStatus:
        with self._lock:
            wait_seconds = None
            if self.wait_until is not None:
                wait_seconds = max(0, int(self.wait_until - time.monotonic()))
            users = list(self.users)
            # During a long crawl, do not serialize thousands of users every poll.
            if self.state in ("running", "waiting") and len(users) > 50:
                users = users[-50:]
            return FollowingStatus(
                state=self.state,
                username=self.username,
                user_id=self.user_id,
                fetched=self.fetched,
                total=self.total,
                wait_seconds=wait_seconds,
                error=self.error,
                path=self.path,
                resumed=self.resumed,
                is_private=self.is_private,
                users=users,
            )

    def start(self, raw_username: str) -> FollowingStatus:
        username = normalize_username(raw_username)
        if not username or not USERNAME_RE.fullmatch(username):
            raise HTTPException(status_code=400, detail="Enter a valid Instagram username")
        if not session_exists():
            raise HTTPException(status_code=401, detail="Not logged in")
        with self._lock:
            if self.state in ("running", "waiting"):
                raise HTTPException(status_code=409, detail="A following fetch is already running")
            self._stop.clear()
            self.state = "running"
            self.username = username
            self.user_id = None
            self.fetched = 0
            self.total = None
            self.wait_until = None
            self.error = None
            self.path = str(checkpoint_path(username))
            self.resumed = False
            self.is_private = False
            self.users = []
        # instagrapi is blocking. daemon=True so quitting the app does not hang.
        thread = threading.Thread(
            target=self._run,
            args=(username,),
            name="darkroom-following",
            daemon=True,
        )
        thread.start()
        return self.snapshot()

    def stop(self) -> FollowingStatus:
        self._stop.set()
        return self.snapshot()

    def _set(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def _wait(self, seconds: float) -> bool:
        """Sleep `seconds`, but return True immediately if the user hit Stop."""
        deadline = time.monotonic() + seconds
        self._set(state="waiting", wait_until=deadline)
        while time.monotonic() < deadline:
            if self._stop.is_set():
                return True
            self._stop.wait(timeout=min(1.0, deadline - time.monotonic()))
        self._set(state="running", wait_until=None)
        return self._stop.is_set()

    def _run(self, username: str) -> None:
        path = checkpoint_path(username)
        try:
            self._fetch(username, path)
        except Exception as exc:
            self._set(state="error", error=_message(exc), wait_until=None)

    def _fetch(self, username: str, path: Path) -> None:
        client = load_client()
        client.delay_range = DELAY_RANGE

        existing = _load(path)
        # Resume skips user_info_by_username — that would be an extra request
        # just to rediscover a pk we already stored.
        resume = (
            existing is not None
            and not existing.complete
            and existing.username == username
            and bool(existing.user_id)
        )

        if resume and existing:
            user_id = existing.user_id
            total = existing.following_count
            users = list(existing.users)
            cursor = existing.cursor
            is_private = existing.is_private
        else:
            # The following endpoint takes a numeric pk, not the handle.
            try:
                info = client.user_info_by_username(username)
            except (UserNotFound, InvalidTargetUser) as exc:
                self._set(state="error", error=_message(exc), wait_until=None)
                return
            user_id = info.pk
            total = info.following_count
            users = []
            cursor = ""
            is_private = info.is_private

        # pk is stable (usernames change). Pages can overlap; skip dupes.
        seen = {u.pk for u in users}

        checkpoint = Checkpoint(
            username=username,
            user_id=user_id,
            following_count=total,
            cursor=cursor,
            complete=False,
            is_private=is_private,
            users=users,
        )
        _save(path, checkpoint)
        self._set(
            user_id=user_id,
            total=total,
            fetched=len(users),
            users=list(users),
            resumed=resume,
            is_private=is_private,
            path=str(path),
        )

        soft_blocks = 0
        while not self._stop.is_set():
            try:
                # Chunked instead of user_following(amount=0): that helper
                # walks the whole list in one call with no cursor we can save.
                # max_id is Instagram's next_max_id from the previous page.
                chunk, next_id = client.user_following_v1_chunk(
                    user_id,
                    max_amount=PAGE_SIZE,
                    max_id=cursor,
                )
            except FeedbackRequired as exc:
                # Harsher than a wait: Instagram thinks the account is acting
                # unusually. Retrying here makes it worse.
                _save(path, checkpoint)
                self._set(state="error", error=_message(exc), wait_until=None)
                return
            except LoginRequired as exc:
                _save(path, checkpoint)
                self._set(state="error", error=_message(exc), wait_until=None)
                return
            except (PleaseWaitFewMinutes, RateLimitError, ClientThrottledError):
                soft_blocks += 1
                if soft_blocks > MAX_SOFT_BLOCKS:
                    self._set(
                        state="error",
                        error=(
                            "Instagram kept asking us to wait. Progress is saved; "
                            "try again later from the same username."
                        ),
                        wait_until=None,
                    )
                    return
                _save(path, checkpoint)
                if self._wait(SOFT_BLOCK_WAIT_S):
                    break
                continue

            added = False
            for user in chunk:
                item = _dump_user(user)
                if item.pk in seen:
                    continue
                seen.add(item.pk)
                users.append(item)
                added = True

            next_cursor = next_id or ""
            # Same cursor twice would loop forever; treat it as the end.
            exhausted = not next_cursor or next_cursor == cursor
            if exhausted and not added and not users:
                # Empty list: either they follow nobody, or a private account
                # we do not follow (Instagram will not leak that list).
                empty_error = None
                if is_private:
                    empty_error = (
                        f"@{username} is private. Following is only visible if "
                        "your logged-in account follows them."
                    )
                checkpoint.complete = True
                checkpoint.users = users
                checkpoint.cursor = ""
                _save(path, checkpoint)
                self._set(
                    state="done",
                    fetched=0,
                    users=[],
                    wait_until=None,
                    error=empty_error,
                )
                return

            cursor = "" if exhausted else next_cursor
            checkpoint.cursor = cursor
            checkpoint.users = users
            checkpoint.complete = exhausted
            _save(path, checkpoint)
            self._set(fetched=len(users), users=list(users))

            if exhausted:
                self._set(state="done", wait_until=None, error=None)
                return

        checkpoint.users = users
        checkpoint.complete = False
        _save(path, checkpoint)
        self._set(
            state="idle",
            error="Stopped. Progress is saved; fetch the same username to resume.",
            wait_until=None,
            fetched=len(users),
            users=list(users),
        )


store = FollowingStore()
