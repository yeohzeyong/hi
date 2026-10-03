"""Auction listing scraper and parser.

bplelonglist.com, lelongtips.com.my, auctionpro.my, lelongsifu.com.my and
listinglelong.my all run the same listing engine (same search URL and
``/auction|property/<id>/Lelong-Auction-...-for-RM<price>`` detail pages),
so one parser serves every source configured in ``config.yaml``.

The parser is deliberately text/regex based rather than tied to CSS classes:
when the site redesigns, labels such as "Reserve Price" and "sq.ft" rarely
change, so extraction keeps working. The listing URL slug
(``Lelong-Auction-Condominium-in-Mont-Kiara-Kuala-Lumpur-for-RM300000``)
is used as a second, independent source for type / area / price.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE = "https://www.bplelonglist.com"
SQM_TO_SQFT = 10.7639

STATES = ["Kuala Lumpur", "Selangor", "Putrajaya", "Penang", "Pulau Pinang", "Johor",
          "Perak", "Negeri Sembilan", "Melaka", "Malacca", "Pahang", "Kedah", "Kelantan",
          "Terengganu", "Perlis", "Sabah", "Sarawak", "Labuan"]

AUCTION_LINK_RE = re.compile(
    r"(?P<host>https?://[A-Za-z0-9.-]+)?/(?P<kind>auction|property)/(?P<id>[A-Za-z0-9=%+_-]{8,})/"
    r"(?P<slug>(?:Lelong-)?Auction-[A-Za-z0-9%._'-]+)")
SLUG_RE = re.compile(r"^(?:Lelong-)?Auction-(?P<head>.+)-in-(?P<place>.+)-for-RM(?P<price>\d+(?:\.\d+)?)", re.I)
DEFAULT_SEARCH = BASE + "/search/?keyword={keyword}&page={page}&sort=recent&state={state}"


@dataclass
class Listing:
    listing_id: str
    url: str
    source: str = ""
    title: str = ""
    property_type: str = ""
    area: str = ""            # area as written by the listing (e.g. "Mont Kiara")
    state: str = ""
    building: str = ""
    address: str = ""
    unit: str = ""
    reserve_price: float | None = None
    built_up: float | None = None
    auction_date: str | None = None    # ISO yyyy-mm-dd
    tenure: str = ""
    title_type: str = ""
    bumi: bool = False
    dual_key: bool = False
    occupied: bool = False
    auctioneer: str = ""
    bank: str = ""
    flags: list[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Search pages
# --------------------------------------------------------------------------
def search_url(state: str, keyword: str, page: int, template: str = DEFAULT_SEARCH) -> str:
    return template.format(keyword=quote_plus(keyword), page=page, state=quote_plus(state))


def extract_listing_links(html: str, base: str = BASE) -> list[str]:
    """Return absolute, de-duplicated auction detail URLs in page order."""
    seen, out = set(), []
    for m in AUCTION_LINK_RE.finditer(html):
        lid = m.group("id")
        if lid in seen:
            continue
        seen.add(lid)
        out.append(urljoin(m.group("host") or base, f"/{m.group('kind')}/{lid}/{m.group('slug')}"))
    return out


def listing_id_from_url(url: str) -> str:
    m = AUCTION_LINK_RE.search(urlparse(url).path)
    return m.group("id") if m else url


def source_name(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = re.sub(r"^(www|central)\.", "", host)
    return host.split(".")[0] if host else ""


# --------------------------------------------------------------------------
# Slug parsing
# --------------------------------------------------------------------------
TYPE_WORDS = ["Duplex Service Apartment", "Service Apartment", "Serviced Apartment",
              "Serviced Residence", "Condominium", "Apartment", "Penthouse", "Duplex",
              "SOHO", "Flat", "Townhouse", "Terrace House", "Semi-D", "Bungalow",
              "Shop Office", "Shop Lot", "Office", "Land", "Factory", "Studio"]


def parse_slug(url: str) -> dict:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    m = SLUG_RE.match(slug)
    if not m:
        return {}
    head = m.group("head").replace("-", " ").strip()
    place = m.group("place").replace("-", " ").strip()
    state = ""
    for s in STATES:
        if place.lower().endswith(s.lower()):
            state = s
            place = place[: -len(s)].strip()
            break
    ptype, building = head, ""
    for t in TYPE_WORDS:
        if head.lower().endswith(t.lower()):
            ptype = head[-len(t):]
            building = head[: -len(t)].strip()
            break
    else:
        # Marketing-style slugs: "Freehold Setapak Green Condominium Strategic
        # Location 5 min to ..." - take the earliest type word.
        hits = [(m.start(), -len(t), t) for t in TYPE_WORDS
                for m in [re.search(rf"\b{re.escape(t)}\b", head, re.I)] if m]
        if hits:
            pos, neg_len, t = min(hits)
            ptype = head[pos:pos - neg_len]
            building = head[:pos].strip()
    building = re.sub(r"(?i)^(freehold|leasehold)\s+", "", building)
    return {"property_type": ptype, "building": building, "area": place,
            "state": state, "reserve_price": float(m.group("price"))}


# --------------------------------------------------------------------------
# Detail page parsing
# --------------------------------------------------------------------------
MONEY = r"RM\s*([\d,]+(?:\.\d{1,2})?)"


def _num(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s.replace(",", "").strip())
    except ValueError:
        return None


def parse_date(text: str) -> str | None:
    """Parse the many date styles used on Malaysian auction listings."""
    if not text:
        return None
    t = re.sub(r"\b(Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)(day|sday|nesday|urday|rsday)?\b\.?,?",
               "", text, flags=re.I)
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t)
    t = re.sub(r"[,]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    patterns = [
        r"\d{1,2} [A-Za-z]{3,9} \d{4}", r"[A-Za-z]{3,9} \d{1,2} \d{4}",
        r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}", r"\d{4}-\d{2}-\d{2}",
    ]
    for p in patterns:
        m = re.search(p, t)
        if not m:
            continue
        s = m.group(0)
        for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y",
                    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except ValueError:
                continue
    return None


def _label(text: str, labels: str, value: str = r"([^\n]{2,200})") -> str | None:
    m = re.search(rf"(?:{labels})\s*[:\-]?\s*\n?\s*{value}", text, re.I)
    return m.group(1).strip() if m else None


def parse_built_up(text: str) -> float | None:
    unit = r"(sq\.?\s*f(?:ee)?t\.?|sqft|sf\b|square\s*f(?:ee|oo)t|sq\.?\s*m\.?|sqm|m2|m²|square\s*met(?:er|re)s?)"
    m = re.search(rf"(?:built[\s-]*up|floor\s*area|land\s*area|size|area)[^\d\n]{{0,40}}([\d,]+(?:\.\d+)?)\s*{unit}",
                  text, re.I)
    if not m:
        m = re.search(rf"([\d,]+(?:\.\d+)?)\s*{unit}", text, re.I)
    if not m:
        return None
    val = _num(m.group(1))
    if val is None:
        return None
    if re.match(r"(sq\.?\s*m|sqm|m2|m²|square\s*met)", m.group(2), re.I):
        val *= SQM_TO_SQFT
    return round(val, 1)


ROAD_WORDS = re.compile(r"^(jalan|jln|lorong|lrg|persiaran|lebuh|lebuhraya|taman|tmn|kampung|kg|off|no\.?|lot|unit|parcel|level|tingkat|block|blok)\b", re.I)


def derive_building(address: str, title: str) -> str:
    """Best-effort building name from the address ('B-15-07, Residensi X, Jalan..')."""
    for part in (address or "").split(","):
        part = part.strip()
        if not part or UNIT_RE.fullmatch(part) or ROAD_WORDS.match(part) or re.search(r"\d{5}", part):
            continue
        if re.search(r"[A-Za-z]{3,}", part) and not re.fullmatch(r"[\d\W]+", part):
            return re.sub(r"^(?:[A-Z]?\d+[A-Z]?-)+\d+[A-Z]?\s+", "", part)
    t = re.sub(r"(?i)^lelong\s+auction\s+", "", title or "")
    if t and not re.search(r"(?i)\bfor\s+RM", t):
        return t.split(",")[0].strip()
    return ""


UNIT_RE = re.compile(r"\b(?:unit\s*(?:no\.?)?\s*[:\-]?\s*)?((?:[A-Z]{1,2}\d?-)?\d{1,3}[A-Z]?-\d{1,3}[A-Z]?(?:-\d{1,3})?)\b", re.I)


def parse_detail(html: str, url: str) -> Listing:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        if tag.get("type") != "application/ld+json":
            tag.decompose()
    title = ""
    if soup.find("h1"):
        title = soup.find("h1").get_text(" ", strip=True)
    elif soup.title:
        title = soup.title.get_text(" ", strip=True)
    # Main content only if we can find it; otherwise the whole page.
    main = soup.find("main") or soup.find(id=re.compile("content|detail", re.I)) or soup.body or soup
    text = main.get_text("\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)

    slug = parse_slug(url)
    lst = Listing(listing_id=listing_id_from_url(url), url=url, source=source_name(url), title=title)

    # JSON-LD, when present, is the most structured source.
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if not isinstance(it, dict):
                continue
            offers = it.get("offers") or {}
            if isinstance(offers, dict) and offers.get("price") and lst.reserve_price is None:
                lst.reserve_price = _num(str(offers["price"]))
            addr = it.get("address")
            if isinstance(addr, dict) and not lst.address:
                lst.address = ", ".join(str(v) for k, v in addr.items() if not k.startswith("@") and v)

    price = _label(text, r"reserve\s*price|harga\s*rizab", MONEY)
    lst.reserve_price = _num(price) or lst.reserve_price or slug.get("reserve_price")
    lst.built_up = parse_built_up(text)
    lst.auction_date = parse_date(_label(text, r"auction\s*date|date\s*of\s*auction|tarikh\s*lelong") or "")
    lst.address = (_label(text, r"property\s*address|address|alamat") or lst.address or "").strip()
    lst.auctioneer = (_label(text, r"auctioneer|pelelong") or "")[:120]
    lst.bank = (_label(text, r"assignee|chargee|bank|lender|pemegang\s*gadaian") or "")[:120]
    lst.property_type = (_label(text, r"property\s*type|type\s*of\s*property|jenis\s*hartanah", r"([^\n]{2,60})")
                         or slug.get("property_type", ""))
    lst.area = slug.get("area") or ""
    lst.state = slug.get("state") or ""
    lst.building = _label(text, r"(?:building|project|development|scheme)\s*name|condominium\s*name",
                          r"([^\n]{2,80})") or ""

    low = text.lower()
    if "freehold" in low or "pegangan bebas" in low:
        lst.tenure = "Freehold"
    elif "leasehold" in low or "pajakan" in low:
        m = re.search(r"leasehold[^\n]{0,60}?(\d{2,3})\s*years?", text, re.I)
        exp = re.search(r"expir\w*[^\n]{0,20}?(20\d{2}|21\d{2})", text, re.I)
        lst.tenure = "Leasehold" + (f" {m.group(1)}y" if m else "") + (f" exp {exp.group(1)}" if exp else "")
    if re.search(r"master\s*title", low):
        lst.title_type = "Master title"
    elif re.search(r"strata\s*title", low):
        lst.title_type = "Strata title"
    elif re.search(r"individual\s*title", low):
        lst.title_type = "Individual title"
    lst.bumi = bool(re.search(r"(?<!non-)(?<!non )(?<!not )(?<!non)\bbumi(putera)?\s*lot|(?<!non-)(?<!non )bumiputera\s*(only|status)"
                              r"|malay\s*reserv|rizab\s*melayu", low))
    lst.dual_key = bool(re.search(r"dual[\s-]*key", low))
    lst.occupied = bool(re.search(r"\b(tenanted|occupied by|occupants?)\b", low)) and "vacant" not in low

    if not lst.building:
        # Address beats the URL slug: slugs on some sites are marketing copy
        # ("Nestled in a prime location Condominium ...").
        slug_b = slug.get("building", "")
        lst.building = (derive_building(lst.address, "")
                        or (slug_b if 0 < len(slug_b.split()) <= 5 else "")
                        or derive_building("", title))
    um = UNIT_RE.search(lst.address or "")
    if um:
        lst.unit = um.group(1).upper()

    if lst.title_type == "Master title":
        lst.flags.append("Master title only - financing/transfer slower")
    if lst.bumi:
        lst.flags.append("Bumi lot / Malay reserve - check eligibility")
    if lst.occupied:
        lst.flags.append("May be occupied - vacant possession not guaranteed")
    if re.search(r"\bnon[\s-]*laca\b|without\s*laca", low):
        lst.flags.append("Non-LACA - check developer consent & title chain")
    if re.search(r"(purchaser|buyer)[^.\n]{0,80}(arrears|outstanding)", low):
        lst.flags.append("Buyer bears outstanding arrears per conditions of sale")
    m = re.search(r"leasehold[^\n]{0,60}?expir\w*[^\n]{0,20}?(20\d{2}|21\d{2})", text, re.I)
    if m and int(m.group(1)) - date.today().year < 60:
        lst.flags.append(f"Short lease remaining (expires {m.group(1)}) - banks may limit loan")

    lst.raw_text = text[:20000]
    return lst


# --------------------------------------------------------------------------
# Crawl
# --------------------------------------------------------------------------
def crawl(fetcher, state: str, keywords: list[str], max_pages: int, known_ids: set[str],
          stop_after_known_pages: int = 2, seen_sink: dict | None = None, stats: dict | None = None,
          template: str = DEFAULT_SEARCH):
    """Yield (url, html) for detail pages not seen before.

    Every listing URL encountered on a search page is recorded in
    ``seen_sink`` (id -> url) so the caller can mark it as still listed and
    spot reserve-price changes from the slug without re-fetching.
    Results are sorted newest first, so once a couple of consecutive search
    pages contain nothing new we stop (``stop_after_known_pages=0`` disables
    this for a backfill).
    """
    for kw in keywords:
        known_streak = 0
        seen_this_kw: set[str] = set()
        for page in range(1, max_pages + 1):
            url = search_url(state, kw, page, template)
            try:
                html = fetcher.get(url)
            except Exception as exc:
                log.warning("search page failed %s: %s", url, exc)
                break
            if stats is not None:
                stats["search_pages"] = stats.get("search_pages", 0) + 1
            links = [u for u in extract_listing_links(html, url) if listing_id_from_url(u) not in seen_this_kw]
            if not links:
                break
            new = [u for u in links if listing_id_from_url(u) not in known_ids]
            seen_this_kw.update(listing_id_from_url(u) for u in links)
            if seen_sink is not None:
                seen_sink.update({listing_id_from_url(u): u for u in links})
            log.info("[%s] page %d: %d listings, %d new", kw, page, len(links), len(new))
            known_streak = 0 if new else known_streak + 1
            for u in new:
                try:
                    yield u, fetcher.get(u)
                    known_ids.add(listing_id_from_url(u))
                except Exception as exc:
                    log.warning("detail failed %s: %s", u, exc)
            if stop_after_known_pages and known_streak >= stop_after_known_pages:
                break


def search_page_ids(html: str) -> set[str]:
    return {listing_id_from_url(u) for u in extract_listing_links(html)}
