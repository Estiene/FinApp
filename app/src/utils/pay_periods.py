import calendar
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

def generate_pay_periods(
    first_pay_date: date,
    frequency: str,
    semimonthly_days: tuple[int, int] | None = None,
    horizon_months: int = 12
) -> list[tuple[date, date]]:
    """
    Returns a list of (start, end) tuples for each pay period,
    beginning at first_pay_date and extending horizon_months into the future.

    frequency:
      - 'weekly'
      - 'biweekly'
      - 'monthly'
      - 'twice_monthly'  (requires semimonthly_days)

    semimonthly_days: (day1, day2) for twice_monthly
    """
    periods: list[tuple[date, date]] = []

    if frequency in ('weekly', 'biweekly'):
        step = timedelta(weeks=1 if frequency == 'weekly' else 2)
        current = first_pay_date
        end_horizon = first_pay_date + relativedelta(months=horizon_months)

        # Build spans between pay dates
        while current <= end_horizon:
            prev = current - step
            periods.append((prev, current))
            current += step

    elif frequency == 'monthly':
        current = first_pay_date
        for _ in range(horizon_months):
            start = current.replace(day=1)
            last_day = calendar.monthrange(current.year, current.month)[1]
            end   = current.replace(day=last_day)
            periods.append((start, end))
            current += relativedelta(months=1)

    elif frequency == 'twice_monthly':
        if not semimonthly_days or len(semimonthly_days) != 2:
            raise ValueError("Provide semimonthly_days=(day1, day2) for twice_monthly")
        d1, d2 = semimonthly_days

        for m in range(horizon_months):
            base = first_pay_date + relativedelta(months=m)
            y, mo = base.year, base.month
            last = calendar.monthrange(y, mo)[1]
            a = min(d1, last)
            b = min(d2, last)

            # first half: from month start up to day a
            periods.append((date(y, mo, 1), date(y, mo, a)))
            # second half: from day a up to day b
            periods.append((date(y, mo, a), date(y, mo, b)))

    else:
        raise ValueError(f"Unsupported frequency: {frequency}")

    # ensure chronological order
    periods.sort(key=lambda span: span[0])
    return periods
