from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from collections.abc import Callable, Mapping
from typing import cast

from aiohttp import ClientSession

from .const import (
    ANDROID_CERT_SHA1,
    ANDROID_PACKAGE,
    APP_VERSION,
    BRAND_ID,
    FIREBASE_API_KEY,
    FIREBASE_APP_ID,
    FIREBASE_DEBUG_TOKEN,
    FIREBASE_PROJECT_ID,
    IDENTITY_BASE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPE,
    TOKEN_EXPIRY_MARGIN,
    USER_AGENT,
)
from .exceptions import MyQApiError, MyQAuthenticationError
from .models import OAuthTokens

TokenListener = Callable[[OAuthTokens], None]


class MyQAuth:
    def __init__(
        self,
        session: ClientSession,
        tokens: OAuthTokens,
        token_listener: TokenListener,
    ) -> None:
        self._session = session
        self._tokens = tokens
        self._token_listener = token_listener
        self._refresh_lock = asyncio.Lock()

    async def async_access_token(self) -> str:
        if self._tokens.expires_at - TOKEN_EXPIRY_MARGIN.total_seconds() > time.time():
            return self._tokens.access_token
        async with self._refresh_lock:
            if self._tokens.expires_at - TOKEN_EXPIRY_MARGIN.total_seconds() > time.time():
                return self._tokens.access_token
            return (await self.async_refresh()).access_token

    async def async_refresh(self) -> OAuthTokens:
        payload = await _post_json(
            self._session,
            f"{IDENTITY_BASE_URL}/connect/token",
            data={
                "client_id": OAUTH_CLIENT_ID,
                "scope": OAUTH_SCOPE,
                "redirect_uri": OAUTH_REDIRECT_URI,
                "grant_type": "refresh_token",
                "refresh_token": self._tokens.refresh_token,
            },
            headers=_token_headers(),
        )
        tokens = _oauth_tokens(payload, self._tokens.refresh_token)
        self._tokens = tokens
        self._token_listener(tokens)
        return tokens


async def async_exchange_code(session: ClientSession, code: str, verifier: str) -> OAuthTokens:
    """Exchange a PKCE authorization code using an App Check token."""
    app_check_token = await _mint_app_check_token(session)
    payload = await _post_json(
        session,
        f"{IDENTITY_BASE_URL}/connect/token",
        data={
            "client_id": OAUTH_CLIENT_ID,
            "scope": OAUTH_SCOPE,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "code_verifier": verifier,
        },
        headers={
            **_token_headers(),
            "Firebase-AppCheck-Token": app_check_token,
        },
    )
    return _oauth_tokens(payload)


async def _mint_app_check_token(session: ClientSession) -> str:
    endpoint = (
        "https://firebaseappcheck.googleapis.com/v1/projects/"
        f"{FIREBASE_PROJECT_ID}/apps/{FIREBASE_APP_ID}:exchangeDebugToken"
    )
    payload = await _post_json(
        session,
        endpoint,
        params={"key": FIREBASE_API_KEY},
        json_body={"debugToken": FIREBASE_DEBUG_TOKEN},
        headers={
            "X-Android-Package": ANDROID_PACKAGE,
            "X-Android-Cert": ANDROID_CERT_SHA1,
        },
    )
    token = payload.get("token")
    if not isinstance(token, str) or not token:
        raise MyQApiError("Firebase App Check did not return a token")
    return token


async def _post_json(
    session: ClientSession,
    url: str,
    *,
    data: Mapping[str, str] | None = None,
    params: Mapping[str, str] | None = None,
    json_body: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
) -> dict[str, object]:
    async with session.post(
        url,
        data=data,
        params=params,
        json=json_body,
        headers=headers,
    ) as response:
        body = await response.text()
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as error:
            raise MyQApiError(
                f"MyQ returned HTTP {response.status} with an invalid JSON body"
            ) from error
        if not isinstance(parsed, dict):
            raise MyQApiError("MyQ returned an unexpected JSON response")
        payload = cast(dict[str, object], parsed)
        if response.status < 400:
            return payload
        error_code = payload.get("code") or payload.get("error")
        if response.status in {400, 401, 403}:
            raise MyQAuthenticationError(str(error_code or response.status))
        raise MyQApiError(f"MyQ request failed with HTTP {response.status}")


def _oauth_tokens(
    payload: Mapping[str, object],
    existing_refresh_token: str | None = None,
) -> OAuthTokens:
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token", existing_refresh_token)
    expires_in = payload.get("expires_in")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        raise MyQApiError("MyQ returned an incomplete OAuth token response")
    if not isinstance(expires_in, int | float):
        raise MyQApiError("MyQ returned an invalid OAuth expiry")
    return OAuthTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=time.time() + float(expires_in),
    )


def create_authorization_url() -> tuple[str, str]:
    """Create an authorization URL and its PKCE verifier."""
    verifier = secrets.token_urlsafe(32)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    query = urllib.parse.urlencode(
        {
            "acr_values": "unified_flow:v1 brand:myq",
            "client_id": OAUTH_CLIENT_ID,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "ui_locales": "en-US",
            "redirect_uri": OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": OAUTH_SCOPE,
            "prompt": "login",
        }
    )
    return f"{IDENTITY_BASE_URL}/connect/authorize?{query}", verifier


def _token_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "App-Version": APP_VERSION,
        "BrandId": BRAND_ID,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": USER_AGENT,
    }
