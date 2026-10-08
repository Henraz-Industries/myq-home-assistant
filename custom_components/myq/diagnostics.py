from __future__ import annotations

from typing import Any

from aiohttp import ClientError
from homeassistant.core import HomeAssistant

from .const import CONF_EMAIL, CONF_TOKENS
from .exceptions import MyQApiError, MyQAuthenticationError
from .runtime import MyQConfigEntry

REDACTED = "**REDACTED**"

# Keys whose values identify the account, a device, or a network, or grant access.
# Any key containing one of these fragments is redacted, so new fields such as
# `camera_serial_number` or `stream_url` are covered without listing them here.
# Transmitter maps are keyed by remote IDs, so their whole value is redacted.
REDACT_KEY_FRAGMENTS = (
    "account",
    "email",
    "href",
    "ip_address",
    "mac",
    "password",
    "physical_",
    "secret",
    "serial",
    "source_id",
    "ssid",
    "token",
    "transmitter",
    "url",
)
REDACT_KEYS = {"id", "parent_device_id", "user_id"}
# Shorter redacted values (such as a "1" brand ID) would mask unrelated text.
MIN_IDENTIFIER_LENGTH = 6


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: MyQConfigEntry,
) -> dict[str, Any]:
    del hass
    client = entry.runtime_data.client
    devices: dict[str, Any]
    try:
        items = await client.async_get_device_items()
    except (ClientError, MyQApiError, MyQAuthenticationError) as error:
        devices = {"error": type(error).__name__}
    else:
        # Identifiers also appear inside other values, such as the camera's
        # `links` paths, so every redacted string is masked wherever it occurs.
        identifiers = set(items)
        for account_items in items.values():
            _collect_identifiers(account_items, identifiers)
        # Account IDs are identifiers, so number the accounts instead.
        devices = {
            f"account_{index}": [_redact(item, identifiers) for item in account_items]
            for index, account_items in enumerate(items.values(), start=1)
        }

    return {
        "entry": _redact({**entry.data, CONF_EMAIL: REDACTED, CONF_TOKENS: REDACTED}, set()),
        "devices": devices,
    }


def _collect_identifiers(value: Any, identifiers: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _is_sensitive(key) and isinstance(item, str):
                identifiers.add(item)
            else:
                _collect_identifiers(item, identifiers)
    elif isinstance(value, list | tuple):
        for item in value:
            _collect_identifiers(item, identifiers)


def _redact(value: Any, identifiers: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive(key) else _redact(item, identifiers)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item, identifiers) for item in value]
    if isinstance(value, str):
        # Longest first, so an identifier containing another is masked whole.
        for identifier in sorted(identifiers, key=len, reverse=True):
            if len(identifier) >= MIN_IDENTIFIER_LENGTH:
                value = value.replace(identifier, REDACTED)
    return value


def _is_sensitive(key: object) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return lowered in REDACT_KEYS or any(fragment in lowered for fragment in REDACT_KEY_FRAGMENTS)
