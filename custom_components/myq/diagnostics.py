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
REDACT_KEY_FRAGMENTS = (
    "account",
    "email",
    "href",
    "ip_address",
    "mac",
    "password",
    "secret",
    "serial",
    "ssid",
    "token",
    "url",
)
REDACT_KEYS = {"id", "parent_device_id", "user_id"}


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
        # Account IDs are identifiers, so number the accounts instead.
        devices = {
            f"account_{index}": [_redact(item) for item in account_items]
            for index, account_items in enumerate(items.values(), start=1)
        }

    return {
        "entry": _redact({**entry.data, CONF_EMAIL: REDACTED, CONF_TOKENS: REDACTED}),
        "devices": devices,
    }


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive(key) else _redact(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _is_sensitive(key: object) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return lowered in REDACT_KEYS or any(fragment in lowered for fragment in REDACT_KEY_FRAGMENTS)
