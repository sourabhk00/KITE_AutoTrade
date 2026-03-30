"""
utils/helpers.py — Utility functions
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path


def save_json(path: str, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def now_ist() -> str:
    return datetime.now().strftime("%H:%M")


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def round2(x: float) -> float:
    return round(x, 2)


def pct_diff(a: float, b: float) -> float:
    return (a - b) / b * 100 if b else 0.0


def rate_limit_sleep(calls_per_sec: float = 3.0):
    time.sleep(1.0 / calls_per_sec)
