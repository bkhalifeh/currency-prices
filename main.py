"""Scrape the last currency-price message from the derham_ir Telegram channel.

Fetches the public channel preview at https://t.me/s/derham_ir, finds the most
recent price post, writes the parsed result to latest.json, and appends it as a
row to the prices.db SQLite history (one row per Telegram post).

Set the FIXTURE env var to a local HTML file to parse that instead of making a
network request (used for tests / verification).
"""

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://t.me/s/derham_ir"
OUT_PATH = Path(__file__).with_name("latest.json")
DB_PATH = Path(__file__).with_name("prices.db")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Normalised Persian label -> output key.
LABELS = {
    "درهم امارات": "aed",
    "یورو": "eur",
    "دلار آمریکا": "usd",
    "پوند انگلیس": "gbp",
    "یوآن چین": "cny",
    "لیر ترکیه": "try",
}
KEYS = list(LABELS.values())

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_LINE_RE = re.compile(r"^(?P<label>.+?)\s*[:：]\s*(?P<value>[\d,]+)$")
_TIME_RE = re.compile(r"^ساعت\s*[:：]\s*(?P<value>\d{1,2}:\d{2})$")


def normalise(text: str) -> str:
    """Fold Arabic letter variants to Persian and localise digits to ASCII."""
    return text.translate(_DIGITS).replace("ي", "ی").replace("ك", "ک")


def fetch() -> str:
    fixture = os.environ.get("FIXTURE")
    if fixture:
        return Path(fixture).read_text(encoding="utf-8")
    resp = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select("div.tgme_widget_message_text")

    for block in reversed(blocks):
        lines = [
            normalise(line).strip()
            for line in block.get_text("\n").splitlines()
            if line.strip()
        ]
        if not any(line.startswith("درهم امارات") for line in lines):
            continue
        if not any(line.startswith("ساعت") for line in lines):
            continue

        prices: dict[str, int] = {}
        time_label = None
        for line in lines:
            time_match = _TIME_RE.match(line)
            if time_match:
                time_label = time_match["value"]
                continue
            match = _LINE_RE.match(line)
            if not match:
                continue
            label = match["label"].strip()
            if label in LABELS:
                prices[LABELS[label]] = int(match["value"].replace(",", ""))

        missing = set(LABELS.values()) - set(prices)
        if missing:
            raise ValueError(f"price block missing keys: {sorted(missing)}")

        message = block.find_parent(class_="tgme_widget_message")
        post = message.get("data-post") if message else None
        time_el = message.select_one("time[datetime]") if message else None
        post_dt = time_el["datetime"] if time_el else None

        return {
            "source": URL,
            "post": post,
            "post_url": f"https://t.me/{post}" if post else None,
            "datetime": post_dt,
            "time_label": time_label,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "prices": prices,
        }

    raise ValueError("no price message found on the page")


def save_history(data: dict, db_path: Path = DB_PATH) -> bool:
    """Append the reading to the SQLite history. Returns True if a new row was
    inserted, False if this post is already recorded."""
    cols = ["post", "datetime", "time_label", "fetched_at", *KEYS]
    quoted = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join("?" for _ in cols)
    row = [
        data["post"],
        data["datetime"],
        data["time_label"],
        data["fetched_at"],
        *(data["prices"][k] for k in KEYS),
    ]

    con = sqlite3.connect(db_path)
    try:
        coldefs = (
            "post TEXT PRIMARY KEY, datetime TEXT, time_label TEXT, "
            "fetched_at TEXT, " + ", ".join(f'"{k}" INTEGER' for k in KEYS)
        )
        con.execute(f"CREATE TABLE IF NOT EXISTS prices ({coldefs})")
        cur = con.execute(
            f"INSERT OR IGNORE INTO prices ({quoted}) VALUES ({placeholders})", row
        )
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def main() -> None:
    data = parse(fetch())
    OUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    inserted = save_history(data)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(
        f"history: {'appended' if inserted else 'already recorded'} {data['post']}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # surface failure to the workflow
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
