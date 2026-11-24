/* ------------------------------------------------------------
   Veredicto en matriz de puntos.
   El texto se dibuja con Doto en un lienzo auxiliar, se detecta
   cada punto de la tipografía y se vuelve a dibujar como un círculo.
   Con errores el texto es rojo; si todo está bien, verde. En ambos
   casos cada punto sube y baja levemente de intensidad, con una
   onda lenta de izquierda a derecha y un desfase propio.
   Sin movimiento si el sistema lo pide; pausa fuera de pantalla.
   ------------------------------------------------------------ */
(() => {
  "use strict";

  const host = document.getElementById("veredicto");
  if (!host) return;
  const label = host.querySelector(".verdict-text");
  const canvas = host.querySelector("canvas");
  const ctx = canvas.getContext("2d");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const TONES = { error: "#d62828", ok: "#16924a", neutral: "#13233a" };
  const MIN_ALPHA = 0.66;          // intensidad mínima de un punto
  const LEVELS = 8;                // niveles de intensidad por cuadro
  const SPEED = 2.1;               // radianes por segundo (≈ 3 s por ciclo)

  const V = {
    text: "", tone: "neutral", dots: [], r: 2, w: 0, h: 0,
    running: false, visible: true, last: 0, start: performance.now(), pending: 0
  };

  function hash(n) {
    let h = Math.imul(n ^ 0x9e3779b9, 0x85ebca6b);
    h ^= h >>> 13;
    h = Math.imul(h, 0xc2b2ae35);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }

  /* Detecta los puntos del texto como componentes conexas */
  function sample() {
    if (!V.text.trim()) { V.dots = []; return false; }
    const cs = getComputedStyle(label);
    const weight = cs.fontWeight || "640";
    let size = parseFloat(cs.fontSize) || 56;
    const S = 3;                                   // supermuestreo
    const off = document.createElement("canvas");
    const o = off.getContext("2d", { willReadFrequently: true });
    const font = (px) => `${weight} ${px}px Doto`;

    o.font = font(size * S);
    let m = o.measureText(V.text);
    const maxW = Math.max(120, host.clientWidth - 8);
    if (m.width / S > maxW) {
      size *= maxW / (m.width / S);
      o.font = font(size * S);
      m = o.measureText(V.text);
    }
    const pad = 3 * S;
    const ascent = Math.ceil(m.actualBoundingBoxAscent || size * 0.8 * S);
    const descent = Math.ceil(m.actualBoundingBoxDescent || 0);
    const W = Math.ceil(m.width) + pad * 2;
    const H = ascent + descent + pad * 2;
    off.width = W;
    off.height = H;
    o.font = font(size * S);
    o.textBaseline = "alphabetic";
    o.fillStyle = "#000";
    o.fillText(V.text, pad, pad + ascent);

    const data = o.getImageData(0, 0, W, H).data;
    const seen = new Uint8Array(W * H);
    const dots = [];
    const stack = [];
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const i = y * W + x;
        if (seen[i] || data[i * 4 + 3] < 128) continue;
        let n = 0, sx = 0, sy = 0, x0 = x, x1 = x, y0 = y, y1 = y;
        seen[i] = 1;
        stack.push(i);
        while (stack.length) {
          const j = stack.pop();
          const jx = j % W, jy = (j - jx) / W;
          n++; sx += jx; sy += jy;
          if (jx < x0) x0 = jx; if (jx > x1) x1 = jx;
          if (jy < y0) y0 = jy; if (jy > y1) y1 = jy;
          const near = [j - 1, j + 1, j - W, j + W];
          for (let k = 0; k < 4; k++) {
            const q = near[k];
            if (q < 0 || q >= W * H || seen[q]) continue;
            if ((k === 0 && jx === 0) || (k === 1 && jx === W - 1)) continue;
            if (data[q * 4 + 3] < 128) continue;
            seen[q] = 1;
            stack.push(q);
          }
        }
        dots.push({ x: (sx / n + 0.5) / S, y: (sy / n + 0.5) / S, s: Math.max(x1 - x0 + 1, y1 - y0 + 1) / S });
      }
    }
    if (dots.length < 3) { V.dots = []; return false; }
    const sizes = dots.map((d) => d.s).sort((a, b) => a - b);
    V.r = sizes[Math.floor(sizes.length / 2)] * 0.54;
    dots.forEach((d, i) => { d.ph = hash(i + 17) * 2.6; });
    V.dots = dots;
    V.w = W / S;
    V.h = H / S;
    return true;
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(V.w * dpr);
    canvas.height = Math.round(V.h * dpr);
    canvas.style.width = `${V.w}px`;
    canvas.style.height = `${V.h}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function draw(t) {
    if (!V.dots.length) return;
    ctx.clearRect(0, 0, V.w, V.h);
    ctx.fillStyle = TONES[V.tone] || TONES.neutral;
    const animate = V.tone !== "neutral" && !reduceMotion;
    const paths = Array.from({ length: LEVELS }, () => new Path2D());
    for (const d of V.dots) {
      let k = LEVELS - 1;
      if (animate) {
        const wave = 0.5 + 0.5 * Math.sin(t * SPEED - d.x * 0.045 + d.ph);
        k = Math.round((1 - wave) * (LEVELS - 1));
      }
      paths[k].moveTo(d.x + V.r, d.y);
      paths[k].arc(d.x, d.y, V.r, 0, Math.PI * 2);
    }
    for (let k = 0; k < LEVELS; k++) {
      ctx.globalAlpha = MIN_ALPHA + (1 - MIN_ALPHA) * (k / (LEVELS - 1));
      ctx.fill(paths[k]);
    }
    ctx.globalAlpha = 1;
  }

  function frame(now) {
    if (!V.running) return;
    requestAnimationFrame(frame);
    if (now - V.last < 33) return;   // 30 cuadros por segundo
    V.last = now;
    draw((now - V.start) / 1000);
  }

  function updateLoop() {
    const want = V.dots.length && V.tone !== "neutral" && !reduceMotion && V.visible && !document.hidden;
    if (want && !V.running) {
      V.running = true;
      requestAnimationFrame(frame);
    } else if (!want) {
      V.running = false;
      draw((performance.now() - V.start) / 1000);
    }
  }

  function render() {
    const ok = sample();
    host.classList.toggle("dots", ok);
    if (!ok) { V.running = false; return; }
    resize();
    draw((performance.now() - V.start) / 1000);
    updateLoop();
  }

  function schedule() {
    cancelAnimationFrame(V.pending);
    V.pending = requestAnimationFrame(render);
  }

  window.Veredicto = {
    set(text, tone) {
      const t = tone in TONES ? tone : "neutral";
      if (text === V.text && t === V.tone) return;
      const sameText = text === V.text;
      V.text = text;
      V.tone = t;
      label.textContent = text;
      host.dataset.tone = t;
      if (sameText && V.dots.length) {
        draw((performance.now() - V.start) / 1000);
        updateLoop();
      } else {
        schedule();
      }
    }
  };

  new IntersectionObserver((entries) => {
    V.visible = entries[0].isIntersecting;
    updateLoop();
  }).observe(host);
  document.addEventListener("visibilitychange", updateLoop);

  let lastWidth = 0;
  new ResizeObserver(() => {
    if (Math.abs(host.clientWidth - lastWidth) < 1) return;
    lastWidth = host.clientWidth;
    schedule();
  }).observe(host);

  if (document.fonts) {
    document.fonts.load("640 40px Doto").then(schedule, () => {});
    document.fonts.ready.then(schedule);
  }
})();
