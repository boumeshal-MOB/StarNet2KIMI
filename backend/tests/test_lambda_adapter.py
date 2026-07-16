from __future__ import annotations

import json
import math

from lambda_app.handler import lambda_handler


class Context:
    aws_request_id = "test-request"


def invoke(operation: str, payload: dict) -> dict:
    return lambda_handler(
        {
            "contract_version": "btm.topographic-adjustment.lambda.v1",
            "request_id": "unit-test",
            "operation": operation,
            "payload": payload,
        },
        Context(),
    )


def prepared_payload() -> dict:
    return {
        "points": [
            {"id": "S1", "e": 0.0, "n": 0.0, "h": 0.0, "role": "station", "free": False},
            {"id": "P1", "e": 10.1, "n": 9.9, "h": 0.1, "role": "monitoring", "free": True},
        ],
        "sights": [
            {
                "id": "obs-1",
                "station_id": "S1",
                "target_id": "P1",
                "hz_rad": math.pi / 4,
                "vz_rad": math.pi / 2,
                "slope_distance_m": math.sqrt(200),
                "instrument_height_m": 0.0,
                "target_height_m": 0.0,
            }
        ],
        "constraints": [],
        "default_weights": {
            "direction_arcsec": 1.0,
            "zenith_arcsec": 1.0,
            "distance_mm": 1.0,
            "distance_ppm": 0.0,
        },
        "adjustment": {
            "fixed_orientations_rad": {"S1": 0.0},
            "max_iterations": 30,
            "convergence_threshold_m": 1e-9,
        },
        "auto_adjust": {"enabled": False},
        "starnet": {"generate_inputs": True, "run_label": "UNIT_TEST"},
    }


def test_calculate_returns_python_result_and_starnet_inputs():
    response = invoke("calculate", prepared_payload())
    assert response["statusCode"] == 200
    calculation = response["result"]
    result = calculation["result"]
    assert result["ok"] is True
    point = next(row for row in result["points"] if row["id"] == "P1")
    assert abs(point["e"] - 10.0) < 1e-5
    assert abs(point["n"] - 10.0) < 1e-5
    assert abs(point["h"]) < 1e-5
    assert "DB S1" in calculation["starnet_inputs"]["dat"]
    assert "RUN_LABEL UNIT_TEST" in calculation["starnet_inputs"]["prj"]


def test_parse_starnet_outputs_restores_physical_point_ids():
    response = invoke(
        "parse-starnet-outputs",
        {
            "pts": "P_001 10.0000 20.0000 5.0000 0.0010 0.0011 0.0012\n",
            "err": "CONVERGED YES\nITERATIONS 4\nCHI2_STATUS passed\nRANK 3\nRANK_DEFICIENCY 0\n",
            "engine_names": {"POINT-001": "P_001"},
        },
    )
    assert response["statusCode"] == 200
    parsed = response["result"]
    assert parsed["points"][0]["physical_point_id"] == "POINT-001"
    assert parsed["summary"]["converged"] is True


def test_api_gateway_transport_is_supported():
    direct = {
        "contract_version": "btm.topographic-adjustment.lambda.v1",
        "request_id": "gateway-test",
        "operation": "build-starnet-inputs",
        "payload": prepared_payload(),
    }
    response = lambda_handler({"requestContext": {}, "body": json.dumps(direct)}, Context())
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["ok"] is True
