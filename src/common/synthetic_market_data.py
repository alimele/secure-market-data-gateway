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
    "AURORA": {
        "symbol": "AURORA",
        "company_name": "Aurora Mobility PJSC",
        "prices": [
            {"date": "2026-08-01T09:30:00+00:00", "open": 24.65, "high": 25.10, "low": 24.40, "close": 24.85, "volume": 650000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-02T09:30:00+00:00", "open": 24.90, "high": 25.30, "low": 24.70, "close": 25.15, "volume": 720000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-03T09:30:00+00:00", "open": 25.10, "high": 25.55, "low": 24.95, "close": 25.40, "volume": 695000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-04T09:30:00+00:00", "open": 25.35, "high": 25.80, "low": 25.10, "close": 25.60, "volume": 710000, "dividends": 0.0, "stock_splits": 0.0},
        ],
    },
    "NEXUS": {
        "symbol": "NEXUS",
        "company_name": "Nexus Digital Holdings",
        "prices": [
            {"date": "2026-08-01T09:30:00+00:00", "open": 71.00, "high": 72.10, "low": 70.75, "close": 71.50, "volume": 420000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-02T09:30:00+00:00", "open": 71.60, "high": 72.85, "low": 71.20, "close": 72.30, "volume": 445000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-03T09:30:00+00:00", "open": 72.25, "high": 73.40, "low": 71.90, "close": 73.00, "volume": 460000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-04T09:30:00+00:00", "open": 73.10, "high": 74.20, "low": 72.80, "close": 73.75, "volume": 480000, "dividends": 0.0, "stock_splits": 0.0},
        ],
    },
    "OASIS": {
        "symbol": "OASIS",
        "company_name": "Oasis Utilities Group",
        "prices": [
            {"date": "2026-08-01T09:30:00+00:00", "open": 9.38, "high": 9.55, "low": 9.30, "close": 9.45, "volume": 1800000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-02T09:30:00+00:00", "open": 9.48, "high": 9.60, "low": 9.40, "close": 9.52, "volume": 1850000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-03T09:30:00+00:00", "open": 9.50, "high": 9.65, "low": 9.44, "close": 9.58, "volume": 1920000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-04T09:30:00+00:00", "open": 9.55, "high": 9.70, "low": 9.48, "close": 9.63, "volume": 1980000, "dividends": 0.0, "stock_splits": 0.0},
        ],
    },
    "FALCON": {
        "symbol": "FALCON",
        "company_name": "Falcon Logistics Co.",
        "prices": [
            {"date": "2026-08-01T09:30:00+00:00", "open": 35.90, "high": 36.50, "low": 35.65, "close": 36.20, "volume": 890000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-02T09:30:00+00:00", "open": 36.25, "high": 36.85, "low": 36.00, "close": 36.60, "volume": 920000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-03T09:30:00+00:00", "open": 36.55, "high": 37.10, "low": 36.30, "close": 36.90, "volume": 945000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-04T09:30:00+00:00", "open": 36.85, "high": 37.40, "low": 36.60, "close": 37.15, "volume": 970000, "dividends": 0.0, "stock_splits": 0.0},
        ],
    },
    "CEDAR": {
        "symbol": "CEDAR",
        "company_name": "Cedar Healthcare Ltd.",
        "prices": [
            {"date": "2026-08-01T09:30:00+00:00", "open": 18.50, "high": 18.85, "low": 18.35, "close": 18.70, "volume": 560000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-02T09:30:00+00:00", "open": 18.75, "high": 19.10, "low": 18.55, "close": 18.95, "volume": 580000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-03T09:30:00+00:00", "open": 18.90, "high": 19.25, "low": 18.70, "close": 19.10, "volume": 595000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-04T09:30:00+00:00", "open": 19.05, "high": 19.40, "low": 18.85, "close": 19.25, "volume": 610000, "dividends": 0.0, "stock_splits": 0.0},
        ],
    },
    "HORIZON": {
        "symbol": "HORIZON",
        "company_name": "Horizon Industrial Systems",
        "prices": [
            {"date": "2026-08-01T09:30:00+00:00", "open": 52.10, "high": 52.85, "low": 51.80, "close": 52.45, "volume": 740000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-02T09:30:00+00:00", "open": 52.50, "high": 53.20, "low": 52.20, "close": 52.90, "volume": 760000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-03T09:30:00+00:00", "open": 52.85, "high": 53.60, "low": 52.55, "close": 53.30, "volume": 785000, "dividends": 0.0, "stock_splits": 0.0},
            {"date": "2026-08-04T09:30:00+00:00", "open": 53.25, "high": 54.00, "low": 52.95, "close": 53.70, "volume": 810000, "dividends": 0.0, "stock_splits": 0.0},
        ],
    }
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
