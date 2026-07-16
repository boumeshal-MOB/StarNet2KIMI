"""AWS Lambda entrypoint for BTM topographic calculations."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any

from .calculator import execute
from .contracts import CONTRACT_VERSION, ContractError, decode_event, validate_invocation


def lambda_handler(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    started = time.perf_counter()
    gateway = False
    request_id = str(getattr(context, "aws_request_id", "unknown"))
    try:
        invocation, gateway = decode_event(event)
        request_id, operation, payload = validate_invocation(invocation)
        result = execute(operation, payload)
        response = {
            "ok": True,
            "contract_version": CONTRACT_VERSION,
            "request_id": request_id,
            "operation": operation,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "result": result,
        }
        _log("completed", request_id, operation=operation, duration_ms=response["duration_ms"])
        return _transport(response, 200, gateway)
    except (ContractError, KeyError, TypeError, ValueError) as error:
        response = {
            "ok": False,
            "contract_version": CONTRACT_VERSION,
            "request_id": request_id,
            "error": {"code": "INVALID_TOPOGRAPHIC_INPUT", "message": str(error)},
        }
        _log("rejected", request_id, error_type=type(error).__name__, message=str(error))
        return _transport(response, 422, gateway)
    except Exception as error:  # Boundary: detailed exception is logged, not returned to clients.
        _log("failed", request_id, error_type=type(error).__name__, message=str(error))
        response = {
            "ok": False,
            "contract_version": CONTRACT_VERSION,
            "request_id": request_id,
            "error": {
                "code": "TOPOGRAPHIC_ENGINE_ERROR",
                "message": "Topographic calculation failed",
            },
        }
        return _transport(response, 500, gateway)


def _transport(payload: dict[str, Any], status_code: int, gateway: bool) -> dict[str, Any]:
    if not gateway:
        return {"statusCode": status_code, **payload}
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, allow_nan=False, separators=(",", ":")),
    }


def _log(event: str, request_id: str, **fields: Any) -> None:
    print(
        json.dumps(
            {"event": event, "request_id": request_id, **fields},
            default=str,
            separators=(",", ":"),
        )
    )
