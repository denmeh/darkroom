from __future__ import annotations

from instagrapi.exceptions import (
    ClientThrottledError,
    FeedbackRequired,
    InvalidTargetUser,
    LoginRequired,
    PleaseWaitFewMinutes,
    RateLimitError,
    UserNotFound,
)

# instagrapi sleeps a random float in this range after every private request.
DELAY_RANGE = [3, 7]
# Instagram already returns ~50–100 users per response. 100 means fewer round-trips.
PAGE_SIZE = 100
SOFT_BLOCK_WAIT_S = 30 * 60
MAX_SOFT_BLOCKS = 3


def dump_user(user) -> dict:
    pic = getattr(user, "profile_pic_url", None)
    return {
        "pk": str(user.pk),
        "username": user.username,
        "full_name": user.full_name or "",
        "is_private": user.is_private,
        "is_verified": user.is_verified,
        "profile_pic_url": str(pic) if pic else None,
    }


def error_message(exc: Exception) -> str:
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


def fetch_page(client, kind: str, user_id: str, cursor: str):
    """One Instagram page. kind is 'following' or 'followers'."""
    if kind == "following":
        return client.user_following_v1_chunk(
            user_id, max_amount=PAGE_SIZE, max_id=cursor or ""
        )
    return client.user_followers_v1_chunk(
        user_id, max_amount=PAGE_SIZE, max_id=cursor or ""
    )
