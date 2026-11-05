"""
Tầng chỉ báo – MỘT nguồn số liệu duy nhất cho giao diện, PDF và Telegram (mục 10).

fact_* → indicator_stock_daily, indicator_daily, indicator_group_daily, leaders_daily, indicator_intraday.
Tính lại toàn bộ (CREATE OR REPLACE) để tái lập được từ raw (bước B12.3).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from src.common.config import get, stock_groups
from src.common.logging import get_logger
from src.data import database as db
from src.data.build_facts import attach_shares
from src.finance import breadth as fb
from src.finance import contribution as fc
from src.finance import domestic as fd
from src.finance import foreign_flow as ff
from src.finance.utils import rolling_pct_rank

log = get_logger(__name__)
PCT_METRICS = ["D", "CR5", "IQR_pct", "AD", "NF_total", "HHI", "median_ret_pct"]


def load_inputs(path: Optional[Path] = None) -> Dict[str, pd.DataFrame]:
    stock = db.query_df("SELECT * FROM fact_daily_stock ORDER BY trade_date, symbol", path=path)
    index = db.query_df("SELECT * FROM fact_daily_index ORDER BY trade_date", path=path)
    sec = db.query_df("SELECT symbol, sec_type, exchange, listed_share, as_of FROM dim_securities", path=path)
    uni = db.query_df("SELECT universe, symbol FROM dim_universe", path=path)
    return {"stock": stock, "index": index, "sec": sec, "uni": uni}


def _tech_cols(d: pd.DataFrame) -> pd.DataFrame:
    """Cột kỹ thuật dùng cho độ rộng & cổ phiếu nổi bật (kế thừa logic _symbol_row giữa kỳ)."""
    parts = []
    for _, g in d.groupby("symbol", sort=False):
        g = g.sort_values("trade_date").copy()
        c, v = g["close"], g["vol"]
        g["ma20"] = c.rolling(20, min_periods=10).mean()
        g["above_ma20"] = c > g["ma20"]
        hi20 = c.shift(1).rolling(20, min_periods=10).max()
        lo20 = c.shift(1).rolling(20, min_periods=10).min()
        g["new_high20"] = c > hi20
        g["new_low20"] = c < lo20
        avg20 = v.shift(1).rolling(20, min_periods=10).mean()
        g["vol_ratio"] = v / avg20.replace(0, np.nan)
        g["ret_5d"] = (c / c.shift(5) - 1) * 100
        g["ret_20d"] = (c / c.shift(20) - 1) * 100
        parts.append(g)
    return pd.concat(parts)


def compute(path: Optional[Path] = None, write: bool = True) -> Dict[str, object]:
    inp = load_inputs(path)
    stock, index, sec = inp["stock"], inp["index"], inp["sec"]
    if stock.empty or index.empty:
        raise RuntimeError("Chưa có dữ liệu fact – chạy backfill/build_facts trước")
    stock["trade_date"] = pd.to_datetime(stock["trade_date"])
    index["trade_date"] = pd.to_datetime(index["trade_date"])
    groups = stock_groups()
    sector = groups.set_index("symbol")["sector"]
    family = groups.set_index("symbol")["family"].dropna()

    # ── chỉ số VN-Index ──
    vni = index[index["index_code"] == "VNINDEX"].set_index("trade_date").sort_index().copy()
    vni["prev_value"] = vni["value"].shift(1)
    vni.loc[vni["prev_value"].isna(), "prev_value"] = vni["value"] - vni["change"]
    r_vni = vni["value"] / vni["prev_value"] - 1

    # ── mã × phiên ──
    sec_type = sec.drop_duplicates("symbol", keep="last").set_index("symbol")["sec_type"] if not sec.empty else None
    s = stock.drop(columns=["listed_share"], errors="ignore")
    if not sec.empty:
        s = attach_shares(s.assign(trade_date=s["trade_date"].dt.date), sec)
        s["trade_date"] = pd.to_datetime(s["trade_date"])
    else:
        s["listed_share"] = np.nan
    s = fb.add_validity(s, sec_type)
    s["ret_w"] = s.groupby("trade_date")["ret"].transform(
        lambda x: x.clip(x.quantile(get("cleaning.winsor_lower", .01)), x.quantile(get("cleaning.winsor_upper", .99))))

    # ── Module A ──
    day = fb.daily_breadth(s, r_vni)
    s, cday, meta = fc.contributions(s, vni[["value", "prev_value"]])
    day = day.join(cday[["dI", "sumC", "sumC_raw", "eps", "eps_raw", "CR5"]], how="left")
    day = day.join(vni[["value", "prev_value"]].rename(columns={"value": "vni"}), how="left")

    # ── Module B ──
    den = ff.decide_denominator(s)
    s = ff.stock_flows(s, den["chosen"])
    s["absorb_state"] = fd.absorb_states(s["nf"], s["ret"]).values
    s.loc[~s["is_valid"], "absorb_state"] = "neutral"
    mflow = ff.market_flows(s)
    day = day.join(mflow, how="left")
    # NF_top: mua ròng chuẩn hóa vào Top10 vốn hóa (H2c)
    topn = int(get("foreign.top_value_n", 10))
    top = s[s["is_valid"]].sort_values("w", ascending=False).groupby("trade_date").head(topn)
    tg = top.groupby("trade_date")
    day["NF_top"] = tg["net_flow"].sum() / tg["tv"].sum().replace(0, np.nan)

    # ── Module D (cấp mã) ──
    s["ER_I"] = s["ret"] - s["trade_date"].map(r_vni)
    s["ER_M"] = s["ret"] - s["trade_date"].map(day["median_ret_pct"] / 100)
    s = _tech_cols(s)
    s["sector"] = s["symbol"].map(sector).fillna("Khác")
    s["family"] = s["symbol"].map(family)

    # ── nhóm đối chứng (B6.1) – cần vốn hóa & thanh khoản ──
    from src.analytics.event_study import match_control
    ctrl = match_control(s)
    uni = db.query_df("SELECT universe, symbol FROM dim_universe", path=path)
    uni = uni[uni["universe"] != "CONTROL"]
    if ctrl is not None and not ctrl.empty:
        uni = pd.concat([uni, pd.DataFrame({"universe": "CONTROL", "symbol": ctrl["control_symbol"]})])
        if write:
            with db.connect(path=path) as con:
                con.execute("DELETE FROM dim_universe WHERE universe = 'CONTROL'")
                db.upsert("dim_universe", pd.DataFrame({"universe": "CONTROL", "symbol": ctrl["control_symbol"],
                                                        "effective_date": None, "source": "control_group.csv"}), con=con)

    # ── nhóm: ngành, họ, FTSE, đối chứng, VN30 ──
    grp_rows = []
    gc_sec = fc.group_contrib(s, sector, "sector", day)
    gc_fam = fc.group_contrib(s, family, "family", day)
    gf_sec = ff.group_flows(s, sector, "sector")
    gf_fam = ff.group_flows(s, family, "family")
    gpieces = [gc_sec.merge(gf_sec, on=["trade_date", "group_name", "group_type"], how="outer", suffixes=("", "_f")),
               gc_fam.merge(gf_fam, on=["trade_date", "group_name", "group_type"], how="outer", suffixes=("", "_f"))]
    for uname in ("FTSE", "CONTROL", "VN30"):
        syms = set(uni.loc[uni["universe"] == uname, "symbol"])
        if not syms:
            continue
        mp = pd.Series({x: uname for x in syms})
        a = fc.group_contrib(s, mp, "universe", day)
        b = ff.group_flows(s, mp, "universe")
        gpieces.append(a.merge(b, on=["trade_date", "group_name", "group_type"], how="outer", suffixes=("", "_f")))
    groups_df = pd.concat(gpieces, ignore_index=True)
    groups_df = groups_df.drop(columns=[c for c in groups_df.columns if c.endswith("_f")])
    groups_df["absorb_state"] = fd.absorb_states(groups_df["nf"], groups_df["ret_eq"]).values
    vin = gc_fam[gc_fam["group_name"] == get("contribution.family_default", "VINGROUP")].set_index("trade_date")
    day["C_vingroup"] = vin["C"]
    day["index_ex_vingroup_ret_pct"] = vin["index_ex_group_ret_pct"]

    # ── phân vị lịch sử 20/60/250 (chỉ dữ liệu đến t−1) ──
    day = day.sort_index()
    for m in PCT_METRICS:
        for w in get("windows.pct_windows", [20, 60, 250]):
            day[f"{m}_pct{w}"] = rolling_pct_rank(day[m], int(w))
    lead = fc.leaders(s, day)
    st_codes = day["session_type"].tolist()
    day["n_sessions_same_type_5"] = [sum(1 for x in st_codes[max(0, i - 4):i + 1] if x == st_codes[i])
                                     for i in range(len(st_codes))]
    day["source"] = s.groupby("trade_date")["source"].agg(lambda x: x.mode().iat[0] if len(x) else None)
    day = day.reset_index().rename(columns={"index": "trade_date"})

    s_cols = ["trade_date", "symbol", "source", "sector", "family", "ref", "ceiling", "floor", "open", "high", "low",
              "close", "vol", "tv", "tv_pt", "fb", "fs", "remain", "room", "listed_share", "is_valid", "is_ceiling",
              "is_floor", "ret", "ret_w", "w", "C", "C_raw", "net_flow", "nf", "FPR", "U", "room_changed", "z_nf",
              "pct60_nf", "streak", "reversal", "absorb_state", "ER_I", "ER_M", "ma20", "above_ma20", "new_high20",
              "new_low20", "vol_ratio", "ret_5d", "ret_20d"]
    stock_ind = s[s_cols].sort_values(["trade_date", "symbol"]).reset_index(drop=True)
    meta.update({"denominator": den})
    if write:
        db.replace_table("indicator_stock_daily", stock_ind, path)
        db.replace_table("indicator_daily", day, path)
        db.replace_table("indicator_group_daily", groups_df, path)
        db.replace_table("leaders_daily", lead, path)
        db.replace_table("pipeline_meta", pd.DataFrame([{
            "scale_k": meta["scale_k"], "eps_median_raw": meta["eps_median_raw"], "eps_median": meta["eps_median"],
            "denominator": den["chosen"], "foreign_includes_deal": den["includes_deal"],
            "share_exceed_bigdeal": den["share_exceed_bigdeal"], "n_bigdeal": den["n_bigdeal"],
            "computed_at": pd.Timestamp.now()}]), path)
        intraday_indicators(path)
    log.info("Chỉ báo: %d phiên, %d dòng mã×phiên; trung vị |ε| = %.3f (k = %.4f); mẫu số nf = %s",
             len(day), len(stock_ind), meta["eps_median"], meta["scale_k"], den["chosen"])
    return {"day": day, "stock": stock_ind, "groups": groups_df, "leaders": lead, "meta": meta}


def intraday_indicators(path: Optional[Path] = None) -> pd.DataFrame:
    """Chỉ báo trong phiên (5 phút) cho phiên gần nhất có nến: lợi suất lũy kế VN30 và trung vị rổ VN30."""
    it = db.query_df("SELECT * FROM fact_intraday ORDER BY ts", path=path)
    if it.empty:
        db.replace_table("indicator_intraday", pd.DataFrame(columns=["ts", "session_date", "vn30_ret_pct",
                                                                     "median_ret_pct", "D_intraday"]), path)
        return pd.DataFrame()
    it["session_date"] = pd.to_datetime(it["ts"]).dt.date
    rows = []
    for d, g in it.groupby("session_date"):
        piv = g.pivot_table(index="ts", columns="symbol", values="close")
        first = piv.iloc[0]
        cum = piv / first - 1
        idx = cum["VN30"] if "VN30" in cum else cum.mean(axis=1)
        stocks = cum.drop(columns=["VN30"], errors="ignore")
        med = stocks.median(axis=1)
        rows.append(pd.DataFrame({"ts": cum.index, "session_date": d, "vn30_ret_pct": idx.values * 100,
                                  "median_ret_pct": med.values * 100, "D_intraday": (idx - med).values * 100}))
    out = pd.concat(rows, ignore_index=True)
    db.replace_table("indicator_intraday", out, path)
    return out


if __name__ == "__main__":
    r = compute()
    print(r["meta"])
    print(r["day"].tail(3).T)
