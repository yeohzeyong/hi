"""Generate the dashboard (docs/index.html), CSV and Markdown shortlist."""

from __future__ import annotations

import csv
import html
import json
from datetime import datetime

from .config import DOCS_DIR
from .scoring import GRADE_ORDER


def _slim(ev: dict) -> dict:
    """Drop bulky debug fields but keep a few kept/removed comps for audit."""
    out = {k: v for k, v in ev.items() if k != "comps_debug"}
    dbg = ev.get("comps_debug") or {}
    out["audit"] = {
        kind: {
            "raw": d.get("raw_count", 0),
            "crit": d.get("criteria", ""),
            "kept": [{"p": c["price"], "s": c["built_up"], "t": c.get("title", "")[:60], "u": c.get("url", ""),
                      "src": c.get("portal", ""), "m": c.get("match", "")} for c in d.get("kept", [])[:12]],
            "removed": [{"p": c.get("price"), "s": c.get("built_up"), "t": c.get("title", "")[:60],
                         "r": c.get("reason", "")} for c in d.get("removed", [])[:12]],
        } for kind, d in dbg.items() if kind in ("sale", "rent") and isinstance(d, dict)
    }
    return out


def write_csv(results: list[dict], path):
    cols = ["grade", "verdict", "score", "area", "building", "built_up", "reserve_price", "price_psf", "auction_date",
            "market_value", "discount", "rent_estimate", "installment", "maintenance", "rent_cover",
            "max_bid", "station", "walk_m", "dual_key", "rounds", "flags", "url"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for e in results:
            l, f, st = e["listing"], e["finance"], e.get("station") or {}
            w.writerow([e["grade"], (e.get("verdict") or {}).get("action"), e["score"], l["area_label"], l["building"], l["built_up"], l["reserve_price"],
                        f.get("price_psf"), l["auction_date"], e["market_value"], f.get("discount"),
                        e["rent_estimate"], f.get("installment"), f.get("maintenance"), f.get("rent_cover"),
                        e["max_bid"].get("max_bid"), st.get("name"), st.get("walk_m"), l["dual_key"],
                        e["unit_history"].get("rounds"), "; ".join(e["cons"][:3]), l["url"]])


def write_markdown(results: list[dict], path, min_grade: str):
    keep = [e for e in results if GRADE_ORDER[e["grade"]] >= GRADE_ORDER[min_grade] and e["status"] == "ok"]
    lines = [f"# Auction shortlist - {datetime.now():%d %b %Y}", "",
             f"{len(keep)} listing(s) graded {min_grade} or better out of {len(results)} evaluated.", ""]
    for e in keep:
        l, f = e["listing"], e["finance"]
        lines += [f"## [{e['grade']}] {l['building'] or l['title']} - {l['area_label']}",
                  f"- Reserve **RM{l['reserve_price']:,.0f}** ({l['built_up']:,.0f} sqft, RM{f.get('price_psf')} psf), "
                  f"auction {l['auction_date'] or 'TBC'}",
                  f"- **{(e.get('verdict') or {}).get('action', '')}**: {(e.get('verdict') or {}).get('text', '')}",
                  *[f"- ✅ {p}" for p in e["pros"]], *[f"- ⚠️ {c}" for c in e["cons"]],
                  f"- {l['url']}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_html(results: list[dict], bstats: dict, cfg: dict, path):
    data = json.dumps({"generated": datetime.now().strftime("%d %b %Y %H:%M"),
                       "results": [_slim(e) for e in results],
                       "buildings": bstats,
                       "targets": cfg["targets"], "finance": cfg["finance"],
                       "criteria": {"areas": list(cfg["search"]["areas"]),
                                    "min_sqft": cfg["search"]["min_built_up_sqft"]}},
                      default=str)
    # Listing text scraped from portals can contain "<!--", "<script" or
    # "</script>", which would break the inline <script>. Escape the
    # characters HTML cares about; JSON/JS read them back unchanged.
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    path.write_text(TEMPLATE.replace("__DATA__", data), encoding="utf-8")


def generate(results: list[dict], bstats: dict, cfg: dict, out_dir=None):
    out_dir = out_dir or DOCS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    write_html(results, bstats, cfg, out_dir / "index.html")
    write_csv(results, out_dir / "shortlist.csv")
    write_markdown(results, out_dir / "shortlist.md", cfg["scoring"].get("shortlist_min_grade", "B"))
    (out_dir / ".nojekyll").write_text("")
    return out_dir / "index.html"


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Auction Deal Tracker</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--muted:#5d6470;--line:#e3e6eb;--accent:#0f6fde;
--a:#0a8a4a;--b:#3a7bd5;--c:#b7791f;--d:#9aa1ab;--bad:#c0392b;--chip:#eef1f5}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1115;--card:#171a20;--ink:#e8eaee;
--muted:#9aa3b0;--line:#2a2f38;--accent:#5aa2ff;--a:#2ecc71;--b:#6aa5ff;--c:#e0a84a;--d:#6b7380;--bad:#ff6b5b;--chip:#222730}}
:root[data-theme="dark"]{--bg:#0f1115;--card:#171a20;--ink:#e8eaee;--muted:#9aa3b0;--line:#2a2f38;--accent:#5aa2ff;
--a:#2ecc71;--b:#6aa5ff;--c:#e0a84a;--d:#6b7380;--bad:#ff6b5b;--chip:#222730}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:20px 16px 8px;max-width:1200px;margin:auto}h1{margin:0 0 4px;font-size:22px}
.sub{color:var(--muted)}main{max-width:1200px;margin:auto;padding:0 16px 40px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.kpi b{display:block;font-size:20px}.kpi span{color:var(--muted);font-size:12px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0}
select,input,button{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
.tabs button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;margin:10px 0;overflow:hidden}
.row{display:grid;grid-template-columns:44px 1fr auto;gap:12px;padding:12px 14px;cursor:pointer;align-items:center}
.g{width:40px;height:40px;border-radius:10px;display:grid;place-items:center;font-weight:700;color:#fff;font-size:18px}
.gA{background:var(--a)}.gB{background:var(--b)}.gC{background:var(--c)}.gD,.gQ{background:var(--d)}
.t{font-weight:600}.m{color:var(--muted);font-size:12.5px}.nums{text-align:right;white-space:nowrap}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}.chip{background:var(--chip);border-radius:999px;padding:1px 8px;font-size:12px}
.chip.good{color:var(--a)}.chip.bad{color:var(--bad)}
.detail{display:none;border-top:1px solid var(--line);padding:12px 14px}.card.open .detail{display:block}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
table{border-collapse:collapse;width:100%}td{padding:3px 0;border-bottom:1px dashed var(--line)}td:last-child{text-align:right}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:6px 0}
ul{margin:4px 0;padding-left:18px}a{color:var(--accent)}.links{display:flex;flex-wrap:wrap;gap:4px 12px}.links a{white-space:nowrap}
.v{display:inline-block;font-weight:700;font-size:12px;border-radius:6px;padding:1px 7px;margin-right:6px;color:#fff}
.vBID{background:var(--a)}.vWAIT{background:var(--c)}.vPASS{background:var(--d)}.vVERIFY{background:var(--b)}
.verdict{padding:8px 14px;border-top:1px solid var(--line);font-size:13px}
.empty{padding:30px;text-align:center;color:var(--muted)}
.tbl{overflow-x:auto}.tbl table td,.tbl table th{padding:6px 8px;text-align:left;border-bottom:1px solid var(--line)}
@media (max-width:600px){.row{grid-template-columns:40px 1fr}.nums{grid-column:2;text-align:left}}
</style>
</head>
<body>
<header>
  <h1>Auction Deal Tracker</h1>
  <div class="sub" id="sub"></div>
</header>
<main>
  <div class="kpis" id="kpis"></div>
  <div class="card" id="banner" hidden style="padding:12px 14px;border-color:var(--c)"></div>
  <div class="bar tabs"><button data-tab="deals" class="on">Deals</button><button data-tab="history">Building auction history</button><button data-tab="method">How it scores</button></div>
  <section id="deals">
    <div class="bar">
      <select id="fGrade"><option value="">All grades</option><option value="A">A only</option><option value="AB" selected>A + B</option><option value="ABC">A-C</option></select>
      <select id="fArea"><option value="">All areas</option></select>
      <label><input type="checkbox" id="fDual"> Dual key</label>
      <label><input type="checkbox" id="fCover"> Rent covers costs</label>
      <select id="fSort"><option value="score">Sort: score</option><option value="date">Auction date</option><option value="cover">Rent cover</option><option value="disc">Discount</option><option value="walk">Walk to rail</option></select>
      <input id="fText" placeholder="Search building..." size="16">
    </div>
    <div id="list"></div>
  </section>
  <section id="history" hidden><div class="tbl" id="hist"></div></section>
  <section id="method" hidden><div class="card" style="padding:14px" id="meth"></div></section>
</main>
<script>
const D = __DATA__;
const $ = s => document.querySelector(s);
const rm = v => v == null ? "-" : "RM" + Math.round(v).toLocaleString();
const pct = v => v == null ? "-" : (v * 100).toFixed(0) + "%";
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const R = D.results.filter(e => e.status === "ok");
$("#sub").textContent = `Updated ${D.generated} · ${D.criteria.areas.join(", ")} · ≥${D.criteria.min_sqft} sqft`;
const cnt = g => R.filter(e => e.grade === g).length;
$("#kpis").innerHTML = [["A deals", cnt("A")], ["B deals", cnt("B")], ["Active listings evaluated", R.length],
  ["Need data (?)", cnt("?")]].map(([k, v]) => `<div class="kpi"><b>${v}</b><span>${k}</span></div>`).join("");
const noPrice = cnt("?");
if (noPrice && noPrice >= R.length / 2) {
  $("#banner").hidden = false;
  $("#banner").innerHTML = `<b>Market prices missing for ${noPrice} of ${R.length} units.</b> PropertyGuru/iProperty block GitHub's servers, so rent and value come from your PC: double-click <code>run_local.bat</code> (weekly). Until then units show grade "?" with reserve price, size and MRT distance only.`;
}
if (!R.some(e => e.grade === "A" || e.grade === "B")) $("#fGrade").value = "";
[...new Set(R.map(e => e.listing.area_label))].sort().forEach(a => $("#fArea").insertAdjacentHTML("beforeend", `<option>${esc(a)}</option>`));

function lowyat(e) {
  const f = e.forum;
  if (!f) return "";
  if (!f.snippets.length) return `<h3 style="margin-top:12px">What owners say on Lowyat</h3><div class="m">No Lowyat discussion found for this building.</div>`;
  const icon = { negative: "🔴", positive: "🟢", neutral: "⚪" };
  return `<h3 style="margin-top:12px">What owners say on Lowyat</h3><ul>${f.snippets.map(s =>
    `<li>${icon[s.tone] || ""} <span class="m">[${esc(s.topics.join(", "))}${s.date ? " · " + esc(s.date) : ""}]</span> “${esc(s.text)}” <a href="${esc(s.url)}" target="_blank" rel="noopener">thread</a></li>`).join("")}</ul>`;
}
function card(e) {
  const l = e.listing, f = e.finance || {}, st = e.station, b = e.max_bid || {};
  const g = e.grade === "?" ? "Q" : e.grade, v = e.verdict || {};
  const chips = [];
  if (f.rent_cover != null) chips.push([`cover ${f.rent_cover.toFixed(2)}x`, f.rent_cover >= D.targets.min_rent_cover]);
  if (f.discount != null) chips.push([`${pct(f.discount)} below mkt`, f.discount >= D.targets.min_discount]);
  if (st) chips.push([`${st.walk_m}m ${st.type} ${st.name}`, st.walk_m <= 800]);
  const pd = e.parts || {};
  if (pd.rental_demand != null) chips.push([`rental demand ${pd.rental_demand >= 10 ? "high" : pd.rental_demand >= 6 ? "medium" : "low"}`, pd.rental_demand >= 6]);
  if (pd.resale != null) chips.push([`resale ${pd.resale >= 7 ? "good" : pd.resale >= 4 ? "fair" : "weak"}`, pd.resale >= 4]);
  if (l.dual_key) chips.push(["dual key", true]);
  if ((e.unit_history || {}).rounds > 1) chips.push([`round ${e.unit_history.rounds}`, true]);
  if (e.low_confidence) chips.push(["low data confidence", false]);
  const up = f.upfront || {};
  const audit = k => { const a = (e.audit || {})[k]; if (!a) return "<i>none fetched</i>";
    return `${a.kept.length} similar of ${a.raw} found${a.crit ? `<br><span class="m">matched on: ${esc(a.crit)}</span>` : ""}<br><details><summary>see comps</summary><b>Kept</b><ul>${a.kept.map(c => `<li>${rm(c.p)} · ${c.s} sqft · <a href="${esc(c.u)}" target="_blank">${esc(c.t || c.src)}</a>${c.m ? `<br><span class="m">${esc(c.m)}</span>` : ""}</li>`).join("")}</ul><b>Removed</b><ul>${a.removed.map(c => `<li>${rm(c.p)} · ${c.s ?? "?"} sqft · ${esc(c.r)}</li>`).join("")}</ul></details>`; };
  const ev = (e.unit_history || {}).events || [];
  return `<div class="card"><div class="row" onclick="this.parentNode.classList.toggle('open')">
    <div class="g g${g}">${e.grade}</div>
    <div><div class="t">${esc(l.building || l.title)} <span class="m">· ${esc(l.area_label)} · ${esc(l.property_type)}</span></div>
      <div class="m">${Math.round(l.built_up || 0).toLocaleString()} sqft${l.bedrooms ? ` · ${l.bedrooms}BR` : ""} · ${esc(l.tenure || "tenure ?")} · auction ${esc(l.auction_date || "TBC")} · score ${e.score}</div>
      <div class="chips">${chips.map(([t, ok]) => `<span class="chip ${ok ? "good" : "bad"}">${esc(t)}</span>`).join("")}</div></div>
    <div class="nums"><div class="t">${rm(l.reserve_price)}</div><div class="m">${f.price_psf ? "RM" + f.price_psf + " psf" : ""}</div>
      <div class="m">max bid <b>${rm(b.max_bid)}</b></div></div></div>
    ${v.action ? `<div class="verdict"><span class="v v${v.action}">${v.action}</span>${esc(v.text)}</div>` : ""}
    <div class="detail"><div class="cols">
      <div><h3>Why</h3><ul>${e.pros.map(p => `<li>✅ ${esc(p)}</li>`).join("")}${e.cons.map(c => `<li>⚠️ ${esc(c)}</li>`).join("")}${e.notes.map(n => `<li>ℹ️ ${esc(n)}</li>`).join("")}</ul></div>
      <div><h3>Monthly at reserve</h3><table>
        <tr><td>Est. rent (cleaned)</td><td>${rm(e.rent_estimate)}</td></tr>
        <tr><td>Installment (${pct(D.finance.loan_margin)} loan, ${(D.finance.interest_rate * 100).toFixed(2)}%, ${D.finance.tenure_years}y)</td><td>${rm(f.installment)}</td></tr>
        <tr><td>Maintenance + sinking</td><td>${rm(f.maintenance)}</td></tr><tr><td>Quit rent / assessment / insurance</td><td>${rm(f.other_monthly)}</td></tr>
        <tr><td>Cash flow after 1-mth vacancy</td><td>${rm(f.monthly_cashflow)}</td></tr>
        <tr><td>Gross / net yield</td><td>${pct(f.gross_yield)} / ${pct(f.net_yield)}</td></tr></table>
        <h3>Valuation</h3><table><tr><td>Market value (cheaper ${Math.round(((e.sale_comps || {}).valuation_quantile || .25) * 100)}% of similar units)</td><td>${rm(e.market_value)}</td></tr>
        ${(e.sale_comps || {}).cheapest_equiv ? `<tr><td>Cheapest similar unit on market (size-adjusted)</td><td><a href="${esc(e.sale_comps.cheapest.url)}" target="_blank" rel="noopener">${rm(e.sale_comps.cheapest_equiv)}</a></td></tr>` : ""}
        <tr><td>Walk-away bid</td><td><b>${rm(b.max_bid)}</b> (${esc(b.binding || "-")})</td></tr>
        ${Object.entries(b.caps || {}).map(([k, v]) => `<tr><td>&nbsp;cap by ${k}</td><td>${rm(v)}</td></tr>`).join("")}</table></div>
      <div><h3>Cash needed</h3><table>${Object.entries(up).map(([k, v]) => `<tr><td>${k.replace(/_/g, " ")}</td><td>${rm(v)}</td></tr>`).join("")}
        <tr><td><b>Total</b></td><td><b>${rm(f.cash_needed)}</b></td></tr><tr><td>10% deposit on auction day</td><td>${rm(f.deposit_on_auction_day)}</td></tr></table>
        <h3>Auction history (this unit)</h3>${ev.length ? `<ul>${ev.map(x => `<li>${esc(x.date)} · ${rm(x.price)} · ${esc(x.outcome || "")}</li>`).join("")}</ul>` : "<i>first time seen</i>"}</div>
      <div><h3>Sale comps</h3>${audit("sale")}<h3>Rent comps</h3>${audit("rent")}
        ${(() => { const m = e.market_ctx || {}; const bits = [];
          if (m.built_year) bits.push(`built ${m.built_year}`);
          if (m.area_sale_psf) bits.push(`area sale RM${m.area_sale_psf.toFixed(0)} psf`);
          if (m.area_rent_psf) bits.push(`area rent RM${m.area_rent_psf.toFixed(2)} psf`);
          if (m.trend) bits.push(`price trend ${(m.trend.pct * 100).toFixed(1)}% / ${m.trend.days}d`);
          return bits.length ? `<h3>Building vs area</h3><div class="m">${bits.map(esc).join(" · ")}</div>` : ""; })()}
        <h3>Listing</h3><div class="m">${esc(l.address)}<br>${esc(l.title_type)} ${l.bumi ? "· Bumi lot" : ""}<br>${esc(l.bank)} ${esc(l.auctioneer)}
        ${(l.also_listed || []).length ? `<br>Also listed: ${l.also_listed.map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener">${i + 1}</a>`).join(" ")}` : ""}</div></div>
    </div>${lowyat(e)}<div class="links" style="margin-top:10px">${Object.entries(e.links || {}).map(([k, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${k.replace(/_/g, " ")}</a>`).join("")}</div></div></div>`;
}
function render() {
  const g = $("#fGrade").value, a = $("#fArea").value, t = $("#fText").value.toLowerCase();
  let rows = R.filter(e => (!g || g.includes(e.grade)) && (!a || e.listing.area_label === a)
    && (!$("#fDual").checked || e.listing.dual_key) && (!$("#fCover").checked || (e.finance.rent_cover || 0) >= D.targets.min_rent_cover)
    && (!t || (e.listing.building + " " + e.listing.title).toLowerCase().includes(t)));
  const s = $("#fSort").value, k = {
    score: e => -e.score, date: e => e.listing.auction_date || "9", cover: e => -(e.finance.rent_cover || 0),
    disc: e => -(e.finance.discount ?? -9), walk: e => (e.station || {}).walk_m ?? 1e9 }[s];
  rows.sort((x, y) => k(x) < k(y) ? -1 : k(x) > k(y) ? 1 : 0);
  $("#list").innerHTML = rows.length ? rows.map(card).join("") : `<div class="empty">No listings match. Loosen the filters, or wait for tomorrow's run.</div>`;
}
document.querySelectorAll("#deals select, #deals input").forEach(el => el.addEventListener("input", render));
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
  document.querySelectorAll(".tabs button").forEach(x => x.classList.toggle("on", x === b));
  ["deals", "history", "method"].forEach(id => $("#" + id).hidden = id !== b.dataset.tab); });
const H = Object.entries(D.buildings).sort((a, b) => b[1].events - a[1].events);
$("#hist").innerHTML = H.length ? `<table><tr><th>Building</th><th>Auction events</th><th>Units</th><th>Last 12m</th><th>Median reserve psf</th><th>Likely-sold psf</th><th>Sell-through</th></tr>${H.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v.events}</td><td>${v.units}</td><td>${v.last_12m}</td><td>${v.median_reserve_psf ?? "-"}</td><td>${v.sold_psf ?? "-"}</td><td>${v.sell_through == null ? "-" : pct(v.sell_through)}</td></tr>`).join("")}</table>` : `<div class="empty">History builds up with every daily run (run <code>scrape --backfill</code> once to seed it).</div>`;
$("#meth").innerHTML = `<p><b>Score (0-100)</b> = rent cover (30) + discount to market (25) + rental demand (15) + resale potential (10) + walk to MRT/LRT/Monorail (10) + dual key (5) + auction history (5).</p>
<p><b>Market value</b> is set on the <i>cheaper end</i> of genuinely similar units (lower quartile, same type, bedrooms and size), and each unit shows the cheapest similar unit already for sale - an auction should beat it, since you take on unknown condition.</p>
<p><b>Rental demand</b>: building rental yield, how many similar units are offered for rent, rent vs the area, unit size, rail access. <b>Resale potential</b>: building age, freehold, building price vs the area (catch-up room) and the tracked price trend. <b>Lowyat</b> comments are shown on each card; repeated complaints about water, flooding, security, lifts or management are flagged.</p>
<p><b>A</b> needs score ≥ 70 <i>and</i> rent ≥ ${D.targets.min_rent_cover}× (installment + maintenance + other) <i>and</i> ≥ ${pct(D.targets.min_discount)} below market <i>and</i> enough clean comps. Otherwise B ≥ 55, C ≥ 40.</p>
<p><b>Market data hygiene</b>: portal listings mentioning auction/lelong/below-market, room rentals, stale ads, duplicates across agents and portals, wrong unit sizes, bait lowballs and statistical outliers are removed; asking prices are haircut toward transacted levels. Open any deal and expand "see comps" to audit what was kept and dropped.</p>
<p><b>Verdict</b>: <b>BID</b> = targets met at reserve, bid up to the walk-away price. <b>WAIT</b> = not worth it now, but a typical 10% cut next round would make it work. <b>PASS</b> = doesn't work even after a cut. <b>VERIFY</b> = looks good but the data is thin or the discount is suspiciously deep.</p>
<p><b>Walk-away bid</b> = the highest price that still meets both the rent-cover and discount targets after a ${D.finance.repair_buffer_psf} RM/sqft repair buffer. Never bid above it.</p>`;
render();
</script>
</body>
</html>
"""
