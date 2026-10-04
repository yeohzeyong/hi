# Our Wheel Playbook — Rules Synthesized from 5 Options Books + Professional Practice

**Sources studied:**
- Freeman Publications, *The Options Wheel Strategy*
- Kevin Smith, *A Simple Guide to Selling Options* and *The 90-Minute Guide to Selling Options*
- Ned Jenkins, *Options Trading Strategies*
- Benjamin Ray, *Options Trading Strategies (Bears)*

Where the books disagree, this note states the conflict and the rule we use.

> Educational, not personalized financial advice. Options can lose money quickly. Paper-trade first.

---

## 1. What the books agree on
| Rule | Freeman | Smith | Jenkins / Ray |
|---|---|---|---|
| Only wheel stocks you're happy to own at the strike | ✔ "Do not make the mistake of writing CSPs on random stocks" | ✔ Quality dividend companies that "dominate their industries" | ✔ "Never sell naked puts in a constantly declining market" |
| No margin, ever | ✔ "DON'T do it" | ✔ cash-secured | ✔ "Investing more than you can" listed as a classic mistake |
| 21–45 days to expiry | ✔ 21–45 | ✔ "sweet spot 18–45" | — |
| Delta about 0.20–0.30 | Uses delta as the probability guide | ✔ "between −0.20 and −0.30" | — |
| Take profits early | ✔ **50% profit or 21 days to expiry, whichever comes first** (Spintwig backtest) | ✔ 50/85/90% rules, plus an annualized-return-remaining test | ✔ "Have pre-planned exit strategies" |
| Avoid earnings | ✔ Screen for "no earnings in the next 30 days" | ✔ "Try to avoid writing options over earnings" | ✔ Check for events in the option's life |
| Avoid penny / hyped stocks | ✔ | ✔ Market cap > $40B; avoid energy and mining | ✔ |
| Use limit orders | ✔ | ✔ | — |
| Never roll for a debit | ✔ "Pay attention to the credit and debit terms" | ✔ Every roll must be for a net credit | — |
| Don't double down to recover losses | — | Allows it as an advanced "Lever 3" | ✔ "Piling it on" listed as a classic mistake |

## 2. Where they disagree, and our ruling
| Issue | Book views | **Our rule** |
|---|---|---|
| Put strike | Freeman: near the money (you want the shares). Smith: 0.20–0.30 delta (income first) | **0.25–0.30 delta at or below our value "buy-below" price.** The put is a paid limit order. Use 0.15–0.20 in downtrends or on high-volatility stocks |
| Downtrending stocks | Freeman: avoid freefall; wait for support and price above the 50-day average. Value investing: buy when it's down | **Sell puts only once price has stabilized at clear support** (e.g., AON ~$255–260, UBER ~$65). Otherwise just buy shares in tranches |
| Stock screen | Smith: P/E < 20, dividend 2.5–6%, dividend cover > 2x, 10+ years of dividend growth | **Our moat score ≥ 75** (from the top-5 model) **plus P/E reasonable for its quality.** Dividends are a bonus, not a requirement (SPGI and V yield ~1%) |
| Position size | Freeman: CSP ≤ 10% of the portfolio (≤ 35% for accounts under $30k). Smith: 5–10% per trade | **≤ 35% of the account per CSP while under $30k; ≤ 20% at $30k and above** |
| Repairing a losing put | Smith's 4 levers: 1) roll down and out; 2) roll out; 3) add contracts; 4) take shares and sell calls | **Levers 1, 2 and 4 only. Lever 3 (adding contracts) is banned** for a small account: it's doubling down |
| High VIX | Freeman: avoid the wheel when VIX > 30 | **VIX 20–30:** normal, the best premiums. **VIX > 30:** half size, delta ≤ 0.20, quality names only |
| Weekly options | Freeman's backtest favors short holding periods; Smith says weeklies raise commissions and stress | **Sell 30–45 days and close early (50% / 21 days).** That captures the backtest benefit without weekly churn |

---

## 3. The rules

### A. Pre-trade checklist (all must pass)
1. **Ownership test:** would I hold 100 shares at this strike for 5–10 years? Moat score ≥ 75.
2. **Size test:** collateral ≤ 35% of the account (under $30k) / ≤ 20% (over $30k).
3. **Event test:** no earnings before expiry. Otherwise delta ≤ 0.15 and a deliberate decision.
4. **Trend test:** price above the 50-day average, *or* at a well-defined support level after stabilizing. Not in freefall (Freeman's ADX < 30–40 is optional).
5. **Volatility test:** implied-volatility rank ≥ 25–30 preferred. VIX rules as above.
6. **Liquidity test:** stock average volume ≥ 1M shares (Freeman's minimum is 200k); option open interest ≥ 500 at the strike; bid-ask spread ≤ ~10% of the premium.
7. **Pay test:** premium ≥ **12% annualized on collateral** (Smith targets 12–24%). Interest earned on collateral is extra.
8. **Order:** limit order at the mid price; adjust by $0.05 if not filled.

### B. Selling puts
- Delta **0.25–0.30**, or 0.15–0.20 when trending down or volatility is high. **30–45 days** to expiry.
- **Close at 50% profit or at 21 days to expiry**, whichever comes first. Also close early if the remaining annualized return falls below ~8–10% (Smith's test: (premium left ÷ days left) × (365 ÷ collateral)).
- **Stagger expirations** (Smith's "time diversification") so not everything rides on one date.

### C. When a put goes against you
1. **Thesis still intact?** If the business is broken, close the put and take the loss. Don't wheel a broken company.
2. **Lever 1:** when only 10–20% of the time value is left, **roll down and out ≤ 1–3 months for a net credit.**
3. **Lever 2:** if Lever 1 can't produce a credit, **roll to the same strike, further out (≤ 3 months), for a net credit.**
4. **Lever 4:** otherwise **take the shares.** You wanted them at this price. Then go to section D.
5. Never pay to roll. Never roll beyond ~3 months. **Never add contracts.**

### D. Covered calls (after assignment, or once a holding reaches 100 shares)
- Strike **≥ cost basis** so you never lock in a loss. Delta **0.15–0.30**, 30–45 days. Sell after earnings, not before.
- **Deep-value or long-term core holdings:** delta **≤ 0.15–0.20**, or don't sell calls at all. The upside is the point of the investment.
- **Repair mode** (stock far below cost): Smith's 0.15-delta calls. Accept small premiums rather than selling calls below cost basis.
- **Watch ex-dividend dates.** In-the-money calls are often exercised early the day before the stock goes ex-dividend.
- **If called away:** start again with a put. Don't chase by buying the stock at a higher price (Freeman: "Don't save stock").

### E. Portfolio and behavior
- **No margin. No naked calls. No penny stocks. No "hot" stocks.**
- Track every trade in a ledger showing **cost basis** (premiums lower it).
- Realistic expectation: **~8–15% a year over a full cycle.** The books' 15–24% figures assume good conditions. Expect to lag buy-and-hold in strong bull markets, and to lose money in crashes (same downside as owning the stock).

---

## 4. Our strategy, phase by phase

**Current account:** 11 MSFT (~$5,693) + 4 GOOG (~$1,361) + $1,500 cash ≈ **$8,550**, adding $1,500 a month.
**Size limit now:** 35% × $8,550 ≈ **$3,000 collateral** → only underlyings ≤ ~$30.

| Phase | Account size | Allowed CSP collateral | What we do |
|---|---|---|---|
| **0: Now to Dec 2026** | ~$8.5–13k | ≤ ~$3–4.5k | **Paper-trade** the wheel on AON, SPGI and UBER using every rule above. Real money keeps going into value stocks (AON on Monday, ≤ $275). |
| **1: Training wheel (early 2027)** | ~$10–15k | ≤ $3.5–5k | Optional first live CSP on **SCHD (~$33)**, a diversified dividend ETF with no single-company earnings risk. Small premium (~0.8%/month); watch the bid-ask spread. The goal is learning the mechanics, not income. |
| **2: First real stock wheel (~mid 2027)** | ≥ ~$18k | ≤ ~$6.3k | **UBER CSP at ≤ $62.50**, delta 0.15–0.20, expiries that avoid earnings. Satellite only (moat score 72). Only if price has stabilized at support. |
| **3: Covered calls on core holdings** | Once any holding reaches 100 shares | — | E.g., AON after ~18 months of buying. Calls at delta ≤ 0.20 above cost basis, or none during deep value. |
| **4: Core value wheel** | ≥ ~$75–125k | ≤ 20–35% | CSPs on AON / SPGI / AXP / V at their buy-below or strong-buy prices. The put becomes a paid limit order for the stock you were going to buy anyway. |

### What we will not do
- Sell puts on sub-$30 junk just to fit the account.
- Wheel MSFT or GOOG by buying 89 or 96 more shares. Both are fairly priced, not cheap.
- Use put spreads before completing 3 months of paper trading. Freeman suggests credit spreads for small accounts; they're defined-risk but need active management and can't be "wheeled".
- Double down (Lever 3), use margin, or roll for debits.

---

## 5. Worked example (paper trade to run now)
**AON** at $269.45, near its 52-week low. Earnings ~Oct 23. Assumed volatility ~30% (estimates, not quotes).
1. **Wait** for AON to hold the $255–265 area *after* Oct 23 earnings. That passes the trend and event tests.
2. **Sell** a ~35–45-day put at **$250–255** (delta ~0.21–0.27) for ≈ **$3.70–5.10** → ~1.5–2.0% in ~6 weeks (~12–15% annualized). That passes the pay test.
3. **Manage:** buy back at ~50% profit or at 21 days to expiry.
4. **If tested:** roll down and out for a credit within 1–3 months, or take the shares at an effective ~$246–250 (inside the strong-buy zone).
5. **After assignment:** sell calls at strike ≥ $255 with delta ≤ 0.20 after earnings, or hold the shares without calls as a deep-value position.

## Sources (books)
- Freeman Publications, *The Options Wheel Strategy*: Ch. 2 (mechanics, 21–45 days), Ch. 4 (candidates: trend, ADX, volume ≥ 200k, above the 50-day average, no earnings within 30 days, avoid penny stocks), Ch. 6 (VIX > 30), Ch. 9 (close at 50% or 21 days per the Spintwig backtest; avoid assignment if short-term; "Don't save stock"), Ch. 10 (≥ $2,500 to start; CSP ≤ 10% of portfolio, ≤ 35% under $30k; no margin)
- Kevin Smith, *A Simple Guide to Selling Options* and *The 90-Minute Guide*: delta −0.20 to −0.30; 18–45 days; 12–24% annualized target, ≤ 2%/month; stock screen (market cap > $40B, P/E < 20, dividend 2.5–6%, cover > 2x, FCF cover > 1, 10+ years of dividend growth); 4 repair levers; roll at 10–20% time value left, for a net credit, ≤ 1–3 months; 0.15-delta repair calls; annualized-return-remaining test; time diversification; limit orders
- Ned Jenkins, *Options Trading Strategies*: never sell puts into a constantly declining market; check events and implied volatility before expiry; discipline and exit plans
- Benjamin Ray, *Options Trading Strategies (Bears)*: Ch. 14 classic mistakes: one-basket risk, investing more than you can afford, "piling it on", no plan, insufficient cash to cover puts; Ch. 21 risk management
