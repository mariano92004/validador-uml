/* ------------------------------------------------------------
   Campo de píxeles del inicio (el mismo lenguaje del portfolio)
   Ruido de valor animado, umbralado con Bayer en tres capas:
   baldosas (núcleo de cada isla), puntitos sueltos (borde) y nada.
   Es la única animación de la página: va a 30 cuadros por segundo,
   se pausa fuera de pantalla y queda quieta si se pide menos movimiento.
   ------------------------------------------------------------ */
(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

  const BAYER4 = Float32Array.from(
    [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5],
    (v) => (v + 0.5) / 16
  );
  window.BAYER4 = BAYER4;

  const hero = document.querySelector(".hero");
  const field = hero && hero.querySelector(".field");
  const fctx = field && field.getContext("2d");
  if (!hero || !fctx) return;

  function hash(x, y) {
    let h = (Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263)) | 0;
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }

  function vnoise(x, y) {
    const xi = Math.floor(x), yi = Math.floor(y);
    const xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const a = hash(xi, yi), b = hash(xi + 1, yi);
    const c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  }

  function fbm(x, y) {
    return vnoise(x, y) * 0.55 +
      vnoise(x * 2.03 + 31.7, y * 2.03 + 11.3) * 0.3 +
      vnoise(x * 4.11 + 7.1, y * 4.11 + 57.9) * 0.15;
  }

  const TILE = ["#bccde1", "#7f9cc0", "#3d5a80", "#14243b"]; // claro a oscuro
  const DOT = "#97a9bf";
  const ACCENT = ["#8db4de", "#2a5ba6"];

  const F = {
    W: 0, H: 0, cell: 9, cols: 0, rows: 0, dpr: 1,
    mask: null, accent: null,
    px: -9999, py: -9999, tx: -9999, ty: -9999, energy: 0,
    start: performance.now(), last: 0, running: false, visible: true
  };

  function measure() {
    const r = hero.getBoundingClientRect();
    F.W = r.width;
    F.H = r.height;
    F.cell = parseFloat(getComputedStyle(hero).getPropertyValue("--cell")) || 9;
    F.dpr = Math.min(window.devicePixelRatio || 1, 2);
    field.width = Math.round(F.W * F.dpr);
    field.height = Math.round(F.H * F.dpr);
    fctx.setTransform(F.dpr, 0, 0, F.dpr, 0, 0);
    F.cols = Math.ceil(F.W / F.cell);
    F.rows = Math.ceil(F.H / F.cell);

    // Zonas libres alrededor del texto, para que nada lo tape.
    const zones = [];
    const k = clamp(F.W / 1100, 0.45, 1);
    const add = (sel, pad, fallBase) => {
      const fall = fallBase * k;
      hero.querySelectorAll(sel).forEach((el) => {
        const b = el.getBoundingClientRect();
        if (!b.width) return;
        zones.push({
          x0: b.left - r.left - pad, y0: b.top - r.top - pad,
          x1: b.right - r.left + pad, y1: b.bottom - r.top + pad, fall
        });
      });
    };
    add(".name span", 10, 110);
    add(".lede", 14, 90);
    add(".hero-links li", 12, 70);
    add(".file", 8, 46);
    add(".actions", 8, 46);

    const n = F.cols * F.rows;
    F.mask = new Float32Array(n);
    F.accent = new Int8Array(n);
    const fade = Math.min(160, F.H * 0.22);
    for (let row = 0; row < F.rows; row++) {
      const y = row * F.cell + F.cell / 2;
      const bottom = clamp((F.H - y) / fade, 0, 1);
      for (let col = 0; col < F.cols; col++) {
        const x = col * F.cell + F.cell / 2;
        let m = 1;
        for (const z of zones) {
          const dx = Math.max(z.x0 - x, 0, x - z.x1);
          const dy = Math.max(z.y0 - y, 0, y - z.y1);
          const t = clamp(Math.sqrt(dx * dx + dy * dy) / z.fall, 0, 1);
          const s = t * t * (3 - 2 * t);
          if (s < m) m = s;
        }
        const i = row * F.cols + col;
        F.mask[i] = m * bottom;
        const h = hash(col + 913, row + 271);
        F.accent[i] = h > 0.9965 ? 2 : h > 0.992 ? 1 : 0;
      }
    }
  }

  function draw(t) {
    if (!F.mask) return;
    const { cols, rows, cell } = F;
    // Se "condensa" una sola vez al cargar.
    const intro = reduceMotion ? 0 : 0.5 * Math.pow(1 - clamp(t / 1.8, 0, 1), 3);
    const T_TILE = 0.7 + intro;
    const T_DOT = 0.53 + intro;

    F.px += (F.tx - F.px) * 0.18;
    F.py += (F.ty - F.py) * 0.18;
    F.energy *= 0.975;
    const R2 = 95 * 95;
    const boostMax = 0.5 * F.energy;

    const tiles = [new Path2D(), new Path2D(), new Path2D(), new Path2D()];
    const dots = new Path2D();
    const acc = [new Path2D(), new Path2D()];
    const gap = cell > 8 ? 1.5 : 1;
    const size = cell - gap * 2;
    const ds = 2;
    const ax = t * 0.035, bx = t * 0.024, by = t * 0.012;

    for (let row = 0; row < rows; row++) {
      const y = row * cell;
      const ny1 = row * 0.085 + 3.3;
      const ny2 = row * 0.07 + 20 + by;
      for (let col = 0; col < cols; col++) {
        const i = row * cols + col;
        const m = F.mask[i];
        if (m <= 0.001) continue;
        const x = col * cell;

        const f = fbm(col * 0.07 + ax, ny1) * 0.62 + fbm(col * 0.09 - bx + 50, ny2) * 0.38;
        let v = (f - 0.5) * 2.6 + 0.5;

        if (boostMax > 0.01) {
          const dx = x + cell / 2 - F.px, dy = y + cell / 2 - F.py;
          const d2 = dx * dx + dy * dy;
          if (d2 < R2 * 4) v += boostMax * Math.exp(-d2 / R2);
        }
        v *= m;

        const b = BAYER4[((row & 3) << 2) | (col & 3)];
        if (v > T_TILE) {
          const a = F.accent[i];
          if (a) {
            acc[a - 1].rect(x + gap, y + gap, size, size);
          } else {
            const lvl = (v - T_TILE) / 0.32;
            const kk = clamp(Math.floor(lvl * 4 + b - 0.5), 0, 3);
            tiles[kk].rect(x + gap, y + gap, size, size);
          }
        } else if (v > T_DOT && b < ((v - T_DOT) / (T_TILE - T_DOT)) * 0.55) {
          dots.rect(x + cell / 2 - ds / 2, y + cell / 2 - ds / 2, ds, ds);
        }
      }
    }

    fctx.clearRect(0, 0, F.W, F.H);
    fctx.fillStyle = DOT;
    fctx.fill(dots);
    for (let kk = 0; kk < 4; kk++) {
      fctx.fillStyle = TILE[kk];
      fctx.fill(tiles[kk]);
    }
    fctx.fillStyle = ACCENT[0];
    fctx.fill(acc[0]);
    fctx.fillStyle = ACCENT[1];
    fctx.fill(acc[1]);
  }

  function frame(now) {
    if (!F.running) return;
    requestAnimationFrame(frame);
    if (now - F.last < 33) return; // ~30 fps alcanza para algo tan lento
    F.last = now;
    draw((now - F.start) / 1000);
  }

  function start() {
    if (reduceMotion || F.running || !F.visible || document.hidden) return;
    F.running = true;
    requestAnimationFrame(frame);
  }

  function stop() { F.running = false; }

  function redrawStatic() {
    draw(reduceMotion ? 0 : (performance.now() - F.start) / 1000);
  }

  measure();
  redrawStatic();

  hero.addEventListener("pointermove", (e) => {
    const r = hero.getBoundingClientRect();
    F.tx = e.clientX - r.left;
    F.ty = e.clientY - r.top;
    if (F.px < -999) { F.px = F.tx; F.py = F.ty; }
    F.energy = Math.min(1, F.energy + 0.12);
    if (reduceMotion) redrawStatic();
  }, { passive: true });

  new IntersectionObserver((entries) => {
    F.visible = entries[0].isIntersecting;
    if (F.visible) start(); else stop();
  }).observe(hero);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop(); else start();
  });

  let rt;
  const remeasure = () => {
    clearTimeout(rt);
    rt = setTimeout(() => { measure(); redrawStatic(); }, 80);
  };
  new ResizeObserver(remeasure).observe(hero);
  window.addEventListener("filechange", remeasure);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(remeasure);

  start();
})();
