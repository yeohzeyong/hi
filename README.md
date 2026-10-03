# Malaysia Auction Property Tracker

This tool shortlists investment-grade **bank auction (lelong) units in KL** every day.
It is built around one question:

> *Will the rent pay the installment and the maintenance, and am I buying far
> enough below the real market to cover what I can't see inside?*

It scrapes [bplelonglist.com](https://www.bplelonglist.com/) and
[lelongtips.com.my](https://www.lelongtips.com.my/) (the same listing engine;
duplicates across the two sites are merged), values each unit
against cleaned **PropertyGuru + iProperty** sale and rent data, measures the
walk to the nearest **MRT / LRT / Monorail**, and remembers every auction it has
seen. It then grades each unit A-D, gives a **walk-away bid** price, and gives a plain
**BID / WAIT / PASS / VERIFY** verdict.

(`pine/` holds unrelated TradingView scripts.)

---

## What it does each day

```
bplelonglist ──► parse ──► SQLite history ──► market comps ──► clean ──► value ──► score ──► dashboard
  (5 areas,        reserve,    every price,      PG + iProperty   remove     rent cover,   A/B/C/D,   + Telegram
   newest first)   sqft, date,  round, relist     (cached 21 days) fakes      discount,     max bid    alert for A
                   tenure,      = auction                                     MRT walk
                   bumi, dual   history
                   key, flags
```

| Your requirement | How it's handled |
|---|---|
| ≥ 1,000 sqft | Hard filter (`search.min_built_up_sqft`) |
| Bukit Bintang, Setapak, Titiwangsa, Mont Kiara, Cheras | `search.areas`. Each area has its own keyword list, so you can add aliases |
| Dual key preferred | Detected from listing text and portal data. Earns +5 points, and the rent estimate gets a premium when comps are ordinary units |
| Walking distance to MRT | Station coordinates come from OpenStreetMap and building locations from Nominatim. Distance = straight line × 1.3 detour. Agents' "7 min (570 m) from … MRT" text on portal listings is a fallback |
| Easy to rent out | Rentability score: number of live rent listings in the building, unit size sweet spot (1,000-1,300 sqft), and the walk to rail |
| Rent covers installment + maintenance | **Rent cover ratio** = rent ÷ (installment + maintenance + quit rent/assessment/insurance). Grade A requires ≥ 1.00× |
| Cheap enough, since the condition is unknown | Grade A requires ≥ 20% below the *cleaned* market value. The walk-away bid also sets aside RM25/sqft for repairs and 12 months of possible maintenance arrears |
| Fake / auction listings on portals | 7-layer cleaner (below). Every dashboard card shows which comps were kept and which were dropped, and why |
| Learn from past auctions | lelongtips keeps old auctions online, and `scrape --backfill` seeds history from it. Every run is stored. The same unit coming back with a ~10% lower reserve counts as a new **round**. Per building it reports auction frequency, median reserve psf, "likely sold" psf and sell-through rate |
| Works long term | Runs unattended on GitHub Actions. Results are cached, fixes go in config files (no code changes needed), it fails loudly if a site blocks it, and history keeps accumulating |

### Fake-listing defence (portal comps)
1. **Keywords**: auction, lelong, below market, BMV, "10% deposit", room rentals, Airbnb/short-stay, etc. → dropped
2. **De-duplication**: the same unit posted by several agents, or on both PG and iProperty, counts once
3. **Building match**: the comp's title or address must match the building name
4. **Size band**: comps must be within ±30% of the auction unit's size
5. **Plausibility**: sale RM150-3,500 psf, rent RM0.8-9 psf, ads older than 240 days dropped
6. **Bait lowballs**: anything under 70% of the median psf is dropped (this is where fake "cheap" posts end up)
7. **Robust outliers**: median absolute deviation (z > 2.5), not the mean

Asking prices are then haircut (−8% sale, −5% rent) toward what actually transacts.
The estimate blends 70% median and 30% 25th percentile, so it errs low. With
fewer than 4 clean comps, a listing is marked low-confidence and capped at grade B.

### Grading
Score out of 100:
- rent cover: 30
- discount to market: 25
- walk to rail: 15
- rentability: 15
- dual key: 5
- auction history: 10

**A** needs all of these:
- score ≥ 70
- rent cover ≥ 1.0×
- discount ≥ 20%
- rail ≤ 1.2 km
- confident data
- no Bumi-lot or master-title issue

Otherwise **B** ≥ 55, **C** ≥ 40, **D** below that, and **?** when there is no market data yet.

**Walk-away bid** is the highest price that still meets *both* the rent-cover
and discount targets. Bid up to it and no further.

**Verdict** (what to do):

| Verdict | Meaning |
|---|---|
| **BID** | Targets are met at the reserve price. Bid up to the walk-away price. If your results file shows units in this building usually sell well above reserve, it warns that you'll probably be outbid. |
| **WAIT** | Not worth it at this reserve. If unsold, it typically returns ~10% cheaper, which *would* work. You'll be alerted when it comes back and qualifies. |
| **PASS** | Doesn't work even after a 10% cut. |
| **VERIFY** | Looks good, but the market data is thin or the discount is suspiciously deep (≥ 45%). Usually that means occupancy, arrears, title trouble or a wrong size. |

Occupied units get an RM10k eviction buffer in the cash-needed figure.

---

## Setup (once, about 10 minutes)

### 1. Let it run daily on GitHub (free)
1. Merge this branch into your **default branch**. GitHub only runs scheduled workflows from the default branch.
2. **Actions** tab → enable workflows → open *Auction tracker* → **Run workflow** → choose `scrape --backfill` once. This crawls older listings to seed the auction history and can take a few hours.
3. After that it runs by itself every day at 07:07 MYT. The database is committed back into `data/tracker.db`, so history grows.
4. **Dashboard**: Settings → Pages → Source: **GitHub Actions**. The dashboard is then at `https://<you>.github.io/<repo>/`.
   On a private repo without Pages, download the `dashboard` artifact from each run, or open `docs/index.html` after a `git pull`.
5. **Telegram alerts** (optional, recommended):
   1. Create a bot with [@BotFather](https://t.me/BotFather).
   2. Send it a message, then get your chat id from `https://api.telegram.org/bot<TOKEN>/getUpdates`.
   3. Add both as repo secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

   You get one message per new A-grade deal, and again if a re-auction cuts its price.

### 2. Run on your own PC with your Chrome (best for PropertyGuru / iProperty)
PropertyGuru and iProperty use Cloudflare, which often blocks cloud servers
but rarely blocks a real Chrome on a home connection. The tracker can drive your
installed Chrome with its own saved profile. If a captcha ever appears, solve it
once in that window and the cookies are kept.

```bash
pip install -r requirements.txt -r requirements-browser.txt
python -m auction_tracker comps --backend chrome   # refresh market data with your Chrome
python -m auction_tracker evaluate                 # re-score, writes docs/index.html
```
- **Windows**: double-click `run_local.bat`, or schedule it in Task Scheduler.
- **macOS/Linux**: use `run_local.sh` with cron.

A good long-term rhythm:
- GitHub scrapes auctions daily.
- Your PC refreshes comps weekly. Comps are cached for 21 days, so only new buildings are fetched.
- After a local refresh, commit and push `data/tracker.db` so the cloud run uses your fresh comps.

### Commands
```bash
python -m auction_tracker run                  # full daily pipeline
python -m auction_tracker check <listing-url>  # analyse one listing right now
python -m auction_tracker scrape --backfill    # crawl history
python -m auction_tracker comps --force        # re-fetch all market comps
python -m auction_tracker evaluate             # re-score after editing config/overrides (no network needed)
python -m auction_tracker reparse              # re-run the parser over stored pages
```

---

## Making it smarter over time
- **`config.yaml`**: interest rate, loan margin (auction loans are usually 90%), maintenance psf, repair buffer, targets, areas. Edit it, then run `evaluate`.
- **`data/building_overrides.yaml`**: your own knowledge always wins:
  - the real maintenance fee from the management office
  - the rent a unit actually achieved
  - a transacted psf from Brickz / JPPH
  - pinned coordinates
  - `exclude: true` for a building you never want to see again
- **`data/manual_comps.csv`**: paste real transactions or rentals you trust (for example from Brickz or NAPIC). They are merged with the portal comps.
- **`data/auction_results.csv`**: paste **real auction outcomes**: date, building, sqft, reserve and sold price. Useful sources:
  - Facebook auction groups (e.g. StayWokeProp)
  - auctioneer results
  - "sold" posts

  This gives each building an actual sold psf, and shows how far above reserve units really go. That is the best guide to whether your walk-away price can win.

  Facebook needs a login and doesn't allow scraping, so this one stays a quick manual paste.
- **Building auction history** tab: buildings that keep showing up at auction, or rarely sell, are telling you something.

## Before you bid: checklist
The tracker finds candidates. Do these checks yourself before bidding:
1. **Proclamation of Sale (POS) + Conditions of Sale**:
   - Who pays outstanding maintenance, quit rent and assessment?
   - Is it LACA (charge, title issued) or non-LACA (assignment, needs developer consent)?
2. **Title search**: individual/strata title or master title, restriction in interest, Bumi lot, lease expiry.
3. **Management office**: actual maintenance psf, arrears on the unit, any special levy, whether the unit is occupied.
4. **Site visit**: building upkeep, lifts, security, parking. Check the unit from outside (windows, door).
5. **Loan**: get an auction loan pre-approval (usually 90% margin). Balance is due within **90-120 days**.
6. **Auction day**: bring a 10% deposit bank draft made out as the POS specifies, and never bid above the walk-away price.

## Limitations
- The sites' HTML could not be inspected while this was built. The parsers are written to survive layout changes:
  - bplelonglist: label regexes plus the URL slug
  - PropertyGuru / iProperty: the known `__NEXT_DATA__` path plus a schema-agnostic fallback

  If a site changes and parsing breaks, the daily run fails with an error rather than going stale. `reparse` replays stored pages after a parser fix.
- Auction outcomes are *inferred*, because bplelonglist does not publish results:
  - relisted later = unsold
  - disappeared before the auction date = withdrawn
  - never seen again = likely sold
- Portal asking prices are not transactions. For high-conviction deals, check Brickz / NAPIC transacted prices (the link is on every card) and put them in `manual_comps.csv`.
- This is a research tool, not financial advice.

PropertyGuru parsing paths are based on the MIT-licensed [propertyguru-mcp](https://github.com/kkukoo/propertyguru-mcp).
Scraping may conflict with a portal's terms of use. The tracker requests slowly and caches aggressively; keep it that way.
