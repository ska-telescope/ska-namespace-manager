from ska_ser_namespace_manager.core.utils import parse_timedelta


def test_parse_timedelta():
    assert 0.5 == parse_timedelta("0.5s").total_seconds()
    assert 30 == parse_timedelta("30s").total_seconds()
    assert 30 == parse_timedelta("0.5m").total_seconds()
    assert 77 == parse_timedelta("1m17s").total_seconds()
    assert 3658 == parse_timedelta("1h58s").total_seconds()
    assert 3658 == parse_timedelta("1h58s").total_seconds()
    assert 86400 * 2 == parse_timedelta("2d").total_seconds()
    assert (
        86400 * 5 + 60 * 60 * 3 + 60 * 28 + 5
        == parse_timedelta("5d3h28m5s").total_seconds()
    )
