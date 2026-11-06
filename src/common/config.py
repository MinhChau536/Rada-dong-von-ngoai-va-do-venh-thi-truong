"""
Cấu hình tập trung (bước B0.6).

- load_settings(): đọc config/settings.yaml (có cache) – mọi ngưỡng/cửa sổ lấy từ đây.
- env(): đọc biến môi trường từ .env (python-dotenv), không bao giờ ghi giá trị ra log.
- Các hàm đọc tệp cấu hình nhóm: stock_groups, ftse_universe, events, control_group.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"

try:  # đọc khóa API từ .env (SSI_CONSUMER_ID, NEO_USERNAME, …)
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except Exception:  # pragma: no cover
    pass


@lru_cache(maxsize=1)
def load_settings() -> Dict[str, Any]:
    with open(CONFIG_DIR / "settings.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg


def reload_settings() -> Dict[str, Any]:
    load_settings.cache_clear()
    return load_settings()


def get(path: str, default: Any = None) -> Any:
    """Lấy tham số theo đường dẫn chấm, ví dụ get('alerts.cr5_min')."""
    node: Any = load_settings()
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(name, default)


def _real(v: Optional[str]) -> bool:
    return bool(v) and not str(v).startswith("your_")


def ssi_configured() -> bool:
    return _real(env("SSI_CONSUMER_ID")) and _real(env("SSI_CONSUMER_SECRET"))


def neo_configured() -> bool:
    return _real(env("NEO_USERNAME")) and _real(env("NEO_PASSWORD"))


def is_main_store(path=None) -> bool:
    """True khi đang ghi vào kho chính data/ffr.duckdb (không phải kho tạm của pytest/kiểm tra) → được phép ghi docs/."""
    return path is None and not os.getenv("FFR_DB_PATH")


def abs_path(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else ROOT / p


def db_path() -> Path:
    override = os.getenv("FFR_DB_PATH")
    p = Path(override) if override else abs_path(get("paths.db", "data/ffr.duckdb"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@lru_cache(maxsize=1)
def load_data_dictionary() -> Dict[str, Any]:
    with open(CONFIG_DIR / "data_dictionary.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def field_map(table: str, source: str = "ssi") -> Dict[str, str]:
    """
    Ánh xạ tên trường nguồn (đã hạ chữ thường) → cột chuẩn. Mỗi cột có thể có nhiều bí danh vì tài liệu SSI viết
    hoa/thường không thống nhất (ClosePrice / Closeprice) và có lỗi chính tả (Toreignsellvaltotal).
    """
    out: Dict[str, str] = {}
    for col, spec in load_data_dictionary().get(table, {}).items():
        names = spec.get(source) or []
        if isinstance(names, str):
            names = [names]
        for n in names:
            out[str(n).lower()] = col
    return out


def _read_csv(name: str) -> pd.DataFrame:
    p = CONFIG_DIR / name
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8")


def stock_groups() -> pd.DataFrame:
    df = _read_csv("stock_groups.csv")
    if df.empty:
        return df
    df["foreign_limit"] = pd.to_numeric(df["foreign_limit"], errors="coerce").fillna(0.49)
    df["in_vn30"] = df["in_vn30"].astype(str).str.strip().isin(["1", "true", "True"])
    df["family"] = df["family"].replace("", None)
    return df


def ftse_universe() -> pd.DataFrame:
    df = _read_csv("ftse_universe.csv")
    if not df.empty:
        df["effective_date"] = pd.to_datetime(df["effective_date"], errors="coerce")
    return df


def events() -> pd.DataFrame:
    df = _read_csv("events.csv")
    if not df.empty:
        df["event_date"] = pd.to_datetime(df["event_date"])
        df["effective_date"] = pd.to_datetime(df["effective_date"].replace("", None), errors="coerce")
    return df


def control_group() -> pd.DataFrame:
    return _read_csv("control_group.csv")
