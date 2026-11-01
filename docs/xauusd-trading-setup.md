# XAUUSD day trading with Claude: setup

What is installed in this repo for gold (XAUUSD) day trading, the parts you set up on
your own computer, and the guardrails. Reviewed 2026-11-01.

> Not financial advice. XAUUSD is usually traded as a leveraged CFD, and most retail CFD
> accounts lose money (brokers must publish the share, typically 70%+). Whether you may
> trade it at all depends on your country. Start on a **demo** account.

## 1. Skills installed in `.claude/skills/` (this repo)

| Skill | Source | Use for gold |
|---|---|---|
| `analyze-gold` | Tradecraft @ 760405f | Gold calibration: sessions (London to NY, 08:00-21:00 UTC), ATR-based stop minimum, news gate 30 min before and 60 min after CPI/NFP/FOMC, DXY and real-yield checks, skip conditions. Markdown only. |
| `fxmacrodata-calendar` | tradermonty @ c03eafb | USD release calendar (CPI, NFP, PCE, FOMC...). Public USD rows need no key; `FXMACRODATA_API_KEY` optional. |
| `technical-analyst` | tradermonty | Structure, support/resistance and scenarios from chart screenshots you give it (works for FX pairs and gold). |
| `pre-trade-discipline-gate` | tradermonty | Offline checklist before a manual entry: no plan, oversized, revenge trade or breaker active → blocked. Journals the decision. |
| `drawdown-circuit-breaker` | tradermonty | Daily/weekly/monthly drawdown and losing-streak cooldowns. Advisory. Its halts end on NYSE session dates, a close enough proxy for gold. |
| `trader-memory-core` | tradermonty | Trade/thesis journal and postmortems. State in `state/` (git-ignored). |
| `backtest-expert` | tradermonty | Method for testing a gold strategy honestly (robustness, slippage, bias). |
| `mt5-robot-tester` | tradermonty | Batch-runs the MT5 Strategy Tester on Expert Advisors. Windows + MT5 only. Backtests, it does not trade. |

Also installed earlier: the `trader-*` day-trader pack. It is for **US stocks only**
(NYSE hours, whole shares, Alpaca) and does not handle XAUUSD.

Tests from the upstream repos were not copied. Script paths in the SKILL.md files were
rewritten from `skills/<name>/` to `.claude/skills/<name>/`.

Python packages some scripts need (once, in the Python you use):

```bash
python3 -m pip install pyyaml jsonschema requests "pandas-market-calendars==5.2.2"
```

## 2. MetaTrader 5 connection: meta-trader-mcp (on your computer)

Gives Claude your MT5 prices, account, positions, a free ForexFactory economic calendar
(`get_economic_calendar`, no key) and, only if you switch it on, orders.

**Review notes (v1.2.2 wheel from PyPI, read 2026-11-01):**
- Trading is **off** by default (`MTM_ENABLE_TRADING=false`). Every order goes through a
  risk check: max lot (`MTM_MAX_LOT`, default 10) and an equity-drawdown ceiling
  (`MTM_MAX_DRAWDOWN_PCT`, default 5). Closing or reducing a position is always allowed.
- It also has code-execution tools (`execute_shell`, `execute_python`, `execute_mql_script`,
  `write_ea`...). They are behind a separate switch, `MTM_ENABLE_EXEC`, off by default.
  **Leave it off.** Turning it on lets the AI run any command on your computer.
- Servers bind to 127.0.0.1 by default. Network calls go to your MT5 bridge and to
  optional data feeds (ForexFactory, Yahoo/Nasdaq RSS; Finnhub, FMP, Alpha Vantage,
  Polygon, Marketaux only if you give them keys).
- **Caveat:** the GitHub repo PyPI points to (github.com/shubhvisputek/meta-trader-mcp)
  returned 404 on 2026-11-01, so there is no public source or issue tracker right now.
  Pin the reviewed version (`==1.2.2`) and do not upgrade blindly.

**Requirements:** MT5 desktop terminal installed and logged in to a **demo** account
(Windows native; macOS/Linux via Wine; or a remote Windows bridge). `uv` installed
(docs.astral.sh/uv). The commands pin Python 3.12 because the `MetaTrader5` package may not support
newer Python versions yet; uv downloads 3.12 by itself.

**Claude Code** (run in this repo, on the computer with MT5):

```bash
claude mcp add meta-trader-mcp -e MTM_ENABLE_TRADING=false -e MTM_ENABLE_EXEC=false -- uvx --python 3.12 --from "meta-trader-mcp[windows]==1.2.2" meta-trader-mcp serve --transport stdio
```

**Claude Desktop** (Settings > Developer > Edit Config, `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "meta-trader-mcp": {
      "command": "uvx",
      "args": ["--python", "3.12", "--from", "meta-trader-mcp[windows]==1.2.2", "meta-trader-mcp", "serve", "--transport", "stdio"],
      "env": {
        "MTM_MODE": "auto",
        "MTM_ENABLE_TRADING": "false",
        "MTM_ENABLE_EXEC": "false"
      }
    }
  }
}
```

The server reuses the logged-in terminal session. Do not paste your MT5 password into the
chat. If you must set `MT5_PASSWORD`, type it into the config file yourself.

**Order tool permissions.** If you later set `MTM_ENABLE_TRADING=true` (demo first),
keep every state-changing tool on "ask", never "allow". In this repo's
`.claude/settings.json`:

```json
{
  "permissions": {
    "ask": [
      "mcp__meta-trader-mcp__place_market_order",
      "mcp__meta-trader-mcp__place_pending_order",
      "mcp__meta-trader-mcp__modify_position",
      "mcp__meta-trader-mcp__modify_pending_order",
      "mcp__meta-trader-mcp__close_position",
      "mcp__meta-trader-mcp__cancel_pending_order"
    ],
    "deny": [
      "mcp__meta-trader-mcp__close_all_positions",
      "mcp__meta-trader-mcp__cancel_all_pending_orders"
    ]
  }
}
```

In Claude Desktop: Customize > Connectors > meta-trader-mcp, set the order tools to
"Needs approval" and the close-all/cancel-all tools to "Blocked".

## 3. A gold day trade, step by step

1. **Calendar.** `/fxmacrodata-calendar` (or ask for `get_economic_calendar`). No new
   entries 30 min before to 60 min after a red USD event.
2. **Session.** London or New York only (08:00-21:00 UTC). Avoid rollover (~22:00 UTC):
   spreads widen.
3. **Chart.** Screenshot H4/H1 (M15 for entries) → `/technical-analyst`, with the
   `/analyze-gold` checklist (stop ≥ max(structure, 1× H1 ATR, 2.5 points); skip if
   H1 ATR > 20 or spread > 1.0).
4. **Size.** Gold CFD: 1 standard lot = 100 oz, so $1 move = $100 per lot. Lots =
   risk $ / (stop distance in $ × 100). Example: $10,000 × 1% = $100 risk, 3.5 stop →
   100 / 350 = 0.28 lots. Check your broker's contract size: some differ.
5. **Gates.** `/drawdown-circuit-breaker`, then `/pre-trade-discipline-gate`. Any block →
   no trade.
6. **Order.** You place it, or Claude prepares it and you approve that one order on the
   permission card. Demo first.
7. **Journal.** `/trader-memory-core` to log it; postmortem when closed.

## 4. Looked at and not installed

- **Tradecraft `gold-orb-ea` and the rest of Tradecraft:** `gold-orb-ea` walks through
  installing a third-party EA that trades with no confirmation, names one broker and
  makes "high-probability" claims. The full pipeline would pull in a dozen more skills.
- **forexfactory-mcp:** not needed; meta-trader-mcp's calendar uses the same free
  ForexFactory feed. It would also need Playwright and Chromium.
- **openclaw `gold-trading-skill`:** promotes a paid "Gold-Oracle" system.
- **Fully automated gold bots** (claude-trading-bot, zero-was-here/tradingbot, which
  advertises "80-120% annual returns"): they trade without asking you.
- **gold-mcp:** free tier is fine, but low adoption and the README mostly sells paid tiers.
- tradermonty stock-only skills (screeners, CANSLIM, VCP, dividends) and the FMP
  economic calendar (endpoint may need a paid FMP plan).
