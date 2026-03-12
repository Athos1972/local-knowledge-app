from common.time_utils import format_duration_human


def test_format_duration_human_values() -> None:
    assert format_duration_human(0) == "0s"
    assert format_duration_human(59.4) == "59s"
    assert format_duration_human(61) == "1m 1s"
    assert format_duration_human(3661) == "1h 1m 1s"
    assert format_duration_human(90061) == "1d 1h 1m 1s"
