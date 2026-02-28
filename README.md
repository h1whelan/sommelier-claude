# SommelierClaude

An AI wine sommelier that picks you a case of 6 bottles every month — and buys them for you.

This is not a Python app or a web service. It's a [Claude Code](https://claude.ai/claude-code) session launched via cron. Claude browses UK wine retailer websites, uses its own wine knowledge, matches wines to your taste profile, places the order, and publishes the results — all autonomously. Six surprise bottles turn up at your door.

## How it works

1. **Cron triggers `run.sh`** on the 1st of each month
2. **Claude reads `CLAUDE.md`** — its instructions as a sommelier
3. **Claude reads `taste-profile.md`** — your personal wine preferences
4. **Claude browses retailers** — Majestic, Berry Bros & Rudd, Laithwaites, etc.
5. **Claude picks 6 wines** — a mix of safe picks and discoveries
6. **Claude buys them** — automated checkout via Playwright (headless browser)
7. **Claude writes up the picks** — saves to `history/`, publishes HTML, sends a Telegram notification
8. **Wines arrive. You drink them and leave feedback** — Claude reads it next month and refines your profile

The taste profile is a living document. It starts minimal and gets richer over time as you provide feedback. The feedback loop is the key — Claude learns what you actually enjoy.

## Project structure

```
sommelier-claude/
├── CLAUDE.md              # The sommelier's instructions
├── run.sh                 # Launcher script (cron target)
├── taste-profile.md       # Your wine preferences (evolves over time)
├── history/               # Past picks (Claude reads to avoid repeats)
│   └── 2026-03.md
├── feedback/              # Drop notes here about past picks
├── scripts/
│   ├── purchase.py        # Playwright-based automated checkout
│   └── import-vivino.py   # Parse Vivino GDPR export into taste-profile.md
└── logs/                  # Session logs and screenshots (gitignored)
```

## Set up your own

### Prerequisites

- [Claude Code](https://claude.ai/claude-code) installed (`claude` CLI)
- Python 3 + Playwright (`pip install playwright && python -m playwright install chromium`)
- Retailer accounts with saved payment methods and delivery addresses
- A Telegram bot for notifications (optional — edit `CLAUDE.md` to remove or change)

### Steps

1. **Fork this repo**

2. **Edit `taste-profile.md`** with your own wine preferences — grapes you like, regions you enjoy, price range, styles you prefer. Be specific. The more detail you give, the better the picks.

3. **Edit `CLAUDE.md`** to match your setup:
   - Change retailer list to your local retailers
   - Update the notification command (or remove it)
   - Update the website publishing path (or remove it)
   - Adjust the budget cap (default: £250/month)

4. **Set up retailer credentials** in `~/.sommelier-claude/credentials.json`:
   ```json
   {
       "majestic": { "email": "you@example.com", "password": "..." },
       "bbr": { "email": "you@example.com", "password": "..." }
   }
   ```
   Each retailer account needs a saved payment method and delivery address.

5. **Import Vivino data** (optional): Request a GDPR data export from Vivino settings. Once it arrives:
   ```bash
   python3 scripts/import-vivino.py /path/to/vivino-export/
   ```

6. **Test it manually**:
   ```bash
   ./run.sh
   ```
   Watch the log: `tail -f logs/$(date +%Y-%m).log`

7. **Set up cron**:
   ```bash
   crontab -e
   # Add:
   0 9 1 * * /path/to/sommelier-claude/run.sh
   ```

### Leaving feedback

After trying wines, drop a note in `feedback/`:

```bash
echo "The 2019 Barolo was incredible. The Grüner Veltliner was too acidic for me." > feedback/2026-03.md
```

Claude reads this next month and updates your taste profile accordingly.

### How purchasing works

The `scripts/purchase.py` script uses Playwright (headless Chromium) to automate checkout:
1. Logs into retailer accounts using saved credentials
2. Navigates to each wine's product page
3. Adds to cart
4. Verifies total is within budget cap
5. Completes checkout using the account's saved payment method

If automation fails (CAPTCHAs, site changes, etc.), Claude falls back to sending you the wine links via Telegram so you can order manually.

Screenshots of every step are saved to `logs/screenshots/` for debugging.

## Example output

Each month produces:
- `history/YYYY-MM.md` — detailed picks with reasoning and order confirmations
- An HTML page published to your website (if configured)
- A Telegram message confirming the order
- 6 bottles arriving at your door

## License

MIT — see [LICENSE](LICENSE).
