"""Aim line and goal status (Stage 11). Pure functions - no database access.

Aim line: a straight line from the baseline (at the goal's start date) to the
target (at the target date). A goal is "below aim" when the median of its last
three data points is on the wrong side of that line on the latest point's date.
If the target is lower than the baseline, the goal is a DECREASE goal (e.g.
fewer call-outs), and "wrong side" means above the line.
"""

from dataclasses import dataclass
from datetime import date
from statistics import median

RECENT_DAYS = 30  # no data for longer than this -> "no recent data"
MEDIAN_OF = 3

# Severity order for sorting attention lists (most urgent first).
SEVERITY = {"below_aim": 0, "no_recent_data": 1, "no_data": 2, "no_baseline": 3,
            "on_track": 4, "not_started": 5, "met": 6}
ATTENTION = ("below_aim", "no_recent_data", "no_data", "no_baseline")


@dataclass(frozen=True)
class Point:
    on: date
    value: float


@dataclass
class GoalStatus:
    status: str
    latest: float | None = None
    expected: float | None = None
    gap: float | None = None  # how far behind the aim line (positive = behind)
    last_recorded_on: date | None = None
    decreasing: bool = False


def is_decreasing(baseline: float | None, target: float | None) -> bool:
    return baseline is not None and target is not None and target < baseline


def aim_value(baseline: float, target: float, start: date, end: date, on: date) -> float:
    """Expected value on a date; clamped to the goal period."""
    if end <= start:
        return target
    if on <= start:
        return baseline
    if on >= end:
        return target
    fraction = (on - start).days / (end - start).days
    return baseline + (target - baseline) * fraction


def goal_status(
    *,
    baseline: float | None,
    target: float | None,
    start: date | None,
    end: date | None,
    points: list[Point],
    today: date,
) -> GoalStatus:
    points = sorted(points, key=lambda p: p.on)
    decreasing = is_decreasing(baseline, target)
    latest = points[-1] if points else None
    result = GoalStatus(
        status="on_track",
        latest=latest.value if latest else None,
        last_recorded_on=latest.on if latest else None,
        decreasing=decreasing,
    )

    if baseline is None or target is None or start is None or end is None:
        result.status = "no_baseline"
        return result
    if latest is None:
        result.status = "no_data" if (today - start).days > RECENT_DAYS else "not_started"
        return result

    expected = aim_value(baseline, target, start, end, latest.on)
    recent = median(p.value for p in points[-MEDIAN_OF:])
    result.expected = round(expected, 2)
    result.gap = round((recent - expected) if decreasing else (expected - recent), 2)

    reached = latest.value <= target if decreasing else latest.value >= target
    if reached:
        result.status = "met"
    elif (today - latest.on).days > RECENT_DAYS:
        result.status = "no_recent_data"
    elif result.gap > 0:
        result.status = "below_aim"
    else:
        result.status = "on_track"
    return result
