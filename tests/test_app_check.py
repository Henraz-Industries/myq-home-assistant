import hashlib
import urllib.parse
from typing import cast

from aiohttp import ClientSession

from custom_components.myq.oauth import async_exchange_code

from .http import FakeResponse, FakeSession


async def test_authorization_exchange_preserves_app_check_request() -> None:
    session = FakeSession(
        post_responses=[
            FakeResponse("", body='{"token":"app-check"}'),
            FakeResponse(
                "",
                body='{"access_token":"access","refresh_token":"refresh","expires_in":3600}',
            ),
        ]
    )

    tokens = await async_exchange_code(cast(ClientSession, session), "code", "verifier")

    assert len(session.calls) == 2
    registration, exchange = session.calls
    target = urllib.parse.urlsplit(registration.url)
    assert registration.method == "POST"
    assert target.scheme == "https"
    assert target.netloc == "firebaseappcheck.googleapis.com"
    assert not target.query
    segments = target.path.split("/")
    assert len(segments) == 6
    assert segments[1:3] == ["v1", "projects"]
    assert segments[4] == "apps"
    assert segments[5].endswith(":exchangeDebugToken")
    parameters = registration.kwargs["params"]
    payload = registration.kwargs["json"]
    headers = registration.kwargs["headers"]
    assert set(parameters) == {"key"}
    assert set(payload) == {"debugToken"}
    assert set(headers) == {"X-Android-Package", "X-Android-Cert"}
    values = (
        segments[3],
        segments[5].removesuffix(":exchangeDebugToken"),
        parameters["key"],
        payload["debugToken"],
        headers["X-Android-Package"],
        headers["X-Android-Cert"],
    )
    fingerprint = hashlib.sha256("\0".join(values).encode("ascii")).hexdigest()
    assert fingerprint == "5915def6a7fc9910782f10180f78595ac10b01585e1fc9c3d9e50eea3e310d15"
    assert exchange.kwargs["headers"]["Firebase-AppCheck-Token"] == "app-check"
    assert exchange.kwargs["data"]["code"] == "code"
    assert exchange.kwargs["data"]["code_verifier"] == "verifier"
    assert tokens.access_token == "access"
    assert tokens.refresh_token == "refresh"
