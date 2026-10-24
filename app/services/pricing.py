"""What a stay at a rental costs, night by night.

Each night is priced by the rate period that covers it (its price per night),
or by the property's own price. The minimum stay is the property's, or the
check-in night's rate period's if that asks for more. Then two discounts,
one after the other:
- for the length of the stay: monthly from 28 nights, else weekly from 7;
- for the timing of the booking: last minute when check-in is close, or early
  bird when it's far ahead (if both apply, the larger).
"""
from datetime import date, timedelta

from app.models import AvailabilityBlock, Property, RatePeriod

MAX_NIGHTS = 365


class PricingError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _round(value: float) -> float:
    return round(value + 1e-9, 2)


def quote(prop: Property, start: date, end: date, today: date | None = None) -> dict:
    today = today or date.today()
    nights = (end - start).days
    if nights < 1 or nights > MAX_NIGHTS:
        raise PricingError("Invalid date", 400)

    periods = RatePeriod.query.filter(
        RatePeriod.property_id == prop.id, RatePeriod.start_date <= end, RatePeriod.end_date >= start
    ).all()

    def period_for(night: date):
        return next((period for period in periods if period.start_date <= night <= period.end_date), None)

    # Consecutive nights at the same price and period make one line.
    lines: list[dict] = []
    missing = False
    for offset in range(nights):
        night = start + timedelta(days=offset)
        period = period_for(night)
        price = period.official_price_per_night if period and period.official_price_per_night is not None else prop.price
        if price is None:
            missing = True
        label = period.label if period else None
        last = lines[-1] if lines else None
        if last and last["price"] == price and last["label"] == label:
            last["nights"] += 1
        else:
            lines.append({"label": label, "price": price, "nights": 1})
    for line in lines:
        line["amount"] = _round(line["price"] * line["nights"]) if line["price"] is not None else None

    check_in_period = period_for(start)
    min_stay = max(prop.min_stay or 1, (check_in_period.min_stay if check_in_period else None) or 1)

    discounts = []
    subtotal = None if missing else _round(sum(line["amount"] for line in lines))
    if subtotal is not None:
        running = subtotal
        if nights >= 28 and prop.monthly_discount_pct:
            discounts.append({"kind": "MONTHLY", "pct": prop.monthly_discount_pct})
        elif nights >= 7 and prop.weekly_discount_pct:
            discounts.append({"kind": "WEEKLY", "pct": prop.weekly_discount_pct})

        ahead = (start - today).days
        timing = []
        if prop.last_minute_discount_pct and prop.last_minute_days and 0 <= ahead <= prop.last_minute_days:
            timing.append({"kind": "LAST_MINUTE", "pct": prop.last_minute_discount_pct})
        if prop.early_bird_discount_pct and prop.early_bird_days and ahead >= prop.early_bird_days:
            timing.append({"kind": "EARLY_BIRD", "pct": prop.early_bird_discount_pct})
        if timing:
            discounts.append(max(timing, key=lambda item: item["pct"]))

        for discount in discounts:
            discount["amount"] = _round(running * discount["pct"] / 100)
            running = _round(running - discount["amount"])
        total = running
    else:
        total = None

    blocked = AvailabilityBlock.query.filter(
        AvailabilityBlock.property_id == prop.id,
        AvailabilityBlock.start_date < end,
        AvailabilityBlock.end_date > start,
    ).first()

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "nights": nights,
        "currency": prop.currency,
        "lines": lines,
        "subtotal": subtotal,
        "discounts": discounts,
        "total": total,
        "minStay": min_stay,
        "meetsMinStay": nights >= min_stay,
        "available": blocked is None,
    }


def parse_range(start: str | None, end: str | None) -> tuple[date, date]:
    try:
        return date.fromisoformat(start or ""), date.fromisoformat(end or "")
    except ValueError as err:
        raise PricingError("Invalid date", 400) from err
