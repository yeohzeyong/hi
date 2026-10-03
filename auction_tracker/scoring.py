"""Score and grade one auction listing as an investment."""

from __future__ import annotations

from datetime import date

from . import finance

GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1, "?": 0}


def _lerp(x, x0, x1, y0, y1):
    if x is None:
        return None
    if x <= x0:
        return y0
    if x >= x1:
        return y1
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def matched_area(text: str, areas: dict) -> str | None:
    t = (text or "").lower()
    for label, kws in areas.items():
        if any(k.lower() in t for k in kws):
            return label
    return None


def is_residential_type(ptype: str, title: str, allowed: list[str]) -> bool:
    t = f"{ptype} {title}".lower()
    return any(a in t for a in allowed)


def evaluate(lst: dict, sale: dict | None, rent: dict | None, station: dict | None,
             unit_hist: dict, bstats: dict | None, override: dict, cfg: dict) -> dict:
    fin_cfg = {**cfg["finance"]}
    if override.get("maintenance_psf"):
        fin_cfg["maintenance_psf"] = override["maintenance_psf"]
    targets = cfg["targets"]
    tcfg = cfg["transit"]
    sqft = lst.get("built_up")
    price = lst.get("reserve_price")
    pros, cons, notes = [], [], []

    # ---- eligibility --------------------------------------------------
    status = "ok"
    if not price or not sqft:
        status = "incomplete"
        cons.append("Missing reserve price or built-up - check listing manually")
    elif sqft < cfg["search"]["min_built_up_sqft"]:
        status = "too_small"
    if lst.get("auction_date") and lst["auction_date"] < date.today().isoformat():
        status = "past"
    if cfg["scoring"].get("exclude_bumi_lot") and lst.get("bumi"):
        status = "excluded_bumi"

    # ---- market value & rent -----------------------------------------
    market_value = None
    if override.get("market_psf") and sqft:
        market_value = override["market_psf"] * sqft
        notes.append("Market value from your override")
    elif sale and sale.get("estimate"):
        market_value = sale["estimate"]
    rent_est = None
    if override.get("rent"):
        rent_est = override["rent"]
        notes.append("Rent from your override")
    elif rent and rent.get("estimate"):
        rent_est = rent["estimate"]
        if lst.get("dual_key") and rent.get("dual_key_share", 0) < 0.5:
            rent_est *= 1 + fin_cfg.get("dual_key_rent_premium", 0)
            notes.append("Dual-key premium applied to rent")

    fin = finance.analyse(price, sqft, rent_est, fin_cfg, market_value) if price and sqft else {}
    bid = finance.max_bid(sqft, rent_est, market_value, fin_cfg, targets) if sqft else {"max_bid": None}

    # ---- component scores (max points in brackets) --------------------
    parts = {}
    cover = fin.get("rent_cover")
    parts["cashflow"] = _lerp(cover, 0.75, 1.25, 0, 30)                       # [30]
    disc = fin.get("discount")
    parts["discount"] = _lerp(disc, 0.0, 0.35, 0, 25)                         # [25]
    walk = station["walk_m"] if station else None
    parts["transit"] = (_lerp(-walk, -1500, -tcfg["good_walk_m"], 0, 15)      # [15]
                        if walk is not None else 5)
    liq = 0.0                                                                 # [15]
    if rent:
        liq += min(rent["n"], 10) / 10 * 7
    if sqft:
        liq += 5 if sqft <= 1300 else 3 if sqft <= 1600 else 1
    if walk is not None and walk <= tcfg["ok_walk_m"]:
        liq += 3
    parts["rentability"] = liq
    parts["dual_key"] = 5 if lst.get("dual_key") else 0                       # [5]
    hist = 0.0                                                                # [10]
    rounds = unit_hist.get("rounds", 1)
    hist += min(rounds - 1, 3) * 2
    if bstats:
        if bstats.get("last_12m", 0) >= 6:
            hist -= 3
            cons.append(f"{bstats['last_12m']} auctions in this building in 12 months - possible distress/oversupply")
        if bstats.get("sold_psf") and price and sqft and price / sqft <= bstats["sold_psf"]:
            hist += 4
            pros.append(f"Reserve psf at/below past auction sale psf (RM{bstats['sold_psf']})")
    parts["history"] = max(-5.0, min(hist, 10.0))
    score = round(sum(v for v in parts.values() if v is not None), 1)

    # ---- explanation ---------------------------------------------------
    if cover is not None:
        (pros if cover >= targets["min_rent_cover"] else cons).append(
            f"Rent RM{fin['rent']:,} vs installment+maintenance RM{fin['monthly_cost']:,} -> {cover:.2f}x cover")
    else:
        cons.append("No reliable rent data yet")
    if disc is not None:
        (pros if disc >= targets["min_discount"] else cons).append(f"{disc:.0%} below cleaned market value")
    else:
        cons.append("No reliable sale comps yet")
    if station:
        msg = f"{station['walk_m']} m (~{station['walk_min']} min) to {station['type']} {station['name']}"
        (pros if walk <= tcfg["ok_walk_m"] else cons).append(msg)
    else:
        notes.append("Location not geocoded - add lat/lon override")
    if lst.get("dual_key"):
        pros.append("Dual-key layout")
    if rounds > 1:
        pros.append(f"Round {rounds}: reserve cut {unit_hist['cut_from_first']:.0%} from first auction")
    for f in lst.get("flags", []):
        cons.append(f)
    if bid.get("max_bid") is not None and price:
        if bid["max_bid"] < price:
            cons.append(f"Walk-away price RM{bid['max_bid']:,} is BELOW reserve - targets not met at reserve")
        else:
            pros.append(f"Headroom to bid up to RM{bid['max_bid']:,} ({bid['binding']}-limited)")

    # ---- grade -----------------------------------------------------------
    low_conf = not (sale and sale.get("confident")) or not (rent and rent.get("confident"))
    if override.get("market_psf") and override.get("rent"):
        low_conf = False
    if market_value is None and rent_est is None:
        grade = "?"
    elif (score >= 70 and cover and cover >= targets["min_rent_cover"]
          and disc is not None and disc >= targets["min_discount"]
          and (walk is None or walk <= tcfg["max_walk_m"])):
        grade = "A"
    elif score >= 55:
        grade = "B"
    elif score >= 40:
        grade = "C"
    else:
        grade = "D"
    if grade == "A" and (low_conf or lst.get("bumi") or lst.get("title_type") == "Master title"):
        grade = "B"
        notes.append("Capped at B: low data confidence or title/bumi issue - verify manually")
    if override.get("exclude"):
        status = "excluded_by_you"

    return {
        "status": status, "grade": grade, "score": score, "parts": {k: (round(v, 1) if v is not None else None)
                                                                     for k, v in parts.items()},
        "market_value": round(market_value) if market_value else None,
        "rent_estimate": round(rent_est) if rent_est else None,
        "sale_comps": sale, "rent_comps": rent, "station": station,
        "finance": fin, "max_bid": bid, "unit_history": unit_hist, "building_stats": bstats,
        "low_confidence": low_conf, "pros": pros, "cons": cons, "notes": notes,
    }
