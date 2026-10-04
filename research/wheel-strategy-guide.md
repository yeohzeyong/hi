# The Wheel Strategy: A Value Investor's Guide (October 2026)

**Your position:** 11 MSFT (~$517), 4 GOOG (~$340), $1,500 cash, adding $1,500 a month.

> Educational, not personalized advice. Option premiums below are **Black-Scholes estimates** (assumed volatility shown, risk-free rate 3.75%, Nov 20, 2026 expiry, ~47 days). Real quotes will differ, so check your broker's option chain before trading.

---

## 1. The reality check: one contract = 100 shares
| What you'd do | What it requires | Your status |
|---|---|---|
| Sell covered calls on MSFT | 100 shares (~$51,750) | You have 11 → **89 short (~$46,000)** |
| Sell covered calls on GOOG | 100 shares (~$34,000) | You have 4 → **96 short (~$32,700)** |
| Cash-secured put on AON, $255 strike | $25,500 cash | $1,500 → **not possible** |
| Cash-secured put on SPGI, $365 strike | $36,500 cash | not possible |
| Cash-secured put on GOOG, $315 strike | $31,500 cash | not possible |
| Cash-secured put with $1,500 | Strike ≤ **$15** | Possible, but only on low-priced stocks |

**Don't wheel stocks under $15 just because you can afford them.** Their premiums look juicy *because* the risk is high. Selling puts on businesses you wouldn't own breaks the value discipline everything else in this plan rests on. A put obligates you to buy the stock.

---

## 2. How the wheel works (example: AON at $269.45, assumed volatility ~30%)

### Step 1: Sell a cash-secured put (CSP)
- Sell **1 AON Nov 20 $255 put** for ≈ **$5.09 → $509 collected**. Set aside $25,500 as collateral.
- That is ~2.0% in 47 days (~15% annualized). Delta about −0.27, so roughly a 30% chance of ending below $255.
- **This is your strong-buy price from the AON plan ($255).** You get paid to wait for the price you already wanted.

### Step 2a: AON finishes above $255 → keep $509, sell another put. Repeat.

### Step 2b: AON finishes below $255 → you buy 100 shares at $255
- Effective cost = $255 − $5.09 = **$249.91**, about 7% below today's price.

### Step 3: Sell covered calls on the 100 shares
- With AON at $255, sell **1 call at $275 (30–45 days out)** for ≈ **$3.77 → $377**. The strike stays **above your cost basis**.
- **If AON finishes below $275:** keep the premium and sell another call.
- **If AON finishes above $275:** the shares are sold ("called away") at $275. Your profit is ($275 − $249.91) + $3.77 ≈ **$28.86/share (~$2,886, ~11.5%)**. Go back to Step 1.

### Illustrative premiums (estimates, Nov 20 expiry)
| Trade | Volatility used | Premium | Delta | % of strike | Annualized |
|---|---|---|---|---|---|
| AON $250 put | 30% | $371 | −0.21 | 1.5% | ~11.5% |
| AON $255 put | 30% | $509 | −0.27 | 2.0% | ~15.5% |
| SPGI $365 put | 27% | $578 | −0.25 | 1.6% | ~12.3% |
| GOOG $315 put | 32% | $521 | −0.22 | 1.7% | ~12.8% |
| MSFT $560 call (if you had 100 sh) | 28% | $723 | +0.25 | 1.3% | ~10.0% |
| GOOG $370 call (if you had 100 sh) | 32% | $595 | +0.27 | 1.6% | ~12.5% |
| SCHD $32 put (~$33 ETF) | 15% | $27 | −0.25 | 0.8% | ~6.5% |

**Earnings fall inside this window:** AON ~Oct 23, SPGI ~Oct 28, MSFT and GOOG ~Oct 28. Premiums are higher because the risk of a large move is higher.

---

## 3. The rules
**Choosing the stock**
1. Only wheel stocks you'd happily own for 10 years **at the strike price**: SPGI, AON, AXP, V, BRK.B, and GOOG/MSFT at the right price.
2. Set put strikes **at or below your "buy below" price** from the value plan. The premium then pays you to place a limit order you wanted anyway.

**Selling puts**
3. Use **0.20–0.30 delta**, **30–45 days to expiry**.
4. **Close at 50% of the maximum profit** (buy the option back), then sell a new one. This frees capital and cuts tail risk.
5. **Avoid earnings** inside the window, or drop to ~0.15 delta if you do hold through them.
6. **If the price falls toward your strike:** either take assignment (you wanted the stock), or roll down and out **only for a net credit**. Never pay to roll.

**Selling calls**
7. Strike **≥ cost basis**. Never lock in a loss.
8. For deep-value positions you want to keep (AON at $255, for example), use **low delta (0.10–0.20)** or skip calls entirely. Calls cap your upside exactly when the market recognizes the value.

**Risk control**
9. **Cash-secured only.** No margin, no naked options, no leverage.
10. Keep one name at **≤ 25–30%** of the account.

**What to expect, honestly**
- **Typical returns:** ~8–15% a year in flat-to-rising markets. The wheel **lags buy-and-hold in strong rallies**, because calls get exercised and you lose the upside.
- **In a crash** you still own the stock. The premium only cushions ~1.5–2% a month. The wheel is not lower-risk than owning the stock: you take the **same downside with capped upside**, paid for with the premiums.

---

## 4. Your plan
### Now ($1,500)
- **Don't start the wheel yet.** Use the $1,500 for the Monday AON purchase as planned (limit ≤ $275; SPGI ≤ $390 if AON opens above $290).
- **Paper-trade the wheel for 2–3 months.** Most brokers offer a simulated account. Run AON and SPGI puts there to learn assignment, rolling and closing at 50% before risking money.

### Paths to your first real contract
| Path | Capital | Time at $1,500/mo | Notes |
|---|---|---|---|
| **A. Training wheels: SCHD** (100 quality dividend payers, ~$33) | ~$3,200 per put | ~1–2 months | Low risk, low premium (~6.5% annualized), wider spreads. Good for learning mechanics |
| **B. First real wheel: AON** CSP at ≤ $255 | ~$25,500 (keep in a T-bill ETF while waiting) | ~16–17 months | Matches the value plan. Interest on the collateral adds ~3–4% |
| **C. Buy shares until you reach 100, then covered calls** | ~$27,000 (AON) | ~18 months | Simplest. Value buying continues uninterrupted |

### What not to do
- **Don't** buy 89 more MSFT or 96 more GOOG just to wheel them. Both are fairly priced (~25x and ~23x), not undervalued. Keep your 11 MSFT and 4 GOOG as long-term holdings.
- **Don't** sell puts on sub-$15 "cheap" stocks to make the numbers work.
- **Don't** use defined-risk **put spreads** until you've paper-traded. An AON $255/$245 spread collects ~$222 against ~$778 maximum loss (estimated). That fits your budget, but it isn't a wheel: you can't take assignment, and early assignment needs active handling.

### Before your first live trade
- Your broker must approve you for options (usually level 1–2: covered calls and cash-secured puts).
- Check the bid-ask spread. Use limit orders at the mid price and avoid illiquid strikes.
- Know your expiry-day process and how your broker handles assignment.
- **Tax:** if you're a non-US investor, US option premiums generally aren't subject to US withholding the way dividends are, but your local tax rules apply. Confirm with a tax adviser.

## Sources
- Earnings dates: AON ~Oct 23 ([Barchart](https://www.barchart.com/story/news/35299313/aon-s-quarterly-earnings-preview-what-you-need-to-know)), SPGI ~Oct 28 ([Earnings Whispers](https://beta.earningswhispers.com/go/w/SPGI)), MSFT and GOOG ~Oct 28 (estimated; [MarketScreener](https://in.marketscreener.com/quote/stock/MICROSOFT-CORPORATION-4835/calendar/), [Wall Street Horizon](https://www.wallstreethorizon.com/alphabet-earnings-calendar))
- AON volatility history: [FlashAlpha](https://flashalpha.com/stock/aon/iv) (ATM ~25–28% over May–Jul 2026); SCHD price: [Digrin](https://www.digrin.com/stocks/detail/SCHD/price)
