"""Turn noisy portal listings into a defensible market value and rent.

Layers of defence against fake / auction / bait listings:
  1. keyword filter  - "auction", "lelong", "below market", room rentals...
  2. de-duplication  - one unit posted by five agents counts once
  3. size band       - only comparable unit sizes
  4. plausibility    - psf must be inside sane bounds for KL
  5. lowball cut     - bait prices far under the median are dropped
  6. robust outliers - median absolute deviation, not mean/stdev
  7. haircut         - asking price -> realistic transacted price
Each removed comp keeps its reason so the report can show what was dropped.
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


def clean_comps(comps: list[dict], kind: str, subject_sqft: float | None, cfg: dict) -> tuple[list[dict], list[dict]]:
    kw = [k.lower() for k in cfg.get("exclude_keywords", {}).get("common", [])]
    if kind == "rent":
        kw += [k.lower() for k in cfg.get("exclude_keywords", {}).get("rent", [])]
    lo_psf, hi_psf = cfg.get("sale_psf_range" if kind == "sale" else "rent_psf_range", [0, 1e9])
    band = cfg.get("size_band", 0.3)

    max_age = cfg.get("max_listing_age_days")
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
        psf = c["price"] / c["built_up"]
        if not lo_psf <= psf <= hi_psf:
            removed.append({**c, "reason": f"implausible psf {psf:.2f}"})
            continue
        if subject_sqft and abs(c["built_up"] - subject_sqft) / subject_sqft > band:
            removed.append({**c, "reason": "different unit size"})
            continue
        kept.append({**c, "psf": psf})

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
    return kept, removed


def summarize(kept: list[dict], subject_sqft: float | None, kind: str, cfg: dict) -> dict | None:
    if not kept:
        return None
    psfs = [c["psf"] for c in kept]
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
