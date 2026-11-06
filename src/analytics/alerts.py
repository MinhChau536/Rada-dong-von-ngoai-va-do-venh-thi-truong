"""
Cảnh báo theo quy tắc (bước B8.1, B8.2, B8.4) – 8 quy tắc ở bảng mục 8.6, ngưỡng đọc từ settings.yaml.

Chống trùng: event_id = hash(loại, mã, phiên); cùng (loại, mã) trong cooldown 30 phút chỉ gửi 1 tin;
tối đa 5 cảnh báo thị trường/ngày theo ưu tiên; cảnh báo hệ thống (quy tắc 8) không giới hạn.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from src.common import fmt
from src.common.config import abs_path, get
from src.common.logging import get_logger
from src.data import database as db

log = get_logger(__name__)
PRIO_ORDER = {"system": 0, "high": 1, "medium": 2, "low": 3}


def event_id(alert_type: str, symbol: str, session) -> str:
    return hashlib.sha1(f"{alert_type}|{symbol}|{pd.Timestamp(session).date()}".encode()).hexdigest()[:16]


def _a(rule, typ, sym, prio, msg, session) -> Dict:
    return {"rule_no": rule, "alert_type": typ, "symbol": sym or "", "priority": prio, "message": msg,
            "trade_date": pd.Timestamp(session).date(), "event_id": event_id(typ, sym or "", session)}


def evaluate(day: pd.Series, leaders: pd.DataFrame, top_flow: pd.DataFrame, wl: pd.DataFrame,
             system: Optional[Dict] = None) -> List[Dict]:
    """Trả về danh sách cảnh báo kích hoạt cho một phiên (chưa lọc)."""
    A = get("alerts")
    out: List[Dict] = []
    sess = day["trade_date"]
    dI, cr5 = day.get("dI"), day.get("CR5")
    # 1. Chỉ số do ít mã dẫn dắt
    if dI is not None and cr5 is not None and abs(dI) >= A["dI_min"] and cr5 >= A["cr5_min"]:
        side = "pos" if dI > 0 else "neg"
        names = ", ".join(leaders[leaders["side"] == side].sort_values("rank")["symbol"].head(5))
        out.append(_a(1, "index_concentrated", "", "high",
                      f"VN-Index {fmt.num(dI, 2, True)} điểm, trong đó 5 mã đóng góp {fmt.frac_pct(cr5, 0)}: {names}", sess))
    # 2. Độ vênh cao
    if day.get("session_type") in ("narrow_up", "narrow_down") and bool(day.get("high_divergence")):
        out.append(_a(2, "high_divergence", "", "high",
                      f"Chỉ số {fmt.pct(day.get('r_vni_pct'))} nhưng trung vị cổ phiếu {fmt.pct(day.get('median_ret_pct'))}, "
                      f"độ vênh cao hơn {fmt.num(day.get('D_pct250'), 0)}% số phiên một năm qua", sess))
    # 3. Dòng vốn ngoại toàn sàn bất thường
    z = day.get("z_NF_total")
    if z is not None and not pd.isna(z) and abs(z) >= A["z_total_nf"]:
        verb = "mua" if day["NF_total"] > 0 else "bán"
        tops = top_flow.sort_values("net_flow", ascending=(verb == "bán")).head(3)["symbol"].tolist() if top_flow is not None else []
        out.append(_a(3, "foreign_market", "", "medium",
                      f"Khối ngoại {verb} ròng {fmt.bn(abs(day['NF_total']), 0, False)} (z = {fmt.num(z, 2, True)}), tập trung vào {', '.join(tops)}", sess))
    # 4–7. Watchlist
    for r in (wl.itertuples() if wl is not None else []):
        if not getattr(r, "is_valid", True):
            continue
        p60 = getattr(r, "pct60_nf", np.nan)
        if p60 is not None and not pd.isna(p60) and (p60 >= A["wl_nf_pct_hi"] or p60 <= A["wl_nf_pct_lo"]):
            verb = "mua" if r.net_flow > 0 else "bán"
            out.append(_a(4, "wl_foreign", r.symbol, "high",
                          f"Khối ngoại {verb} ròng {r.symbol} {fmt.bn(abs(r.net_flow), 1, False)}, phân vị {fmt.num(p60, 0)} trong 60 phiên, chuỗi {abs(int(r.streak))} phiên", sess))
        sd = getattr(r, "sd60_ER_M", np.nan)
        if sd is not None and not pd.isna(sd) and sd > 0 and abs(r.ER_M) >= A["wl_er_sd_mult"] * sd:
            out.append(_a(5, "wl_deviation", r.symbol, "medium",
                          f"{r.symbol} {fmt.pct(r.ret * 100)} trong khi cổ phiếu điển hình {fmt.pct(day.get('median_ret_pct'))}", sess))
        if r.symbol in set(leaders["symbol"]):
            out.append(_a(6, "wl_leader", r.symbol, "medium",
                          f"{r.symbol} đóng góp {fmt.num(r.C, 2, True)} điểm vào VN-Index hôm nay", sess))
        if getattr(r, "U", None) is not None and not pd.isna(r.U) and r.U >= A["room_used_min"]:
            out.append(_a(7, "wl_room", r.symbol, "low", f"Room ngoại của {r.symbol} đã dùng {fmt.frac_pct(r.U, 1)}", sess))
    # 8. Sự cố dữ liệu
    if system:
        if system.get("source") == "NEO":
            out.append(_a(8, "system_failover", "", "system",
                          f"Đang dùng nguồn dự phòng NEO từ {system.get('since', '?')}", sess))
        if system.get("stale_minutes") is not None and system["stale_minutes"] > A["stale_minutes"]:
            out.append(_a(8, "system_stale", "", "system",
                          f"Dữ liệu cũ hơn {int(system['stale_minutes'])} phút trong phiên", sess))
    return out


def dispatch(alerts: List[Dict], now: datetime, mode: str = "live", sender: Optional[Callable[[str], bool]] = None,
             path: Optional[Path] = None, history: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Lọc cooldown + giới hạn ngày, gửi (nếu có sender), ghi alert_log. Trả về các dòng đã ghi."""
    A = get("alerts")
    cooldown = timedelta(minutes=int(A["cooldown_min"]))
    hist = history if history is not None else db.query_df(
        "SELECT * FROM alert_log WHERE mode = ? AND ts >= ?", [mode, now - timedelta(days=1)], path=path)
    sent = hist[hist["status"].isin(["sent", "simulated"])] if not hist.empty else hist
    day0 = now.date()
    n_market_today = int(((pd.to_datetime(sent["ts"]).dt.date == day0) & (sent["priority"] != "system")).sum()) if not sent.empty else 0
    rows = []
    for a in sorted(alerts, key=lambda x: PRIO_ORDER.get(x["priority"], 9)):
        status = "simulated" if mode == "backtest" else "sent"
        if not sent.empty:
            same = sent[(sent["alert_type"] == a["alert_type"]) & (sent["symbol"] == a["symbol"])]
            if (same["event_id"] == a["event_id"]).any() or (now - pd.to_datetime(same["ts"]) < cooldown).any():
                status = "suppressed_duplicate"
        if status in ("sent", "simulated") and a["priority"] != "system" and n_market_today >= int(A["max_market_per_day"]):
            status = "suppressed_limit"
        if status == "sent" and sender is not None:
            ok = sender(f"⚠️ {a['message']}\n— {get('app.bot_disclaimer')}")
            status = "sent" if ok else "send_failed"
        row = {**a, "ts": now, "status": status, "channel": "telegram" if sender else "log", "mode": mode}
        rows.append(row)
        if status in ("sent", "simulated"):
            sent = pd.concat([sent, pd.DataFrame([row])], ignore_index=True)
            if a["priority"] != "system":
                n_market_today += 1
    out = pd.DataFrame(rows)
    if not out.empty and history is None:
        db.append("alert_log", out[["event_id", "ts", "trade_date", "alert_type", "rule_no", "symbol", "priority",
                                    "message", "status", "channel", "mode"]], path)
    return out


def context_for(date, path: Optional[Path] = None, watch: Optional[List[str]] = None):
    """Đọc ngữ cảnh một phiên từ kho chỉ báo (dùng chung cho live, backtest, bot)."""
    d = pd.Timestamp(date)
    day = db.query_df("SELECT * FROM indicator_daily WHERE trade_date = ?", [d], path=path)
    if day.empty:
        return None
    lead = db.query_df("SELECT * FROM leaders_daily WHERE trade_date = ?", [d], path=path)
    st = db.query_df("SELECT * FROM indicator_stock_daily WHERE trade_date = ? AND is_valid", [d], path=path)
    from src.analytics.watchlist_impact import get_watchlist
    syms = watch or get_watchlist(path)
    wl = st[st["symbol"].isin(syms)].copy()
    if not wl.empty:
        hist = db.query_df("SELECT symbol, trade_date, ER_M FROM indicator_stock_daily WHERE symbol IN ({}) "
                           "AND trade_date < ? AND is_valid ORDER BY trade_date".format(",".join("?" * len(syms))),
                           syms + [d], path=path)
        sd = hist.groupby("symbol")["ER_M"].apply(lambda x: x.tail(int(get("windows.er_sd_window", 60))).std())
        wl["sd60_ER_M"] = wl["symbol"].map(sd)
    return {"day": day.iloc[0], "leaders": lead, "flow": st[["symbol", "net_flow"]], "wl": wl}


def backtest(n_sessions: Optional[int] = None, path: Optional[Path] = None, write_note: bool = True) -> Dict:
    """B8.4 – chạy lại quy tắc trên N phiên lịch sử, mỗi phiên đánh giá 4 lần trong ngày để đo hiệu quả chống trùng."""
    n = n_sessions or int(get("alerts.backtest_sessions", 60))
    dates = db.query_df("SELECT trade_date FROM indicator_daily ORDER BY trade_date DESC LIMIT ?", [n], path=path)
    if dates.empty:
        return {}
    db.execute("DELETE FROM alert_log WHERE mode = 'backtest'", path=path)
    hist = pd.DataFrame(columns=["event_id", "ts", "alert_type", "symbol", "priority", "status"])
    all_rows = []
    for d in sorted(pd.to_datetime(dates["trade_date"])):
        ctx = context_for(d, path)
        if ctx is None:
            continue
        al = evaluate(ctx["day"], ctx["leaders"], ctx["flow"], ctx["wl"])
        for hh, mm in ((10, 0), (10, 15), (11, 0), (14, 45)):
            now = datetime(d.year, d.month, d.day, hh, mm)
            out = dispatch(al, now, mode="backtest", history=hist, path=path)
            hist = pd.concat([hist, out], ignore_index=True)
            all_rows.append(out)
    res = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    if res.empty:
        return {}
    db.append("alert_log", res[["event_id", "ts", "trade_date", "alert_type", "rule_no", "symbol", "priority",
                                "message", "status", "channel", "mode"]], path)
    kept = res[res["status"] == "simulated"]
    per_day = kept[kept["priority"] != "system"].groupby("trade_date").size().reindex(
        sorted(res["trade_date"].unique()), fill_value=0)
    summary = {
        "sessions": int(res["trade_date"].nunique()), "raw_triggers": int(len(res)),
        "kept": int(len(kept)), "dup_suppressed": int((res["status"] == "suppressed_duplicate").sum()),
        "limit_suppressed": int((res["status"] == "suppressed_limit").sum()),
        "mean_market_per_day": float(per_day.mean()), "max_market_per_day": int(per_day.max()),
        "by_type": kept["alert_type"].value_counts().to_dict(),
        "raw_unique_per_day": float(res.drop_duplicates(["trade_date", "event_id"]).groupby("trade_date").size().mean()),
    }
    from src.common.config import is_main_store
    if write_note and is_main_store(path):
        p = abs_path("docs/notes/alert_backtest.md")
        lines = ["# Chạy lại cảnh báo trên dữ liệu lịch sử (bước B8.4)", "",
                 f"- Số phiên: **{summary['sessions']}**; mỗi phiên đánh giá 4 lần (10:00, 10:15, 11:00, 14:45).",
                 f"- Số lượt kích hoạt thô: {summary['raw_triggers']}; số cảnh báo duy nhất/ngày trước lọc: "
                 f"{summary['raw_unique_per_day']:.2f}.",
                 f"- Bị chặn do trùng/cooldown: {summary['dup_suppressed']}; bị chặn do giới hạn ngày: {summary['limit_suppressed']}.",
                 f"- Cảnh báo thị trường được giữ: trung bình **{summary['mean_market_per_day']:.2f}/ngày**, tối đa "
                 f"{summary['max_market_per_day']}/ngày (ngưỡng ≤ {get('alerts.max_market_per_day')}).",
                 "", "| Loại | Số lượng |", "|---|---|"] + [f"| {k} | {v} |" for k, v in summary["by_type"].items()] + [
                 "", "_Tạo tự động bởi `src/analytics/alerts.py::backtest` – chạy lại khi đổi ngưỡng trong settings.yaml._"]
        p.write_text("\n".join(lines), encoding="utf-8")
    return summary
