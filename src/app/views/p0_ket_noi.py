"""
Trang "Kết nối dữ liệu": kiểm tra trực tiếp SSI REST, NEO REST, NEO WebSocket; IP cần đăng ký; số bản ghi tầng raw;
nút chạy nền các tác vụ tải dữ liệu thật (backfill SSI, bộ ghi NEO, ảnh chụp cuối phiên NEO, dựng lại chỉ báo).
Ứng dụng KHÔNG dùng dữ liệu giả lập: khi kho trống, đây là trang mặc định để người dùng biết cần làm gì.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from src.app import data_access as da
from src.app.components.ui import esc, header, md, pal, section, table_html
from src.common.config import ROOT, abs_path, get

JOBS = {
    "backfill": ("Tải lịch sử SSI (01/04/2025 → hôm qua)", ["-m", "src.data.backfill"]),
    "rebuild": ("Dựng lại toàn bộ chỉ báo từ raw", ["-m", "src.data.rebuild_all"]),
    "neo_rec": ("Ghi luồng NEO WebSocket (8:55–15:05)", ["-m", "src.data.recorder_neo"]),
    "neo_eod": ("Dựng ảnh chụp cuối phiên từ NEO", ["-m", "src.data.neo_eod"]),
}


def _start(job: str) -> None:
    log_dir = abs_path("logs")
    log_dir.mkdir(exist_ok=True)
    out = open(log_dir / f"job_{job}.log", "w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.Popen([sys.executable, *JOBS[job][1]], cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT,
                         creationflags=flags)
    st.session_state.setdefault("_jobs", {})[job] = p


def _job_state(job: str) -> str:
    p = st.session_state.get("_jobs", {}).get(job)
    if p is None:
        return "chưa chạy"
    rc = p.poll()
    return "đang chạy…" if rc is None else ("xong" if rc == 0 else f"lỗi (mã {rc})")


def _tail(path: Path, n: int = 14) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    return "\n".join(lines)


def _badge(ok: bool) -> str:
    p = pal()
    c, t = (p["up"], "KẾT NỐI ĐƯỢC") if ok else (p["down"], "CHƯA KẾT NỐI")
    return f'<span class="ffr-chip" style="background:{c};color:#fff">{t}</span>'


def render() -> None:
    p = pal()
    header("Kết nối dữ liệu", "Kiểm tra trực tiếp SSI FastConnect Data và VPBankS NEO API · tải và dựng dữ liệu thật",
           pills=["Không dùng dữ liệu giả lập"])
    if not da.ready():
        md(f'<div class="ffr-insight"><b>Kho chỉ báo đang trống.</b> FTSE Flow Radar chỉ hiển thị số liệu tải từ API '
           f'(SSI là nguồn chính, NEO là luồng song song). Hãy làm theo 3 bước bên dưới; các trang phân tích sẽ tự mở '
           f'khi bảng <code>indicator_daily</code> có dữ liệu.</div>')

    from src.data import diagnostics as dg
    if "diag" not in st.session_state or st.button("↻ Kiểm tra lại kết nối", key="diag_btn"):
        with st.spinner("Đang gọi thử SSI, NEO REST và NEO WebSocket…"):
            st.session_state["diag"] = dg.run_all()
            st.session_state["diag_ip"] = dg.public_ip()
    diag, ip = st.session_state["diag"], st.session_state.get("diag_ip", "—")

    section("Bước 1 · Đăng ký IP và khóa", "SSI và NEO đều kiểm soát địa chỉ IP gọi API")
    md(f'<div class="ffr-card"><div class="ffr-lbl">IP công khai của máy đang chạy ứng dụng</div>'
       f'<div class="ffr-val" style="color:{p["accent"]}">{esc(ip)}</div>'
       f'<div style="font-size:13px;color:{p["muted"]};margin-top:6px">Đăng ký IP này tại <b>iBoard › Dịch vụ API</b> '
       f'(SSI FastConnect Data) và tại cổng <b>NEO API</b> của VPBankS. Khóa đọc từ tệp <code>.env</code> '
       f'(không bao giờ hiển thị hay ghi log).</div></div>')

    section("Bước 2 · Kết quả gọi thử", "gọi thật tới máy chủ, không dùng bộ nhớ đệm")
    cols = st.columns(3)
    for col, (name, r) in zip(cols, diag.items()):
        with col:
            hint = f'<div style="font-size:12px;color:{p["muted"]};margin-top:8px">→ {esc(r["hint"])}</div>' if r["hint"] else ""
            md(f'<div class="ffr-card"><div style="display:flex;justify-content:space-between;align-items:center">'
               f'<b style="font-size:15px">{esc(name)}</b>{_badge(r["ok"])}</div>'
               f'<div style="font-size:13px;margin-top:8px">{esc(r["detail"])}</div>{hint}</div>')

    section("Bước 3 · Tải và dựng dữ liệu", "tác vụ chạy nền – có thể chuyển trang trong lúc chờ")
    c = st.columns(4)
    for col, (job, (label, _)) in zip(c, JOBS.items()):
        with col:
            md(f'<div class="ffr-kpi"><small>{esc(label)}</small><b style="font-size:15px">{_job_state(job)}</b></div>')
            if st.button("Chạy", key=f"run_{job}", width="stretch", disabled=_job_state(job) == "đang chạy…"):
                _start(job)
                st.rerun()
    md(f'<div style="font-size:12.5px;color:{p["muted"]};margin-top:8px">Thứ tự: <b>Tải lịch sử SSI</b> (≈ 30 phút, '
       f'giãn cách {get("ssi.min_interval_sec")} giây/lần gọi, tự tiếp tục từ điểm dừng) → <b>Dựng lại chỉ báo</b>. '
       f'Bộ ghi NEO nên chạy mỗi phiên kể cả khi SSI ổn định; nếu SSI không truy cập được, sau 15:05 bấm '
       f'<b>Dựng ảnh chụp cuối phiên từ NEO</b> rồi <b>Dựng lại chỉ báo</b>. Dòng lệnh tương ứng: '
       f'<code>python -m src.data.backfill</code>, <code>python -m src.data.rebuild_all</code>, '
       f'<code>python -m src.data.recorder_neo</code>.</div>')
    running = [j for j in JOBS if _job_state(j) == "đang chạy…"]
    for j in st.session_state.get("_jobs", {}):
        txt = _tail(abs_path("logs") / f"job_{j}.log")
        if txt:
            with st.expander(f"Nhật ký: {JOBS[j][0]} – {_job_state(j)}", expanded=j in running):
                st.code(txt, language="text")
    if running and st.button("↻ Cập nhật trạng thái tác vụ"):
        da.clear_cache()
        st.rerun()

    section("Tầng raw trong kho DuckDB", "số bản ghi theo nguồn")
    rc = da.raw_counts()
    rows = [[t, ", ".join(f"{s}: {n:,}" for s, n in d.items()) or "trống"] for t, d in rc.items()]
    md(table_html(["Bảng", "Bản ghi theo nguồn"], rows, left=(0, 1)))
    ing = da.table("ingest_log")
    if not ing.empty:
        section("Nhật ký gọi API gần nhất", "ingest_log")
        ing = ing.sort_values(ing.columns[0]).tail(12)
        st.dataframe(ing, hide_index=True, width="stretch")
