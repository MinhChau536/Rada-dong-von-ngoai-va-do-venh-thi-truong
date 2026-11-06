"""
Dựng bảng chuẩn từ tầng raw (bước B2.1).

- Đọc payload JSON gốc, ánh xạ tên trường theo config/data_dictionary.yaml (SSI hoặc NEO).
- Đổi kiểu số, GIỮ NULL (không điền 0), chuẩn ngày theo giờ Việt Nam.
- Loại trùng theo (trade_date, symbol): giữ nguồn ưu tiên cao nhất (SSI > NEO), ghi data_quality_log.
- Dựng dim_securities (ListedShare theo ngày lấy), dim_universe (VN30, FTSE, CONTROL), dim_events, fact_intraday.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from src.common.config import events, field_map, ftse_universe, control_group, stock_groups
from src.common.logging import get_logger
from src.common.timeutil import now_vn
from src.data import database as db

log = get_logger(__name__)

NUM_STOCK = ["ref", "ceiling", "floor", "open", "high", "low", "close", "vol", "tv", "vol_pt", "tv_pt",
             "fb_vol", "fs_vol", "fb", "fs", "remain"]
NUM_INDEX = ["value", "change", "ratio_change", "open", "high", "low", "vol", "tv"]
INT_INDEX = ["advances", "declines", "no_changes", "ceilings", "floors"]


def source_priority() -> List[str]:
    return ["SSI", "NEO"]          # SSI là nguồn chính; NEO thay thế khi SSI thiếu phiên/mã


_THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")


def _num(s: pd.Series) -> pd.Series:
    """Chuỗi số SSI ('20150', '-0.70'); phòng trường hợp có dấu phân cách nghìn '1,234,500'. Giữ NULL."""
    x = s.astype(str).str.strip()
    x = x.where(~x.str.match(_THOUSANDS), x.str.replace(",", "", regex=False))
    x = x.replace({"": np.nan, "None": np.nan, "nan": np.nan, "null": np.nan})
    return pd.to_numeric(x, errors="coerce")


def _parse(raw: pd.DataFrame, table: str) -> pd.DataFrame:
    """payload JSON → DataFrame cột chuẩn. So khớp tên trường KHÔNG phân biệt hoa/thường, theo nguồn SSI hoặc NEO."""
    out = []
    for src, g in raw.groupby("source"):
        fmap = field_map(table, "neo" if src.upper().startswith("NEO") else "ssi")
        recs = []
        for p in g["payload"]:
            d = json.loads(p)
            row = {}
            for k, v in d.items():
                col = fmap.get(str(k).lower())
                if col is not None and col not in row:
                    row[col] = v
            recs.append(row)
        df = pd.DataFrame.from_records(recs)
        df["source"] = src
        df["_key_date"] = g["trade_date"].values
        for k in [c for c in g.columns if c not in ("payload", "source", "trade_date")]:
            df["_key_" + k] = g[k].values
        out.append(df)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _dedupe(df: pd.DataFrame, keys: List[str], name: str, qrows: list) -> pd.DataFrame:
    pri = {s: i for i, s in enumerate(source_priority())}
    df = df[df["source"].isin(pri)].copy()
    df["_p"] = df["source"].map(pri)
    df = df.sort_values(keys + ["_p"])
    dup = df.duplicated(keys, keep="first")
    if dup.any():
        qrows.append({"trade_date": None, "check_name": f"dedupe_{name}", "metric": "n_duplicates",
                      "value": int(dup.sum()), "status": "info", "detail": "Giữ nguồn ưu tiên cao nhất"})
    return df[~dup].drop(columns="_p")


def build_daily_stock(path: Optional[Path] = None) -> pd.DataFrame:
    raw = db.query_df("SELECT trade_date, symbol, source, payload FROM raw_daily_stock", path=path)
    if raw.empty:
        log.warning("raw_daily_stock trống")
        return pd.DataFrame()
    df = _parse(raw, "daily_stock")
    df["trade_date"] = pd.to_datetime(df["_key_date"]).dt.date
    df["symbol"] = df["_key_symbol"].astype(str).str.upper().str.strip()
    for c in NUM_STOCK + ["room_api", "listed_share_api"]:
        df[c] = _num(df[c]) if c in df.columns else np.nan
    qrows: list = []
    df = _dedupe(df, ["trade_date", "symbol"], "daily_stock", qrows)
    # NULL theo cột – ghi nhật ký (không điền giá trị)
    for c in NUM_STOCK:
        n_null = int(df[c].isna().sum())
        if n_null:
            qrows.append({"trade_date": None, "check_name": "null_count", "metric": c, "value": n_null,
                          "status": "info", "detail": "fact_daily_stock"})
    # Tổng room = giới hạn sở hữu × ListedShare (as-of)
    sec = build_securities(path, write=False)
    df = attach_shares(df, sec)
    lim = stock_groups().set_index("symbol")["foreign_limit"] if not stock_groups().empty else pd.Series(dtype=float)
    df["listed_share"] = df["listed_share"].fillna(df["listed_share_api"])
    df["room"] = df["room_api"].where(df["room_api"] > 0, df["symbol"].map(lim).fillna(0.49) * df["listed_share"])
    df["loaded_at"] = now_vn().replace(tzinfo=None)
    cols = ["trade_date", "symbol", "source"] + NUM_STOCK + ["room", "loaded_at"]
    fact = df[cols].copy()
    with db.connect(path=path) as con:
        con.execute("DELETE FROM fact_daily_stock")
        db.upsert("fact_daily_stock", fact, con=con)
    db.log_quality(qrows, path)
    log.info("fact_daily_stock: %d dòng, %d mã, %d phiên", len(fact), fact["symbol"].nunique(), fact["trade_date"].nunique())
    return fact


def attach_shares(df: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """Gắn ListedShare có hiệu lực tại ngày giao dịch (bản ghi as_of gần nhất ≤ ngày; nếu không có dùng bản sớm nhất)."""
    if sec.empty:
        df["listed_share"] = np.nan
        return df
    s = sec[["symbol", "as_of", "listed_share"]].copy()
    s["as_of"] = pd.to_datetime(s["as_of"]).astype("datetime64[ns]")
    d = df.copy()
    d["_dt"] = pd.to_datetime(d["trade_date"]).astype("datetime64[ns]")
    d = d.sort_values("_dt")
    s = s.sort_values("as_of")
    m = pd.merge_asof(d, s, left_on="_dt", right_on="as_of", by="symbol", direction="backward")
    first = s.groupby("symbol")["listed_share"].first()
    m["listed_share"] = m["listed_share"].fillna(m["symbol"].map(first))
    return m.drop(columns=["_dt", "as_of"])


def build_securities(path: Optional[Path] = None, write: bool = True) -> pd.DataFrame:
    raw = db.query_df("SELECT symbol, as_of, source, payload FROM raw_securities", path=path)
    if raw.empty:
        return pd.DataFrame(columns=["symbol", "sec_type", "exchange", "listed_share", "as_of", "source"])
    pri = {s: i for i, s in enumerate(source_priority())}
    raw = raw[raw["source"].isin(pri)]
    recs = []
    for src, payload, as_of in zip(raw["source"], raw["payload"], raw["as_of"]):
        fmap = field_map("securities", "neo" if src.upper().startswith("NEO") else "ssi")
        d = {fmap[k.lower()]: v for k, v in json.loads(payload).items() if k.lower() in fmap}
        d.update({"as_of": as_of, "source": src})
        recs.append(d)
    recs = pd.DataFrame.from_records(recs)
    for c in ("symbol", "sec_type", "exchange", "listed_share"):
        if c not in recs:
            recs[c] = None
    recs["symbol"] = recs["symbol"].astype(str).str.upper().str.strip()
    recs["listed_share"] = _num(recs["listed_share"])
    pri = {s: i for i, s in enumerate(source_priority())}
    recs = recs.assign(_p=recs["source"].map(pri)).sort_values(["symbol", "as_of", "_p"]).drop(columns="_p")
    recs = recs[recs["listed_share"].notna()].drop_duplicates(["symbol", "as_of"], keep="first")
    out = recs[["symbol", "sec_type", "exchange", "listed_share", "as_of", "source"]].copy()
    if write:
        out["loaded_at"] = now_vn().replace(tzinfo=None)
        with db.connect(path=path) as con:
            con.execute("DELETE FROM dim_securities")
            db.upsert("dim_securities", out, con=con)
    return out


def build_daily_index(path: Optional[Path] = None) -> pd.DataFrame:
    raw = db.query_df("SELECT trade_date, index_code, source, payload FROM raw_daily_index", path=path)
    if raw.empty:
        return pd.DataFrame()
    df = _parse(raw, "daily_index")
    df["trade_date"] = pd.to_datetime(df["_key_date"]).dt.date
    df["index_code"] = df["_key_index_code"]           # mã chuẩn đã gán khi tải (SSI có thể trả 'HNXIndex')
    for c in NUM_INDEX:
        df[c] = _num(df[c]) if c in df.columns else np.nan
    for c in INT_INDEX:
        df[c] = _num(df[c]).astype("Int64") if c in df.columns else pd.NA
    qrows: list = []
    df = _dedupe(df, ["trade_date", "index_code"], "daily_index", qrows)
    df["loaded_at"] = now_vn().replace(tzinfo=None)
    cols = ["trade_date", "index_code", "source"] + NUM_INDEX + INT_INDEX + ["loaded_at"]
    fact = df[cols]
    with db.connect(path=path) as con:
        con.execute("DELETE FROM fact_daily_index")
        db.upsert("fact_daily_index", fact, con=con)
    db.log_quality(qrows, path)
    return fact


def build_intraday(path: Optional[Path] = None) -> pd.DataFrame:
    raw = db.query_df("SELECT ts, symbol, source, payload FROM raw_intraday", path=path)
    if raw.empty:
        return pd.DataFrame()
    pri = {s: i for i, s in enumerate(source_priority())}
    raw = raw[raw["source"].isin(pri)]
    fmap = field_map("intraday", "ssi")
    rec = pd.DataFrame.from_records([{fmap[k.lower()]: v for k, v in json.loads(p).items() if k.lower() in fmap}
                                     for p in raw["payload"]])
    out = pd.DataFrame({"ts": raw["ts"].values, "symbol": raw["symbol"].values, "source": raw["source"].values})
    for c in ("open", "high", "low", "close", "vol"):
        out[c] = _num(rec[c]).values if c in rec.columns else np.nan
    out = out.drop_duplicates(["ts", "symbol"])
    with db.connect(path=path) as con:
        con.execute("DELETE FROM fact_intraday")
        db.upsert("fact_intraday", out, con=con)
    return out


def build_dims(path: Optional[Path] = None) -> None:
    rows = []
    comp = db.query_df("SELECT index_code, symbol, as_of, source FROM raw_index_components", path=path)
    if not comp.empty:
        comp = comp[comp["source"].isin(source_priority())]
        latest = comp["as_of"].max()
        for s in comp.loc[comp["as_of"] == latest, "symbol"]:
            rows.append({"universe": "VN30", "symbol": s, "effective_date": latest, "source": "IndexComponents"})
    else:  # dự phòng: cột in_vn30 của stock_groups.csv
        g = stock_groups()
        for s in g.loc[g["in_vn30"], "symbol"]:
            rows.append({"universe": "VN30", "symbol": s, "effective_date": None, "source": "stock_groups.csv"})
    fu = ftse_universe()
    for r in fu.itertuples():
        rows.append({"universe": "FTSE", "symbol": r.symbol,
                     "effective_date": None if pd.isna(r.effective_date) else r.effective_date.date(),
                     "source": "ftse_universe.csv"})
    cg = control_group()
    if not cg.empty and "control_symbol" in cg.columns:
        for s in cg["control_symbol"].dropna().unique():
            rows.append({"universe": "CONTROL", "symbol": s, "effective_date": None, "source": "control_group.csv"})
    du = pd.DataFrame(rows)
    ev = events()
    de = pd.DataFrame({
        "event_id": ev["event_id"], "event_date": ev["event_date"].dt.date,
        "effective_date": ev["effective_date"].apply(lambda x: None if pd.isna(x) else x.date()),
        "label": ev["label"], "description": ev["description"], "source_url": ev["source_url"]})
    with db.connect(path=path) as con:
        con.execute("DELETE FROM dim_universe")
        if not du.empty:
            du["effective_date"] = pd.to_datetime(du["effective_date"]).dt.date
            db.upsert("dim_universe", du, con=con)
        con.execute("DELETE FROM dim_events")
        db.upsert("dim_events", de, con=con)


def build_all(path: Optional[Path] = None) -> dict:
    db.init_schema(path)
    build_securities(path)
    f = build_daily_stock(path)
    i = build_daily_index(path)
    it = build_intraday(path)
    build_dims(path)
    return {"fact_daily_stock": len(f), "fact_daily_index": len(i), "fact_intraday": len(it)}


if __name__ == "__main__":
    print(build_all())
