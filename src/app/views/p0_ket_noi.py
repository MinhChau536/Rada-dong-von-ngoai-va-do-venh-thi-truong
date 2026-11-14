"""
Trang "Kết nối dữ liệu": kiểm tra trực tiếp SSI FastConnect V3 (REST + WebSocket); số bản ghi tầng raw;
nút chạy nền các tác vụ tải dữ liệu thật (tải lịch sử SSI, ghi luồng WebSocket SSI, dựng lại chỉ báo).
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
from src.common.config import ROOT, abs_path, get, ssi_base_url, ssi_stream_url

JOBS = {
    "update": ("Cập nhật dữ liệu mới (tải bù phiên thiếu + dựng lại chỉ báo, kiểm định, triển vọng)", ["-m", "src.data.updater"]),
    "backfill": (f"Tải dữ liệu SSI ({pd.Timestamp(get('history.start_date')):%d/%m/%Y} → phiên gần nhất)", ["-m", "src.data.backfill"]),
    "rebuild": ("Dựng lại toàn bộ chỉ báo từ raw", ["-m", "src.data.rebuild_all"]),
    "ssi_rec": ("Ghi luồng WebSocket SSI (8:55–15:05)", ["-m", "src.data.recorder_ssi"]),
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
    header("Kết nối dữ liệu", "Kiểm tra trực tiếp SSI FastConnect V3 (REST + WebSocket) · tải và dựng dữ liệu thật",
           pills=["Nguồn duy nhất: SSI FastConnect V3", "Không dùng dữ liệu giả lập"])
    if not da.ready():
        md(f'<div class="ffr-insight"><b>Kho chỉ báo đang trống.</b> FTSE Flow Radar chỉ hiển thị số liệu thật tải từ '
           f'SSI FastConnect V3. Hãy làm theo 3 bước bên dưới; các trang phân tích sẽ tự mở khi bảng '
           f'<code>indicator_daily</code> có dữ liệu.</div>')

    from src.data import diagnostics as dg
    if "diag" not in st.session_state or st.button("↻ Kiểm tra lại kết nối", key="diag_btn"):
        with st.spinner("Đang gọi thử SSI REST và WebSocket…"):
            st.session_state["diag"] = dg.run_all()
            st.session_state["diag_ip"] = dg.public_ip()
    diag, ip = st.session_state["diag"], st.session_state.get("diag_ip", "—")

    section("Bước 1 · Khóa API", "SSI FastConnect V3 – API Key + API Secret tạo tại Developer Portal")
    md(f'<div class="ffr-card"><div class="ffr-lbl">Máy chủ</div>'
       f'<div style="font-size:14px;margin-top:4px"><code>{esc(ssi_base_url())}</code> · <code>{esc(ssi_stream_url())}</code></div>'
       f'<div style="font-size:13px;color:{p["muted"]};margin-top:6px">Tạo khóa tại <b>developers.ssi.com.vn › Quản lý API Key</b>, '
       f'nhóm quyền <b>Market Data / stream DATA</b>, rồi điền <code>SSI_API_KEY</code>, <code>SSI_API_SECRET</code> vào tệp '
       f'<code>.env</code>. Không cần Private Key hay OTP (hệ thống chỉ đọc dữ liệu, không đặt lệnh). Khóa không bao giờ '
       f'hiển thị hay ghi log. IP công khai của máy: <b>{esc(ip)}</b>.</div></div>')

    section("Bước 2 · Kết quả gọi thử", "gọi thật tới máy chủ, không dùng bộ nhớ đệm")
    cols = st.columns(max(1, len(diag)))
    for col, (name, r) in zip(cols, diag.items()):
        with col:
            hint = f'<div style="font-size:12px;color:{p["muted"]};margin-top:8px">→ {esc(r["hint"])}</div>' if r["hint"] else ""
            md(f'<div class="ffr-card"><div style="display:flex;justify-content:space-between;align-items:center">'
               f'<b style="font-size:15px">{esc(name)}</b>{_badge(r["ok"])}</div>'
               f'<div style="font-size:13px;margin-top:8px">{esc(r["detail"])}</div>{hint}</div>')

    section("Bước 3 · Tải và dựng dữ liệu", "tác vụ chạy nền – có thể chuyển trang trong lúc chờ")
    try:
        from src.data import updater
        cov, last = updater.coverage(), updater.last_status()
        behind = updater.is_behind()
        state = (f'<b style="color:{p["down"]}">CHẬM – thiếu phiên {esc(cov["expected_last_session"])}</b>' if behind
                 else f'<b style="color:{p["up"]}">ĐÃ CẬP NHẬT</b>')
        md(f'<div class="ffr-card" style="margin-bottom:8px">{state} · raw cổ phiếu tới <b>{esc(cov["raw_stock"])}</b> · '
           f'chỉ báo tới <b>{esc(cov["indicators"])}</b> · phiên đã đóng gần nhất <b>{esc(cov["expected_last_session"])}</b>'
           + (f' · lần cập nhật gần nhất {esc(last.get("started"))} ({esc(last.get("status"))})' if last else "")
           + '</div>')
    except Exception:  # noqa: BLE001 – kho chưa khởi tạo
        pass
    c = st.columns(len(JOBS))
    for col, (job, (label, _)) in zip(c, JOBS.items()):
        with col:
            md(f'<div class="ffr-kpi"><small>{esc(label)}</small><b style="font-size:15px">{_job_state(job)}</b></div>')
            if st.button("Chạy", key=f"run_{job}", width="stretch", disabled=_job_state(job) == "đang chạy…"):
                _start(job)
                st.rerun()
    md(f'<div style="font-size:12.5px;color:{p["muted"]};margin-top:8px">Thứ tự: <b>Tải dữ liệu SSI</b> (≈ 10–20 phút lần '
       f'đầu: ~400 cổ phiếu HOSE × ~400 phiên, giá + khối ngoại + room; tự tiếp tục từ điểm dừng) → <b>Dựng lại chỉ báo</b>. '
       f'Trong giờ giao dịch bật <b>Ghi luồng WebSocket SSI</b> để lưu chỉ số, lệnh khớp và room ngoại theo thời gian thực. '
       f'Hằng ngày chỉ cần <b>Cập nhật dữ liệu mới</b> (tự tải bù mọi phiên còn thiếu). '
       f'Dòng lệnh tương ứng: <code>python -m src.data.updater</code>, <code>python -m src.data.backfill</code>, '
       f'<code>python -m src.data.rebuild_all</code>, <code>python -m src.data.recorder_ssi</code>; tự động hằng ngày: '
       f'<code>python -m src.data.scheduler</code> (đăng ký chạy nền: <code>tools/install_windows_task.ps1</code>).</div>')
    running = [j for j in JOBS if _job_state(j) == "đang chạy…"]
    for j in st.session_state.get("_jobs", {}):
        txt = _tail(abs_path("logs") / f"job_{j}.log")
        if txt and j in JOBS:
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
