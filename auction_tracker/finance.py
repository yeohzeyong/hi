"""Malaysian auction purchase maths: costs, installment, cash flow, max bid."""

from __future__ import annotations


def monthly_installment(principal: float, annual_rate: float, years: int) -> float:
    if principal <= 0:
        return 0.0
    r, n = annual_rate / 12, years * 12
    if r == 0:
        return principal / n
    return principal * r / (1 - (1 + r) ** -n)


def _tiered(amount: float, tiers: list[tuple[float, float]]) -> float:
    """tiers: [(band_size, rate), ...] - last band_size may be float('inf')."""
    total, remaining = 0.0, amount
    for size, rate in tiers:
        take = min(remaining, size)
        total += take * rate
        remaining -= take
        if remaining <= 0:
            break
    return total


def stamp_duty_transfer(price: float) -> float:
    """Memorandum of Transfer stamp duty (Stamp Act 1949, rates from 2024)."""
    return _tiered(price, [(100_000, 0.01), (400_000, 0.02), (500_000, 0.03), (float("inf"), 0.04)])


def stamp_duty_loan(loan: float) -> float:
    return loan * 0.005


def legal_fee(amount: float) -> float:
    """Solicitors' Remuneration Order 2023 scale (approx.), min RM500."""
    return max(500.0, _tiered(amount, [(500_000, 0.0125), (7_000_000, 0.01), (float("inf"), 0.01)]))


def analyse(price: float, built_up: float, monthly_rent: float | None, fin: dict,
            market_value: float | None = None) -> dict:
    """Full cost / cash-flow picture for buying at ``price``."""
    loan = price * fin["loan_margin"]
    inst = monthly_installment(loan, fin["interest_rate"], fin["tenure_years"])
    maint = built_up * fin["maintenance_psf"]
    other = fin.get("other_monthly", 0)
    monthly_cost = inst + maint + other

    upfront = {
        "downpayment": price - loan,
        "stamp_duty_transfer": stamp_duty_transfer(price),
        "stamp_duty_loan": stamp_duty_loan(loan),
        "legal_fees": legal_fee(price) + legal_fee(loan),
        "valuation_fee": fin.get("valuation_fee", 0),
        "misc_fees": fin.get("misc_fees", 0),
        "repair_buffer": built_up * fin.get("repair_buffer_psf", 0),
        "arrears_buffer": maint * fin.get("arrears_buffer_months", 0),
    }
    cash_in = sum(upfront.values())
    all_in_cost = price + cash_in - upfront["downpayment"]

    out = {
        "price": round(price),
        "loan": round(loan),
        "installment": round(inst),
        "maintenance": round(maint),
        "other_monthly": round(other),
        "monthly_cost": round(monthly_cost),
        "upfront": {k: round(v) for k, v in upfront.items()},
        "cash_needed": round(cash_in),
        "deposit_on_auction_day": round(price * 0.10),
        "all_in_cost": round(all_in_cost),
        "price_psf": round(price / built_up, 1) if built_up else None,
    }
    if monthly_rent:
        vacancy = fin.get("vacancy_months_per_year", 1) / 12
        eff_rent = monthly_rent * (1 - vacancy)
        out.update({
            "rent": round(monthly_rent),
            "effective_rent": round(eff_rent),
            "rent_cover": round(monthly_rent / monthly_cost, 2),
            "rent_cover_after_vacancy": round(eff_rent / monthly_cost, 2),
            "monthly_cashflow": round(eff_rent - monthly_cost),
            "gross_yield": round(monthly_rent * 12 / all_in_cost, 4),
            "net_yield": round((eff_rent - maint - other) * 12 / all_in_cost, 4),
            "cash_on_cash": round((eff_rent - monthly_cost) * 12 / cash_in, 4) if cash_in else None,
        })
    if market_value:
        out["discount"] = round(1 - price / market_value, 4)
        out["discount_after_buffers"] = round(1 - all_in_cost / market_value, 4)
    return out


def max_bid(built_up: float, monthly_rent: float | None, market_value: float | None,
            fin: dict, targets: dict) -> dict:
    """Walk-away price: the highest bid that still meets BOTH targets.

    * cash-flow: rent covers installment + maintenance + other x min_rent_cover
    * discount : price <= market value x (1 - min_discount) - repair buffer
    """
    k = monthly_installment(1.0, fin["interest_rate"], fin["tenure_years"]) * fin["loan_margin"]
    fixed = built_up * fin["maintenance_psf"] + fin.get("other_monthly", 0)
    caps = {}
    if monthly_rent:
        caps["cashflow"] = max(0.0, (monthly_rent / targets.get("min_rent_cover", 1.0) - fixed) / k)
    if market_value:
        caps["discount"] = max(0.0, market_value * (1 - targets.get("min_discount", 0.2))
                               - built_up * fin.get("repair_buffer_psf", 0))
    if not caps:
        return {"max_bid": None, "binding": None, "caps": {}}
    inc = targets.get("bid_increment", 1000)
    binding = min(caps, key=caps.get)
    value = int(caps[binding] // inc * inc)
    return {"max_bid": value, "binding": binding, "caps": {k2: round(v) for k2, v in caps.items()}}
