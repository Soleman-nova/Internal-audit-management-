"""Shared date helpers.

Calendar-month bucketing shows up in both the dashboard and the report
analytics endpoint, and both had (or would have grown) their own copy. It is
easy to get wrong in the same way twice, so it lives here once.
"""
import datetime


def month_starts(today, count):
    """The first day of each of the last ``count`` calendar months, oldest first.

    Calendar arithmetic, not 30-day steps — stepping back by ``30 * i`` days
    skips February entirely and double-counts 31-day months, so a "last six
    months" chart silently loses and duplicates buckets.
    """
    starts = []
    year, month = today.year, today.month
    for _ in range(count):
        starts.append(datetime.date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    starts.reverse()
    return starts


def month_end(start):
    """The last day of the calendar month that ``start`` begins."""
    next_start = (
        datetime.date(start.year + 1, 1, 1) if start.month == 12
        else datetime.date(start.year, start.month + 1, 1)
    )
    return next_start - datetime.timedelta(days=1)
