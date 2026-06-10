from datetime import UTC, datetime, timedelta

from scripts.seed_demo import TELEMETRY_SAMPLE_COUNT, build_telemetry_samples


def test_build_telemetry_samples_creates_ordered_environment_data() -> None:
    end_time = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)

    samples = build_telemetry_samples(9, now=end_time)

    assert len(samples) == TELEMETRY_SAMPLE_COUNT
    assert samples[0].timestamp == end_time - timedelta(
        minutes=30 * (TELEMETRY_SAMPLE_COUNT - 1)
    )
    assert samples[-1].timestamp == end_time
    assert all(sample.iot_node_id == 9 for sample in samples)
    assert all(sample.temperature_celsius is not None for sample in samples)
    assert all(sample.humidity_percent is not None for sample in samples)
    assert samples[0].temperature_celsius != samples[-1].temperature_celsius
