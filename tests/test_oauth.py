import asyncio
from typing import cast

from aiohttp import ClientSession

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
