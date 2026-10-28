"""Configuration for the eBay sourcing pipeline.

Credentials are always read from the environment so that the repository can be
public without risking a secret leak. Watchlists live in a TOML file that is
safe to commit.

All endpoint URLs and scopes below are taken from eBay's published Buy API
specification and the official eBay OAuth client, not from memory.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from .errors import ConfigError

ENVIRONMENT_PRODUCTION = "production"
ENVIRONMENT_SANDBOX = "sandbox"

#: OAuth token endpoints, keyed by environment.
TOKEN_URLS: dict[str, str] = {
    ENVIRONMENT_PRODUCTION: "https://api.ebay.com/identity/v1/oauth2/token",
    ENVIRONMENT_SANDBOX: "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
}

#: Root URLs for the RESTful Buy APIs, keyed by environment.
API_BASE_URLS: dict[str, str] = {
    ENVIRONMENT_PRODUCTION: "https://api.ebay.com",
    ENVIRONMENT_SANDBOX: "https://api.sandbox.ebay.com",
}

#: The Browse and Item APIs both live under /buy/browse/v1.
BROWSE_BASE_PATH = "/buy/browse/v1"

DEFAULT_MARKETPLACE_ID = "EBAY_US"

#: Application-level scope required by the Browse and Item APIs.
DEFAULT_SCOPE = "https://api.ebay.com/oauth/api_scope"

#: Additional scope required by the Order API (procurement order placement).
BUY_ORDER_SCOPE = "https://api.ebay.com/oauth/api_scope/buy.order"

DEFAULT_DB_PATH = Path("data/ebay_sourcing.db")


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for a single pipeline run."""

    client_id: str
    client_secret: str
    marketplace_id: str = DEFAULT_MARKETPLACE_ID
    environment: str = ENVIRONMENT_PRODUCTION
    db_path: Path = DEFAULT_DB_PATH
    request_timeout: float = 30.0
    max_retries: int = 4
    rate_limit_per_minute: int = 60
    scopes: tuple[str, ...] = (DEFAULT_SCOPE,)

    def __post_init__(self) -> None:
        if self.environment not in API_BASE_URLS:
            raise ConfigError(
                f"Unknown environment {self.environment!r}. "
                f"Expected one of: {', '.join(sorted(API_BASE_URLS))}."
            )
        if not self.scopes:
            raise ConfigError("At least one OAuth scope must be configured.")

    @property
    def token_url(self) -> str:
        """URL of the OAuth token service for the active environment."""
        return TOKEN_URLS[self.environment]

    @property
    def api_base_url(self) -> str:
        """Root URL of the RESTful Buy APIs for the active environment."""
        return API_BASE_URLS[self.environment]

    @property
    def browse_base_url(self) -> str:
        """Base URL shared by the Browse and Item APIs."""
        return f"{self.api_base_url}{BROWSE_BASE_PATH}"

    @property
    def is_sandbox(self) -> bool:
        return self.environment == ENVIRONMENT_SANDBOX

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        """Build settings from environment variables.

        Raises:
            ConfigError: If credentials are missing or a value is malformed.
        """
        env = os.environ if env is None else env

        client_id = (env.get("EBAY_CLIENT_ID") or "").strip()
        client_secret = (env.get("EBAY_CLIENT_SECRET") or "").strip()
        if not client_id or not client_secret:
            raise ConfigError(
                "Missing eBay credentials. Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET "
                "in the environment; see .env.example for the full list of variables."
            )

        scopes_raw = (env.get("EBAY_SCOPES") or DEFAULT_SCOPE).strip()
        scopes = tuple(scope for scope in scopes_raw.split() if scope)
        if not scopes:
            raise ConfigError("EBAY_SCOPES was set but contained no usable scope.")

        try:
            timeout = float(env.get("EBAY_REQUEST_TIMEOUT") or 30.0)
            max_retries = int(env.get("EBAY_MAX_RETRIES") or 4)
            rate_limit = int(env.get("EBAY_RATE_LIMIT_PER_MINUTE") or 60)
        except ValueError as exc:
            raise ConfigError(f"Malformed numeric environment setting: {exc}") from exc

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            marketplace_id=(env.get("EBAY_MARKETPLACE_ID") or DEFAULT_MARKETPLACE_ID).strip(),
            environment=(env.get("EBAY_ENVIRONMENT") or ENVIRONMENT_PRODUCTION).strip().lower(),
            db_path=Path(env.get("EBAY_SOURCING_DB") or DEFAULT_DB_PATH),
            request_timeout=timeout,
            max_retries=max_retries,
            rate_limit_per_minute=rate_limit,
            scopes=scopes,
        )


@dataclass(frozen=True)
class Watch:
    """A tracked product query feeding the stock tracking and sourcing stages."""

    name: str
    query: str
    category_ids: tuple[str, ...] = ()
    max_price: Decimal | None = None
    target_price: Decimal | None = None
    currency: str = "GBP"
    condition_ids: tuple[str, ...] = ()
    min_seller_feedback: Decimal | None = None
    free_shipping_only: bool = False
    min_results: int = 1

    @property
    def filters(self) -> list[str]:
        """Build the eBay ``filter`` expression for this watch.

        eBay expects range filters in the form ``price:[min..max]`` and
        multi-value filters in the form ``conditions:{A|B}``.
        """
        filters: list[str] = []
        if self.max_price is not None:
            filters.append(f"price:[0..{self.max_price}]")
        if self.condition_ids:
            joined = "|".join(self.condition_ids)
            filters.append("conditions:{" + joined + "}")
        if self.free_shipping_only:
            filters.append("maxDeliveryCost:0")
        return filters

    def to_dict(self) -> dict[str, Any]:
        """Serialise the watch for storage in the database."""
        return {
            "name": self.name,
            "query": self.query,
            "category_ids": list(self.category_ids),
            "max_price": str(self.max_price) if self.max_price is not None else None,
            "target_price": str(self.target_price) if self.target_price is not None else None,
            "currency": self.currency,
            "condition_ids": list(self.condition_ids),
            "min_seller_feedback": (
                str(self.min_seller_feedback) if self.min_seller_feedback is not None else None
            ),
            "free_shipping_only": self.free_shipping_only,
            "min_results": self.min_results,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Watch":
        """Rebuild a watch from its stored representation."""

        def _decimal_or_none(value: Any) -> Decimal | None:
            if value in (None, ""):
                return None
            return Decimal(str(value))

        return cls(
            name=str(data["name"]),
            query=str(data["query"]),
            category_ids=tuple(data.get("category_ids") or ()),
            max_price=_decimal_or_none(data.get("max_price")),
            target_price=_decimal_or_none(data.get("target_price")),
            currency=str(data.get("currency") or "GBP"),
            condition_ids=tuple(data.get("condition_ids") or ()),
            min_seller_feedback=_decimal_or_none(data.get("min_seller_feedback")),
            free_shipping_only=bool(data.get("free_shipping_only", False)),
            min_results=int(data.get("min_results", 1) or 1),
        )


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return tuple(str(part).strip() for part in value if str(part).strip())


def _as_decimal(value: Any, name: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 - re-raised as a configuration error
        raise ConfigError(f"Watch {name!r} has an invalid decimal value {value!r}.") from exc


def load_watches(path: str | Path) -> list[Watch]:
    """Load watch definitions from a TOML file.

    The file uses one ``[[watch]]`` table per tracked product.

    Raises:
        ConfigError: If the file is missing, unreadable or malformed.
    """
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Watchlist file not found: {path}")

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Could not parse watchlist {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read watchlist {path}: {exc}") from exc

    entries = data.get("watch")
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ConfigError(f"Expected a list of [[watch]] tables in {path}.")

    watches: list[Watch] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise ConfigError(f"Entry {index} in {path} is not a table.")
        name = str(entry.get("name") or "").strip()
        query = str(entry.get("query") or "").strip()
        if not name:
            raise ConfigError(f"Entry {index} in {path} is missing a name.")
        if not query:
            raise ConfigError(f"Watch {name!r} in {path} is missing a query.")
        if name in seen:
            raise ConfigError(f"Duplicate watch name {name!r} in {path}.")
        seen.add(name)

        watches.append(
            Watch(
                name=name,
                query=query,
                category_ids=_as_tuple(entry.get("category_ids")),
                max_price=_as_decimal(entry.get("max_price"), name),
                target_price=_as_decimal(entry.get("target_price"), name),
                currency=str(entry.get("currency") or "GBP"),
                condition_ids=_as_tuple(entry.get("condition_ids")),
                min_seller_feedback=_as_decimal(entry.get("min_seller_feedback"), name),
                free_shipping_only=bool(entry.get("free_shipping_only", False)),
                min_results=int(entry.get("min_results", 1) or 1),
            )
        )

    return watches
