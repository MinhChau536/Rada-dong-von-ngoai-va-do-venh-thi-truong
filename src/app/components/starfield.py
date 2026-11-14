"""
Nền "Đêm sao tương tác" (kế thừa cách chèn hiệu ứng của web phân tích chứng khoán cũ – components/background_fx.py).

• Sao 3 lớp độ sâu, lấp lánh, dịch theo chuột (thị sai) · rê chuột: sao gần con trỏ sáng lên và nối thành chòm sao
• Sao băng ngẫu nhiên · bấm chuột: bắn sao băng + chùm tia sáng tại điểm bấm · tinh vân trôi chậm
• Chế độ Sáng: bầu trời bình minh, sao xanh; chế độ Tối: trời đêm sâu, sao trắng/xanh/vàng

Streamlit không chạy <script> trong st.markdown → dùng components.html (iframe cùng origin) chèn MỘT LẦN mã lõi vào
trang chính (window.parent); các lần chạy lại chỉ gửi cấu hình (bật/tắt, Sáng/Tối) qua sự kiện "ffrstars".
Tự giảm tốc khi tab ẩn, tôn trọng "giảm chuyển động" của hệ điều hành, canvas nằm dưới mọi nội dung (z-index âm).
"""
from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

_THEMES = {
    "dark": {"sky": "radial-gradient(ellipse at 75% -10%, #23205a 0%, #0b1024 42%, #050814 100%)",
             "star": "255,255,255", "tints": ["255,255,255", "186,214,255", "255,232,190"], "line": "160,200,255",
             "meteor": "220,235,255", "neb": ["rgba(99,102,241,.55)", "rgba(20,184,166,.40)", "rgba(168,85,247,.40)"],
             "neb_op": 0.55, "glow": "rgba(147,197,253,.16)", "base": 0.85},
    "light": {"sky": "linear-gradient(180deg, #d6e4fb 0%, #e8effc 45%, #f5f8fd 100%)",
              "star": "30,64,175", "tints": ["30,64,175", "13,148,136", "79,70,229"], "line": "37,99,235",
              "meteor": "37,99,235", "neb": ["rgba(96,165,250,.45)", "rgba(45,212,191,.35)", "rgba(196,181,253,.45)"],
              "neb_op": 0.45, "glow": "rgba(37,99,235,.10)", "base": 0.55},
}

_CORE = r"""
(function () {
  if (window.__ffrStarsLoaded) return; window.__ffrStarsLoaded = true;
  const doc = document;
  let root = null, cv = null, ctx = null, glow = null, running = false;
  let W = 0, H = 0, stars = [], meteors = [], sparks = [], t = 0, nextMeteor = 120;
  const m = { x: -9999, y: -9999, px: 0, py: 0, on: false };
  const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const R = 150;
  const C = () => window.__ffrStarCfg;

  function style(c) {
    let st = doc.getElementById("ffr-stars-style");
    if (!st) { st = doc.createElement("style"); st.id = "ffr-stars-style"; doc.head.appendChild(st); }
    st.textContent = `
      #ffr-stars { position: fixed; inset: 0; z-index: -1; pointer-events: none; overflow: hidden; background: ${c.sky}; }
      #ffr-stars canvas { position: absolute; inset: 0; }
      #ffr-stars .neb { position: absolute; width: 55vmax; height: 55vmax; border-radius: 50%; filter: blur(90px);
        opacity: ${c.neb_op}; will-change: transform; transition: background 1.2s; }
      #ffr-glow { position: absolute; left: 0; top: 0; width: 460px; height: 460px; margin: -230px 0 0 -230px; border-radius: 50%;
        background: radial-gradient(circle, ${c.glow} 0%, transparent 65%); opacity: 0; transition: opacity .4s; }
      @keyframes ffrn1 { 0%{transform:translate(0,0) scale(1)} 50%{transform:translate(12vw,8vh) scale(1.18)} 100%{transform:translate(0,0) scale(1)} }
      @keyframes ffrn2 { 0%{transform:translate(0,0) scale(1.1)} 50%{transform:translate(-14vw,-6vh) scale(.92)} 100%{transform:translate(0,0) scale(1.1)} }
      @media (prefers-reduced-motion: reduce) { #ffr-stars .neb { animation: none !important; } }`;
  }

  function build(c) {
    root = doc.createElement("div"); root.id = "ffr-stars";
    [{ top: "-22vmax", left: "-12vmax", a: "ffrn1 46s" }, { top: "18vh", right: "-26vmax", a: "ffrn2 58s" },
     { bottom: "-30vmax", left: "22vw", a: "ffrn1 64s reverse" }].forEach((s, i) => {
      const n = doc.createElement("div"); n.className = "neb";
      Object.assign(n.style, { top: s.top || "", left: s.left || "", right: s.right || "", bottom: s.bottom || "",
        background: `radial-gradient(circle, ${c.neb[i]} 0%, transparent 70%)`, animation: s.a + " ease-in-out infinite" });
      root.appendChild(n);
    });
    glow = doc.createElement("div"); glow.id = "ffr-glow"; root.appendChild(glow);
    cv = doc.createElement("canvas"); root.appendChild(cv); ctx = cv.getContext("2d");
    doc.body.prepend(root); resize();
  }

  function resize() {
    if (!cv) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = innerWidth; H = innerHeight;
    cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.round(Math.min(650, (W * H) / 2300));
    stars = Array.from({ length: n }, () => {
      const z = Math.random() ** 1.6;                       // nhiều sao xa (mờ, nhỏ), ít sao gần
      return { x: Math.random() * W, y: Math.random() * H, z, r: .35 + z * 1.55, ph: Math.random() * 6.28,
               sp: .6 + Math.random() * 2.2, tint: Math.random() < .82 ? 0 : (Math.random() < .5 ? 1 : 2), b: 0 };
    });
  }

  function meteor(x, y, fast) {
    const ang = (Math.PI / 5) + Math.random() * (Math.PI / 6) * (Math.random() < .5 ? 1 : -1);
    const dir = Math.random() < .5 ? 1 : -1, v = (fast ? 15 : 9) + Math.random() * 6;
    meteors.push({ x, y, vx: Math.cos(ang) * v * dir, vy: Math.sin(ang) * v, life: 1, len: 14 + Math.random() * 10 });
  }

  function frame() {
    if (!running) return;
    const c = C(); t += reduce ? 0 : 1 / 60;
    ctx.clearRect(0, 0, W, H);
    m.px += ((m.on ? m.x : W / 2) - m.px) * .04; m.py += ((m.on ? m.y : H / 2) - m.py) * .04;
    const ox = (m.px - W / 2) / W, oy = (m.py - H / 2) / H;
    const near = [];
    for (const s of stars) {
      const x = ((s.x - ox * 40 * s.z) % W + W) % W, y = ((s.y - oy * 28 * s.z) % H + H) % H;
      s.sx = x; s.sy = y;
      let a = c.base * (.35 + .65 * s.z) * (.6 + .4 * Math.sin(t * s.sp + s.ph));
      let r = s.r;
      if (m.on) {
        const d = Math.hypot(x - m.x, y - m.y);
        if (d < R) { const k = 1 - d / R; s.b = Math.max(s.b, k); if (s.z > .25) near.push(s); }
      }
      s.b *= .93; a = Math.min(1, a + s.b * .9); r += s.b * 1.6;
      const col = c.tints[s.tint];
      ctx.fillStyle = `rgba(${col},${a})`; ctx.beginPath(); ctx.arc(x, y, r, 0, 6.283); ctx.fill();
      if (s.z > .8 || s.b > .4) {                             // sao sáng có quầng
        ctx.fillStyle = `rgba(${col},${a * .12})`; ctx.beginPath(); ctx.arc(x, y, r * 4, 0, 6.283); ctx.fill();
      }
    }
    if (near.length > 1) {                                    // chòm sao quanh con trỏ
      near.sort((p, q) => Math.hypot(p.sx - m.x, p.sy - m.y) - Math.hypot(q.sx - m.x, q.sy - m.y));
      const g = near.slice(0, 12);
      ctx.lineWidth = 1;
      for (let i = 0; i < g.length; i++) {
        let best = null, bd = 1e9;
        for (let j = 0; j < g.length; j++) { if (i === j) continue;
          const d = Math.hypot(g[i].sx - g[j].sx, g[i].sy - g[j].sy); if (d < bd) { bd = d; best = g[j]; } }
        const k = 1 - Math.hypot(g[i].sx - m.x, g[i].sy - m.y) / R;
        if (best && bd < 120) { ctx.strokeStyle = `rgba(${c.line},${.45 * k})`;
          ctx.beginPath(); ctx.moveTo(g[i].sx, g[i].sy); ctx.lineTo(best.sx, best.sy); ctx.stroke(); }
        if (i < 4) { ctx.strokeStyle = `rgba(${c.line},${.22 * k})`; ctx.setLineDash([2, 4]);
          ctx.beginPath(); ctx.moveTo(g[i].sx, g[i].sy); ctx.lineTo(m.x, m.y); ctx.stroke(); ctx.setLineDash([]); }
      }
    }
    if (!reduce && --nextMeteor <= 0) { meteor(Math.random() * W, Math.random() * H * .35, false); nextMeteor = 200 + Math.random() * 380; }
    meteors = meteors.filter(s => s.life > 0 && s.x > -200 && s.x < W + 200 && s.y < H + 200);
    for (const s of meteors) {
      s.x += s.vx; s.y += s.vy; s.life -= .012;
      const tx = s.x - s.vx * s.len, ty = s.y - s.vy * s.len;
      const gr = ctx.createLinearGradient(s.x, s.y, tx, ty);
      gr.addColorStop(0, `rgba(${c.meteor},${.95 * s.life})`); gr.addColorStop(1, `rgba(${c.meteor},0)`);
      ctx.strokeStyle = gr; ctx.lineWidth = 2.2; ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(tx, ty); ctx.stroke();
      ctx.fillStyle = `rgba(255,255,255,${s.life})`; ctx.beginPath(); ctx.arc(s.x, s.y, 1.8, 0, 6.283); ctx.fill();
    }
    sparks = sparks.filter(p => p.a > .02);
    for (const p of sparks) {
      p.x += p.vx; p.y += p.vy; p.vx *= .95; p.vy = p.vy * .95 + .03; p.a *= .955;
      ctx.fillStyle = `rgba(${c.tints[p.tint]},${p.a})`; ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 6.283); ctx.fill();
    }
    if (doc.hidden) setTimeout(() => requestAnimationFrame(frame), 600); else requestAnimationFrame(frame);
  }

  function apply() {
    const c = C();
    if (!c.enabled) {
      running = false;
      if (root) { root.remove(); root = null; cv = null; }
      const st = doc.getElementById("ffr-stars-style"); if (st) st.remove();
      return;
    }
    style(c);
    if (!root) build(c);
    else { root.style.background = c.sky;
      root.querySelectorAll(".neb").forEach((n, i) => n.style.background = `radial-gradient(circle, ${c.neb[i]} 0%, transparent 70%)`); }
    if (!running) { running = true; requestAnimationFrame(frame); }
  }

  addEventListener("resize", resize);
  doc.addEventListener("mousemove", e => {
    m.x = e.clientX; m.y = e.clientY; m.on = true;
    if (glow) { glow.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`; glow.style.opacity = 1; }
  }, { passive: true });
  doc.addEventListener("mouseleave", () => { m.on = false; if (glow) glow.style.opacity = 0; });
  doc.addEventListener("mousedown", e => {
    if (!running) return;
    meteor(e.clientX, e.clientY, true);
    for (let i = 0; i < 22; i++) { const a = Math.random() * 6.283, v = 1 + Math.random() * 3.2;
      sparks.push({ x: e.clientX, y: e.clientY, vx: Math.cos(a) * v, vy: Math.sin(a) * v, a: .95, r: .8 + Math.random() * 1.6,
                    tint: Math.floor(Math.random() * 3) }); }
  }, { passive: true });
  addEventListener("ffrstars", apply);
  apply();
})();
"""

_LOADER = """
<script>
(function () {
  const P = window.parent;
  P.__ffrStarCfg = __CFG__;
  if (!P.__ffrStarsLoaded) {
    const s = P.document.createElement("script");
    s.textContent = __CORE__;
    P.document.head.appendChild(s);
  } else {
    P.dispatchEvent(new P.Event("ffrstars"));
  }
})();
</script>
"""


def inject(enabled: bool, dark: bool) -> None:
    """Gọi MỖI lần chạy trang (kể cả khi tắt) để bầu trời bật/tắt và đổi Sáng/Tối theo lựa chọn hiện tại."""
    cfg = dict(_THEMES["dark" if dark else "light"])
    cfg["enabled"] = bool(enabled)
    html = _LOADER.replace("__CFG__", json.dumps(cfg)).replace("__CORE__", json.dumps(_CORE))
    with st.container(key="ffr_fx"):                         # khung chứa bị ẩn bằng CSS (.st-key-ffr_fx) – script vẫn chạy
        if hasattr(st, "iframe"):
            st.iframe(html, height=1)
        else:                                                 # Streamlit cũ chưa có st.iframe
            components.html(html, height=0)
