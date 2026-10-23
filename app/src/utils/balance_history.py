"""Explicit, immutable forecast captures and chart geometry for saved history."""
from datetime import timedelta
from types import SimpleNamespace
from .dashboard import build_dashboard_data
from .cash_flow_projection import daily_account_projection
from ..models import AccountForecastSnapshot, AccountForecastPoint


def capture_forecast(account, cards, today, horizon):
    if horizon not in (30, 90, 180):
        raise ValueError('Choose a 30, 90 or 180 day forecast.')
    summary = build_dashboard_data([account], today=today, credit_cards=cards)['account_summaries'][0]
    balance = summary['projected_balance']
    forecast = AccountForecastSnapshot(account_id=account.id, base_date=today,
        base_balance=balance, horizon_days=horizon, early_pay_days=account.early_pay_days or 0)
    # Match Dashboard: anchor future projections at today's displayed balance,
    # rather than replaying old planned card payments from an actual snapshot.
    anchor = SimpleNamespace(id=account.id, starting_balance=balance,
        balance_as_of=today, incomes=account.incomes, bills=account.bills)
    forecast.points.append(AccountForecastPoint(balance_date=today, balance=balance))
    for row in daily_account_projection(anchor, today, today + timedelta(days=horizon), cards):
        forecast.points.append(AccountForecastPoint(balance_date=row['date'], balance=row['balance']))
    return forecast


def chart_geometry(observations, snapshots, start, end):
    values = [float(o.balance) for o in observations]
    visible = [[p for p in s.points if start <= p.balance_date <= end] for s in snapshots]
    values += [float(p.balance) for points in visible for p in points]
    if not values:
        return None
    low, high = min(values), max(values)
    padding = max((high - low) * .1, 1)
    low, high = low - padding, high + padding
    def point(day, amount):
        return dict(x=round(90 + (day - start).days / max((end - start).days, 1) * 850, 2),
                    y=round(300 - (float(amount) - low) / (high - low) * 270, 2),
                    date=day, balance=amount)
    colors = ['#2563eb', '#9333ea', '#b45309']
    forecasts = []
    for index, (snapshot, points) in enumerate(zip(snapshots, visible)):
        coordinates = [point(p.balance_date, p.balance) for p in points]
        forecasts.append(dict(snapshot=snapshot, color=colors[index], points=coordinates,
            path=' '.join(f"{p['x']},{p['y']}" for p in coordinates)))
    return dict(actual=[point(o.balance_date, o.balance) for o in observations], forecasts=forecasts,
                ticks=[dict(y=300 - i * 67.5, value=low + i * (high-low)/4) for i in range(5)])
