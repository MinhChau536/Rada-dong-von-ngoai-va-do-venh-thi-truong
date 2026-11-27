"""
Đẩy dữ liệu phiên mới lên GitHub để bản công khai (Streamlit Community Cloud) tự cập nhật.

    python -m tools.publish_data            # xuất data/snapshot_delta rồi commit + push đúng thư mục đó
    python -m tools.publish_data --no-push  # chỉ xuất, không đụng git

Chạy tự động sau khi tải xong số liệu cuối ngày (src/data/recorder_ssi.py, run.py) khi `publish.auto_push: true`
trong config/settings.yaml. Chỉ commit thư mục data/snapshot_delta (pathspec), KHÔNG BAO GIỜ đụng tới .env, báo cáo
hay tệp nào khác đang sửa dở. Vì SSI FastConnect yêu cầu đăng ký IP, máy chủ đám mây không tự gọi SSI được – dữ liệu
luôn do máy đã đăng ký IP tải về rồi đẩy lên.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DELTA_REL = "data/snapshot_delta"


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    # tắt gc/maintenance tự động cho lệnh của bộ đẩy: repack ~300 MB làm commit treo hàng phút giữa phiên
    return subprocess.run(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300, check=check)


def publish(push: bool = True) -> dict:
    sys.path.insert(0, str(ROOT))
    from src.common.logging import get_logger
    from tools import snapshot
    log = get_logger("ffr.publish")
    man = snapshot.export_delta()
    last = str(man.get("last_session", ""))[:10]
    if not push:
        return {"state": "exported", "last_session": last}
    try:
        if _git("rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
            return {"state": "no-git", "last_session": last}
        import shutil
        shutil.rmtree(ROOT / LIVE_REL, ignore_errors=True)        # số chính thức đã có → bỏ số liệu tạm tính
        state = _commit_push([DELTA_REL, LIVE_REL], f"Dữ liệu SSI tới phiên {last}", log)
        if state == "pushed":
            log.info("Đã đẩy dữ liệu tới phiên %s lên GitHub – bản công khai tự cập nhật sau 1–3 phút", last)
        return {"state": state, "last_session": last}
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Không đẩy được dữ liệu lên GitHub: %s", exc)
        return {"state": "error", "last_session": last}


LIVE_REL = "data/live_snapshot"
_LAST_LIVE = {"t": 0.0}


def _unpushed_foreign_commits() -> int:
    """Số commit chưa đẩy KHÔNG phải do bộ đẩy dữ liệu tạo – có thì không tự push (tránh đẩy hộ code đang làm dở)."""
    r = _git("log", "@{u}..HEAD", "--format=%s", check=False)
    if r.returncode != 0:
        return 0
    return sum(1 for s in r.stdout.splitlines() if s.strip() and not s.startswith(("Dữ liệu SSI", "Số liệu trong phiên")))


def _commit_push(paths, message: str, log) -> str:
    # chỉ giữ đường dẫn còn trên đĩa hoặc git đang theo dõi: `git add` một thư mục đã xóa mà chưa từng commit
    # (data/live_snapshot sau khi có số chính thức) báo lỗi 128 → trước đây làm hỏng mọi lần đẩy từ 26/11/2026
    paths = [p for p in paths if (ROOT / p).exists() or _git("ls-files", "--error-unmatch", "--", p, check=False).returncode == 0]
    if not paths:
        return "unchanged"
    _git("add", "-A", "--", *paths)
    if _git("diff", "--cached", "--quiet", "--", *paths, check=False).returncode == 0:
        return "unchanged"
    if _unpushed_foreign_commits():
        log.warning("Có commit code chưa đẩy – không tự push dữ liệu để khỏi đẩy hộ; chạy git push thủ công")
        _git("reset", "-q", "--", *paths, check=False)
        return "skipped-unpushed"
    _git("commit", "-m", message, "--", *paths)
    r = _git("push", "origin", "HEAD", check=False)
    if r.returncode != 0:
        log.warning("Đẩy dữ liệu lên GitHub lỗi: %s", (r.stderr or r.stdout).strip()[:300])
        return "push-failed"
    return "pushed"


def publish_live(min_interval: float = None) -> dict:
    """Trong phiên: đẩy số liệu tạm tính của hôm nay (data/live_snapshot, vài trăm KB) để bản công khai cập nhật theo phút."""
    import time as _t
    sys.path.insert(0, str(ROOT))
    from src.common.config import get
    from src.common.logging import get_logger
    from src.common.timeutil import now_vn
    from tools import snapshot
    log = get_logger("ffr.publish")
    if not get("publish.live_push", False):
        return {"state": "disabled"}
    gap = float(get("publish.live_push_sec", 120) if min_interval is None else min_interval)
    if _t.monotonic() - _LAST_LIVE["t"] < gap:
        return {"state": "wait"}
    _LAST_LIVE["t"] = _t.monotonic()
    man = snapshot.export_live()
    if not man:
        return {"state": "no-live"}
    try:
        state = _commit_push([LIVE_REL], f"Số liệu trong phiên {man['session_date']} {now_vn():%H:%M}", log)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Không đẩy được số liệu trong phiên: %s", exc)
        state = "error"
    return {"state": state, "session": man["session_date"]}


def auto_publish() -> dict:
    """Gọi sau mỗi lần cập nhật cuối ngày – tôn trọng cấu hình publish.auto_push."""
    sys.path.insert(0, str(ROOT))
    from src.common.config import get
    if not get("publish.auto_push", False):
        return {"state": "disabled"}
    return publish(push=True)


if __name__ == "__main__":
    print(publish(push="--no-push" not in sys.argv))
