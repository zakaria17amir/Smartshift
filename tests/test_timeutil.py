from datetime import date, datetime

import pytest

from timeutil import (
    fmt_date,
    fmt_date_long,
    fmt_time,
    hours,
    overlaps,
    parse_date,
    parse_time,
    shift_week,
    week_days,
    week_monday,
)


def test_parse_time_variants():
    assert [parse_time(s) for s in ["9:00", "09:00", "9.00", "14:30", " 9:00 "]] == [540, 540, 540, 870, 540]


def test_parse_time_rejects():
    with pytest.raises(ValueError, match="should look like 09:00"):
        parse_time("9h")


def test_parse_time_rejects_out_of_range():
    with pytest.raises(ValueError, match="should look like 09:00"):
        parse_time("24:00")
    with pytest.raises(ValueError, match="should look like 09:00"):
        parse_time("9:60")


def test_fmt_time():
    assert fmt_time(540) == "09:00" and fmt_time(0) == "00:00"
    assert fmt_time(570) == "09:30"
    assert fmt_time(parse_time("14:30")) == "14:30"


def test_parse_date_variants():
    assert {parse_date(s) for s in ["2026-10-20", "20.10.2026", "2026.10.20.", "20/10/2026", "10/20/2026"]} == {"2026-10-20"}


def test_parse_date_objects():
    assert parse_date(date(2026, 10, 20)) == "2026-10-20"
    assert parse_date(datetime(2026, 10, 20, 9, 30)) == "2026-10-20"


def test_parse_date_rejects():
    with pytest.raises(ValueError, match="should look like 2026-10-20"):
        parse_date("next tuesday")
    with pytest.raises(ValueError, match="should look like 2026-10-20"):
        parse_date("2026-02-30")


def test_fmt_date():
    assert fmt_date("2026-10-20") == "Tue 20 Oct"
    assert fmt_date_long("2026-10-20") == "Tuesday 20 October 2026"


def test_week_helpers():
    assert week_monday("2026-10-22") == "2026-10-19"
    assert week_monday("2026-10-19") == "2026-10-19"
    assert week_days("2026-10-19")[6] == "2026-10-25"
    assert len(week_days("2026-10-19")) == 7
    assert shift_week("2026-10-19", -1) == "2026-10-12"
    assert shift_week("2026-10-19", 2) == "2026-11-02"


def test_overlaps_half_open():
    assert overlaps(540, 660, 660, 720) is False and overlaps(540, 660, 600, 720) is True


def test_hours():
    assert hours(540, 630) == 1.5
