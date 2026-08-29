from __future__ import annotations


class DarkroomError(Exception):
    """Domain error; the API maps `status_code` to HTTP."""

    status_code: int = 400


class NotLoggedIn(DarkroomError):
    status_code = 401

    def __init__(self) -> None:
        super().__init__("Not logged in")


class ScanNotFound(DarkroomError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("Scan not found")


class ScanBusy(DarkroomError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("A scan is already running")


class LoginInProgress(DarkroomError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("Login already in progress")


class InvalidAccount(DarkroomError):
    status_code = 400

    def __init__(self) -> None:
        super().__init__("Invalid account")


class SessionNotFound(DarkroomError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("Saved session not found")


class InstagramUnreachable(DarkroomError):
    status_code = 503

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or "Could not reach Instagram")


class SessionExpired(DarkroomError):
    """Instagram rejected this saved session; the file has been deleted."""

    status_code = 401

    def __init__(self, pk: str = "") -> None:
        super().__init__("That session expired. Sign in again.")
        self.pk = pk
