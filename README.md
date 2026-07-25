# Grok Portfolio Mirror

Mirrors @grkportfolio's (Autopilot's "Grok Portfolio," run by Dr. Alejandro
Lopez-Lira's AI Finance Labs) disclosed stock positions into a Bitget
tokenized-stocks sub-account, since Bitget's supported brokerages (IBKR,
Schwab, Fidelity, E*Trade, Vanguard, Robinhood) don't accept Nigerian
residents.

## How it works

1. **Fetch** (`scripts/fetch_grok_portfolio.py`) -- asks Grok (via xAI's API
   with live X-search) for @grkportfolio's latest posts, extracted as
   structured JSON.
2. **Diff** (`scripts/diff_engine.py`) -- compares the new extraction against
   the last saved state (`data/latest.json`) to find real position changes.
3. **Map** (`scripts/ticker_mapping.py`) -- resolves each ticker to its
   Bitget tokenized-stock symbol via `config/ticker_map.json`.
4. **Size** (`scripts/size_positions.py`) -- converts weight-% changes into
   USDT trade amounts, sized against your actual sub-account balance.
5. **Execute** (`scripts/execute_trades.py`) -- places orders via Bitget's
   official `bgc` CLI ([Bitget-AI/agent_hub](https://github.com/Bitget-AI/agent_hub)).
6. **Notify** (`scripts/notify.py`) -- sends a Telegram summary of what
   happened.

Orchestrated by `scripts/main.py`, run on a schedule by
`.github/workflows/grok_mirror.yml` (every 6 hours, free on GitHub Actions).

## One-time setup

### 1. Bitget

- Create an **Agent trading sub-account** in the Bitget app (Account →
  Sub-accounts → Create → "Agent trading sub-account") -- this keeps this
  bot's capital fully isolated from your main account and any other
  portfolios you add later.
- Fund it with a small amount of USDT to start.
- Confirm tokenized stocks are tradeable from within the sub-account
  before funding it further.
- Create an API key **scoped to that sub-account** with trade permission.
  Store the key, secret, and passphrase as GitHub Actions secrets (see below).

### 2. xAI

- Create an API key at [console.x.ai](https://console.x.ai).
- Verify the exact request shape for live X-search against
  [docs.x.ai](https://docs.x.ai) -- `scripts/fetch_grok_portfolio.py` has a
  best-effort implementation flagged with comments where the schema may
  need adjusting.

### 3. Telegram (optional but recommended)

- Message [@BotFather](https://t.me/BotFather) on Telegram, run `/newbot`,
  save the token it gives you.
- Message your new bot once, then fetch your chat ID from
  `https://api.telegram.org/bot<TOKEN>/getUpdates`.

### 4. GitHub repo secrets

In your repo: Settings → Secrets and variables → Actions → New repository
secret. Add:

- `XAI_API_KEY`
- `BITGET_API_KEY`
- `BITGET_SECRET_KEY`
- `BITGET_PASSPHRASE`
- `TELEGRAM_BOT_TOKEN` (optional)
- `TELEGRAM_CHAT_ID` (optional)

## Testing before going live

The workflow ships with `DRY_RUN: 'true'` set in the env block --
**leave this as `true`** until you've watched several runs complete
successfully and manually reviewed the Telegram summaries. Dry-run mode
runs the entire pipeline (fetch, diff, size) but logs what *would* have
been traded instead of calling `bgc` for real.

Once you're confident:
1. Flip `DRY_RUN` to `'false'` in the workflow file.
2. Consider testing one more round with `PAPER_TRADING: 'true'` set as an
   additional env var, which routes real `bgc` calls to Bitget's sandboxed
   demo environment instead of your live sub-account.
3. Only then remove paper-trading and let it touch real funds.

You can trigger a run manually anytime from the repo's **Actions** tab
(`workflow_dispatch`), rather than waiting for the next scheduled run.

## Known limitations / things to revisit

- **Partial tweet extractions**: @grkportfolio doesn't always post the full
  15-position book in one tweet. `main.py` suppresses "closed position"
  actions when a new extraction looks partial (fewer than 70% of the
  previously known position count), to avoid selling off positions that
  are still held but just weren't mentioned in that particular post. Watch
  the Telegram summaries for a while to see how often this triggers.
- **Ticker mapping coverage**: `config/ticker_map.json` only has entries for
  tickers already seen in earlier research. New tickers Grok picks will show
  up as "unmapped" in the run summary -- add them to the map as they appear.
- **Cash-equivalent positions** (e.g. SGOV, T-bill ETFs): Bitget doesn't
  tokenize these. Current handling just skips them; decide if you want that
  weight sitting idle as USDT instead.
- **xAI live-search API shape**: flagged inline in
  `fetch_grok_portfolio.py` -- verify against current docs before first run.
- **`bgc` account-balance and order command shapes**: flagged inline in
  `size_positions.py` and `execute_trades.py` -- run `bgc discover` to
  confirm exact command/response formats for your installed CLI version.

## Disclaimer

This is a personal automation project mirroring a third party's disclosed
trading activity with a delay and independent execution venue. It is not
financial advice, and past performance of the mirrored portfolio is not
indicative of future results. You are solely responsible for any trades
this pipeline places on your behalf.
