from datetime import date

from gsc_client import gsc_reporting_period


def test_gsc_period_monday():
    start, end = gsc_reporting_period(date(2026, 10, 5))
    assert start == date(2026, 9, 26)
    assert end == date(2026, 10, 2)


def test_gsc_period_tuesday():
    start, end = gsc_reporting_period(date(2026, 10, 6))
    assert start == date(2026, 9, 27)
    assert end == date(2026, 10, 3)


def test_gsc_period_wednesday():
    start, end = gsc_reporting_period(date(2026, 10, 7))
    assert start == date(2026, 9, 28)
    assert end == date(2026, 10, 4)


def test_gsc_period_sunday_stays_previous_week():
    start, end = gsc_reporting_period(date(2026, 10, 11))
    assert start == date(2026, 9, 28)
    assert end == date(2026, 10, 4)
