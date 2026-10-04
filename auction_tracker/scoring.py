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


def rental_demand(sale, rent, ctx, sqft, walk, ok_walk) -> tuple[float, list[str], list[str]]:
    """[15] Will tenants want it? Building yield, how active its rental market
    is, rent vs the area, unit size, rail access."""
    pts, pros, cons = 0.0, [], []
    if sale and rent and sale.get("median_psf"):
        y = rent["median_psf"] * 12 / sale["median_psf"]
        pts += 6 if y >= 0.06 else 4 if y >= 0.05 else 2 if y >= 0.04 else 0
        (pros if y >= 0.05 else cons).append(f"Building rental yield ~{y:.1%} (rent vs asking price of similar units)")
    if rent:
        pts += 3 if rent["n"] >= 8 else 2 if rent["n"] >= 4 else 1
    a_rent = ctx.get("area_rent_psf")
    if rent and a_rent:
        rel = rent["median_psf"] / a_rent
        pts += 3 if rel >= 1.05 else 2 if rel >= 0.95 else 0
        if rel >= 1.05:
            pros.append(f"Rents {rel - 1:.0%} above similar units in the area - sought-after building")
        elif rel < 0.9:
            cons.append(f"Rents {1 - rel:.0%} below similar units in the area")
    elif rent:
        pts += 1
    if sqft:
        pts += 2 if 900 <= sqft <= 1300 else 1 if sqft <= 1600 else 0
    if walk is not None and walk <= ok_walk:
        pts += 1
    return min(pts, 15.0), pros, cons


def resale_potential(lst, sale, ctx) -> tuple[float, list[str], list[str]]:
    """[10] Can it sell higher later? Building age, tenure, priced below the
    area (catch-up room) and the building's own price trend."""
    pts, pros, cons = 0.0, [], []
    by = ctx.get("built_year")
    if by:
        age = date.today().year - by
        pts += 4 if age <= 5 else 3 if age <= 10 else 2 if age <= 15 else 1 if age <= 20 else 0
        (pros if age <= 10 else cons if age > 20 else []).append(f"Building completed {by} ({age} years old)")
    if "freehold" in (lst.get("tenure") or "").lower():
        pts += 2
    a_sale = ctx.get("area_sale_psf")
    if sale and a_sale:
        rel = sale["median_psf"] / a_sale
        pts += 2 if rel <= 0.9 else 1 if rel <= 1.0 else 0
        if rel <= 0.9:
            pros.append(f"Building trades {1 - rel:.0%} below similar units in the area - room to catch up")
    tr = ctx.get("trend")
    if tr:
        pts += 2 if tr["pct"] >= 0.03 else 1 if tr["pct"] >= 0 else 0
        (pros if tr["pct"] >= 0 else cons).append(
            f"Asking prices here {tr['pct']:+.0%} over the last {tr['days']} days (tracked)")
    return min(pts, 10.0), pros, cons


def evaluate(lst: dict, sale: dict | None, rent: dict | None, station: dict | None,
             unit_hist: dict, bstats: dict | None, override: dict, cfg: dict, ctx: dict | None = None) -> dict:
    ctx = ctx or {}
    fin_cfg = {**cfg["finance"]}
    if override.get("maintenance_psf"):
        fin_cfg["maintenance_psf"] = override["maintenance_psf"]
    if lst.get("occupied"):
        fin_cfg["misc_fees"] = fin_cfg.get("misc_fees", 0) + fin_cfg.get("occupied_buffer", 0)
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
    parts["transit"] = (_lerp(-walk, -1500, -tcfg["good_walk_m"], 0, 10)      # [10]
                        if walk is not None else 3)
    parts["rental_demand"], d_pros, d_cons = rental_demand(                   # [15]
        sale, rent, ctx, sqft, walk, tcfg["ok_walk_m"])
    parts["resale"], r_pros, r_cons = resale_potential(lst, sale, ctx)       # [10]
    pros += d_pros + r_pros
    cons += d_cons + r_cons
    parts["dual_key"] = 5 if lst.get("dual_key") else 0                       # [5]
    hist = 0.0                                                                # [5]
    rounds = unit_hist.get("rounds", 1)
    hist += min(rounds - 1, 3) * 2
    if bstats:
        if bstats.get("last_12m", 0) >= 6:
            hist -= 3
            cons.append(f"{bstats['last_12m']} auctions in this building in 12 months - possible distress/oversupply")
        if bstats.get("sold_psf") and price and sqft and price / sqft <= bstats["sold_psf"]:
            hist += 4
            pros.append(f"Reserve psf at/below past auction sale psf (RM{bstats['sold_psf']})")
    parts["history"] = max(-5.0, min(hist, 5.0))
    score = round(sum(v for v in parts.values() if v is not None), 1)

    # ---- explanation ---------------------------------------------------
    if cover is not None:
        (pros if cover >= targets["min_rent_cover"] else cons).append(
            f"Rent RM{fin['rent']:,} vs installment+maintenance RM{fin['monthly_cost']:,} -> {cover:.2f}x cover")
    else:
        cons.append("No reliable rent data yet")
    if disc is not None:
        q = int((sale or {}).get("valuation_quantile", 0.25) * 100)
        (pros if disc >= targets["min_discount"] else cons).append(
            f"{disc:.0%} below market (valued on the cheaper {q}% of similar units)")
    else:
        cons.append("No reliable sale comps yet")
    fsum = ctx.get("forum") or {}
    serious = {t: n for t, n in (fsum.get("negative_topics") or {}).items()
               if t in ("water", "flood", "security", "management", "lifts") and n >= 2}
    if serious:
        cons.append("Lowyat owners/tenants repeatedly complain about "
                    + ", ".join(f"{t} ({n})" for t, n in sorted(serious.items(), key=lambda x: -x[1]))
                    + " - read the comments before bidding")
    elif fsum.get("found"):
        notes.append(f"Lowyat: {fsum['threads']} thread(s), {fsum['comments']} relevant comment(s) - see card")
    cheap = (sale or {}).get("cheapest_equiv")
    if cheap and price and price >= cheap:
        cons.append(f"A similar unit is already listed for ~RM{cheap:,} (size-adjusted) - "
                    "cheaper than this auction, with no auction risk")
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

    if disc is not None and disc >= targets.get("suspicious_discount", 0.45):
        cons.append(f"{disc:.0%} discount is unusually deep - verify size, occupancy, arrears and title "
                    "before trusting it")
    if lst.get("occupied"):
        notes.append(f"Eviction buffer RM{fin_cfg.get('occupied_buffer', 0):,} added to cash needed")

    # ---- grade -----------------------------------------------------------
    low_conf = not (sale and sale.get("confident")) or not (rent and rent.get("confident"))
    if override.get("market_psf") and override.get("rent"):
        low_conf = False
    if market_value is None and rent_est is None:
        grade = "?"
    elif (score >= 70 and cover and cover >= targets["min_rent_cover"]
          and disc is not None and disc >= targets["min_discount"]
          and (bid.get("max_bid") or 0) >= (price or 0)
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
    verdict = make_verdict(price, bid.get("max_bid"), disc, low_conf, bstats, targets,
                           has_data=market_value is not None or rent_est is not None)

    return {
        "status": status, "grade": grade, "score": score, "verdict": verdict, "parts": {k: (round(v, 1) if v is not None else None)
                                                                     for k, v in parts.items()},
        "market_value": round(market_value) if market_value else None,
        "rent_estimate": round(rent_est) if rent_est else None,
        "sale_comps": sale, "rent_comps": rent, "station": station,
        "finance": fin, "max_bid": bid, "unit_history": unit_hist, "building_stats": bstats,
        "low_confidence": low_conf, "pros": pros, "cons": cons, "notes": notes,
    }


def make_verdict(price, max_bid, disc, low_conf, bstats, targets, has_data=True) -> dict:
    """BID / WAIT / PASS / VERIFY - what to actually do about this auction."""
    if not has_data or not price or max_bid is None:
        return {"action": "VERIFY", "text": "Not enough market data - check rent and sale prices manually first."}
    nxt = price * (1 - targets.get("next_round_cut", 0.10))
    if max_bid >= price:
        text = f"Bid from RM{price:,.0f} up to RM{max_bid:,} - stop there."
        prem = (bstats or {}).get("premium_over_reserve")
        if prem is not None and price * (1 + prem) > max_bid:
            text += (f" Units here have sold ~{prem:.0%} above reserve (~RM{price * (1 + prem):,.0f}),"
                     " above your limit - expect to be outbid; don't chase.")
        action = "BID"
        if low_conf or (disc is not None and disc >= targets.get("suspicious_discount", 0.45)):
            action = "VERIFY"
            text = "Numbers look good but data is thin or the discount looks too good - confirm comps first. " + text
        return {"action": action, "text": text, "next_round_price": round(nxt)}
    if max_bid >= nxt:
        return {"action": "WAIT", "next_round_price": round(nxt),
                "text": (f"Targets not met at RM{price:,.0f}. If unsold it should return at ~RM{nxt:,.0f}, "
                         f"within your RM{max_bid:,} limit - you'll be alerted if it comes back cheaper and meets your targets.")}
    return {"action": "PASS", "next_round_price": round(nxt),
            "text": f"Even a 10% cut (~RM{nxt:,.0f}) stays above your walk-away price of RM{max_bid:,}."}
