# SommelierClaude

An AI wine sommelier that picks you a case of 6 bottles every month.

This is not a Python app or a web service. It's a [Claude Code](https://claude.ai/claude-code) session launched via cron. Claude browses UK wine retailer websites, uses its own wine knowledge, matches wines to your taste profile, and publishes the results — all autonomously.

## How it works

1. **Cron triggers `run.sh`** on the 1st of each month
2. **Claude reads `CLAUDE.md`** — its instructions as a sommelier
3. **Claude reads `taste-profile.md`** — your personal wine preferences
4. **Claude browses retailers** — Majestic, Berry Bros & Rudd, Laithwaites, etc.
5. **Claude picks 6 wines** — a mix of safe picks and discoveries
6. **Claude writes up the picks** — saves to `history/`, publishes HTML, sends a Telegram notification
7. **You drink the wines and leave feedback** — Claude reads it next month and refines your profile

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
│   └── import-vivino.py   # Parse Vivino GDPR export into taste-profile.md
└── logs/                  # Session logs (gitignored)
```

## Set up your own

### Prerequisites

- [Claude Code](https://claude.ai/claude-code) installed (`claude` CLI)
- A Telegram bot for notifications (optional — edit `CLAUDE.md` to remove or change)

### Steps

1. **Fork this repo**

2. **Edit `taste-profile.md`** with your own wine preferences — grapes you like, regions you enjoy, price range, styles you prefer. Be specific. The more detail you give, the better the picks.

3. **Edit `CLAUDE.md`** to match your setup:
   - Change retailer list to your local retailers
   - Update the notification command (or remove it)
   - Update the website publishing path (or remove it)
   - Adjust budget ranges

4. **Import Vivino data** (optional): Request a GDPR data export from Vivino settings. Once it arrives:
   ```bash
   python3 scripts/import-vivino.py /path/to/vivino-export/
   ```

5. **Test it manually**:
   ```bash
   ./run.sh
   ```
   Watch the log: `tail -f logs/$(date +%Y-%m).log`

6. **Set up cron**:
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

## Example output

Each month produces:
- `history/YYYY-MM.md` — detailed picks with reasoning
- An HTML page published to your website (if configured)
- A Telegram message with highlights

## License

MIT — see [LICENSE](LICENSE).
