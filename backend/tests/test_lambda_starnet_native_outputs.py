from __future__ import annotations

from lambda_app.handler import lambda_handler


class Context:
    aws_request_id = "native-starnet-test"


def test_lambda_merges_native_pts_lst_and_err_outputs():
    listing = """
MicroSurvey STAR*NET-PRO Version 6.0.43
Adjustment Statistical Summary
Iterations = 2
Number of Stations = 1
Number of Observations = 3
Number of Unknowns = 3
Number of Redundant Obs = 0
The Chi-Square Test at 5.00% Level Passed
Adjusted Coordinates (Meters)
Station E N Elev Description
P_001 10.0000 20.0000 5.0000
Station Coordinate Standard Deviations (Meters)
Station E N Elev
P_001 0.0010 0.0011 0.0012
"""
    response = lambda_handler(
        {
            "contract_version": "btm.topographic-adjustment.lambda.v1",
            "request_id": "native-output",
            "operation": "parse-starnet-outputs",
            "payload": {
                "pts": "P_001 10.00001 20.00002 5.00003\n",
                "lst": listing,
                "err": "MicroSurvey STAR*NET-PRO Error Log\nNetwork Processing Completed\n",
                "engine_names": {"POINT-001": "P_001"},
            },
        },
        Context(),
    )
    assert response["statusCode"] == 200
    parsed = response["result"]
    point = parsed["points"][0]
    assert point["physical_point_id"] == "POINT-001"
    assert point["e"] == 10.00001  # full precision comes from PTS
    assert point["sigma_e"] == 0.001  # uncertainty comes from LST
    assert parsed["summary"]["chi_square_status"] == "passed"
    assert parsed["summary"]["converged"] is True
    assert parsed["artifacts"]["lst"] is True
