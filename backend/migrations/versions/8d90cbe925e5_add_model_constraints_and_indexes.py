"""add_model_constraints_and_indexes

Revision ID: 8d90cbe925e5
Revises: 7f4ee5733544
Create Date: 2026-06-09 17:41:23.577300

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d90cbe925e5"
down_revision: str | Sequence[str] | None = "7f4ee5733544"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        UPDATE missions
        SET status = 'planned'
        WHERE status NOT IN ('planned', 'in_progress', 'completed', 'cancelled')
        """
    )
    op.execute(
        """
        UPDATE missions
        SET ended_at = NULL
        WHERE ended_at IS NOT NULL
          AND started_at IS NOT NULL
          AND ended_at < started_at
        """
    )
    op.execute(
        """
        UPDATE chat_histories
        SET role = 'user'
        WHERE role NOT IN ('user', 'assistant', 'system', 'tool')
        """
    )
    op.execute(
        """
        UPDATE flight_paths
        SET total_distance_m = NULL
        WHERE total_distance_m < 0
        """
    )
    op.execute(
        """
        UPDATE flight_paths
        SET estimated_duration_s = NULL
        WHERE estimated_duration_s < 0
        """
    )
    op.execute(
        """
        UPDATE iot_nodes
        SET latitude = NULL
        WHERE latitude NOT BETWEEN -90 AND 90
        """
    )
    op.execute(
        """
        UPDATE iot_nodes
        SET longitude = NULL
        WHERE longitude NOT BETWEEN -180 AND 180
        """
    )
    op.execute(
        """
        UPDATE telemetry
        SET latitude = NULL
        WHERE latitude NOT BETWEEN -90 AND 90
        """
    )
    op.execute(
        """
        UPDATE telemetry
        SET longitude = NULL
        WHERE longitude NOT BETWEEN -180 AND 180
        """
    )
    op.execute("UPDATE telemetry SET velocity = NULL WHERE velocity < 0")
    op.execute(
        """
        UPDATE telemetry
        SET heading = NULL
        WHERE heading < 0 OR heading >= 360
        """
    )
    op.execute(
        """
        UPDATE coverage_results
        SET coverage_percent = NULL
        WHERE coverage_percent NOT BETWEEN 0 AND 100
        """
    )

    op.create_check_constraint(
        "ck_missions_status",
        "missions",
        "status IN ('planned', 'in_progress', 'completed', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_missions_date_order",
        "missions",
        "ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at",
    )
    op.create_check_constraint(
        "ck_chat_histories_role",
        "chat_histories",
        "role IN ('user', 'assistant', 'system', 'tool')",
    )
    op.create_check_constraint(
        "ck_flight_paths_total_distance",
        "flight_paths",
        "total_distance_m IS NULL OR total_distance_m >= 0",
    )
    op.create_check_constraint(
        "ck_flight_paths_estimated_duration",
        "flight_paths",
        "estimated_duration_s IS NULL OR estimated_duration_s >= 0",
    )
    op.create_check_constraint(
        "ck_iot_nodes_latitude",
        "iot_nodes",
        "latitude IS NULL OR latitude BETWEEN -90 AND 90",
    )
    op.create_check_constraint(
        "ck_iot_nodes_longitude",
        "iot_nodes",
        "longitude IS NULL OR longitude BETWEEN -180 AND 180",
    )
    op.create_check_constraint(
        "ck_telemetry_latitude",
        "telemetry",
        "latitude IS NULL OR latitude BETWEEN -90 AND 90",
    )
    op.create_check_constraint(
        "ck_telemetry_longitude",
        "telemetry",
        "longitude IS NULL OR longitude BETWEEN -180 AND 180",
    )
    op.create_check_constraint(
        "ck_telemetry_velocity",
        "telemetry",
        "velocity IS NULL OR velocity >= 0",
    )
    op.create_check_constraint(
        "ck_telemetry_heading",
        "telemetry",
        "heading IS NULL OR (heading >= 0 AND heading < 360)",
    )
    op.create_check_constraint(
        "ck_coverage_results_percent",
        "coverage_results",
        "coverage_percent IS NULL OR coverage_percent BETWEEN 0 AND 100",
    )

    op.create_index(
        op.f("ix_chat_histories_mission_id"),
        "chat_histories",
        ["mission_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_histories_mission_id_timestamp",
        "chat_histories",
        ["mission_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_histories_user_id"),
        "chat_histories",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_coverage_results_flight_path_id"),
        "coverage_results",
        ["flight_path_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_coverage_results_mission_id"),
        "coverage_results",
        ["mission_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_flight_paths_mission_id"),
        "flight_paths",
        ["mission_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_iot_nodes_mission_id"),
        "iot_nodes",
        ["mission_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_missions_owner_id"),
        "missions",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reports_author_id"),
        "reports",
        ["author_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reports_mission_id"),
        "reports",
        ["mission_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_telemetry_iot_node_id"),
        "telemetry",
        ["iot_node_id"],
        unique=False,
    )
    op.create_index(
        "ix_telemetry_iot_node_id_timestamp",
        "telemetry",
        ["iot_node_id", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_telemetry_iot_node_id_timestamp", table_name="telemetry")
    op.drop_index(op.f("ix_telemetry_iot_node_id"), table_name="telemetry")
    op.drop_index(op.f("ix_reports_mission_id"), table_name="reports")
    op.drop_index(op.f("ix_reports_author_id"), table_name="reports")
    op.drop_index(op.f("ix_missions_owner_id"), table_name="missions")
    op.drop_index(op.f("ix_iot_nodes_mission_id"), table_name="iot_nodes")
    op.drop_index(op.f("ix_flight_paths_mission_id"), table_name="flight_paths")
    op.drop_index(op.f("ix_coverage_results_mission_id"), table_name="coverage_results")
    op.drop_index(
        op.f("ix_coverage_results_flight_path_id"),
        table_name="coverage_results",
    )
    op.drop_index(op.f("ix_chat_histories_user_id"), table_name="chat_histories")
    op.drop_index(
        "ix_chat_histories_mission_id_timestamp",
        table_name="chat_histories",
    )
    op.drop_index(op.f("ix_chat_histories_mission_id"), table_name="chat_histories")

    op.drop_constraint(
        "ck_coverage_results_percent",
        "coverage_results",
        type_="check",
    )
    op.drop_constraint("ck_telemetry_heading", "telemetry", type_="check")
    op.drop_constraint("ck_telemetry_velocity", "telemetry", type_="check")
    op.drop_constraint("ck_telemetry_longitude", "telemetry", type_="check")
    op.drop_constraint("ck_telemetry_latitude", "telemetry", type_="check")
    op.drop_constraint("ck_iot_nodes_longitude", "iot_nodes", type_="check")
    op.drop_constraint("ck_iot_nodes_latitude", "iot_nodes", type_="check")
    op.drop_constraint(
        "ck_flight_paths_estimated_duration",
        "flight_paths",
        type_="check",
    )
    op.drop_constraint(
        "ck_flight_paths_total_distance",
        "flight_paths",
        type_="check",
    )
    op.drop_constraint("ck_chat_histories_role", "chat_histories", type_="check")
    op.drop_constraint("ck_missions_date_order", "missions", type_="check")
    op.drop_constraint("ck_missions_status", "missions", type_="check")
