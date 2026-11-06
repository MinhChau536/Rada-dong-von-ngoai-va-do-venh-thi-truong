"""
Chạy lại TOÀN BỘ chuỗi xử lý từ raw (bước B12.3 – tái lập).

    python -m src.data.rebuild_all                 # dựng lại toàn bộ chỉ báo từ bảng raw_* (dữ liệu SSI/NEO đã tải)
    python -m src.data.rebuild_all --hash          # in mã băm kết quả để so sánh hai lần chạy

raw → fact → indicator_* → nghiên cứu sự kiện, DiD, kiểm định → watchlist → chạy lại cảnh báo.
"""
from __future__ import annotations

import argparse
import hashlib
import time
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from src.common.config import abs_path, get
from src.common.logging import get_logger
from src.data import database as db

log = get_logger(__name__)
HASH_TABLES = ["indicator_daily", "indicator_stock_daily", "leaders_daily", "stats_results"]


def run_analytics(path: Optional[Path] = None, robustness: bool = True) -> Dict:
    from src.analytics import did, event_study, stats_tests, watchlist_impact as wi
    st = db.query_df("SELECT * FROM indicator_stock_daily", path=path)
    day = db.query_df("SELECT * FROM indicator_daily ORDER BY trade_date", path=path)
    st["trade_date"] = pd.to_datetime(st["trade_date"])
    ev = event_study.run_all(st, day)
    dd = did.estimate(st)
    s_rows = [ev["stats"], dd["stats"], stats_tests.run_all(day, st)]
    wi.ensure_default(path)
    intra = db.query_df("SELECT * FROM fact_intraday", path=path)
    wl = wi.compute(st, day, intra, wi.get_watchlist(path))
    s_rows.append(wl["stats"])
    stats_all = stats_tests.holm(pd.concat([x for x in s_rows if x is not None and not x.empty], ignore_index=True))
    db.replace_table("event_params", ev["event_params"], path)
    db.replace_table("event_results", ev["event_results"], path)
    db.replace_table("event_aar", ev["event_aar"], path)
    db.replace_table("did_coefs", dd["did_coefs"] if not dd["did_coefs"].empty else
                     pd.DataFrame(columns=["outcome", "week", "coef", "ci_lo", "ci_hi", "p_value", "variant"]), path)
    db.replace_table("stats_results", stats_all, path)
    prof = wl["profile"].copy()
    db.replace_table("indicator_watchlist", prof, path)
    db.replace_table("watchlist_reaction", wl["reaction"], path)
    from src.common.config import control_group
    cg = control_group()
    if not cg.empty:
        db.replace_table("control_balance", event_study.control_balance(cg), path)
    out = {"stats_rows": len(stats_all)}
    if robustness:
        out["robustness"] = robustness_table(st, day, path)
    return out


def robustness_table(st: pd.DataFrame, day: pd.DataFrame, path: Optional[Path] = None) -> int:
    """B6.13 – lặp kết quả chính (CAR FTSE [−1;+1], BMP; ρ(nf,r)) qua các biến thể."""
    from src.analytics import event_study, stats_tests
    variants = {
        "Cơ sở (mô hình thị trường, [−130;−11])": dict(),
        "Mô hình điều chỉnh thị trường": dict(model="market_adj"),
        "Cửa sổ ước lượng [−250;−11]": dict(est_window=get("events.estimation_window_long", [-250, -11])),
        "Loại mã trần/sàn": dict(exclude_ceiling_floor=True),
        "Loại họ Vingroup": dict(exclude_family="VINGROUP"),
        "Đối chứng phương án 2 (thanh khoản)": dict(control_col="control_symbol_liq"),
    }
    rows = []
    for name, kw in variants.items():
        res = event_study.run_all(st, day, variant=name, **kw)["stats"]
        if res.empty:
            continue
        sel = res[(res["metric"] == "CAR") & (res["window"] == "[-1;1]") &
                  (res["test"].isin(["BMP", "Welch t (FTSE − đối chứng)"]))]
        for r in sel.itertuples():
            rows.append({"variant": name, "event_id": r.event_id, "group": r.group, "test": r.test,
                         "estimate": r.estimate, "statistic": r.statistic, "p_value": r.p_value, "n": r.n})
    # Trung bình đồng trọng số thay trung vị trong D (độ vững cho H1a)
    alt = day.copy()
    alt["D"] = alt["r_vni_pct"] - alt["mean_ret_pct"]
    for r in stats_tests.h1a(alt):
        if r["test"].startswith("Mann"):
            rows.append({"variant": "D dùng trung bình đồng trọng số", "event_id": "", "group": "Toàn sàn",
                         "test": "H1a " + r["test"], "estimate": r["estimate"], "statistic": r["statistic"],
                         "p_value": r["p_value"], "n": r["n"]})
    df = pd.DataFrame(rows)
    df["sign"] = np.sign(df["estimate"])
    df["sig_5pct"] = df["p_value"] < 0.05
    db.replace_table("robustness_results", df, path)
    from src.common.config import is_main_store
    if is_main_store(path):
        df.to_csv(abs_path("docs/robustness_table.csv"), index=False, encoding="utf-8")
    return len(df)


def results_hash(path: Optional[Path] = None) -> str:
    h = hashlib.sha256()
    for t in HASH_TABLES:
        df = db.query_df(f"SELECT * FROM {t}", path=path)
        if df.empty:
            continue
        drop = [c for c in df.columns if c in ("loaded_at", "computed_at")]
        df = df.drop(columns=drop)
        df = df.sort_values(list(df.columns[:3])).reset_index(drop=True)
        num = df.select_dtypes("number").round(8)
        df[num.columns] = num
        h.update(pd.util.hash_pandas_object(df.astype(str), index=False).values.tobytes())
    return h.hexdigest()[:16]


def main(path: Optional[Path] = None, robustness: bool = True, backtest: bool = True) -> Dict:
    t0 = time.time()
    db.init_schema(path)
    from src.data import build_facts, quality
    from src.analytics import pipeline, alerts
    out = {"facts": build_facts.build_all(path)}
    pipeline.compute(path)
    out["quality"] = quality.run(path)
    out["analytics"] = run_analytics(path, robustness)
    if backtest:
        out["alerts_backtest"] = alerts.backtest(path=path)
    out["hash"] = results_hash(path)
    out["seconds"] = round(time.time() - t0, 1)
    log.info("Hoàn tất rebuild_all trong %.1f giây – hash %s", out["seconds"], out["hash"])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-robustness", action="store_true")
    ap.add_argument("--hash", action="store_true")
    a = ap.parse_args()
    if a.hash:
        print(results_hash())
    else:
        res = main(robustness=not a.no_robustness)
        for k, v in res.items():
            print(f"{k}: {v}")
