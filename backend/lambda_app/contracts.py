"""Stable invocation contract for the stateless BTM calculation Lambda."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

CONTRACT_VERSION = "btm.topographic-adjustment.lambda.v1"


class ContractError(ValueError):
    """Raised when the Lambda invocation does not match the public contract."""


def decode_event(event: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return the direct invocation payload and whether API Gateway wrapping was used."""
    if not isinstance(event, Mapping):
        raise ContractError("event must be an object")
    gateway = "requestContext" in event and "body" in event
    if not gateway:
        return dict(event), False
    body = event.get("body")
    if isinstance(body, str):
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ContractError("API Gateway body must contain valid JSON") from exc
    elif isinstance(body, Mapping):
        decoded = dict(body)
    else:
        raise ContractError("API Gateway body must be a JSON object")
    if not isinstance(decoded, dict):
        raise ContractError("decoded body must be an object")
    return decoded, True


def validate_invocation(event: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
    version = event.get("contract_version")
    if version != CONTRACT_VERSION:
        raise ContractError(f"contract_version must be {CONTRACT_VERSION}")
    request_id = str(event.get("request_id") or "unknown")
    operation = str(event.get("operation") or "run-processing")
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        raise ContractError("payload must be an object")
    return request_id, operation, dict(payload)


def require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    return dict(value)


def require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{name} must be an array")
    return value
