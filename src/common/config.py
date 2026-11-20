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

try:  # đọc khóa API từ .env (SSI_API_KEY, SSI_API_SECRET, …)
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(ROOT / ".env.example", override=False)   # máy mới chưa có .env → dùng cấu hình mẫu đi kèm (token bot)
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
    """SSI FastConnect V3: API Key + API Secret tạo tại Developer Portal (không cần OTP / Private Key)."""
    return _real(env("SSI_API_KEY")) and _real(env("SSI_API_SECRET"))


def ssi_base_url() -> str:
    return (env("SSI_BASE_URL") or get("ssi.base_url", "https://api.ssi.com.vn")).rstrip("/")


def ssi_stream_url() -> str:
    return env("SSI_STREAM_URL") or get("ssi.stream_url", "wss://stream.ssi.com.vn/ws/v3")


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


_ICB_CACHE: Dict[str, Dict[str, str]] = {}


def ssi_icb_sectors() -> Dict[str, str]:
    """{mã: nhóm ngành} từ mã ICB trong danh mục chứng khoán SSI (bảng raw_securities, bản mới nhất mỗi mã)."""
    if "map" in _ICB_CACHE:
        return _ICB_CACHE["map"]
    out: Dict[str, str] = {}
    try:
        from src.data import database as db
        from src.finance.sectors import sector_of
        if db.table_exists("raw_securities"):
            r = db.query_df("SELECT symbol, json_extract_string(arg_max(payload, as_of), '$.icbCode') AS icb "
                            "FROM raw_securities GROUP BY symbol")
            out = {str(s).upper(): sector_of(c) for s, c in zip(r["symbol"], r["icb"]) if c}
    except Exception:  # noqa: BLE001 – kho chưa có danh mục SSI
        out = {}
    if out:
        _ICB_CACHE["map"] = out
    return out


def stock_groups() -> pd.DataFrame:
    """Nhóm cổ phiếu: NGÀNH theo ICB của SSI (ssi_icb_sectors); HỌ cổ phiếu (Vingroup…) là định nghĩa nhóm nghiên cứu
    trong config/stock_groups.csv; foreign_limit chỉ là giới hạn sở hữu theo quy định, dùng dự phòng khi SSI không trả room."""
    df = _read_csv("stock_groups.csv")
    icb = ssi_icb_sectors()
    if df.empty and not icb:
        return df
    if df.empty:
        df = pd.DataFrame(columns=["symbol", "family", "foreign_limit", "in_vn30"])
    extra = sorted(set(icb) - set(df["symbol"]))
    if extra:
        df = pd.concat([df, pd.DataFrame({"symbol": extra, "family": "", "foreign_limit": "", "in_vn30": "0"})],
                       ignore_index=True)
    df["sector"] = df["symbol"].map(icb).fillna("Khác") if icb else df.get("sector", "Khác")
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


def control_group_path() -> Path:
    """Nhóm đối chứng ghép từ dữ liệu (B6.1)."""
    return CONFIG_DIR / "control_group.csv"


def control_group() -> pd.DataFrame:
    p = control_group_path()
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8")
