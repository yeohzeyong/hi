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
# Bump when parsing improves: stored pages are then re-parsed automatically.
PARSER_VERSION = 5
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
    bedrooms: int | None = None
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
    """Return absolute, de-duplicated auction detail URLs in page order.

    A page can mention the same listing several times with different slugs
    (e.g. a shortened one without the price, which the site answers with
    404), so keep the most complete slug per listing id.
    """
    best: dict[str, tuple] = {}
    for m in AUCTION_LINK_RE.finditer(html):
        lid, slug = m.group("id"), m.group("slug")
        rank = ("-for-RM" in slug, len(slug))
        if lid not in best or rank > best[lid][0]:
            url = urljoin(m.group("host") or base, f"/{m.group('kind')}/{lid}/{slug}")
            best[lid] = (rank, url)
    return [u for _, u in best.values()]


def detail_candidates(url: str) -> list[str]:
    """URL to try first, then the bare id path (the slug is often decorative)."""
    m = AUCTION_LINK_RE.search(url)
    if not m:
        return [url]
    p = urlparse(url)
    return [url, f"{p.scheme}://{p.netloc}/{m.group('kind')}/{m.group('id')}"]


def fetch_detail(fetcher, url: str) -> str:
    last = None
    for cand in detail_candidates(url):
        try:
            return fetcher.get(cand)
        except Exception as exc:
            last = exc
    raise last


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
        r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}", r"\d{4}-\d{2}-\d{2}", r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2}\b",
    ]
    for p in patterns:
        m = re.search(p, t)
        if not m:
            continue
        s = m.group(0)
        for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y",
                    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y"):
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
    m = None
    for label in (r"built[\s-]*up", r"floor\s*area|size", r"land\s*area|area"):   # built-up wins over land area
        m = re.search(rf"(?:{label})[^\d\n]{{0,40}}([\d,]+(?:\.\d+)?)\s*{unit}", text, re.I)
        if m:
            break
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


STATE_WORDS = {s.lower() for s in STATES} | {"wilayah persekutuan", "w.p. kuala lumpur", "wp kuala lumpur", "malaysia"}
FLOOR_RE = re.compile(r"^(\d{1,3}(st|nd|rd|th)?\s*(floor|flr|fl)\b|(floor|level|tingkat|lantai)\s*\d|ground floor|mezzanine)", re.I)
ROAD_WORDS = re.compile(r"^(jalan|jln|lorong|lrg|persiaran|lebuh|lebuhraya|taman|tmn|kampung|kg|off|no\.?|lot|unit|parcel|level|tingkat|block|blok)\b", re.I)


# Neighbourhood / district names: they appear in addresses but are never
# the building ("Blok D5, Taman Melati, Setapak").
AREA_WORDS = {"setapak", "wangsa maju", "cheras", "mont kiara", "mont' kiara", "mon't kiara", "montkiara",
              "bukit bintang", "titiwangsa", "sentul", "gombak", "kepong", "ampang", "segambut",
              "sri hartamas", "dutamas", "bangsar", "brickfields", "pudu", "imbi", "klcc", "kl city centre",
              "old klang road", "bukit jalil", "sri petaling", "setiawangsa", "keramat", "jalan ipoh",
              "kuala lumpur", "wilayah persekutuan", "malaysia", "selangor"}
GENERIC_NAMES = {"residential", "residence", "residences", "residensi", "apartment", "apartments", "condominium",
                 "kondominium", "condo", "pangsapuri", "rumah pangsa", "flat", "flats", "service apartment",
                 "serviced apartment", "shop", "shop office", "office", "unit", "property"}
TOWER_PART_RE = re.compile(r"^\(?\s*(on site is\b|also known as\b|tower|block|blok|menara|wing|phase|fasa)\b"
                           r"|\btower\s*[A-Z0-9]{1,2}\b|\btower\s*$", re.I)
STREET_NO_RE = re.compile(r"\s+(?:no\.?|lot|plot)\s*\d+[A-Z]?\s*$", re.I)


def clean_building_name(name: str) -> str:
    """'Residensi Ascenda No. 3' -> 'Residensi Ascenda' (the number belongs to the road)."""
    n = STREET_NO_RE.sub("", (name or "").strip())
    n = re.sub(r"^(?:unit\s*no\.?\s*)", "", n, flags=re.I)
    n = re.sub(r"^(?:[A-Z]?\d+[A-Z]?-)+\d+[A-Z]?\s+", "", n)        # leading unit number
    return n.strip(" ,-")


def _looks_like_building(part: str) -> bool:
    low = part.lower().strip(" .")
    if (not part or UNIT_RE.fullmatch(part) or ROAD_WORDS.match(part) or re.search(r"\d{5}", part)
            or low in STATE_WORDS or FLOOR_RE.match(part) or low in AREA_WORDS or low in GENERIC_NAMES
            or re.match(r"^(off|bandar|desa|seksyen|section|batu)\b", low)):
        return False
    return bool(re.search(r"[A-Za-z]{3,}", part)) and not re.fullmatch(r"[\d\W]+", part)


def derive_building(address: str, title: str) -> str:
    """Property name from an auction address.

    'Unit No., Residensi Ascenda No. 3, Jalan Arena 1, Setapak'   -> 'Residensi Ascenda'
    'Unit No., Tower B, Edgewood (Residensi Skysanctuary 1), ...' -> 'Edgewood (Residensi Skysanctuary 1)'
    'Unit No., Blok D5, Taman Melati, Setapak, ...'              -> ''  (no named building)
    Tower/block labels are remembered but the development name after them wins.
    """
    tower = ""
    for raw in (address or "").split(","):
        part = clean_building_name(raw)
        if not _looks_like_building(part):
            continue
        if TOWER_PART_RE.search(part):
            tower = tower or part
            continue
        return part
    if tower and not re.match(r"^\(|^(tower|block|blok)\b", tower, re.I):
        return tower                                           # e.g. "Royal Tower" with nothing better after it
    t = re.sub(r"(?i)^lelong\s+auction\s+", "", title or "")
    if t and not re.search(r"(?i)\bfor\s+RM", t) and _looks_like_building(clean_building_name(t.split(",")[0])):
        return clean_building_name(t.split(",")[0])
    return ""


UNIT_RE = re.compile(r"\b(?:unit\s*(?:no\.?)?\s*[:\-]?\s*)?((?:[A-Z]{1,2}\d?-)?\d{1,3}[A-Z]?-\d{1,3}[A-Z]?(?:-\d{1,3})?)\b", re.I)


BOILERPLATE_RE = re.compile(r"^(Loan Calculator|Feel Free to Contact Us|Find Your Property|Related Auctions|"
                            r"More Auctions|Contact Us)$", re.M)


def _line_after(text: str, heading: str) -> str | None:
    """The line right below a heading line, e.g. the property type under
    'Auction Property Details'."""
    m = re.search(rf"^{heading}[ \t]*\n([^\n]{{2,40}})$", text, re.I | re.M)
    return m.group(1).strip() if m else None


def _multiline_label(text: str, labels: str) -> str | None:
    """Value spanning several lines, up to the next 'Label:' line.
    'Property Address:\nUnit No.\n, Residensi X, Jalan Y, 55100, KL' -> one string."""
    m = re.search(rf"(?:{labels})\s*:?[ \t]*\n((?:(?![^\n]{{1,30}}:[ \t]*$)[^\n]+(?:\n|$)){{1,4}})", text, re.I | re.M)
    if not m:
        return _label(text, labels)
    val = " ".join(line.strip() for line in m.group(1).strip().split("\n"))
    return re.sub(r"\s+,", ",", val)


def parse_detail(html: str, url: str) -> Listing:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        if tag.get("type") != "application/ld+json":
            tag.decompose()
    title = ""
    for cand in [soup.find("h1"), soup.title]:
        t = cand.get_text(" ", strip=True) if cand else ""
        if t and not re.search(r"\.(com|my)\b", t, re.I):     # skip "bplelonglist.com" logo headings
            title = t
            break
    # Main content only if we can find it; otherwise the whole page.
    main = soup.find("main") or soup.find(id=re.compile("content|detail", re.I)) or soup.body or soup
    text = main.get_text("\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)
    # Drop the enquiry form, search box and "Related Auctions" (other units'
    # prices and sizes would otherwise leak into this listing).
    cut = [m.start() for m in BOILERPLATE_RE.finditer(text)]
    if cut:
        text = text[:min(cut)]

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
    lst.address = (_multiline_label(text, r"property\s*address|address|alamat") or lst.address or "").strip()
    lst.auctioneer = (_label(text, r"auctioneer|pelelong") or "")[:120]
    lst.bank = (_label(text, r"assignee|chargee|bank|lender|pemegang\s*gadaian") or "")[:120]
    lst.property_type = (_label(text, r"property\s*type|type\s*of\s*property|jenis\s*hartanah", r"([^\n]{2,60})")
                         or _line_after(text, r"auction[ \t]+property[ \t]+details")
                         or slug.get("property_type", ""))
    lst.area = slug.get("area") or ""
    lst.state = slug.get("state") or ""
    lst.building = _label(text, r"(?:building|project|development|scheme)\s*name|condominium\s*name",
                          r"([^\n]{2,80})") or ""

    if not lst.building:
        # Address beats the URL slug: slugs on some sites are marketing copy
        # ("Nestled in a prime location Condominium ...").
        slug_b = clean_building_name(slug.get("building", ""))
        lst.building = (derive_building(lst.address, "")
                        or (slug_b if 0 < len(slug_b.split()) <= 5 and _looks_like_building(slug_b)
                            and not TOWER_PART_RE.search(slug_b) else "")
                        or derive_building("", title))
    enrich(lst, text)
    lst.raw_text = text[:20000]
    return lst


def enrich(lst: Listing, text: str) -> Listing:
    """Tenure, title, bumi, dual key, occupancy, unit and risk flags - shared by
    auction-site pages and Telegram posts."""
    low = text.lower()
    if "freehold" in low or "pegangan bebas" in low:
        lst.tenure = "Freehold"
    elif "leasehold" in low or "pajakan" in low:
        m = re.search(r"leasehold[^\n]{0,60}?(\d{2,3})\s*years?", text, re.I)
        exp = re.search(r"(?:expir\w*|till|until)[^\n]{0,20}?(20\d{2}|21\d{2})", text, re.I)
        lst.tenure = "Leasehold" + (f" {m.group(1)}y" if m else "") + (f" exp {exp.group(1)}" if exp else "")
    if re.search(r"master\s*title", low):
        lst.title_type = "Master title"
    elif re.search(r"strata\s*title", low):
        lst.title_type = "Strata title"
    elif re.search(r"individual\s*title", low):
        lst.title_type = "Individual title"
    lst.bumi = bool(re.search(r"(?<!non-)(?<!non )(?<!not )(?<!non)\bbumi(putera)?\s*lot|(?<!non-)(?<!non )bumiputera\s*(only|status)"
                              r"|malay\s*reserv|rizab\s*melayu", low))
    lst.dual_key = lst.dual_key or bool(re.search(r"dual[\s-]*key", low))
    if not lst.bedrooms:
        bm = (re.search(r"bed\s*rooms?\s*:?\s*(\d)", text, re.I)
              or re.search(r"\b(\d)\s*(?:\+\s*\d\s*)?(?:-|\s)?(?:bed\s*rooms?|br|bilik)\b", text, re.I))
        if bm and 0 < int(bm.group(1)) < 10:
            lst.bedrooms = int(bm.group(1))
    lst.occupied = (bool(re.search(r"\b(tenanted|occupied by|occupants?)\b|status\s*:\s*occupied", low))
                    and "vacant" not in low)
    if not lst.unit:
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
    dep = re.search(r"deposit\s*:?\s*(\d{1,2})\s*%", text, re.I)
    if dep and dep.group(1) != "10":
        lst.flags.append(f"Auction-day deposit is {dep.group(1)}% (not the usual 10%)")
    m = re.search(r"leasehold[^\n]{0,60}?(?:expir\w*|till|until)[^\n]{0,20}?(20\d{2}|21\d{2})", text, re.I)
    if m and int(m.group(1)) - date.today().year < 60:
        lst.flags.append(f"Short lease remaining (expires {m.group(1)}) - banks may limit loan")
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
                    yield u, fetch_detail(fetcher, u)
                    known_ids.add(listing_id_from_url(u))
                except Exception as exc:
                    log.warning("detail failed %s: %s", u, exc)
                    if stats is not None and not stats.get("debug_saved"):
                        _save_debug(url, html)
                        stats["debug_saved"] = True
            if stop_after_known_pages and known_streak >= stop_after_known_pages:
                break


def _save_debug(url: str, html: str):
    """Keep one search page per source when detail pages fail, so the
    link format can be inspected and the parser fixed."""
    from .config import DATA_DIR
    d = DATA_DIR / "debug"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{source_name(url)}_search.html").write_text(html[:400_000], encoding="utf-8")


def search_page_ids(html: str) -> set[str]:
    return {listing_id_from_url(u) for u in extract_listing_links(html)}
