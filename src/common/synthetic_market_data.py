from __future__ import annotations

from datetime import datetime

SYNTHETIC_MARKET_DATA = {
    "SYN1": {
        "symbol": "SYN1",
        "company_name": "Aster Gulf Logistics",
        "prices": [
            {"date": "2026-08-01T09:30:00+00:00", "open": 42.25, "high": 43.1, "low": 41.9, "close": 42.75, "volume": 1200000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-02T09:30:00+00:00", "open": 42.8, "high": 43.35, "low": 42.45, "close": 43.2, "volume": 1330000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-03T09:30:00+00:00", "open": 43.15, "high": 44.05, "low": 42.9, "close": 43.9, "volume": 1410000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-04T09:30:00+00:00", "open": 43.9, "high": 44.45, "low": 43.35, "close": 44.1, "volume": 1465000, "dividends": 0.0, "stock_splits": 0.0},
        ],
    },
    "SYN2": {
        "symbol": "SYN2",
        "company_name": "North Harbor Energy",
        "prices": [
            {"date": "2026-08-01T09:30:00+00:00", "open": 58.4, "high": 59.2, "low": 57.8, "close": 58.9, "volume": 980000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-02T09:30:00+00:00", "open": 59.1, "high": 60.0, "low": 58.6, "close": 59.6, "volume": 1050000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-03T09:30:00+00:00", "open": 59.5, "high": 60.3, "low": 59.0, "close": 60.2, "volume": 1120000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-04T09:30:00+00:00", "open": 60.25, "high": 61.1, "low": 59.95, "close": 60.8, "volume": 1175000, "dividends": 0.0, "stock_splits": 0.0},
        ],
    },
    "SYN3": {
        "symbol": "SYN3",
        "company_name": "Verdant Terrace Foods",
        "prices": [
            {"date": "2026-08-01T09:30:00+00:00", "open": 91.3, "high": 92.1, "low": 90.7, "close": 91.9, "volume": 870000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-02T09:30:00+00:00", "open": 92.0, "high": 93.4, "low": 91.5, "close": 92.7, "volume": 890000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-03T09:30:00+00:00", "open": 92.8, "high": 94.0, "low": 92.2, "close": 93.5, "volume": 910000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-04T09:30:00+00:00", "open": 93.6, "high": 94.7, "low": 93.1, "close": 94.3, "volume": 934000, "dividends": 0.0, "stock_splits": 0.0},
        ],
    },
}


def _parse_datetime(value: str) -> datetime:
    iso_value = value.strip()
    if iso_value.endswith("Z"):
        iso_value = iso_value[:-1] + "+00:00"
    if "T" not in iso_value:
        iso_value = f"{iso_value}T00:00:00+00:00"
    return datetime.fromisoformat(iso_value)


def get_synthetic_price_history(symbol: str, interval: str, start_date: str, end_date: str):
    """Return a tiny synthetic market dataset for the demo."""
    market = SYNTHETIC_MARKET_DATA.get(symbol.upper())
    if market is None:
        return []

    start_dt = _parse_datetime(start_date)
    end_dt = _parse_datetime(end_date)
    if "T" not in end_date:
        end_dt = _parse_datetime(f"{end_date}T23:59:59+00:00")

    results = []
    for price in market["prices"]:
        time_value = _parse_datetime(price["date"])
        if start_dt <= time_value <= end_dt:
            results.append({
                "date": time_value,
                "open": float(price["open"]),
                "high": float(price["high"]),
                "low": float(price["low"]),
                "close": float(price["close"]),
                "volume": int(price["volume"]),
                "dividends": float(price["dividends"]),
                "stock_splits": float(price["stock_splits"]),
            })
    return results
