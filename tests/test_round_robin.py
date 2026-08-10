"""Sanity check for measurement()'s round-robin scheduling: the threshold
decision and the interleaving/budget math, both pure and hardware-free."""
import builtins
from measurement import _ask_duration, _format_duration, _round_robin_plan, _should_round_robin


def test_format_duration():
    assert _format_duration(0) == "0h 0m 0s"
    assert _format_duration(3661) == "1h 1m 1s"


def test_should_round_robin_threshold():
    assert _should_round_robin(None, 5) is False          # streaming: no budget to split
    assert _should_round_robin(1200, 1) is False           # single setting: nothing to interleave
    assert _should_round_robin(1200, 3) is False            # 3600 s total: at, not over, threshold
    assert _should_round_robin(1260, 3) is True             # 3780 s total: over threshold


def test_round_robin_plan_cycles_and_sums_to_total():
    settings = [(0, None), (1, None), (2, None)]
    total, bin_s = 1200, 500  # doesn't divide evenly -> exercises the final short chunk
    plan = list(_round_robin_plan(settings, total, bin_s))

    order = [(j, b) for j, b, _ in plan[:3]]
    assert order == settings, "first pass should visit every setting once, in order"

    totals = {}
    for j, b, chunk in plan:
        totals[(j, b)] = totals.get((j, b), 0) + chunk
    assert totals == {s: total for s in settings}


def test_ask_duration_default_and_stream():
    """Enter alone -> 20 min default; 0 -> stream until Ctrl-C (None); a
    number -> that many minutes, in seconds."""
    original_input = builtins.input
    try:
        for reply, expected in [("", 20 * 60), ("0", None), ("5", 300)]:
            builtins.input = lambda _prompt, reply=reply: reply
            assert _ask_duration() == expected
    finally:
        builtins.input = original_input


if __name__ == "__main__":
    test_format_duration()
    test_should_round_robin_threshold()
    test_round_robin_plan_cycles_and_sums_to_total()
    test_ask_duration_default_and_stream()
    print("ok")
