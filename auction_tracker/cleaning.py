"""Turn noisy portal listings into a defensible market value and rent.

Layers of defence against fake / auction / bait listings:
  1. keyword filter  - "auction", "lelong", "below market", room rentals...
  2. de-duplication  - one unit posted by five agents counts once
  3. plausibility    - psf must be inside sane bounds for KL
  4. like-for-like   - same property type, same bedrooms, size within
                       +/-15% (widened to +/-25% only when too few match)
  5. lowball cut     - bait prices far under the median are dropped
  6. robust outliers - median absolute deviation, not mean/stdev
  7. adjustments     - furnished rents -> unfurnished; asking -> transacted
Each removed comp keeps its reason so the report can show what was dropped,
and each kept comp says why it matched.
"""

from __future__ import annotations

import re
import statistics
import time

from .portals import dedupe


def _quantile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


# Property types that price differently and must not be mixed. Order
# matters: "duplex service apartment" is a duplex, "service apartment" is
# not an "apartment".
TYPE_GROUPS = [
    ("duplex/penthouse", ("penthouse", "duplex", "loft")),
    ("soho/studio", ("soho", "sovo", "sofo", "studio", "suite")),
    ("serviced", ("service apartment", "serviced apartment", "service residence", "serviced residence",
                  "servis", "residensi servis")),
    ("condo", ("condominium", "kondominium", "condo")),
    ("apartment", ("apartment", "pangsapuri")),
    ("flat", ("flat", "rumah pangsa")),
]
COMPATIBLE = {frozenset(("condo", "serviced"))}     # close substitutes, used only as a last resort
BED_RE = re.compile(r"\b(\d)\s*(?:\+\s*\d\s*)?(?:-|\s)?(?:bed(?:room)?s?|br|rooms?|bilik)\b", re.I)


def type_group(text: str) -> str | None:
    t = (text or "").lower()
    for group, words in TYPE_GROUPS:
        if any(w in t for w in words):
            return group
    return None


def bedrooms_of(item: dict) -> int | None:
    b = item.get("bedrooms")
    if isinstance(b, (int, float)) and 0 < b < 10:
        return int(b)
    if isinstance(b, str) and b.strip()[:1].isdigit():
        return int(b.strip()[0])
    m = BED_RE.search(f"{item.get('title', '')} {item.get('description', '')}")
    return int(m.group(1)) if m and 0 < int(m.group(1)) < 10 else None


def _hygiene(comps: list[dict], kind: str, cfg: dict) -> tuple[list[dict], list[dict]]:
    """Layers 1-3: fakes, duplicates, nonsense prices."""
    kw = [k.lower() for k in cfg.get("exclude_keywords", {}).get("common", [])]
    if kind == "rent":
        kw += [k.lower() for k in cfg.get("exclude_keywords", {}).get("rent", [])]
    lo_psf, hi_psf = cfg.get("sale_psf_range" if kind == "sale" else "rent_psf_range", [0, 1e9])
    max_age = cfg.get("max_listing_age_days")
    furnished_adj = cfg.get("furnished_rent_premium", 0.10)
    removed: list[dict] = []
    kept: list[dict] = []
    for c in dedupe(comps):
        if max_age and c.get("posted_unix") and time.time() - c["posted_unix"] > max_age * 86400:
            removed.append({**c, "reason": "stale ad"})
            continue
        text = f"{c.get('title', '')} {c.get('description', '')}".lower()
        hit = next((k for k in kw if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", text)), None)
        if hit:
            removed.append({**c, "reason": f"keyword '{hit}'"})
            continue
        if not c.get("built_up") or not c.get("price"):
            removed.append({**c, "reason": "missing price/size"})
            continue
        price = c["price"]
        notes = []
        furn = (c.get("furnishing") or "").lower() or ("fully" if "fully furnished" in text else "")
        if kind == "rent" and "fully" in furn and furnished_adj:
            price *= 1 - furnished_adj          # auction units come unfurnished
            notes.append(f"furnished -{furnished_adj:.0%}")
        psf = price / c["built_up"]
        if not lo_psf <= psf <= hi_psf:
            removed.append({**c, "reason": f"implausible psf {psf:.2f}"})
            continue
        kept.append({**c, "psf": psf, "adj_price": round(price), "notes": notes})
    return kept, removed


def _robust(kept: list[dict], removed: list[dict], cfg: dict) -> list[dict]:
    """Layers 5-6: bait lowballs and statistical outliers."""
    if len(kept) >= 3:
        med = statistics.median(c["psf"] for c in kept)
        cut = cfg.get("lowball_cut", 0.7)
        nxt = []
        for c in kept:
            if c["psf"] < med * cut:
                removed.append({**c, "reason": f"lowball {c['psf'] / med:.0%} of median (bait/auction?)"})
            else:
                nxt.append(c)
        kept = nxt
    if len(kept) >= 4:
        med = statistics.median(c["psf"] for c in kept)
        mad = statistics.median(abs(c["psf"] - med) for c in kept) * 1.4826
        thr = cfg.get("mad_threshold", 2.5)
        if mad > 0:
            nxt = []
            for c in kept:
                z = abs(c["psf"] - med) / mad
                if z > thr:
                    removed.append({**c, "reason": f"outlier z={z:.1f}"})
                else:
                    nxt.append(c)
            kept = nxt
    return kept


def select_comparables(comps: list[dict], kind: str, subject: dict, cfg: dict,
                       scope: str = "building") -> tuple[list[dict], list[dict], dict]:
    """Keep only units genuinely like the auction unit.

    Tries progressively looser tiers and stops at the first that yields
    enough comps:  T1 same type + same bedrooms + size +/-15%
                   T2 same type + same bedrooms + size +/-25%
    In the same building condo/serviced labels count as one type (agents mix
    them up); area-wide comps must match the type exactly.
    Returns (kept, removed, criteria).
    """
    pool, removed = _hygiene(comps, kind, cfg)
    sqft = subject.get("built_up")
    s_group = type_group(f"{subject.get('property_type', '')} {subject.get('title', '')}")
    s_beds = bedrooms_of(subject)
    bands = cfg.get("size_bands", [0.15, 0.25])
    need = cfg.get("min_comps_confident", 4)

    def describe(c):
        c_group = type_group(f"{c.get('ptype', '')} {c.get('title', '')} {c.get('description', '')[:200]}")
        diff = (c["built_up"] - sqft) / sqft if sqft else None
        return c_group, bedrooms_of(c), diff

    if scope == "building":
        # Within one building agents label the same units "Condominium" or
        # "Service Residence" interchangeably - treat those as one type there.
        # Duplex/penthouse/SOHO units are still kept apart.
        tiers = [("T1", bands[0], True), ("T2", bands[-1], True)]
    else:
        tiers = [("T1", bands[0], False), ("T2", bands[-1], False)]
    chosen, chosen_meta = [], None
    first_ok = first_any = None
    for name, band, loose_type in tiers:
        sel = []
        for c in pool:
            g, b, diff = describe(c)
            if diff is not None and abs(diff) > band:
                continue
            if s_group and g and g != s_group and not (loose_type and frozenset((g, s_group)) in COMPATIBLE):
                continue
            if s_group and not g and scope == "area":
                continue              # area-wide comps must prove they're the same type
            if s_beds and b and b != s_beds:
                continue
            sel.append(c)
        if first_ok is None and len(sel) >= 2:
            first_ok = (name, band, loose_type, sel)
        if first_any is None and sel:
            first_any = (name, band, loose_type, sel)
        if len(sel) >= need:
            chosen_meta, chosen = (name, band, loose_type), sel
            break
    if chosen_meta is None:
        best = first_ok or first_any        # a single true match beats none (flagged low-confidence)
        if best:
            chosen_meta, chosen = best[:3], best[3]
        else:
            chosen_meta, chosen = tiers[-1], []

    name, band, loose_type = chosen_meta
    chosen_ids = {id(c) for c in chosen}
    for c in pool:
        if id(c) in chosen_ids:
            continue
        g, b, diff = describe(c)
        if diff is not None and abs(diff) > band:
            why = f"size {diff:+.0%} (limit +/-{band:.0%})"
        elif s_group and g and g != s_group:
            why = f"different type ({g} vs {s_group})"
        elif s_beds and b and b != s_beds:
            why = f"{b} bedrooms vs {s_beds}"
        elif s_group and not g and scope == "area":
            why = "type not stated (area-wide search)"
        else:
            why = "looser match than the units used"
        removed.append({**c, "reason": why})

    kept = []
    for c in chosen:
        g, b, diff = describe(c)
        bits = [scope.replace("building", "same building").replace("area", "same area")]
        if diff is not None:
            bits.append(f"{diff:+.0%} size")
        if g:
            bits.append(g)
        if b:
            bits.append(f"{b}BR")
        bits += c.get("notes", [])
        kept.append({**c, "match": " · ".join(bits)})
    kept = _robust(kept, removed, cfg)
    criteria = {
        "tier": name, "size_band": band, "type": s_group, "bedrooms": s_beds,
        "text": " · ".join(x for x in [
            f"{s_group or 'any type'}" + (" (condo/serviced labels merged)" if loose_type and s_group in ("condo", "serviced") else ""),
            f"{s_beds}BR" if s_beds else "", f"size +/-{band:.0%}", scope] if x),
    }
    return kept, removed, criteria


def clean_comps(comps: list[dict], kind: str, subject_sqft: float | None, cfg: dict) -> tuple[list[dict], list[dict]]:
    """Backwards-compatible wrapper: size-only matching."""
    kept, removed, _ = select_comparables(comps, kind, {"built_up": subject_sqft}, cfg)
    return kept, removed


def summarize(kept: list[dict], subject_sqft: float | None, kind: str, cfg: dict) -> dict | None:
    if not kept:
        return None
    psfs = [c["psf"] for c in kept]   # psf already furnishing-adjusted
    haircut = cfg.get("sale_asking_haircut" if kind == "sale" else "rent_asking_haircut", 0)
    med = statistics.median(psfs)
    p25 = _quantile(psfs, 0.25)
    out = {
        "n": len(kept),
        "median_psf": round(med, 3),
        "p25_psf": round(p25, 3),
        "p75_psf": round(_quantile(psfs, 0.75), 3),
        "median_price": round(statistics.median(c["price"] for c in kept)),
        "haircut": haircut,
        "confident": len(kept) >= cfg.get("min_comps_confident", 4),
        "dual_key_share": round(sum(1 for c in kept if c.get("dual_key")) / len(kept), 2),
    }
    if subject_sqft:
        # Blend median with P25 for a slightly conservative estimate.
        out["estimate"] = round(subject_sqft * (0.7 * med + 0.3 * p25) * (1 - haircut))
    return out
