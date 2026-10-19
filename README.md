# ruhi-feed

Builds `stories.json` — a verbatim Markets · World news feed for the Ruhi Fire TV
screensaver. A GitHub Action runs `fetch_feeds.py` every hour, pulling reputable
finance / crypto / gold / geopolitics / macro RSS feeds and passing through each
outlet's **own headline + own description** (no summarizing, no AI).

The TV reads the result on screensaver launch from:
`https://raw.githubusercontent.com/Rupii/ruhi-feed/main/stories.json`

- `fetch_feeds.py` — the aggregator (Python stdlib only, no dependencies)
- `.github/workflows/hourly.yml` — the hourly job
- `stories.json` — the generated feed (committed by the job)

Run manually: Actions tab → hourly-feed → Run workflow. Repo is public so the raw
URL is readable without auth.
