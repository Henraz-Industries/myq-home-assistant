from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from homeassistant.config_entries import ConfigEntry

from .models import GarageDoor, StoredTokens

if TYPE_CHECKING:
    from .client import MyQClient
    from .coordinator import MyQDataUpdateCoordinator


class MyQConfigData(TypedDict):
    email: str
    mfa_method: str
    tokens: StoredTokens


type MyQCoordinatorData = dict[str, GarageDoor]


@dataclass(frozen=True, slots=True)
class MyQRuntimeData:
    client: MyQClient
    coordinator: MyQDataUpdateCoordinator


type MyQConfigEntry = ConfigEntry[MyQRuntimeData]
