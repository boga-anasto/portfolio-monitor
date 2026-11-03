"""Ambil harga saham IDX dari Yahoo Finance (kode .JK) dan tulis ke data/prices.json.

Tanpa library tambahan. Jika sebuah saham gagal diambil, harga terakhir yang
berhasil dipertahankan dan ditandai ok=false (tidak pernah mengarang harga).
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "prices.json"
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}.JK?interval=1d&range=10d"
HEADERS = {"User-Agent": "Mozilla/5.0 (personal portfolio monitor)"}


def fetch_quote(code):
    req = urllib.request.Request(URL.format(sym=code), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    result = (data.get("chart") or {}).get("result")
    if not result:
        raise ValueError("respons tanpa data: %s" % (data.get("chart") or {}).get("error"))
    res = result[0]
    meta = res["meta"]
    price = meta.get("regularMarketPrice")
    if price is None:
        raise ValueError("regularMarketPrice kosong")
    market_ts = meta.get("regularMarketTime")
    offset = meta.get("gmtoffset", 25200)

    # Penutupan hari bursa sebelumnya dari deret harian (bukan chartPreviousClose,
    # karena nilai itu merujuk ke awal rentang, bukan ke kemarin).
    ts = res.get("timestamp") or []
    closes = ((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    daily = [((t + offset) // 86400, c) for t, c in zip(ts, closes) if c is not None]
    prev_close = None
    if daily and market_ts:
        last_day = (market_ts + offset) // 86400
        if daily[-1][0] == last_day:
            prev_close = daily[-2][1] if len(daily) >= 2 else None
        else:
            prev_close = daily[-1][1]

    return {
        "ok": True,
        "price": price,
        "prev_close": prev_close,
        "market_time": datetime.fromtimestamp(market_ts, timezone.utc).isoformat() if market_ts else None,
        "delayed_by_min": meta.get("exchangeDataDelayedBy"),
        "error": None,
    }


def main():
    tickers = json.loads((ROOT / "tickers.json").read_text())["tickers"]
    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text()).get("quotes", {})
        except Exception:
            old = {}

    quotes, failed = {}, 0
    for t in tickers:
        code = t["code"]
        try:
            q = fetch_quote(code)
        except Exception as e:  # noqa: BLE001
            failed += 1
            q = dict(old.get(code, {}))
            q.update({"ok": False, "error": "%s: %s" % (type(e).__name__, e)})
            print("GAGAL %s -> %s" % (code, q["error"]), file=sys.stderr)
        q["sector"] = t.get("sector")
        quotes[code] = q

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance (.JK)",
        "quotes": quotes,
    }, indent=2, ensure_ascii=False))
    print("Selesai: %d berhasil, %d gagal" % (len(tickers) - failed, failed))
    return 1 if failed == len(tickers) else 0


if __name__ == "__main__":
    sys.exit(main())
