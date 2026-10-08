from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myq.const import CONF_EMAIL, CONF_MFA_METHOD, CONF_TOKENS, DOMAIN
from custom_components.myq.diagnostics import REDACTED, async_get_config_entry_diagnostics
from custom_components.myq.exceptions import MyQApiError
from custom_components.myq.runtime import MyQRuntimeData


def _entry(client: MagicMock) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "driver@example.com",
            CONF_MFA_METHOD: "email",
            CONF_TOKENS: {"access_token": "a", "refresh_token": "r", "expires_at": 1.0},
        },
    )
    entry.runtime_data = MyQRuntimeData(client=client, coordinator=MagicMock())
    return entry


async def test_diagnostics_include_every_device_with_identifiers_redacted(
    hass: HomeAssistant,
) -> None:
    client = MagicMock()
    client.async_get_device_items = AsyncMock(
        return_value={
            "account-1": (
                {
                    "device_family": "camera",
                    "device_platform": "myq",
                    "id": "cam-id",
                    "serial_number": "cam-1",
                    "parent_device_id": "hub-1",
                    "href": "https://devices.myq-cloud.com/cam-1",
                    "state": {
                        "online": True,
                        "stream_url": "rtsp://secret",
                        "mac_address": "aa:bb",
                        "features": [{"live_view_token": "t", "enabled": True}],
                    },
                },
            )
        }
    )

    result = await async_get_config_entry_diagnostics(hass, _entry(client))

    assert result["entry"] == {
        CONF_EMAIL: REDACTED,
        CONF_MFA_METHOD: "email",
        CONF_TOKENS: REDACTED,
    }
    assert result["devices"] == {
        "account_1": [
            {
                "device_family": "camera",
                "device_platform": "myq",
                "id": REDACTED,
                "serial_number": REDACTED,
                "parent_device_id": REDACTED,
                "href": REDACTED,
                "state": {
                    "online": True,
                    "stream_url": REDACTED,
                    "mac_address": REDACTED,
                    "features": [{"live_view_token": REDACTED, "enabled": True}],
                },
            }
        ]
    }


async def test_diagnostics_report_api_failure_without_details(hass: HomeAssistant) -> None:
    client = MagicMock()
    client.async_get_device_items = AsyncMock(side_effect=MyQApiError("HTTP 500 from secret"))

    result = await async_get_config_entry_diagnostics(hass, _entry(client))

    assert result["devices"] == {"error": "MyQApiError"}


async def test_diagnostics_mask_identifiers_inside_links_and_transmitters(
    hass: HomeAssistant,
) -> None:
    client = MagicMock()
    client.async_get_device_items = AsyncMock(
        return_value={
            "acct-1234": (
                {
                    "serial_number": "CAM-0000-1111",
                    "account_id": "acct-1234",
                    "device_family": "camera",
                    "state": {
                        "links": {
                            "stream": "/accounts/acct-1234/devices/cameras/CAM-0000-1111/stream",
                        },
                    },
                },
                {
                    "serial_number": "GDO-2222",
                    "device_family": "garagedoor",
                    "state": {
                        "ook_transmitters": {"TX0001": {"enabled": True}},
                        "last_device_activation_source": "myq_app",
                        "last_device_activation_source_id": "TX0002",
                    },
                },
                {
                    "device_family": "gateway",
                    "state": {"physical_devices": ["CG0000"], "physical_cameras": []},
                },
            )
        }
    )

    result = await async_get_config_entry_diagnostics(hass, _entry(client))

    camera, door, gateway = result["devices"]["account_1"]
    assert camera["state"]["links"] == {
        "stream": f"/accounts/{REDACTED}/devices/cameras/{REDACTED}/stream",
    }
    assert door["state"] == {
        "ook_transmitters": REDACTED,
        "last_device_activation_source": "myq_app",
        "last_device_activation_source_id": REDACTED,
    }
    assert gateway["state"] == {"physical_devices": REDACTED, "physical_cameras": REDACTED}
    for secret in ("acct-1234", "CAM-0000-1111", "GDO-2222", "TX000", "CG0000"):
        assert secret not in str(result)
