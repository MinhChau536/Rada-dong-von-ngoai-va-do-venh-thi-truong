"""
Kiểm thử tích hợp: dữ liệu mẫu → raw → fact → chỉ báo; chất lượng; tái lập (B12.3); đồng nhất ba kênh (B12.5); PDF.
"""
import pandas as pd
import pytest

from src.common import fmt


def test_facts_and_quality(demo_db):
    path, res = demo_db
    from src.data import database as db
    f = db.query_df("SELECT COUNT(*) n, COUNT(DISTINCT trade_date) d FROM fact_daily_stock", path=path).iloc[0]
    assert f["d"] > 100 and f["n"] > 100 * 150
    dup = db.query_df("SELECT trade_date, symbol, COUNT(*) c FROM fact_daily_stock GROUP BY 1,2 HAVING c > 1", path=path)
    assert dup.empty
    q = res["quality"]
    assert q["completeness"] >= 0.98
    assert q["eps_median"] < 0.5
    assert q["breadth_ok_share"] >= 0.95


def test_indicator_identities(demo_db):
    path, _ = demo_db
    from src.data import database as db
    d = db.query_df("SELECT * FROM indicator_daily", path=path)
    assert (d["dI"] - d["sumC"] - d["eps"]).abs().max() < 1e-6            # ΣC + ε = ΔI
    assert d["D"].notna().all() and d["CR5"].between(0, 1).all()
    assert d["HHI"].between(0, 1).all()
    s = db.query_df("SELECT trade_date, SUM(net_flow) nf FROM indicator_stock_daily WHERE is_valid GROUP BY 1", path=path)
    m = d.set_index("trade_date")["NF_total"].reindex(s["trade_date"]).to_numpy()
    assert abs(s["nf"].to_numpy() - m).max() < 1                         # tổng NF các mã = NF HOSE
    g = db.query_df("SELECT trade_date, SUM(net_flow) nf FROM indicator_group_daily WHERE group_type='sector' GROUP BY 1", path=path)
    assert abs(g["nf"].to_numpy() - d.set_index("trade_date")["NF_total"].reindex(g["trade_date"]).to_numpy()).max() < 1
    st = db.query_df("SELECT session_type FROM indicator_daily", path=path)
    assert st["session_type"].isin(["broad_up", "narrow_up", "narrow_down", "broad_down", "flat"]).all()


def test_reproducible_hash(demo_db):
    path, res = demo_db
    from src.analytics import pipeline
    from src.data import build_facts, rebuild_all
    build_facts.build_all(path)
    pipeline.compute(path)
    rebuild_all.run_analytics(path, robustness=False)
    assert rebuild_all.results_hash(path) == res["hash"]


def test_three_channels_consistent(demo_db):
    path, _ = demo_db
    from src.bot import messages as M
    from src.reports import context
    ctx = context.build(path=path)
    k = context.key_numbers(ctx)
    txt = M.market(ctx)
    for key in ("VN-Index", "ΔVN-Index", "Trung vị", "D", "CR5", "AD"):
        assert k[key] in txt, key
    from src.data import database as db
    x = db.query_df("SELECT * FROM indicator_daily ORDER BY trade_date DESC LIMIT 1", path=path).iloc[0]
    assert k["D"] == fmt.num(x["D"], 2, True) and k["NF HOSE"] == fmt.bn(x["NF_total"])   # cùng nguồn giao diện


def test_pdf_reports(demo_db, tmp_path, monkeypatch):
    path, _ = demo_db
    from src.common import config
    monkeypatch.setitem(config.load_settings()["paths"], "reports_dir", str(tmp_path))
    from src.reports import closing, snapshot
    p = snapshot.build(db_path=path)
    assert p is not None and p.exists() and p.stat().st_size > 10_000
    p2, reason = closing.build(db_path=path)
    assert p2 is not None and reason == "ok"


def test_closing_blocked_without_quality(demo_db):
    from src.reports.closing import quality_gate
    ok, reason = quality_gate("2020-01-01", demo_db[0])
    assert not ok and "chất lượng" in reason


def test_bot_messages_have_disclaimer(demo_db):
    path, _ = demo_db
    from src.bot.telegram_api import with_disclaimer
    from src.common.config import get
    assert get("app.bot_disclaimer") in with_disclaimer("x")
    assert with_disclaimer(with_disclaimer("x")).count(get("app.bot_disclaimer")) == 1


@pytest.mark.parametrize("v,d,sign,exp", [(1740.73, 2, False, "1.740,73"), (7.71, 2, True, "+7,71"), (-0.5, 1, False, "-0,5"),
                                          (None, 2, False, "—")])
def test_vn_number_format(v, d, sign, exp):
    assert fmt.num(v, d, sign) == exp
