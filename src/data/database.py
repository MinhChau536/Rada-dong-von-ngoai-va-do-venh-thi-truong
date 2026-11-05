"""
Kho DuckDB (kế thừa ý tưởng data/database.py của đồ án giữa kỳ, viết lại cho lược đồ mới – bước B1.7).

Mỗi thao tác mở một kết nối ngắn rồi đóng, để ứng dụng Streamlit, bộ ghi WebSocket và bộ lập lịch
không giữ khóa tệp lâu. Ghi bảng bằng pandas DataFrame (đăng ký tạm rồi INSERT ... BY NAME).
"""
from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

import duckdb
import pandas as pd

from src.common.config import db_path
from src.common.logging import get_logger
from src.common.timeutil import now_vn

log = get_logger(__name__)
SCHEMA_FILE = Path(__file__).with_name("schema.sql")


@contextlib.contextmanager
def connect(read_only: bool = False, path: Optional[Path] = None, retries: int = 5) -> Iterator[duckdb.DuckDBPyConnection]:
    p = str(path or db_path())
    last_exc: Optional[Exception] = None
    for i in range(retries):
        try:
            if read_only and not Path(p).exists():
                read_only = False  # lần đầu: tạo tệp
            con = duckdb.connect(p, read_only=read_only)
            break
        except duckdb.IOException as exc:  # tệp đang bị tiến trình khác khóa → chờ ngắn rồi thử lại
            last_exc = exc
            time.sleep(0.3 * (i + 1))
    else:
        raise last_exc  # type: ignore[misc]
    try:
        yield con
    finally:
        con.close()


def init_schema(path: Optional[Path] = None) -> None:
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with connect(path=path) as con:
        con.execute(sql)


def query_df(sql: str, params: Sequence | None = None, path: Optional[Path] = None) -> pd.DataFrame:
    with connect(read_only=True, path=path) as con:
        try:
            return con.execute(sql, params or []).df()
        except duckdb.CatalogException:
            return pd.DataFrame()


def execute(sql: str, params: Sequence | None = None, path: Optional[Path] = None) -> None:
    with connect(path=path) as con:
        con.execute(sql, params or [])


def table_exists(name: str, path: Optional[Path] = None) -> bool:
    df = query_df("SELECT 1 FROM information_schema.tables WHERE table_name = ?", [name], path=path)
    return not df.empty


def _check_columns(df: pd.DataFrame) -> None:
    """DuckDB không phân biệt hoa/thường ở tên cột → chặn trùng kiểu 'NF' và 'nf'."""
    low = [c.lower() for c in df.columns]
    dup = {c for c in df.columns if low.count(c.lower()) > 1}
    if dup:
        raise ValueError(f"Tên cột trùng khi bỏ qua hoa/thường: {sorted(dup)}")


def replace_table(name: str, df: pd.DataFrame, path: Optional[Path] = None) -> None:
    """CREATE OR REPLACE – dùng cho bảng chỉ báo tính lại toàn bộ (tái lập được)."""
    _check_columns(df)
    with connect(path=path) as con:
        if df is None or df.shape[1] == 0:          # không có kết quả (vd. chưa có mốc sự kiện trong mẫu) → bỏ bảng cũ
            con.execute(f"DROP TABLE IF EXISTS {name}")
            return
        con.register("_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _df")
        con.unregister("_df")


def upsert(name: str, df: pd.DataFrame, path: Optional[Path] = None, con: duckdb.DuckDBPyConnection | None = None) -> int:
    """INSERT OR REPLACE theo khóa chính của bảng (bảng phải có PRIMARY KEY)."""
    if df is None or df.empty:
        return 0

    def _do(c):
        c.register("_df", df)
        c.execute(f"INSERT OR REPLACE INTO {name} BY NAME SELECT * FROM _df")
        c.unregister("_df")

    if con is not None:
        _do(con)
    else:
        with connect(path=path) as c:
            _do(c)
    return len(df)


def append(name: str, df: pd.DataFrame, path: Optional[Path] = None) -> int:
    if df is None or df.empty:
        return 0
    with connect(path=path) as con:
        con.register("_df", df)
        con.execute(f"INSERT INTO {name} BY NAME SELECT * FROM _df")
        con.unregister("_df")
    return len(df)


# ── Nhật ký vận hành ──────────────────────────────────────────────────────────
def log_quality(rows: Iterable[dict], path: Optional[Path] = None) -> None:
    df = pd.DataFrame(list(rows))
    if df.empty:
        return
    df["created_at"] = now_vn().replace(tzinfo=None)
    for col in ("trade_date", "check_name", "metric", "value", "status", "detail"):
        if col not in df.columns:
            df[col] = None
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    append("data_quality_log", df[["trade_date", "check_name", "metric", "value", "status", "detail", "created_at"]], path)


def log_ingest(source: str, endpoint: str, status: str, n_rows: int = 0, attempts: int = 1,
               elapsed_ms: float = 0.0, message: str = "", path: Optional[Path] = None) -> None:
    try:
        append("ingest_log", pd.DataFrame([{
            "ts": now_vn().replace(tzinfo=None), "source": source, "endpoint": endpoint, "status": status,
            "n_rows": n_rows, "attempts": attempts, "elapsed_ms": elapsed_ms, "message": message[:500]}]), path)
    except Exception as exc:  # pragma: no cover - không để lỗi ghi log làm dừng tải
        log.warning("Không ghi được ingest_log: %s", exc)


def set_source_status(source: str, status: str, message: str = "", ok: bool = True, path: Optional[Path] = None) -> None:
    ts = now_vn().replace(tzinfo=None)
    prev = query_df("SELECT * FROM source_status WHERE source = ?", [source], path=path)
    last_ok = ts if ok else (prev["last_ok"].iloc[0] if not prev.empty else None)
    last_err = None if ok else ts
    if ok and not prev.empty:
        last_err = prev["last_error"].iloc[0]
    upsert("source_status", pd.DataFrame([{"source": source, "status": status, "last_ok": last_ok,
                                            "last_error": last_err, "message": message[:300], "updated_at": ts}]), path)


def get_checkpoint(job: str, path: Optional[Path] = None) -> Optional[str]:
    df = query_df("SELECT last_value FROM checkpoints WHERE job = ?", [job], path=path)
    return None if df.empty else str(df["last_value"].iloc[0])


def set_checkpoint(job: str, value: str, path: Optional[Path] = None) -> None:
    upsert("checkpoints", pd.DataFrame([{"job": job, "last_value": value,
                                          "updated_at": now_vn().replace(tzinfo=None)}]), path)
