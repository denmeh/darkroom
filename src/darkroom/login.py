import tempfile
import time

from darkroom.paths import configure_frozen_env

configure_frozen_env()

from instagrapi import Client
from playwright.sync_api import sync_playwright

from darkroom.session import save_client

LOGIN_URL = "https://www.instagram.com/accounts/login/"
TIMEOUT_S = 300
POLL_S = 0.5


def sessionid_from(context) -> str | None:
    for cookie in context.cookies("https://www.instagram.com"):
        if cookie["name"] == "sessionid" and cookie.get("value"):
            return cookie["value"]
    return None


def wait_for_sessionid(context, timeout_s: float = TIMEOUT_S) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        sessionid = sessionid_from(context)
        if sessionid:
            return sessionid
        time.sleep(POLL_S)
    raise TimeoutError(
        f"No sessionid cookie within {timeout_s:.0f}s. Finish login in the browser."
    )


def login_in_browser() -> tuple[str, str]:
    """Open Chromium, wait for Instagram login, save session. Return (username, pk)."""
    with tempfile.TemporaryDirectory(prefix="darkroom-login-") as profile_dir:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                profile_dir,
                headless=False,
                viewport={"width": 1280, "height": 800},
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(LOGIN_URL)
            sessionid = wait_for_sessionid(context)
            context.close()

    client = Client()
    if not client.login_by_sessionid(sessionid):
        raise RuntimeError("instagrapi rejected the sessionid")
    me = client.account_info()
    save_client(client, me.pk)
    return me.username, me.pk
