"""Market comparables from PropertyGuru and iProperty.

Both portals render with Next.js and embed listing data as JSON. Instead of
depending on an exact schema (which changes often), we walk the whole JSON
tree and pick out any object that carries a price *and* a floor area. A
plain-HTML card parser is the fallback. Every comp keeps its title/description
so the cleaner can throw out auction re-posts and bait listings.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

PRICE_KEYS = ("price", "priceValue", "askingPrice", "listingPrice", "amount", "rental", "rent")
SIZE_KEYS = ("floorArea", "builtUp", "builtUpArea", "builtup", "built_up", "floor_area",
             "size", "sizeSqft", "floorSize", "area", "areaSize")
TITLE_KEYS = ("localizedTitle", "title", "name", "propertyName", "projectName", "headline")
DESC_KEYS = ("description", "summary", "snippet", "subtitle")
URL_KEYS = ("url", "shareLink", "href", "link", "listingUrl", "canonicalUrl")
ID_KEYS = ("id", "listingId", "listing_id", "adId")


def _to_number(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?\b", v.replace("RM", ""))
        if not m:
            return None
        n = float(m.group(1).replace(",", ""))
        mult = {"k": 1e3, "m": 1e6}.get((m.group(2) or "").lower(), 1)
        return n * mult
    if isinstance(v, dict):
        for k in ("value", "amount", "min", "raw", "number", "sqft", "localeStringValue", "pretty", "text"):
            if k in v:
                n = _to_number(v[k])
                if n:
                    return n
    return None


def _size_sqft(v) -> float | None:
    if isinstance(v, dict):
        unit = str(v.get("unit", "") or v.get("units", "")).lower()
        n = _to_number(v)
        if n and ("sqm" in unit or "m2" in unit or unit == "sqmeter"):
            n *= 10.7639
        return n
    if isinstance(v, str) and re.search(r"sq\.?\s*m|sqm|m²", v, re.I):
        n = _to_number(v)
        return n * 10.7639 if n else None
    return _to_number(v)


def _first(d: dict, keys, conv=lambda x: x):
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}):
            val = conv(d[k])
            if val:
                return val
    return None


def _text(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return " ".join(_text(x) for x in v.values() if isinstance(x, (str, dict)))
    return ""


MRT_TEXT_RE = re.compile(r"(\d+)\s*min[^(]*\(\s*([\d,.]+)\s*(k?m)\s*\)\s*from\s*(.+)", re.I)


def parse_mrt_text(text: str) -> dict | None:
    """'7 min (570 m) from KG16 Setiawangsa LRT Station' -> walk metres + station."""
    m = MRT_TEXT_RE.search(text or "")
    if not m:
        return None
    dist = float(m.group(2).replace(",", "")) * (1000 if m.group(3).lower() == "km" else 1)
    return {"walk_m": round(dist), "walk_min": int(m.group(1)), "name": m.group(4).strip()}


def _pg_listing(ld: dict, base_url: str) -> dict | None:
    """Exact parser for PropertyGuru-platform ``listingData`` (PG & iProperty).

    Field paths per the open-source propertyguru-mcp project (MIT):
    price.value, area.localeStringValue / floorArea, localizedTitle,
    fullAddress, mrt.nearbyText, agent.name, isVerified, postedOn.unix, url.
    """
    price = _to_number(ld.get("price"))
    size = _size_sqft(ld.get("floorArea")) or _size_sqft(ld.get("area"))
    if not price or not size:
        return None
    agent = ld.get("agent") or {}
    posted = ld.get("postedOn") or {}
    blob = json.dumps(ld).lower()
    return {
        "id": str(ld.get("id") or ""),
        "title": _text(ld.get("localizedTitle") or ld.get("title") or ""),
        "description": " ".join(_text(x) for x in [ld.get("description", ""), ld.get("highlights", "")])[:600],
        "price": price,
        "built_up": round(size, 1),
        "url": urljoin(base_url, str(ld.get("url") or "")),
        "agent": _text(agent.get("name", "")) if isinstance(agent, dict) else "",
        "address": _text(ld.get("fullAddress") or ld.get("shortAddress") or ""),
        "dual_key": "dual key" in blob or "dual-key" in blob,
        "verified": bool(ld.get("isVerified")),
        "posted_unix": posted.get("unix") if isinstance(posted, dict) else None,
        "mrt": parse_mrt_text(_text((ld.get("mrt") or {}).get("nearbyText", "")) if isinstance(ld.get("mrt"), dict) else ""),
    }


def listings_from_next_data(data: dict, base_url: str) -> list[dict]:
    try:
        entries = data["props"]["pageProps"]["pageData"]["data"]["listingsData"]
    except (KeyError, TypeError):
        return []
    out = []
    for e in entries or []:
        ld = e.get("listingData") if isinstance(e, dict) else None
        if isinstance(ld, dict):
            c = _pg_listing(ld, base_url)
            if c:
                out.append(c)
    return out


def listings_from_json(data, base_url: str) -> list[dict]:
    """Schema-agnostic fallback: any object carrying a price and a floor area."""
    out: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            price = _first(node, PRICE_KEYS, _to_number)
            size = _first(node, SIZE_KEYS, _size_sqft)
            if price and size and 100 <= size <= 20000:
                agent = node.get("agent") or node.get("lister") or {}
                out.append({
                    "id": str(_first(node, ID_KEYS) or ""),
                    "title": _text(_first(node, TITLE_KEYS) or ""),
                    "description": _text(_first(node, DESC_KEYS) or "")[:600],
                    "price": price,
                    "built_up": round(size, 1),
                    "url": urljoin(base_url, str(_first(node, URL_KEYS) or "")),
                    "agent": _text(agent.get("name", "")) if isinstance(agent, dict) else "",
                    "address": _text(node.get("address") or node.get("location") or ""),
                    "dual_key": "dual key" in json.dumps(node).lower(),
                })
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return out


def listings_from_html(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    for tag in soup.find_all("script", id="__NEXT_DATA__") + soup.find_all("script", type="application/json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        exact = listings_from_next_data(data, base_url) if isinstance(data, dict) else []
        results.extend(exact or listings_from_json(data, base_url))
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            results.extend(listings_from_json(json.loads(tag.string or ""), base_url))
        except (json.JSONDecodeError, TypeError):
            continue
    if results:
        return dedupe(results)

    # Fallback: card scraping. Find links to listings and climb to a container
    # whose text contains both a price and a size.
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.search(r"listing|/property/|/ads?/", href):
            continue
        node = a
        for _ in range(5):
            text = node.get_text(" ", strip=True)
            pm = re.search(r"RM\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?", text)
            sm = re.search(r"([\d,]{3,6})\s*(sq\.?\s*ft|sqft|sf)\b", text, re.I)
            if pm and sm:
                price = float(pm.group(1).replace(",", "")) * {"k": 1e3, "m": 1e6}.get((pm.group(2) or "").lower(), 1)
                results.append({"id": "", "title": a.get_text(" ", strip=True)[:150],
                                "description": text[:600], "price": price,
                                "built_up": float(sm.group(1).replace(",", "")),
                                "url": urljoin(base_url, href), "agent": "", "address": "",
                                "dual_key": "dual key" in text.lower()})
                break
            if node.parent is None:
                break
            node = node.parent
    return dedupe(results)


def dedupe(comps: list[dict]) -> list[dict]:
    """Remove repeats: same id, or the same unit re-posted (price+size+title)."""
    seen, out = set(), []
    for c in comps:
        keys = []
        if c.get("id"):
            keys.append(("id", c["id"]))
        keys.append(("ps", round(c["price"], -2), round(c["built_up"])))
        if any(k in seen for k in keys):
            continue
        seen.update(keys)
        out.append(c)
    return out


STOPWORDS = {"the", "residence", "residences", "residensi", "condominium", "condo", "kondominium",
             "apartment", "apartments", "pangsapuri", "service", "serviced", "suites", "tower",
             "block", "@", "at", "kuala", "lumpur", "jalan", "taman", "of", "and", "&"}


def name_tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in STOPWORDS and len(t) > 1}


def matches_building(comp: dict, building: str) -> bool:
    want = name_tokens(building)
    if not want:
        return True
    have = name_tokens(" ".join([comp.get("title", ""), comp.get("address", ""), comp.get("description", "")[:200]]))
    return len(want & have) / len(want) >= 0.6


def page_url(url: str, page: int) -> str:
    """PG-platform pagination is path style: /property-for-sale/2?..."""
    if page <= 1:
        return url
    path, _, query = url.partition("?")
    return f"{path.rstrip('/')}/{page}" + (f"?{query}" if query else "")


def fetch_comps(fetcher, portals_cfg: dict, query: str, building: str | None, pages: int = 1) -> dict:
    """Return {"sale": [...], "rent": [...]} from all configured portals."""
    result = {"sale": [], "rent": []}
    for portal, urls in portals_cfg.items():
        if not isinstance(urls, dict):
            continue
        for kind in ("sale", "rent"):
            tmpl = urls.get(kind)
            if not tmpl:
                continue
            base = tmpl.format(q=quote_plus(query))
            comps = []
            for pg in range(1, pages + 1):
                url = page_url(base, pg)
                try:
                    html = fetcher.get(url)
                except Exception as exc:
                    log.warning("%s %s failed for %r: %s", portal, kind, query, exc)
                    break
                found = listings_from_html(html, url)
                comps.extend(found)
                if len(found) < 15:      # last page
                    break
            if building:
                comps = [c for c in comps if matches_building(c, building)]
            for c in comps:
                c["portal"] = portal
                c["kind"] = kind
            log.info("%s %s %r: %d comps", portal, kind, query, len(comps))
            result[kind].extend(comps)
    for kind in result:
        result[kind] = dedupe(result[kind])
    return result
