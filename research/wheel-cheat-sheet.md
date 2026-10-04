# Wheel Strategy Cheat Sheet (one page)

> Educational, not personalized advice. Greek values come from your broker's option chain; the Uber numbers below are model estimates.

## 1. Before you sell any put (all must pass)
1. **Would I own 100 shares at this strike for years?** Moat score ≥ 75 for core names. Satellites like UBER (72) get small size only.
2. **Strike ≤ my value "buy-below" price**, ideally just under clear support.
3. **Size:** collateral ≤ **35% of the account** (under $30k) or **≤ 20%** (over $30k). Cash only, **no margin**.
4. **No earnings before expiry.** Earnings belong to a separate, deliberate trade.
5. **Not in freefall:** price at support or above its 50-day moving average.
6. **Liquidity:** open interest ≥ 500 at the strike; bid-ask ≤ ~10% of the premium.
7. **Pay:** ≥ **12% annualized** on collateral = (premium ÷ collateral) × (365 ÷ days).
8. **Order:** Sell to Open, **limit at the mid price**.

## 2. The Greeks: what a good short put looks like
| Greek | What it tells you | Target for a good trade | Uber Oct 30 $62.50 put (estimate) |
|---|---|---|---|
| **Delta** | ≈ chance the option ends in the money; also how many shares of exposure you have | **Puts −0.20 to −0.30** (−0.15 to −0.20 in downtrends or high volatility). **Calls +0.15 to +0.30**, strike ≥ cost basis | −0.18 → ~18% chance; you're "long" ~18 shares |
| **Probability of touch** | ≈ 2 × delta: the chance the price touches your strike before expiry | Expect to be tested about twice as often as assigned. Don't panic | ~37% |
| **Theta** | Premium you earn per day from time decay (positive for sellers) | Positive; meaningful vs premium. Decay speeds up in the last ~30–45 days | +$3.70/day (~5% of premium/day) |
| **Gamma** | How fast delta (your risk) changes when the stock moves | **Keep it low:** avoid being near the money in the last ~1–3 weeks → close at 21 days left (45-day trades) or 5–7 days left (short trades) | Low now; rises sharply near expiry |
| **Vega** | P&L change per +1 point of implied volatility (negative for sellers) | **Sell when volatility is high, profit when it falls.** Don't hold short options through a volatility ramp (pre-earnings) | −$4.80 per +1 vol point |
| **IV / IV rank** | How expensive options are vs their own past year | **IV rank ≥ 25–30** preferred. VIX 20–30 is normal; **VIX > 30 → half size, delta ≤ 0.20** | IV rank ~64 ✔ |
| Rho | Interest-rate sensitivity | Ignore for 30–45-day trades | — |

## 3. Choosing the date and strike
- **Date:** **30–45 days**, or the **last expiry before earnings** if that's ≥ ~21 days. If earnings sit inside, **wait until after earnings** and sell then. Don't sell a longer-dated option intending to close it before earnings: the earnings premium makes the buyback expensive.
- **Strike:** just below support, at your value price, at delta −0.20 to −0.30.
- **Stagger expiries** across positions.

## 4. Managing the trade
| Situation | Rule |
|---|---|
| Right after the fill | Place a good-till-cancelled **buy-to-close at 50% profit** |
| 45-day trades | **Close at 50% profit or at 21 days left**, whichever comes first |
| Short (~25-day) trades | Close at 50%, or with **5–7 days left** if near the strike. Never into earnings week |
| Remaining annualized return < ~8–10% | Close and redeploy |
| Put goes in the money, thesis intact | **Lever 1:** roll down and out ≤ 1–3 months for a **net credit** → **Lever 2:** same strike, further out, for a credit → **Lever 4:** take the shares |
| Never | Roll for a debit · roll more than ~3 months out · **add contracts (Lever 3)** · use margin |
| Thesis breaks (bad news) | Close at a loss. Don't wheel a broken company |

## 5. After assignment: covered calls
- Sell calls **after earnings**, **strike ≥ cost basis**, delta **0.15–0.30**, 30–45 days.
- Core or deep-value holdings: delta ≤ 0.15–0.20, or no calls at all. Keep the upside.
- Stock far below cost: stop selling calls rather than lock in a loss.
- **Watch ex-dividend dates:** in-the-money calls get exercised early.
- If called away, start again with a put. Don't chase the stock higher.

## 6. Mindset and reality
- The wheel has the **same downside as owning the stock, with capped upside.** Premiums don't erase losses (Big ERN).
- Realistic return: **~8–15% a year** over a full cycle. It lags in strong bull markets and loses money in crashes.
- Paper-trade first. Log every trade: strike, credit, breakeven, cost basis, exit rule.

## 7. Your current plan (Oct 2026)
- **Value buying:** AON on Monday, limit ≤ $275 (SPGI ≤ $390 if AON opens above $290).
- **Uber put:** **Sell 1 UBER Oct 30 $62.50 put**, limit ~$0.75–0.90, good-till-cancelled close at 50%, out before Nov 3 earnings.
  - If assigned: effective cost ~$61.74, good value against ~$83 weighted fair value. Sell calls after earnings at ≥ $67.50.
  - If not assigned: sell a **Dec 18 put** (~44 days, delta 0.20–0.25) after Nov 3.
- **Size check:** $6,250 of collateral fits only if total investable money is ≥ ~$18k.
