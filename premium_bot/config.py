from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Raised when environment configuration is invalid."""


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _required(name: str) -> str:
    value = _clean(os.getenv(name))
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _bool(name: str, default: bool = False) -> bool:
    value = _clean(os.getenv(name))
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _int_set(name: str, *, required: bool = False) -> frozenset[int]:
    value = _clean(os.getenv(name))
    if not value:
        if required:
            raise ConfigError(f"Missing required environment variable: {name}")
        return frozenset()

    ids: set[int] = set()
    for item in value.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError as exc:
            raise ConfigError(f"{name} contains a non-integer value: {item}") from exc
    if required and not ids:
        raise ConfigError(f"{name} must contain at least one ID")
    return frozenset(ids)


def _decimal(name: str, default: str) -> Decimal:
    value = _clean(os.getenv(name)) or default
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ConfigError(f"{name} must be a decimal number") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be greater than zero")
    return parsed


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_admin_ids: frozenset[int]
    fragment_hash: str
    fragment_cookie: str
    wallet_mnemonic: str
    payment_dry_run: bool
    allowed_durations: frozenset[int]
    max_ton_amount: Decimal
    confirm_ttl_seconds: int
    fragment_wallet_address: str
    strict_fragment_wallet: bool
    show_sender: bool
    toncenter_api_key: str | None
    ton_testnet: bool
    request_timeout: float
    log_level: str

    @classmethod
    def from_env(cls, env_path: str | Path = ".env") -> "Settings":
        load_dotenv(env_path)

        payment_dry_run = _bool("PAYMENT_DRY_RUN", True)
        wallet_mnemonic = _clean(os.getenv("WALLET_MNEMONIC"))
        if not payment_dry_run and not wallet_mnemonic:
            raise ConfigError("WALLET_MNEMONIC is required when PAYMENT_DRY_RUN=false")

        allowed_durations = _int_set("ALLOWED_DURATIONS")
        if not allowed_durations:
            allowed_durations = frozenset({3, 6, 12})
        if any(month <= 0 for month in allowed_durations):
            raise ConfigError("ALLOWED_DURATIONS must contain positive month values")

        try:
            confirm_ttl_seconds = int(_clean(os.getenv("CONFIRM_TTL_SECONDS")) or "300")
        except ValueError as exc:
            raise ConfigError("CONFIRM_TTL_SECONDS must be an integer") from exc
        if confirm_ttl_seconds <= 0:
            raise ConfigError("CONFIRM_TTL_SECONDS must be greater than zero")

        try:
            request_timeout = float(_clean(os.getenv("REQUEST_TIMEOUT")) or "20")
        except ValueError as exc:
            raise ConfigError("REQUEST_TIMEOUT must be a number") from exc
        if request_timeout <= 0:
            raise ConfigError("REQUEST_TIMEOUT must be greater than zero")

        return cls(
            telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
            telegram_admin_ids=_int_set("TELEGRAM_ADMIN_IDS", required=True),
            fragment_hash=_required("FRAGMENT_HASH"),
            fragment_cookie=_required("FRAGMENT_COOKIE"),
            wallet_mnemonic=wallet_mnemonic,
            payment_dry_run=payment_dry_run,
            allowed_durations=frozenset(sorted(allowed_durations)),
            max_ton_amount=_decimal("MAX_TON_AMOUNT", "100"),
            confirm_ttl_seconds=confirm_ttl_seconds,
            fragment_wallet_address=_clean(os.getenv("FRAGMENT_WALLET_ADDRESS"))
            or "EQBAjaOyi2wGWlk-EDkSabqqnF-MrrwMadnwqrurKpkla9nE",
            strict_fragment_wallet=_bool("STRICT_FRAGMENT_WALLET", False),
            show_sender=_bool("SHOW_SENDER", True),
            toncenter_api_key=_clean(os.getenv("TONCENTER_API_KEY")) or None,
            ton_testnet=_bool("TON_TESTNET", False),
            request_timeout=request_timeout,
            log_level=(_clean(os.getenv("LOG_LEVEL")) or "INFO").upper(),
        )
