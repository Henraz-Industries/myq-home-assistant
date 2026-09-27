from unittest.mock import AsyncMock, MagicMock, call

import pytest
from aiohttp import ClientConnectionError
from homeassistant.exceptions import HomeAssistantError

from custom_components.myq.const import DOMAIN
from custom_components.myq.cover import MyQGarageDoor
from custom_components.myq.exceptions import MyQApiError, MyQAuthenticationError
from custom_components.myq.models import GarageDoor


@pytest.mark.parametrize(
    ("state", "closed", "opening", "closing"),
    [
        ("closed", True, False, False),
        ("open", False, False, False),
        ("opening", False, True, False),
        ("closing", False, False, True),
        ("moving", False, False, False),
        ("unknown", None, False, False),
    ],
)
def test_cover_maps_door_state(
    state: str,
    closed: bool | None,
    opening: bool,
    closing: bool,
) -> None:
    entity, _ = _entity(state)

    assert entity.is_closed is closed
    assert entity.is_opening is opening
    assert entity.is_closing is closing


@pytest.mark.parametrize("operation", ["open", "close"])
async def test_cover_commands_client_once_then_refreshes(operation: str) -> None:
    entity, coordinator = _entity("closed")
    commands = {"open": entity.async_open_cover, "close": entity.async_close_cover}
    calls = MagicMock()
    calls.attach_mock(coordinator.client.async_open_door, "open")
    calls.attach_mock(coordinator.client.async_close_door, "close")
    calls.attach_mock(coordinator.async_request_refresh, "refresh")

    await commands[operation]()

    expected = {"open": call.open(entity.door), "close": call.close(entity.door)}[operation]
    assert calls.mock_calls == [expected, call.refresh()]
    assert (
        coordinator.client.async_open_door.await_count
        + coordinator.client.async_close_door.await_count
    ) == 1
    coordinator.async_request_refresh.assert_awaited_once_with()


@pytest.mark.parametrize("operation", ["open", "close"])
@pytest.mark.parametrize("error_type", [MyQApiError, MyQAuthenticationError, ClientConnectionError])
async def test_cover_translates_command_failure_without_retry_or_refresh(
    operation: str,
    error_type: type[MyQApiError | MyQAuthenticationError | ClientConnectionError],
) -> None:
    entity, coordinator = _entity("closed")
    commands = {"open": entity.async_open_cover, "close": entity.async_close_cover}
    calls = MagicMock()
    calls.attach_mock(coordinator.client.async_open_door, "open")
    calls.attach_mock(coordinator.client.async_close_door, "close")
    error = error_type("Command rejected")
    coordinator.client.async_open_door.side_effect = error
    coordinator.client.async_close_door.side_effect = error

    with pytest.raises(HomeAssistantError) as raised:
        await commands[operation]()

    assert raised.value.__cause__ is error
    assert raised.value.translation_domain == DOMAIN
    assert raised.value.translation_key == "command_failed"
    expected = {"open": call.open(entity.door), "close": call.close(entity.door)}[operation]
    assert calls.mock_calls == [expected]
    coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.parametrize("operation", ["open", "close"])
async def test_refresh_failure_does_not_repeat_successful_command(operation: str) -> None:
    entity, coordinator = _entity("closed")
    commands = {"open": entity.async_open_cover, "close": entity.async_close_cover}
    calls = MagicMock()
    calls.attach_mock(coordinator.client.async_open_door, "open")
    calls.attach_mock(coordinator.client.async_close_door, "close")
    calls.attach_mock(coordinator.async_request_refresh, "refresh")
    error = ClientConnectionError("Update failed")
    coordinator.async_request_refresh.side_effect = error

    with pytest.raises(ClientConnectionError) as raised:
        await commands[operation]()

    assert raised.value is error
    expected = {"open": call.open(entity.door), "close": call.close(entity.door)}[operation]
    assert calls.mock_calls == [expected, call.refresh()]
    assert (
        coordinator.client.async_open_door.await_count
        + coordinator.client.async_close_door.await_count
    ) == 1


async def test_missing_door_has_no_state_and_cannot_receive_commands() -> None:
    entity, coordinator = _entity("closed")
    coordinator.data = {}

    assert entity.available is False
    assert entity.is_closed is None
    assert entity.is_opening is False
    assert entity.is_closing is False
    for command in (entity.async_open_cover, entity.async_close_cover):
        with pytest.raises(HomeAssistantError):
            await command()

    coordinator.client.async_open_door.assert_not_awaited()
    coordinator.client.async_close_door.assert_not_awaited()
    coordinator.async_request_refresh.assert_not_awaited()


def _entity(state: str) -> tuple[MyQGarageDoor, MagicMock]:
    door = GarageDoor("account-1", "door-1", "Garage", None, state, True)
    coordinator = MagicMock()
    coordinator.data = {door.serial_number: door}
    coordinator.client.async_open_door = AsyncMock()
    coordinator.client.async_close_door = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    return MyQGarageDoor(coordinator, door), coordinator
