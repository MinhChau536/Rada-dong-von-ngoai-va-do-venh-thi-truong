"""
Dựng bảng chuẩn từ tầng raw (bước B2.1).

- Đọc payload JSON gốc (SSI FastConnect V3), ánh xạ tên trường theo config/data_dictionary.yaml.
- Đổi kiểu số, GIỮ NULL (không điền 0), chuẩn ngày theo giờ Việt Nam.
- Loại trùng theo (trade_date, symbol), ghi data_quality_log.
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
from src.ssi_api.ssi_client import reenrich_stock

log = get_logger(__name__)

NUM_STOCK = ["ref", "ceiling", "floor", "open", "high", "low", "close", "vol", "tv", "vol_pt", "tv_pt",
             "fb_vol", "fs_vol", "fb", "fs", "remain"]
NUM_INDEX = ["value", "change", "ratio_change", "open", "high", "low", "vol", "tv"]
INT_INDEX = ["advances", "declines", "no_changes", "ceilings", "floors"]


def source_priority() -> List[str]:
    # SSI FastConnect V3: "SSI" = REST (chính thức) ưu tiên trên "SSI-WS" = phiên chốt từ luồng WebSocket lúc 15:05
    # (src/data/live.promote) – cùng một nhà cung cấp, bản REST thay thế bản tạm tính khi SSI công bố số cuối ngày.
    return ["SSI", "SSI-WS"]


_THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")


def _num(s: pd.Series) -> pd.Series:
    """Chuỗi số SSI ('20150', '-0.70'); phòng trường hợp có dấu phân cách nghìn '1,234,500'. Giữ NULL."""
    x = s.astype(str).str.strip()
    x = x.where(~x.str.match(_THOUSANDS), x.str.replace(",", "", regex=False))
    x = x.replace({"": np.nan, "None": np.nan, "nan": np.nan, "null": np.nan})
    return pd.to_numeric(x, errors="coerce")


def _parse(raw: pd.DataFrame, table: str) -> pd.DataFrame:
    """payload JSON → DataFrame cột chuẩn. So khớp tên trường KHÔNG phân biệt hoa/thường."""
    out = []
    for src, g in raw.groupby("source"):
        fmap = field_map(table, "ssi")
        recs = []
        for p in g["payload"]:
            d = json.loads(p)
            row = {}
            if table == "daily_stock":
                d = reenrich_stock(d)          # quy đổi thang giá theo logic hiện hành (sửa payload tải bằng bản cũ)
                row["_no_chg"] = d.get("priceChange") in (None, "") and d.get("priceChangePercentage") in (None, "")
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
    # SSI V3 trả null (không phải 0) khi phiên đó mã KHÔNG có giao dịch khối ngoại / thỏa thuận (đối chiếu phản hồi thật:
    # phiên cũ trả "0", phiên gần đây trả null). Mã có giao dịch khớp (close có giá trị) → null nghĩa là 0.
    # Room còn lại / tổng room chỉ đổi khi khối ngoại giao dịch → mang giá trị gần nhất của chính mã đó.
    # SSI V3 trả giá = 0 ở một số phiên cũ (vd. 10–14/01/2020) → coi là THIẾU, không phải giá 0 (tránh r = −100%)
    for c in ("open", "high", "low", "close"):
        bad = df[c].le(0)
        if bad.any():
            df.loc[bad, c] = np.nan
            qrows.append({"trade_date": None, "check_name": "zero_price_as_null", "metric": c, "value": int(bad.sum()),
                          "status": "info", "detail": "SSI V3 trả giá 0 → NULL (loại khỏi Ω_t)"})
    n_unit = fix_value_units(df)
    if n_unit:
        qrows.append({"trade_date": None, "check_name": "value_unit_million", "metric": "rows", "value": n_unit,
                      "status": "info", "detail": "SSI V3 trả giá trị theo TRIỆU đồng ở một số phiên (13/09/2018, "
                                                  "25/04/2019): giá trị/khối lượng < 50 đ/cp → nhân 10^6"})
    df = df.sort_values(["symbol", "trade_date"])
    n_fix = fill_ref_from_prev_close(df)
    if n_fix:
        qrows.append({"trade_date": None, "check_name": "ref_from_prev_close", "metric": "rows", "value": n_fix,
                      "status": "info", "detail": "Phiên cũ SSI không trả priceChange/%: ref điều chỉnh = close điều chỉnh "
                                                  "phiên trước của chính mã; trần/sàn quy cùng hệ số"})
    has_trade = df["close"].notna()
    # Phiên SSI bỏ trống khối ngoại cho TOÀN BỘ mã (vd. 12/11/2026: cả securitiesSummary lẫn indexSummary = null/0)
    # là THIẾU DỮ LIỆU, không phải "không ai giao dịch" → giữ NULL (chỉ báo khối ngoại phiên đó để trống, updater tải lại).
    gap_days = foreign_gap_sessions(df)
    for d in gap_days:
        qrows.append({"trade_date": d, "check_name": "foreign_missing_session", "metric": "fb", "value": 0,
                      "status": "warn", "detail": "SSI không trả khối ngoại cho mọi mã trong phiên – để trống, sẽ tải lại"})
    fillable = has_trade & ~df["trade_date"].isin(gap_days)
    for c in ("fb_vol", "fs_vol", "fb", "fs"):
        n_fill = int((df[c].isna() & fillable).sum())
        df.loc[fillable, c] = df.loc[fillable, c].fillna(0.0)
        if n_fill:
            qrows.append({"trade_date": None, "check_name": "null_as_zero", "metric": c, "value": n_fill,
                          "status": "info", "detail": "SSI V3 trả null khi không có giao dịch → 0"})
    for c in ("vol_pt", "tv_pt"):
        n_fill = int((df[c].isna() & has_trade).sum())
        df.loc[has_trade, c] = df.loc[has_trade, c].fillna(0.0)
        if n_fill:
            qrows.append({"trade_date": None, "check_name": "null_as_zero", "metric": c, "value": n_fill,
                          "status": "info", "detail": "SSI V3 trả null khi không có giao dịch → 0"})
    for c in ("remain", "room_api"):
        n_before = int(df[c].isna().sum())
        df[c] = df.groupby("symbol")[c].ffill()
        if n_before - int(df[c].isna().sum()):
            qrows.append({"trade_date": None, "check_name": "room_ffill", "metric": c,
                          "value": n_before - int(df[c].isna().sum()), "status": "info",
                          "detail": "Room không đổi khi không có giao dịch khối ngoại → mang giá trị phiên trước"})
    # NULL theo cột – ghi nhật ký (không điền giá trị)
    for c in NUM_STOCK:
        n_null = int(df[c].isna().sum())
        if n_null:
            qrows.append({"trade_date": None, "check_name": "null_count", "metric": c, "value": n_null,
                          "status": "info", "detail": "fact_daily_stock"})
    # Sàn niêm yết theo ngày (masterdata). Ngày thiếu masterdata → mang sàn của phiên gần nhất của chính mã đó.
    if "board" not in df.columns:
        df["board"] = None
    df["board"] = df["board"].astype("string").str.upper().str.strip().replace({"": pd.NA, "NONE": pd.NA})
    df["board"] = df.groupby("symbol")["board"].transform(lambda x: x.ffill().bfill())
    n_off = int((df["board"].notna() & (df["board"] != "HOSE")).sum())
    if n_off:
        qrows.append({"trade_date": None, "check_name": "off_board", "metric": "rows_not_on_HOSE", "value": n_off,
                      "status": "info", "detail": "Phiên mã còn ở UPCOM/HNX (trước khi chuyển sàn) – loại khỏi Ω_t HOSE"})
    # Tổng room = giới hạn sở hữu × ListedShare (as-of)
    sec = build_securities(path, write=False)
    df = attach_shares(df, sec)
    lim = stock_groups().set_index("symbol")["foreign_limit"] if not stock_groups().empty else pd.Series(dtype=float)
    df["listed_share"] = df["listed_share"].fillna(df["listed_share_api"])
    df["room"] = df["room_api"].where(df["room_api"] > 0, df["symbol"].map(lim).fillna(0.49) * df["listed_share"])
    df["listed_share_est"] = estimate_shares_from_room(df)
    n_est = int((df["listed_share"].isna() & df["listed_share_est"].notna()).sum())
    if n_est:
        qrows.append({"trade_date": None, "check_name": "listed_share_est", "metric": "rows", "value": n_est,
                      "status": "warn", "detail": "Mã đã hủy niêm yết: số CP niêm yết ước từ tổng room ngoại SSI / 49%"})
    df["loaded_at"] = now_vn().replace(tzinfo=None)
    cols = ["trade_date", "symbol", "source"] + NUM_STOCK + ["room", "loaded_at", "board", "listed_share_est"]
    fact = df[cols].copy()
    with db.connect(path=path) as con:
        con.execute("DELETE FROM fact_daily_stock")
        db.upsert("fact_daily_stock", fact, con=con)
    db.log_quality(qrows, path)
    log.info("fact_daily_stock: %d dòng, %d mã, %d phiên", len(fact), fact["symbol"].nunique(), fact["trade_date"].nunique())
    return fact


def foreign_gap_sessions(df: pd.DataFrame, min_traded: int = 50) -> List:
    """Phiên có ≥ `min_traded` mã khớp lệnh nhưng KHÔNG mã nào có giá trị khối ngoại (fb, fs đều NULL)."""
    t = df[df["close"].notna()]
    if t.empty:
        return []
    g = t.assign(has=t["fb"].notna() | t["fs"].notna()).groupby("trade_date").agg(n=("has", "size"), k=("has", "sum"))
    return sorted(g.index[(g["n"] >= min_traded) & (g["k"] == 0)])


VALUE_VOL_PAIRS =(("tv", "vol"), ("tv_pt", "vol_pt"), ("fb", "fb_vol"), ("fs", "fs_vol"))


def fix_value_units(df: pd.DataFrame, min_vnd_per_share: float = 50.0) -> int:
    """Giá trị giao dịch bị trả theo triệu đồng: giá bình quân ngầm định = giá trị/khối lượng < 50 đ/cp (không thể có
    với cổ phiếu HOSE, mệnh giá 10.000 đ) nhưng ×10^6 thì hợp lý → nhân 10^6. Sửa tại chỗ, trả số ô đã sửa."""
    n = 0
    for val, vol in VALUE_VOL_PAIRS:
        if val not in df.columns or vol not in df.columns:
            continue
        px = df[val] / df[vol].where(df[vol] > 0)
        bad = px.gt(0) & px.lt(min_vnd_per_share) & (px * 1e6).between(100, 1e7)
        df.loc[bad, val] = df.loc[bad, val] * 1e6
        n += int(bad.sum())
    return n


def fill_ref_from_prev_close(df: pd.DataFrame) -> int:
    """Quy ref/trần/sàn về thang giá điều chỉnh cho phiên SSI không trả priceChange lẫn priceChangePercentage.

    Chuỗi giá điều chỉnh liên tục qua ngày GDKHQ nên ref điều chỉnh của phiên t = close điều chỉnh phiên trước
    của chính mã; hệ số k = ref_điều_chỉnh / ref_gốc dùng cho trần/sàn. df phải sắp theo (symbol, trade_date);
    sửa tại chỗ, trả số dòng đã sửa. Phiên đầu tiên của mã (không có phiên trước) giữ nguyên.
    """
    from src.ssi_api.ssi_client import K_MAX, K_MIN
    if "_no_chg" not in df.columns:
        return 0
    prev = df.groupby("symbol")["close"].transform(lambda x: x.ffill().shift(1))
    k = prev / df["ref"]
    m = df["_no_chg"].fillna(False).astype(bool) & df["ref"].gt(0) & prev.gt(0) & k.gt(K_MIN) & k.lt(K_MAX)
    m &= (k - 1).abs() > 1e-6
    df.loc[m, "ref"] = prev[m]
    for c in ("ceiling", "floor"):
        df.loc[m, c] = (df.loc[m, c] * k[m]).round(3)
    return int(m.sum())


def estimate_shares_from_room(df: pd.DataFrame, default_limit: float = 0.49) -> pd.Series:
    """Số cổ phiếu niêm yết ƯỚC từ tổng room ngoại của chính SSI (room = giới hạn sở hữu × số CP niêm yết).
    Chỉ dùng khi securitiesByBoard không còn mã (đã hủy niêm yết). Giới hạn sở hữu: tỷ lệ room/CP niêm yết quan sát
    được của chính mã nếu có, nếu không 49% (mức phổ biến)."""
    room = df["room_api"].where(df["room_api"] > 0)
    ratio = (room / df["listed_share"]).where(df["listed_share"] > 0)
    lim = ratio.groupby(df["symbol"]).transform("median").where(lambda x: (x > 0.05) & (x <= 1.0001))
    return room / lim.fillna(default_limit)


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
        fmap = field_map("securities", "ssi")
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
    # Thay đổi điểm = điểm phiên này − điểm phiên liền trước của cùng chỉ số (đúng cách bảng giá SSI hiển thị);
    # chỉ giữ số indexChange của SSI ở phiên đầu chuỗi hoặc khi thiếu phiên liền trước (cách > 7 ngày)
    df = df.sort_values(["index_code", "trade_date"])
    prev_v = df.groupby("index_code")["value"].shift(1)
    prev_d = pd.to_datetime(df.groupby("index_code")["trade_date"].shift(1))
    ok = prev_v.notna() & ((pd.to_datetime(df["trade_date"]) - prev_d).dt.days <= 7) & df["value"].notna()
    df.loc[ok, "change"] = (df.loc[ok, "value"] - prev_v[ok]).round(2)
    df.loc[ok, "ratio_change"] = (df.loc[ok, "change"] / prev_v[ok] * 100).round(2)
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
        comp = comp[comp["source"].isin(source_priority()) & comp["symbol"].astype(str).str.fullmatch(r"[A-Z0-9]{3}")]
    # SSI V3 securitiesByBoard?index=VN30 chỉ trả CHÍNH mã chỉ số (không có thành phần) → < 20 mã thì coi là không có
    if not comp.empty and comp.loc[comp["as_of"] == comp["as_of"].max(), "symbol"].nunique() >= 20:
        latest = comp["as_of"].max()
        for s in comp.loc[comp["as_of"] == latest, "symbol"]:
            rows.append({"universe": "VN30", "symbol": s, "effective_date": latest, "source": "IndexComponents"})
    else:  # dự phòng: cột in_vn30 của stock_groups.csv (danh mục rổ do nhóm cập nhật – KHÔNG phải số liệu thị trường)
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
