"""
Ngữ cảnh số liệu DÙNG CHUNG cho PDF và Telegram (và đối chiếu với giao diện – bước B12.5).
Mọi con số đọc từ indicator_* và định dạng bằng src.common.fmt nên ba kênh trùng khớp.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from src.analytics import narrative
from src.analytics import watchlist_impact as wi
from src.common import fmt
from src.data import database as db


def latest_date(path: Optional[Path] = None) -> Optional[pd.Timestamp]:
    df = db.query_df("SELECT MAX(trade_date) AS d FROM indicator_daily", path=path)
    return None if df.empty or pd.isna(df["d"].iloc[0]) else pd.Timestamp(df["d"].iloc[0])


def build(date=None, path: Optional[Path] = None) -> Optional[Dict]:
    d = pd.Timestamp(date) if date is not None else latest_date(path)
    if d is None:
        return None
    day = db.query_df("SELECT * FROM indicator_daily WHERE trade_date = ?", [d], path=path)
    if day.empty:
        return None
    day = day.iloc[0]
    hist = db.query_df("SELECT * FROM indicator_daily WHERE trade_date <= ? ORDER BY trade_date", [d], path=path)
    stock = db.query_df("SELECT * FROM indicator_stock_daily WHERE trade_date = ?", [d], path=path)
    lead = db.query_df("SELECT * FROM leaders_daily WHERE trade_date = ? ORDER BY side, rank", [d], path=path)
    groups = db.query_df("SELECT * FROM indicator_group_daily WHERE trade_date = ?", [d], path=path)
    idx = db.query_df("SELECT * FROM fact_daily_index WHERE trade_date = ?", [d], path=path)
    syms = wi.get_watchlist(path)
    wl_hist = db.query_df("SELECT * FROM indicator_stock_daily WHERE symbol IN ({}) AND trade_date <= ?".format(
        ",".join("?" * len(syms))), syms + [d], path=path) if syms else pd.DataFrame()
    intra = db.query_df("SELECT * FROM fact_intraday", path=path)
    prof = wi.compute(pd.concat([wl_hist, stock]).drop_duplicates(["trade_date", "symbol"]), hist, intra, syms, d)["profile"] \
        if syms else pd.DataFrame()
    v = stock[stock["is_valid"]]
    src = str(day.get("source") or "")
    return {
        "date": d, "day": day, "hist": hist, "stock": stock, "leaders": lead, "groups": groups, "index": idx,
        "watch": prof, "top_buy": v.nlargest(5, "net_flow"), "top_sell": v.nsmallest(5, "net_flow"),
        "summary": narrative.market_summary(day, lead, with_disclaimer=False),
        "foreign": narrative.foreign_summary(day, v.nlargest(5, "net_flow"), v.nsmallest(5, "net_flow")),
        "is_demo": src.startswith("DEMO"), "source": src,
    }


def key_numbers(ctx: Dict) -> Dict[str, str]:
    """10 con số dùng để đối chiếu ba kênh (B12.5)."""
    x = ctx["day"]
    return {
        "VN-Index": fmt.num(x["vni"]), "ΔVN-Index": fmt.num(x["dI"], 2, True), "r_VNI": fmt.pct(x["r_vni_pct"]),
        "Trung vị": fmt.pct(x["median_ret_pct"]), "D": fmt.num(x["D"], 2, True), "CR5": fmt.frac_pct(x["CR5"], 0),
        "AD": fmt.num(x["AD"], 2, True), "NF HOSE": fmt.bn(x["NF_total"]), "HHI": fmt.num(x["HHI"], 3),
        "ε": fmt.num(x["eps"], 2, True),
    }
