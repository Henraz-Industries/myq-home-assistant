from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


class StoredTokens(TypedDict):
    access_token: str
    refresh_token: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class OAuthTokens:
    access_token: str
    refresh_token: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class MyQAccount:
    account_id: str
    name: str


@dataclass(frozen=True, slots=True)
class GarageDoor:
    account_id: str
    serial_number: str
    name: str
    device_model: str | None
    door_state: str | None
    online: bool | None
    battery_backup_state: str | None = None
    in_vacation_mode: bool | None = None
    attached_worklight_on: bool | None = None
    active_fault_codes: tuple[str, ...] = ()
    absolute_cycle_count: int | None = None
    service_cycle_count: int | None = None
    last_device_activation_source: str | None = None
