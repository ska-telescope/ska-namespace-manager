import base64
import binascii
import datetime

import pytest
import pytz

from ska_ser_namespace_manager.core.utils import (
    decode_slack_address,
    encode_slack_address,
    format_utc,
    parse_timedelta,
    utc,
)


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


def test_format_utc():
    assert (
        format_utc(datetime.datetime(2022, 5, 21, 12, 34, 56, tzinfo=pytz.UTC))
        == "2022-05-21T12:34:56Z"
    )
    assert (
        format_utc(datetime.datetime(2022, 5, 21, 12, 34, 56))
        == "2022-05-21T12:34:56Z"
    )


def test_utc():
    assert utc().endswith("Z")


def test_encode_slack_address():
    name = "John Doe"
    slack_id = "U1234567890"
    encoded = encode_slack_address(name, slack_id)
    expected = base64.b64encode(f"{name}::{slack_id}".encode("utf-8")).decode(
        "utf-8"
    )
    assert encoded == expected


def test_decode_slack_address():
    name = "Jane Doe"
    slack_id = "U0987654321"
    address = encode_slack_address(name, slack_id)
    decoded_name, decoded_slack_id = decode_slack_address(address)
    assert decoded_name == name
    assert decoded_slack_id == slack_id
    assert decode_slack_address("") == (None, None)


def test_decode_slack_address_invalid():
    with pytest.raises((binascii.Error, UnicodeDecodeError)):
        decode_slack_address("asdasdasdasd")
        decode_slack_address("encoded_user")
