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
    ctx = {
        "date": d, "day": day, "hist": hist, "stock": stock, "leaders": lead, "groups": groups, "index": idx,
        "watch": prof, "top_buy": v.nlargest(5, "net_flow"), "top_sell": v.nsmallest(5, "net_flow"),
        "summary": narrative.market_summary(day, lead, with_disclaimer=False),
        "foreign": narrative.foreign_summary(day, v.nlargest(5, "net_flow"), v.nsmallest(5, "net_flow")),
        "is_demo": False, "source": src,
    }
    ctx.update(overview(ctx, path))
    return ctx


INDEX_NAMES = [("VNINDEX", "VN-Index"), ("VN30", "VN30"), ("HNXINDEX", "HNX-Index"), ("UPCOMINDEX", "UPCoM-Index")]


def overview(ctx: Dict, path: Optional[Path] = None) -> Dict:
    """Khối "tổng quan thị trường" + diễn biến nhiều kỳ + triển vọng thống kê – cùng công thức trang 1 dashboard."""
    from src.analytics import outlook
    from src.analytics.health import market_health, period_returns
    from src.common.config import events, get
    d, hist, stock = ctx["date"], ctx["hist"], ctx["stock"]
    ih = db.query_df("SELECT * FROM fact_daily_index WHERE trade_date <= ? ORDER BY trade_date", [d], path=path)
    ih["trade_date"] = pd.to_datetime(ih["trade_date"])
    idx_hist = {name: ih[ih["index_code"] == code].set_index("trade_date")["value"] for code, name in INDEX_NAMES}
    idx_ret = {name: period_returns(s) for name, s in idx_hist.items() if not s.empty}
    vni = idx_hist["VN-Index"]
    v = stock[stock["is_valid"]]
    pm = float(v["above_ma20"].mean() * 100) if not v.empty else None
    health = market_health(vni, ctx["day"].get("pct_up"), pm, ctx["day"].get("D_pct250"))
    sess = sorted(pd.to_datetime(hist["trade_date"]).unique())
    win = int(get("outlook.recap_long", 20))
    dates20 = sess[-win:]
    st20 = db.query_df("SELECT trade_date, symbol, sector, is_valid, w, ret, C, net_flow FROM indicator_stock_daily "
                       "WHERE trade_date >= ? AND trade_date <= ?", [dates20[0], d], path=path)
    st20["trade_date"] = pd.to_datetime(st20["trade_date"])
    sec1 = outlook.sector_returns(st20, sess[-1:])
    sec5 = outlook.sector_returns(st20, sess[-5:])
    sec20 = outlook.sector_returns(st20, dates20)
    lead20 = outlook.cum_leaders(st20, dates20)
    ev = events()
    e1 = pd.Timestamp(get("periods.announce", "2025-10-08"))
    eff = pd.Timestamp(get("periods.effective", "2026-09-21"))
    grp = db.query_df("SELECT trade_date, group_name, group_type, ret_eq, net_flow FROM indicator_group_daily "
                      "WHERE group_type = 'universe' AND trade_date >= ? AND trade_date <= ?",
                      [min(e1, pd.Timestamp(dates20[0])), d], path=path)
    ftse_rel = {}
    for lbl, since in (("20 phiên", pd.Timestamp(dates20[0])), ("từ công bố E1", e1), ("từ ngày hiệu lực", eff)):
        if since <= d:
            ftse_rel[lbl] = outlook.group_cum_returns(grp, since)
    rc = outlook.recap(hist)
    hz = tuple(get("outlook.horizons", [5, 20]))
    nf = hist.assign(trade_date=pd.to_datetime(hist["trade_date"])).set_index("trade_date")["NF_total"]
    vr = outlook.vol_range(vni, hz)
    an = outlook.analog_probabilities(vni, nf, hz, min_n=int(get("outlook.min_analog", 30)))
    pred = db.query_df("SELECT * FROM alert_predictive", path=path) if db.table_exists("alert_predictive", path) \
        else pd.DataFrame()
    sig = outlook.signals_today(ctx["day"], pred)
    return {"idx_hist": idx_hist, "idx_ret": idx_ret, "health": health, "pct_above_ma20": pm,
            "sec1": sec1, "sec5": sec5, "sec20": sec20, "lead20": lead20, "ftse_rel": ftse_rel, "recap": rc,
            "recap_text": outlook.recap_sentences(rc, idx_ret, sec5, lead20, ftse_rel),
            "vol_range": vr, "analog": an, "signals": sig,
            "outlook_text": outlook.outlook_sentences(vni, vr, an, sig), "events": ev}


def key_numbers(ctx: Dict) -> Dict[str, str]:
    """10 con số dùng để đối chiếu ba kênh (B12.5)."""
    x = ctx["day"]
    return {
        "VN-Index": fmt.num(x["vni"]), "ΔVN-Index": fmt.num(x["dI"], 2, True), "r_VNI": fmt.pct(x["r_vni_pct"]),
        "Trung vị": fmt.pct(x["median_ret_pct"]), "D": fmt.num(x["D"], 2, True), "CR5": fmt.frac_pct(x["CR5"], 0),
        "AD": fmt.num(x["AD"], 2, True), "NF HOSE": fmt.bn(x["NF_total"]), "HHI": fmt.num(x["HHI"], 3),
        "ε": fmt.num(x["eps"], 2, True),
    }
