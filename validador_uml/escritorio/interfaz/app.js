/* ------------------------------------------------------------
   Interfaz del validador: tipos de diagrama, archivos, editor y
   resultado. Python responde a través de window.pywebview.api.
   ------------------------------------------------------------ */
(() => {
  "use strict";

  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));
  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ESC[c]);
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const LH = 22;

  const el = {
    file: $("#archivo"),
    open: $("#abrir"),
    save: $("#guardar"),
    saveAs: $("#guardar-como"),
    kinds: $("#tipos"),
    summary: $("#resumen-tipo"),
    notation: $("#notacion"),
    editor: $("#editor"),
    paint: $("#paint"),
    gutter: $("#gutter"),
    verdictSub: $("#veredicto-sub"),
    phases: $("#fases"),
    diags: $("#diagnosticos")
  };

  const S = {
    kinds: {},
    order: [],
    kind: null,
    drafts: {},      // texto actual de cada tipo
    files: {},       // archivo asociado a cada tipo: {ruta, nombre}
    saved: {},       // contenido en disco de ese archivo
    result: null,
    resultText: null,
    version: 0,
    timer: 0,
    draftTimer: 0,
    notice: ""
  };

  const py = () => window.pywebview && window.pywebview.api;
  const verdict = (text, tone) => window.Veredicto && window.Veredicto.set(text, tone);

  /* ------------------------------------------------------------
     Arranque
     ------------------------------------------------------------ */

  function bridgeReady() {
    return new Promise((resolve, reject) => {
      if (py() && py().catalogo) return resolve();
      window.addEventListener("pywebviewready", () => resolve(), { once: true });
      setTimeout(() => reject(new Error("sin puente")), 10000);
    });
  }

  async function init() {
    el.editor.disabled = true;
    verdict("…", "neutral");
    el.verdictSub.textContent = "Preparando el analizador.";
    try {
      await bridgeReady();
    } catch (e) {
      verdict("Sin motor", "neutral");
      el.verdictSub.textContent = "Esta interfaz se abre desde la aplicación: «python -m validador_uml» o ValidadorUML.exe.";
      return;
    }
    const [catalog, state] = await Promise.all([py().catalogo(), py().estado()]);
    for (const k of catalog.kinds) {
      S.kinds[k.id] = k;
      S.order.push(k.id);
    }
    S.drafts = state.borradores || {};
    for (const [kind, f] of Object.entries(state.archivos || {})) adoptFile(kind, f);
    let kind = S.kinds[state.tipo] ? state.tipo : S.order[0];
    if (state.abrir) {
      if (state.abrir.error) notify(state.abrir.error);
      else { adoptFile(state.abrir.tipo, state.abrir); S.drafts[state.abrir.tipo] = state.abrir.texto; kind = state.abrir.tipo; }
    }
    renderKinds();
    el.editor.disabled = false;
    selectKind(kind);
  }

  /* ------------------------------------------------------------
     Archivos
     ------------------------------------------------------------ */

  function adoptFile(kind, f) {
    S.files[kind] = { ruta: f.ruta, nombre: f.nombre };
    if (typeof f.texto === "string") S.saved[kind] = f.texto;
  }

  function notify(message) {
    S.notice = message;
    renderFile();
    setTimeout(() => { if (S.notice === message) { S.notice = ""; renderFile(); } }, 6000);
  }

  function renderFile() {
    const f = S.files[S.kind];
    const modified = f && el.editor.value !== S.saved[S.kind];
    if (S.notice) {
      el.file.textContent = S.notice;
      el.file.dataset.state = "error";
    } else {
      el.file.dataset.state = "";
      el.file.innerHTML = f
        ? `<strong>${esc(f.nombre)}</strong>${modified ? ' <span class="unsaved">con cambios sin guardar</span>' : ""}`
        : "Sin archivo";
      el.file.title = f ? f.ruta : "";
    }
    if (py()) py().titulo(f ? `${f.nombre}${modified ? " •" : ""} — Validador UML` : "Validador UML");
    window.dispatchEvent(new Event("filechange"));
  }

  async function openFile() {
    const r = await py().abrir();
    if (!r) return;
    if (r.error) return notify(r.error);
    adoptFile(r.tipo, r);
    S.drafts[r.tipo] = r.texto;
    if (r.tipo === S.kind) setText(r.texto, false);
    else selectKind(r.tipo);
  }

  async function saveFile(asNew) {
    const text = el.editor.value;
    const kind = S.kind;
    const r = asNew ? await py().guardar_como(kind, text) : await py().guardar(kind, text);
    if (!r) return;
    if (r.error) return notify(r.error);
    S.files[kind] = { ruta: r.ruta, nombre: r.nombre };
    S.saved[kind] = text;
    renderFile();
  }

  el.open.addEventListener("click", openFile);
  el.save.addEventListener("click", () => saveFile(false));
  el.saveAs.addEventListener("click", () => saveFile(true));

  document.addEventListener("keydown", (e) => {
    if (!(e.ctrlKey || e.metaKey) || !py()) return;
    const k = e.key.toLowerCase();
    if (k === "o") { e.preventDefault(); openFile(); }
    else if (k === "s") { e.preventDefault(); saveFile(e.shiftKey); }
  });

  /* Los enlaces externos se abren en el navegador del sistema, no en la ventana */
  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="http"]');
    if (!a) return;
    e.preventDefault();
    if (py()) py().abrir_enlace(a.href);
  });

  /* ------------------------------------------------------------
     Tipos de diagrama
     ------------------------------------------------------------ */

  function markTabs(selected) {
    for (const t of $$('[role="tab"]', el.kinds)) {
      const on = t === selected;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
    }
  }

  function renderKinds() {
    el.kinds.innerHTML = S.order.map((id) =>
      `<button type="button" class="choice" role="tab" data-kind="${id}" aria-selected="false" tabindex="-1">${esc(S.kinds[id].name)}</button>`
    ).join("");
    el.kinds.addEventListener("click", (e) => {
      const b = e.target.closest("[data-kind]");
      if (b && b.dataset.kind !== S.kind) selectKind(b.dataset.kind);
    });
    el.kinds.addEventListener("keydown", (e) => {
      const tabs = $$('[role="tab"]', el.kinds);
      const i = tabs.indexOf(document.activeElement);
      if (i < 0) return;
      const keys = { ArrowRight: (i + 1) % tabs.length, ArrowLeft: (i - 1 + tabs.length) % tabs.length, Home: 0, End: tabs.length - 1 };
      if (!(e.key in keys)) return;
      e.preventDefault();
      const next = tabs[keys[e.key]];
      next.focus();
      selectKind(next.dataset.kind);
    });
  }

  function selectKind(id) {
    S.kind = id;
    const k = S.kinds[id];
    markTabs($(`[data-kind="${id}"]`, el.kinds));
    el.summary.textContent = k.summary;
    el.notation.textContent = k.notation === "propia" ? "en notación propia" : `en notación ${k.notation}`;
    S.result = null;
    S.resultText = null;
    const text = typeof S.drafts[id] === "string" ? S.drafts[id]
      : typeof S.saved[id] === "string" ? S.saved[id] : k.examples.correcto;
    setText(text, false);
  }

  /* ------------------------------------------------------------
     Editor
     ------------------------------------------------------------ */

  function setText(text, undoable) {
    if (undoable) {
      el.editor.focus({ preventScroll: true });
      el.editor.select();
      let ok = false;
      try { ok = document.execCommand("insertText", false, text); } catch (e) { ok = false; }
      if (ok && el.editor.value === text) return;   // el evento input hace el resto
    }
    el.editor.value = text;
    el.editor.scrollTop = 0;
    onText();
  }

  function onText() {
    const kind = S.kind;
    const text = el.editor.value;
    S.drafts[kind] = text;
    renderPaint();
    renderFile();
    clearTimeout(S.timer);
    S.timer = setTimeout(analyze, 200);
    clearTimeout(S.draftTimer);
    S.draftTimer = setTimeout(() => py().guardar_borrador(kind, text), 600);
  }

  el.editor.addEventListener("input", onText);
  el.editor.addEventListener("scroll", () => {
    el.paint.style.transform = `translate(${-el.editor.scrollLeft}px, ${-el.editor.scrollTop}px)`;
    el.gutter.style.transform = `translateY(${-el.editor.scrollTop}px)`;
  });

  for (const b of $$("[data-ejemplo]")) {
    b.addEventListener("click", () => {
      if (S.kind) setText(S.kinds[S.kind].examples[b.dataset.ejemplo], true);
    });
  }

  function jumpTo(line, col) {
    const lines = el.editor.value.split("\n");
    let idx = 0;
    for (let i = 0; i < line - 1 && i < lines.length; i++) idx += lines[i].length + 1;
    idx += Math.max(0, Math.min(col - 1, (lines[line - 1] || "").length));
    el.editor.focus({ preventScroll: true });
    el.editor.setSelectionRange(idx, idx);
    el.editor.scrollTop = Math.max(0, (line - 4) * LH);
    const box = el.editor.closest(".editor");
    const r = box.getBoundingClientRect();
    if (r.top < 0 || r.bottom > window.innerHeight) box.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  el.diags.addEventListener("click", (e) => {
    const b = e.target.closest("[data-line]");
    if (b) jumpTo(Number(b.dataset.line), Number(b.dataset.col || 1));
  });

  /* Capa detrás del texto: líneas y fragmentos con errores o avisos */
  function renderPaint() {
    const text = el.editor.value;
    const lines = text.split("\n");
    const valid = S.result && S.resultText === text;
    const lineCls = new Map();
    const byLine = new Map();
    if (valid) {
      for (const d of S.result.diagnostics) {
        const cls = d.severity === "error" ? "err" : "warn";
        if (lineCls.get(d.line) !== "err") lineCls.set(d.line, cls);
        if (!byLine.has(d.line)) byLine.set(d.line, []);
        byLine.get(d.line).push({ col: d.col, end: Math.max(d.end, d.col + 1), cls: "m-" + cls });
      }
    }
    let paint = "";
    let gutter = "";
    lines.forEach((ln, i) => {
      const n = i + 1;
      const lc = lineCls.get(n);
      const marks = byLine.get(n);
      paint += `<div class="pl${lc ? " pl-" + lc : ""}">${marks ? markLine(ln, marks) : esc(ln)}</div>`;
      gutter += `<div${lc ? ` class="g-${lc}"` : ""}>${n}</div>`;
    });
    el.paint.innerHTML = paint;
    el.gutter.innerHTML = gutter;
  }

  function markLine(line, marks) {
    let width = line.length;
    for (const m of marks) width = Math.max(width, m.end - 1);
    const text = line.padEnd(width, " ");
    const cls = new Array(text.length).fill("");
    for (const m of marks) {
      for (let c = m.col - 1; c < m.end - 1 && c < text.length; c++) {
        if (!cls[c].includes(m.cls)) cls[c] = cls[c] ? cls[c] + " " + m.cls : m.cls;
      }
    }
    let out = "";
    let i = 0;
    while (i < text.length) {
      let j = i;
      while (j < text.length && cls[j] === cls[i]) j++;
      const seg = esc(text.slice(i, j));
      out += cls[i] ? `<span class="${cls[i]}">${seg}</span>` : seg;
      i = j;
    }
    return out;
  }

  /* ------------------------------------------------------------
     Análisis y resultado
     ------------------------------------------------------------ */

  async function analyze() {
    const text = el.editor.value;
    const kind = S.kind;
    const v = ++S.version;
    let res;
    try {
      res = await py().analizar(kind, text);
    } catch (e) {
      if (v !== S.version) return;
      verdict("1 error", "error");
      el.verdictSub.textContent = `Error interno del validador: ${e.message || e}`;
      return;
    }
    if (v !== S.version || kind !== S.kind || text !== el.editor.value) return;
    S.result = res;
    S.resultText = text;
    renderResult();
    renderPaint();
  }

  function renderResult() {
    const r = S.result;
    const ph = r.phases;
    const writingBad = ph.lexico.errors + ph.sintaxis.errors > 0 || !ph.sintaxis.accepted;

    if (!r.ok) {
      verdict(plural(r.errors, "error", "errores"), "error");
      el.verdictSub.textContent = writingBad
        ? "Hay errores de escritura. Las reglas semánticas se revisan cuando la sintaxis es válida."
        : "La sintaxis es válida, pero el diagrama incumple reglas semánticas.";
    } else {
      verdict("Correcto", "ok");
      el.verdictSub.textContent = r.warnings
        ? `Sin errores. Hay ${plural(r.warnings, "aviso", "avisos")} para revisar.`
        : "El diagrama cumple la gramática y todas las reglas.";
    }

    const bad = (n) => `<span class="bad">${plural(n, "error", "errores")}</span>`;
    const lex = plural(ph.lexico.tokens, "token", "tokens") + (ph.lexico.errors ? `, ${bad(ph.lexico.errors)}` : "");
    let syn;
    if (!ph.sintaxis.errors && ph.sintaxis.accepted) {
      syn = `Aceptado en ${ph.sintaxis.steps} pasos: ${ph.sintaxis.shifts} desplazamientos y ${ph.sintaxis.reductions} reducciones.`;
    } else if (ph.sintaxis.accepted) {
      syn = `${bad(ph.sintaxis.errors)}. El análisis continuó desde cada fin de línea.`;
    } else {
      syn = `${bad(Math.max(1, ph.sintaxis.errors))}. El análisis no pudo completarse.`;
    }
    let sem;
    if (!ph.semantica.ran) {
      sem = "Pendiente: requiere léxico y sintaxis sin errores.";
    } else {
      const parts = [ph.semantica.errors ? bad(ph.semantica.errors) : "sin errores"];
      if (ph.semantica.warnings) parts.push(plural(ph.semantica.warnings, "aviso", "avisos"));
      sem = `${plural(ph.semantica.rules, "regla revisada", "reglas revisadas")}: ${parts.join(" y ")}.`;
    }
    el.phases.innerHTML =
      `<div><dt>Léxico</dt><dd>${lex}</dd></div>` +
      `<div><dt>Sintaxis</dt><dd>${syn}</dd></div>` +
      `<div><dt>Semántica</dt><dd>${sem}</dd></div>`;

    if (!r.diagnostics.length) {
      el.diags.innerHTML = `<li class="empty-note">Sin errores ni avisos.</li>`;
      return;
    }
    const PHASE = { lexico: "léxico", sintaxis: "sintaxis", semantica: "semántica" };
    el.diags.innerHTML = r.diagnostics.map((d) =>
      `<li class="diag diag-${d.severity}">` +
        `<div class="diag-head"><button type="button" class="link diag-where" data-line="${d.line}" data-col="${d.col}">Línea ${d.line}</button>` +
        `<span class="diag-code">${d.severity === "error" ? "Error" : "Aviso"} ${d.code}, ${PHASE[d.phase]}</span></div>` +
        `<p class="diag-msg">${esc(d.message)}</p>` +
      `</li>`
    ).join("");
  }

  init();
})();
