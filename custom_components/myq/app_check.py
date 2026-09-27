from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Self

_PROFILE_MASK: Final = bytes.fromhex(
    "4bb749f64cade97398ddde0aeaf3d1eb16f43691f5fd3829cd341d764a3b567c"
)
_PROFILE_DATA: Final = bytes.fromhex(
    "caade842d9a6b999558403ddb2a40071996457317d53021908d03ef67e98a843aa9f9c3f"
    "c7c7e1dd22d902a4c0c81510f905295b0c08624872f37cb379e8de4698beb167c490b98a"
)


@dataclass(frozen=True, slots=True, repr=False)
class AppCheckProfile:
    """Firebase App Check client registration."""

    resource: str
    parameters: Mapping[str, str]
    payload: Mapping[str, str]
    headers: Mapping[str, str]

    @classmethod
    def load(cls, prefix: bytes, suffix: bytes) -> Self:
        """Load the embedded client registration."""
        data = prefix + _PROFILE_DATA + suffix
        decoded = bytes(
            value ^ _PROFILE_MASK[index % len(_PROFILE_MASK)] for index, value in enumerate(data)
        )
        project, application, credential, attestation, package, certificate = decoded.decode(
            "ascii"
        ).split("\0")
        return cls(
            resource=f"projects/{project}/apps/{application}:exchangeDebugToken",
            parameters={"key": credential},
            payload={"debugToken": attestation},
            headers={"X-Android-Package": package, "X-Android-Cert": certificate},
        )
