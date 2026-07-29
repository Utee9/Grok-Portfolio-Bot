# Portfolio Mirror

Mirrors publicly-disclosed AI-managed stock portfolios (Grok, Claude,
DeepSeek, GPT -- all run by Dr. Alejandro Lopez-Lira's AI Finance Labs via
Autopilot) into their own isolated Bitget tokenized-stock sub-accounts,
since Bitget's supported brokerages don't accept Nigerian residents.

Each portfolio runs as its own independent pipeline: its own data source,
its own Bitget sub-account, its own dry-run/paper-trading toggle. A bug or
bad trade in one can never touch another.

## Structure

```
portfolios/
  grok/       -- @grkportfolio on X (live, active)
  claude/     -- @theaiportfolios on X (live, active)
  deepseek/   -- no dedicated X account; @chatgpttrader-style handle
                 doesn't exist. Tracked via manual_override.json only.
  gpt/        -- @chatgpttrader was suspended. Tracked via
                 manual_override.json only, same as DeepSeek.

portfolios/<name>/
  portfolio.json          -- display name, X handle (or null), secret suffix
  status.json             -- {"dry_run": bool, "paper_trading": bool}
  config/ticker_map.json  -- ticker -> Bitget symbol, per portfolio
  config/manual_override.json -- you edit this by hand, see below
  data/merged_state.json  -- current reconciled target weights (auto-generated)
  data/snapshots/         -- full history of every run (auto-generated)

scripts/
  portfolio_config.py -- loads a portfolio's config + resolves its secret names
  fetch_tweets.py      -- xAI live X-search + trade-vs-commentary extraction
  merge_sources.py     -- reconciles tweet data + manual_override.json per ticker
  ticker_mapping.py    -- ticker -> Bitget symbol lookup
  size_positions.py    -- target-weight rebalancing math, sized against that
                           portfolio's own sub-account
  execute_trades.py    -- places orders via `bgc`, respects dry_run/paper_trading
  notify.py             -- Telegram summary, labelled per portfolio
  main.py               -- orchestrates all of the above for ONE portfolio,
                           selected via the PORTFOLIO env var
```

## How data sources are reconciled

Each portfolio's current target weights come from merging up to two
sources, per ticker, keeping whichever is more recent:

1. **Tweets** (`fetch_tweets.py`) -- only for portfolios with a live X
   account (Grok, Claude). Explicitly classifies each post as either a
   clean weight disclosure ("NOW is 12.6%") or a narrative action with no
   weight ("added DHT to hedge") -- narrative actions are surfaced in the
   Telegram alert but never auto-traded, since there's no reliable size to
   trade them at.
2. **Manual override** (`config/manual_override.json`, one per portfolio)
   -- you edit this whenever you check the Autopilot app. Set `as_of` to
   today's date and list whatever you see. You don't need to do this
   consistently or completely -- it only overrides tickers where your
   manual entry is fresher than what's already known for that ticker.

This is how DeepSeek and GPT get tracked at all, since neither has a live
public trade feed anymore -- their `portfolio.json` has `"x_handle": null`,
so `fetch_tweets.py` is skipped entirely for them and they run purely off
whatever you enter manually.

## Secrets (GitHub repo Settings -> Secrets and variables -> Actions)

Shared across all portfolios:
- `XAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (optional but recommended)

Grok keeps its **original, already-working, unprefixed** names -- do not
change these:
- `BITGET_API_KEY`, `BITGET_SECRET_KEY`, `BITGET_PASSPHRASE`

Every other portfolio gets its own suffixed set, so each Bitget sub-account
stays completely isolated:
- `BITGET_API_KEY_CLAUDE`, `BITGET_SECRET_KEY_CLAUDE`, `BITGET_PASSPHRASE_CLAUDE`
- `BITGET_API_KEY_DEEPSEEK`, `BITGET_SECRET_KEY_DEEPSEEK`, `BITGET_PASSPHRASE_DEEPSEEK`
- `BITGET_API_KEY_GPT`, `BITGET_SECRET_KEY_GPT`, `BITGET_PASSPHRASE_GPT`

**You don't need to add DeepSeek's or GPT's Bitget secrets yet.** If
they're missing, `main.py` automatically falls back to "tracking-only"
mode for that portfolio -- it still fetches/merges/records target weights
and sends a Telegram summary, it just skips sizing and trading entirely
until you've created and funded a sub-account for it.

## Independent dry-run / paper-trading control

Each portfolio's `status.json` controls its own mode -- completely
separate from the others:

```json
{"dry_run": true, "paper_trading": false}
```

- `dry_run: true` -- runs the full pipeline (fetch, merge, size) but never
  calls `bgc` for a real order, just logs what it would have done.
- `paper_trading: true` -- (only relevant once `dry_run` is `false`) routes
  real `bgc` calls to Bitget's sandboxed demo environment instead of your
  live sub-account.

Edit `portfolios/<name>/status.json` directly and commit -- e.g. flip
Claude to live while Grok stays in dry-run, with no workflow or secrets
changes needed.

## Running

The workflow (`.github/workflows/mirror.yml`) runs all four portfolios as
parallel, independent jobs every 6 hours. `fail-fast: false` means one
portfolio failing doesn't cancel the others.

To trigger manually: **Actions tab -> Portfolio Mirror (all portfolios) ->
Run workflow**. Optionally pick a single portfolio from the dropdown to
run just that one instead of all four (useful while testing a new one).

To run locally for one portfolio:

```
PORTFOLIO=claude python scripts/main.py
```

## Known limitations / things to revisit

- **`bgc` command shapes**: `size_positions.py` / `execute_trades.py`
  assume specific `bgc` command names and response fields -- confirm with
  `bgc discover` before relying on any portfolio's real trading.
- **`MAX_SINGLE_TRADE_USDT` = $50** (in `size_positions.py`, shared across
  all portfolios currently): caps any single rebalancing trade. A large
  first-time full-book buy for a well-funded sub-account will take
  multiple runs to fully catch up. Raise once you trust the pipeline.
- **DeepSeek/GPT freshness ceiling**: since these are manual-only, their
  target weights are only ever as fresh as your last edit to their
  `manual_override.json`. There's no way around this without a live
  public trade feed for either.
- **xAI live-search API shape**: flagged inline in `fetch_tweets.py` --
  xAI's tool APIs have changed before (see the 410 Gone incident this repo
  already recovered from) and may again.
- **Concurrent-push handling**: the workflow's commit step does a
  pull-rebase-retry since all 4 portfolios push to the same repo/branch in
  parallel. If you add many more portfolios, watch for push contention.

## Disclaimer

This is a personal automation project mirroring third parties' disclosed
trading activity with a delay and independent execution venue. It is not
financial advice, and past performance of any mirrored portfolio is not
indicative of future results. You are solely responsible for any trades
this pipeline places on your behalf.
