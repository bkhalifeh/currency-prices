# currency-prices

Hourly scrape of the latest currency-price post from the public Telegram channel
[`@derham_ir`](https://t.me/derham_ir) (via the web preview at
`https://t.me/s/derham_ir`).

The most recent price message is parsed and written to [`latest.json`](latest.json):
درهم امارات (`aed`), یورو (`eur`), دلار آمریکا (`usd`), پوند انگلیس (`gbp`),
یوآن چین (`cny`), لیر ترکیه (`try`), plus the post's `ساعت` label (Tehran local
time) and its UTC `datetime`.

Every reading is also appended to `prices.db`, a SQLite history with one row per
Telegram post (`post` is the primary key, so re-runs never duplicate):

```sh
sqlite3 prices.db 'select datetime, time_label, aed, usd, eur from prices order by datetime desc limit 10'
```

## Run

```sh
uv run python main.py                    # live fetch, writes latest.json
FIXTURE=output.html uv run python main.py # parse the bundled sample instead
```

Exits non-zero if no price message can be parsed.

## Automation

`.github/workflows/scrape.yml` runs `main.py` on cron (`35 * * * *`) and on
manual dispatch, committing `latest.json` back to the repo whenever the value
changes. Needs `contents: write` (already set in the workflow). GitHub disables
scheduled workflows after 60 days of repo inactivity.
