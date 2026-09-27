import asyncio
import time
from typing import cast
from unittest.mock import MagicMock

import pytest
from aiohttp import ClientConnectionError, ClientSession

from custom_components.myq.exceptions import MyQApiError, MyQAuthenticationError
from custom_components.myq.models import OAuthTokens
from custom_components.myq.oauth import MyQAuth

from .http import FakeResponse, FakeSession


async def test_expired_access_token_refreshes_once_for_concurrent_callers() -> None:
    session = FakeSession(
        post_responses=[
            FakeResponse(
                "",
                body=(
                    '{"access_token":"new-access","refresh_token":"new-refresh","expires_in":3600}'
                ),
            )
        ]
    )
    persisted: list[OAuthTokens] = []
    auth = MyQAuth(
        cast(ClientSession, session),
        OAuthTokens("expired", "old-refresh", 0),
        persisted.append,
    )

    first, second = await asyncio.gather(
        auth.async_access_token(),
        auth.async_access_token(),
    )

    assert (first, second) == ("new-access", "new-access")
    assert len(session.calls) == 1
    assert len(persisted) == 1
    assert persisted[0].access_token == "new-access"
    assert persisted[0].refresh_token == "new-refresh"


async def test_unexpired_access_token_does_not_refresh() -> None:
    session = FakeSession()
    listener = MagicMock()
    auth = MyQAuth(
        cast(ClientSession, session),
        OAuthTokens("access", "refresh", time.time() + 3600),
        listener,
    )

    assert await auth.async_access_token() == "access"
    assert not session.calls
    listener.assert_not_called()


async def test_refresh_retains_existing_refresh_token_when_omitted() -> None:
    session = FakeSession(
        post_responses=[FakeResponse("", body='{"access_token":"new-access","expires_in":3600}')]
    )
    listener = MagicMock()
    auth = MyQAuth(cast(ClientSession, session), OAuthTokens("old", "refresh", 0), listener)

    assert await auth.async_access_token() == "new-access"

    listener.assert_called_once()
    tokens = listener.call_args.args[0]
    assert tokens.refresh_token == "refresh"
    assert tokens.expires_at > time.time() + 3500
    assert await auth.async_access_token() == "new-access"
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    ("status", "body", "error_type"),
    [
        (401, '{"error":"invalid_grant"}', MyQAuthenticationError),
        (500, '{"error":"unavailable"}', MyQApiError),
        (200, '{"access_token":"invalid","refresh_token":"invalid"}', MyQApiError),
        (200, "not-json", MyQApiError),
    ],
)
async def test_refresh_failure_preserves_tokens_until_successful_retry(
    status: int,
    body: str,
    error_type: type[MyQApiError | MyQAuthenticationError],
) -> None:
    session = FakeSession(
        post_responses=[
            FakeResponse("", status=status, body=body),
            FakeResponse(
                "",
                body='{"access_token":"new-access","refresh_token":"new-refresh","expires_in":3600}',
            ),
        ]
    )
    listener = MagicMock()
    auth = MyQAuth(cast(ClientSession, session), OAuthTokens("old", "old-refresh", 0), listener)

    with pytest.raises(error_type):
        await auth.async_access_token()

    listener.assert_not_called()
    assert len(session.calls) == 1
    assert await auth.async_access_token() == "new-access"
    assert len(session.calls) == 2
    assert all(call.kwargs["data"]["refresh_token"] == "old-refresh" for call in session.calls)
    listener.assert_called_once()
    assert listener.call_args.args[0].refresh_token == "new-refresh"


async def test_network_failure_during_refresh_preserves_tokens() -> None:
    session = FakeSession(
        post_responses=[FakeResponse("", body='{"access_token":"new-access","expires_in":3600}')]
    )
    transport = MagicMock()
    transport.post.side_effect = ClientConnectionError
    listener = MagicMock()
    auth = MyQAuth(transport, OAuthTokens("old", "old-refresh", 0), listener)

    with pytest.raises(ClientConnectionError):
        await auth.async_access_token()

    transport.post.assert_called_once()
    listener.assert_not_called()
    transport.post.side_effect = session.post

    assert await auth.async_access_token() == "new-access"
    assert session.calls[0].kwargs["data"]["refresh_token"] == "old-refresh"
    listener.assert_called_once()
    assert listener.call_args.args[0].refresh_token == "old-refresh"
