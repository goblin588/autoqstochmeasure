"""Boundary checks for the provisional 5am-7:30am overnight blackout window
(settings.BLACKOUT_START/BLACKOUT_END)."""
import datetime

from libraries.settings import in_blackout_window


def _at(hour, minute=0):
    return datetime.datetime(2026, 11, 19, hour, minute)


def test_just_before_start_is_not_blackout():
    assert not in_blackout_window(_at(4, 59))

def test_at_start_is_blackout():
    assert in_blackout_window(_at(5, 0))

def test_inside_window_is_blackout():
    assert in_blackout_window(_at(6, 30))

def test_just_before_end_is_blackout():
    assert in_blackout_window(_at(7, 29))

def test_at_end_is_not_blackout():
    assert not in_blackout_window(_at(7, 30))

def test_just_after_end_is_not_blackout():
    assert not in_blackout_window(_at(7, 31))
