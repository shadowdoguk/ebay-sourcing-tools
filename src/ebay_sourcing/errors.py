"""Exception hierarchy for the eBay sourcing pipeline."""

from __future__ import annotations


class EbaySourcingError(Exception):
    """Base class for every error raised by this package."""


class ConfigError(EbaySourcingError):
    """Raised when configuration is missing or malformed."""


class AuthError(EbaySourcingError):
    """Raised when eBay rejects the supplied credentials or OAuth scopes."""


class ApiError(EbaySourcingError):
    """Raised when the eBay API returns an error response.

    Attributes:
        status_code: HTTP status returned by eBay, when known.
        error_id: eBay's numeric ``errorId`` for the failure, when present.
        detail: The human readable ``message``/``longMessage`` eBay returned.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_id: int | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_id = error_id
        self.detail = detail


class RateLimitError(ApiError):
    """Raised when the API rate limit is exhausted and retries are exhausted."""


class NotFoundError(ApiError):
    """Raised when a requested item does not exist."""


def summarise_error_payload(payload: object) -> tuple[str | None, int | None]:
    """Pull the most useful message and error id out of an eBay error body.

    eBay returns errors either as a bare object or wrapped in an ``errors``
    array, and the interesting text lives in ``longMessage`` when present.
    """
    if not isinstance(payload, dict):
        return None, None

    error_id = payload.get("errorId")
    message = payload.get("longMessage") or payload.get("message")

    for key in ("details", "errors"):
        entries = payload.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if error_id is None:
                candidate = entry.get("errorId")
                if isinstance(candidate, int):
                    error_id = candidate
            entry_message = entry.get("longMessage") or entry.get("message")
            if entry_message and not message:
                message = entry_message

    text = message if isinstance(message, str) else None
    return text, error_id
