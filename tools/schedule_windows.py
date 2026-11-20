"""
Đăng ký lịch chạy tự động trên Windows (Task Scheduler) – KHÔNG cần mở web hay bot:

    python tools/schedule_windows.py            # đăng ký / cập nhật tác vụ
    python tools/schedule_windows.py --remove   # gỡ tác vụ
    python tools/schedule_windows.py --status   # xem trạng thái

Tác vụ "FTSE Flow Radar - SSI" chạy `python -m src.data.recorder_ssi`:
  • 08:50 thứ 2 – thứ 6 (và khi đăng nhập Windows, nếu máy bật muộn – StartWhenAvailable):
      09:00–15:00  ghi luồng WebSocket cả sàn HOSE, cứ 2 phút dựng phiên tạm tính cho web (trễ ≈ 2–3 phút)
      15:05        chốt phiên từ luồng (giá sau ATC, khối ngoại cả phiên) vào kho chính và tính lại toàn bộ chỉ báo
                   → kết quả đầy đủ trước 15:15
      sau đó       hỏi SSI REST 90 giây/lần, có số liệu cuối ngày chính thức thì tải và thay bản tạm tính (đến 18:30)
  • Máy bật sau 15:05: bỏ phần ghi luồng, chỉ tải số liệu cuối ngày chính thức.
  • Chỉ một bộ ghi chạy mỗi ngày (khóa data/.recorder.lock dùng chung với app và bot).
Máy tắt hoặc mất mạng trong giờ giao dịch thì không ghi được luồng của khoảng thời gian đó (WebSocket không tải bù được).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = "FTSE Flow Radar - SSI"


def _ps(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def install() -> int:
    py = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not py.exists():
        py = Path(sys.executable).with_name("pythonw.exe")
    if not py.exists():
        py = Path(sys.executable)
    cmd = f"""
$a = New-ScheduledTaskAction -Execute '{py}' -Argument '-m src.data.recorder_ssi' -WorkingDirectory '{ROOT}'
$t1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 8:50am
$t2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
      -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 11)
Register-ScheduledTask -TaskName '{TASK}' -Action $a -Trigger $t1,$t2 -Settings $s -Force `
  -Description 'FTSE Flow Radar: ghi luong SSI 9:00-15:00, chot phien 15:05, tai so lieu cuoi ngay (thu 2 - thu 6)' | Out-Null
'OK'
"""
    r = _ps(cmd)
    print(r.stdout.strip() or r.stderr.strip())
    return 0 if "OK" in r.stdout else 1


def remove() -> int:
    r = _ps(f"Unregister-ScheduledTask -TaskName '{TASK}' -Confirm:$false; 'Đã gỡ'")
    print(r.stdout.strip() or r.stderr.strip())
    return r.returncode


def status() -> int:
    r = _ps(f"Get-ScheduledTask -TaskName '{TASK}' | Get-ScheduledTaskInfo | "
            "Select-Object LastRunTime, LastTaskResult, NextRunTime | Format-List")
    print(r.stdout.strip() or r.stderr.strip())
    return r.returncode


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    sys.exit(remove() if a.remove else status() if a.status else install())
