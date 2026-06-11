from typing import Any, cast

import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint

from models import (
    ChatHistoryModel,
    ChatSessionModel,
    CoverageResultModel,
    FlightPathModel,
    IoTNodeModel,
    MissionModel,
    ReportModel,
    TelemetryModel,
    UserModel,
)


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (MissionModel, {"name": "Mission", "status": "invalid"}),
        (ChatHistoryModel, {"message": "Hello", "role": "invalid"}),
        (FlightPathModel, {"total_distance_m": -1}),
        (FlightPathModel, {"estimated_duration_s": -1}),
        (IoTNodeModel, {"name": "Node", "latitude": 91}),
        (IoTNodeModel, {"name": "Node", "longitude": -181}),
        (TelemetryModel, {"iot_node_id": 1, "latitude": 91}),
        (TelemetryModel, {"iot_node_id": 1, "longitude": -181}),
        (TelemetryModel, {"iot_node_id": 1, "velocity": -1}),
        (TelemetryModel, {"iot_node_id": 1, "heading": 360}),
        (
            TelemetryModel,
            {"iot_node_id": 1, "temperature_celsius": -273.16},
        ),
        (TelemetryModel, {"iot_node_id": 1, "humidity_percent": -0.01}),
        (TelemetryModel, {"iot_node_id": 1, "humidity_percent": 100.01}),
        (CoverageResultModel, {"coverage_percent": 101}),
    ],
)
def test_models_reject_invalid_domain_values(
    model: type[object],
    data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model(**data)


def test_models_accept_domain_boundaries() -> None:
    assert IoTNodeModel(name="Node", latitude=-90, longitude=180)
    assert TelemetryModel(
        iot_node_id=1,
        latitude=90,
        longitude=-180,
        velocity=0,
        heading=359.999,
        temperature_celsius=-273.15,
        humidity_percent=0,
    )
    assert TelemetryModel(
        iot_node_id=1,
        temperature_celsius=35.5,
        humidity_percent=100,
    )
    assert CoverageResultModel(coverage_percent=0)
    assert CoverageResultModel(coverage_percent=100)


def test_model_constraints_are_declared() -> None:
    expected_constraints = {
        MissionModel: {"ck_missions_status", "ck_missions_date_order"},
        ChatHistoryModel: {"ck_chat_histories_role"},
        FlightPathModel: {
            "ck_flight_paths_total_distance",
            "ck_flight_paths_estimated_duration",
        },
        IoTNodeModel: {"ck_iot_nodes_latitude", "ck_iot_nodes_longitude"},
        TelemetryModel: {
            "ck_telemetry_latitude",
            "ck_telemetry_longitude",
            "ck_telemetry_velocity",
            "ck_telemetry_heading",
            "ck_telemetry_temperature_celsius",
            "ck_telemetry_humidity_percent",
        },
        CoverageResultModel: {"ck_coverage_results_percent"},
    }

    for model, expected in expected_constraints.items():
        table = cast(Any, model).__table__
        actual = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert expected <= actual


def test_foreign_keys_and_time_series_queries_are_indexed() -> None:
    expected_indexes = {
        MissionModel: {
            "ix_missions_owner_id",
            "ix_missions_active_owner_id",
        },
        ChatHistoryModel: {
            "ix_chat_histories_mission_id",
            "ix_chat_histories_user_id",
            "ix_chat_histories_chat_session_id",
            "ix_chat_histories_mission_id_timestamp",
        },
        ChatSessionModel: {
            "ix_chat_sessions_user_id",
            "ix_chat_sessions_user_id_updated_at",
        },
        FlightPathModel: {"ix_flight_paths_mission_id"},
        IoTNodeModel: {
            "ix_iot_nodes_mission_id",
            "ix_iot_nodes_active_mission_id",
        },
        TelemetryModel: {
            "ix_telemetry_iot_node_id",
            "ix_telemetry_iot_node_id_timestamp",
            "ix_telemetry_active_environment_timestamp_node",
        },
        CoverageResultModel: {
            "ix_coverage_results_mission_id",
            "ix_coverage_results_flight_path_id",
        },
        ReportModel: {"ix_reports_mission_id", "ix_reports_author_id"},
    }

    for model, expected in expected_indexes.items():
        table = cast(Any, model).__table__
        actual = {index.name for index in table.indexes}
        assert expected <= actual


def test_password_hash_is_hidden_from_repr_and_serialization() -> None:
    user = UserModel(
        name="User",
        email="user@example.com",
        password_hash="sensitive-hash",
    )

    assert "sensitive-hash" not in repr(user)
    assert "password_hash" not in user.model_dump()
