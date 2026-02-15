"""Unit tests for resolution parsing utility."""

import pytest

from app.camera import parse_resolution


def test_parse_resolution_valid():
    assert parse_resolution("640x480") == (640, 480)


@pytest.mark.parametrize(
    "resolution",
    ["", "640", "x480", "640-480", "640x-1", "abcx123"],
)
def test_parse_resolution_invalid(resolution):
    with pytest.raises(ValueError):
        parse_resolution(resolution)




