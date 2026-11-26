"""
Khởi động FTSE Flow Radar bằng MỘT lệnh:  python run.py        (thêm --no-bot để không chạy bot Telegram)

1. Cập nhật dữ liệu TRƯỚC khi mở web (đường link chỉ hiện khi số liệu đã mới):
   • trong giờ giao dịch (09:00–15:00, thứ 2–6): bật bộ ghi luồng WebSocket SSI và chờ phiên tạm tính đầu tiên;
   • ngoài giờ: nếu kho thiếu phiên đã đóng cửa gần nhất thì tải từ SSI REST và tính lại chỉ báo (lần đầu có thể vài phút).
2. Chạy bot Telegram ở tiến trình nền (nếu .env có TELEGRAM_BOT_TOKEN).
3. Mở web Streamlit – in đường link http://localhost:8501.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
for _s in (sys.stdout, sys.stderr):          # console Windows mặc định (cp1252) không in được tiếng Việt
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")   # tiến trình con (bot, streamlit) cũng in UTF-8
sys.path.insert(0, str(ROOT))


def say(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def refresh_data(wait_live_sec: int = 60) -> None:
    from src.common.config import ssi_configured
    from src.common.timeutil import in_session
    from src.data import autoupdate, updater
    if not ssi_configured():
        say("Chưa có SSI_API_KEY / SSI_API_SECRET trong .env – mở web ở chế độ kết nối dữ liệu.")
        return
    if in_session():
        from src.data import live
        autoupdate.start_recorder_if_session()           # vẫn bật bộ ghi: SSI phát dữ liệu lúc nào thì dựng lúc đó
        if live.meta():
            say("Đã có số liệu trong phiên – mở web.")
            return
        if not live.ssi_has_today():
            say("SSI FastConnect CHƯA phát dữ liệu phiên hôm nay (masterdata, nến 1 phút đều trống) – có thể là ngày "
                "nghỉ hoặc SSI đang gián đoạn. Mở web ngay với phiên gần nhất; bộ ghi chạy nền, có số liệu thì web tự làm mới.")
            return
        say(f"Đang trong giờ giao dịch – bộ ghi luồng WebSocket SSI đang dựng phiên tạm tính (tối đa {wait_live_sec} giây)…")
        t0 = time.time()
        while time.time() - t0 < wait_live_sec:
            m = live.meta()
            if m:
                say(f"Đã có số liệu trong phiên tới {str(m.get('last_tick'))[-8:]} ({int(m['n_traded'])} mã có khớp lệnh).")
                return
            time.sleep(3)
        say("Chưa dựng xong phiên tạm tính – web vẫn mở và tự làm mới khi có số liệu.")
        return
    if autoupdate.recorder_alive():
        say("Bộ ghi luồng đang chốt phiên / tải số liệu cuối ngày – web sẽ tự cập nhật khi xong.")
        return
    if not updater.is_behind():
        say(f"Dữ liệu đã mới (tới phiên {updater.coverage()['indicators']}).")
        return
    say("Kho thiếu phiên đã đóng cửa – đang tải từ SSI REST và tính lại chỉ báo…")
    try:
        r = updater.update()
        say(f"Cập nhật {r.get('status')}: dữ liệu tới {r['after']['indicators']} ({r.get('seconds')} giây).")
        from tools.publish_data import auto_publish
        pub = auto_publish()
        if pub.get("state") == "pushed":
            say(f"Đã đẩy dữ liệu tới phiên {pub['last_session']} lên GitHub – bản công khai tự cập nhật sau 1–3 phút.")
    except updater.Busy:
        say("Một tiến trình khác đang cập nhật – web sẽ tự cập nhật khi xong.")
    except Exception as exc:  # noqa: BLE001
        say(f"Cập nhật lỗi ({exc}) – mở web với dữ liệu hiện có; xem logs/app.log.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-bot", action="store_true", help="không chạy bot Telegram")
    ap.add_argument("--port", default="8501")
    a = ap.parse_args()
    refresh_data()
    from src.common.config import env
    bot = None
    if not a.no_bot and env("TELEGRAM_BOT_TOKEN"):
        say("Chạy bot Telegram ở nền (python -m src.bot.bot).")
        bot = subprocess.Popen([sys.executable, "-m", "src.bot.bot"], cwd=str(ROOT))
    elif not a.no_bot:
        say("Không có TELEGRAM_BOT_TOKEN trong .env – bỏ qua bot.")
    say(f"Mở web: http://localhost:{a.port}  (Ctrl+C để dừng)")
    try:
        subprocess.run([sys.executable, "-m", "streamlit", "run", "src/app/main.py", "--server.port", a.port], cwd=str(ROOT))
    finally:
        if bot and bot.poll() is None:
            bot.terminate()


if __name__ == "__main__":
    main()
