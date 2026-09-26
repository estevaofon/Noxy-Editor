// editor.js — o cliente burro: pinta o quadro que o Noxy manda e encaminha
// teclado e mouse como eventos. Nao guarda o texto. Uma requisicao em voo
// por vez; scroll acumula, drag e poll pendentes sao substituidos.
(() => {
  "use strict";
  const token = new URLSearchParams(location.search).get("t") || "";
  // id desta carga da pagina: o bye de um reload nao pode encerrar o editor
  const PAGE_ID = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2));
  const $ = (id) => document.getElementById(id);
  const els = {
    rootName: $("root-name"), tree: $("tree"), tabs: $("tabs"), runBtn: $("run-btn"),
    editor: $("editor"), gutter: $("gutter"), text: $("text"), cursor: $("cursor"), welcome: $("welcome"),
    main: $("main"), output: $("output"), outputText: $("output-text"), outputClose: $("output-close"), outputResize: $("output-resize"), outputHead: $("output-head"),
    panelTabs: $("panel-tabs"), searchView: $("search-view"), termView: $("term-view"),
    status: $("status"), statusLeft: $("status-left"), statusMsg: $("status-msg"), statusRight: $("status-right"),
    modal: $("modal"), modalText: $("modal-text"), modalButtons: $("modal-buttons"),
    input: $("input"),
  };
  const LINE_H = 22;
  let rows = 30;
  let treeVersion = 0;
  let outputVersion = -1;
  let frame = null;
  let internalClip = "";
  let inflight = false;
  const queue = [];
  let dead = false;

  // cp conta code points: a unidade de coluna do Noxy (JS conta UTF-16).
  const cp = (s) => Array.from(s).length;
  function utf16Offset(s, codePoints) {
    let i = 0, n = 0;
    while (n < codePoints && i < s.length) { i += s.codePointAt(i) > 0xffff ? 2 : 1; n++; }
    return i;
  }
  function rowsNow() { return Math.max(1, Math.floor(els.editor.clientHeight / LINE_H)); }

  // ---- fila de requisicoes
  function send(ev) {
    if (dead) return;
    if (ev.kind === "scroll") {
      const q = queue.find((e) => e.kind === "scroll");
      if (q) { q.delta += ev.delta; pump(); return; }
    } else if (ev.kind === "drag" || ev.kind === "poll") {
      const i = queue.findIndex((e) => e.kind === ev.kind);
      if (i >= 0) { queue[i] = ev; pump(); return; }
    }
    queue.push(ev);
    pump();
  }

  async function pump() {
    if (inflight || queue.length === 0) return;
    inflight = true;
    const ev = queue.shift();
    ev.rows = rows;
    ev.tree_version = treeVersion;
    ev.page = PAGE_ID;
    try {
      const res = await fetch("/event", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Noxy-Token": token },
        body: JSON.stringify(ev),
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      render(await res.json());
    } catch (err) {
      dead = true;
      els.status.classList.add("dead");
      els.statusMsg.textContent = "conexão perdida: " + err.message;
      return;
    }
    inflight = false;
    pump();
  }

  // ---- render
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function render(f) {
    frame = f;
    document.title = f.title;
    renderTabs(f.tabs);
    if (f.tree_version !== treeVersion) { treeVersion = f.tree_version; renderTree(f.root, f.tree); }
    renderView(f);
    els.statusLeft.textContent = f.status.left;
    els.statusRight.textContent = f.status.right;
    els.statusMsg.textContent = f.status.message;
    if (f.output.version !== outputVersion) {
      outputVersion = f.output.version;
      els.outputText.textContent = f.output.text + (f.output.running ? "\n…" : "");
      els.outputText.scrollTop = els.outputText.scrollHeight;
    }
    renderPanel(f.panel);
    renderModal(f.modal);
    if (f.clipboard) {
      internalClip = f.clipboard;
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(f.clipboard).catch(() => {});
    }
    focusInput();
  }

  function renderTabs(tabs) {
    els.tabs.replaceChildren(...tabs.map((t, i) => {
      const tab = el("div", "tab" + (t.active ? " active" : ""));
      tab.title = t.path;
      tab.append(el("span", "name", t.name + (t.dirty ? " ●" : "")));
      const close = el("span", "close", "×");
      close.title = "Fechar (Ctrl+W)";
      close.addEventListener("mousedown", (e) => { e.stopPropagation(); e.preventDefault(); send({ kind: "tab_close", index: i }); });
      tab.append(close);
      tab.addEventListener("mousedown", (e) => {
        e.preventDefault();
        if (e.button === 1) send({ kind: "tab_close", index: i });
        else if (e.button === 0) send({ kind: "tab_select", index: i });
      });
      return tab;
    }));
  }

  function renderTree(root, nodes) {
    els.rootName.textContent = root;
    els.tree.replaceChildren(...nodes.map((n) => {
      const node = el("div", "node " + (n.is_dir ? "dir" : "file"));
      node.style.paddingLeft = (10 + n.depth * 14) + "px";
      node.append(el("span", "chev", n.is_dir ? (n.expanded ? "▾" : "▸") : ""));
      node.append(el("span", "name", n.name));
      node.addEventListener("mousedown", (e) => {
        e.preventDefault();
        send({ kind: n.is_dir ? "tree_toggle" : "tree_open", path: n.path });
      });
      return node;
    }));
  }

  function renderView(f) {
    if (f.tabs.length === 0) {
      els.welcome.classList.remove("hidden");
      els.cursor.classList.add("hidden");
      els.text.replaceChildren();
      els.gutter.replaceChildren();
      return;
    }
    els.welcome.classList.add("hidden");
    const v = f.view;
    const lines = [], nums = [];
    for (const line of v.lines) {
      const cur = line.n === v.cursor.line;
      const div = el("div", "line" + (cur ? " cur" : ""));
      div.dataset.n = line.n;
      for (const sp of line.spans) div.append(el("span", "k-" + sp.k + (sp.s ? " sel" : ""), sp.t));
      lines.push(div);
      nums.push(el("div", "gline" + (cur ? " cur" : ""), String(line.n + 1)));
    }
    els.text.replaceChildren(...lines, els.cursor);   // o cursor vive dentro de #text: mesmas coordenadas, mesmo scroll
    els.gutter.replaceChildren(...nums);
    placeCursor(v);
  }

  // placeCursor usa um Range no texto da linha: fica exato com tabs,
  // caracteres largos e qualquer fonte. Depois rola a vista na horizontal
  // para o cursor continuar visivel (a vertical e do Noxy).
  function placeCursor(v) {
    const lineEl = els.text.querySelector(`.line[data-n="${v.cursor.line}"]`);
    if (!lineEl) { els.cursor.classList.add("hidden"); return; }
    const lineRect = lineEl.getBoundingClientRect();
    let x = lineRect.left + 4;
    let remaining = v.cursor.col;
    const walker = document.createTreeWalker(lineEl, NodeFilter.SHOW_TEXT);
    let node, last = null;
    while ((node = walker.nextNode())) {
      const len = cp(node.data);
      if (remaining <= len) {
        const r = document.createRange();
        r.setStart(node, utf16Offset(node.data, remaining));
        r.collapse(true);
        x = r.getBoundingClientRect().left;
        remaining = -1;
        break;
      }
      remaining -= len;
      last = node;
    }
    if (remaining >= 0 && last) {
      const r = document.createRange();
      r.setStart(last, last.data.length);
      r.collapse(true);
      x = r.getBoundingClientRect().left;
    }
    const textRect = els.text.getBoundingClientRect();
    els.cursor.style.left = (x - textRect.left) + "px";
    els.cursor.style.top = (lineRect.top - textRect.top) + "px";
    els.cursor.classList.remove("hidden");
    const box = els.editor.getBoundingClientRect();
    const gutterW = els.gutter.getBoundingClientRect().width;
    const margin = 24;
    if (x < box.left + gutterW + margin) {
      els.editor.scrollLeft = Math.max(0, els.editor.scrollLeft - (box.left + gutterW + margin - x));
    } else if (x + 2 > box.right - margin) {
      els.editor.scrollLeft += (x + 2) - (box.right - margin);
    }
    els.cursor.style.animation = "none";
    void els.cursor.offsetWidth;
    els.cursor.style.animation = "";
  }

  function renderModal(m) {
    if (!m.text) { els.modal.classList.add("hidden"); return; }
    els.modalText.textContent = m.text;
    els.modalButtons.replaceChildren(...m.buttons.map((b) => {
      const btn = el("button", "", b.label);
      btn.addEventListener("click", () => send({ kind: "modal", key: b.id }));
      return btn;
    }));
    els.modal.classList.remove("hidden");
  }

  // ---- teclado: teclas de navegacao e combinacoes viram key; caracteres
  // chegam pelo textarea (input / compositionend), o que faz acentos e IME
  // funcionarem.
  const NAV = { ArrowLeft: 1, ArrowRight: 1, ArrowUp: 1, ArrowDown: 1, Home: 1, End: 1, PageUp: 1, PageDown: 1, Enter: 1, Backspace: 1, Delete: 1, Tab: 1, Escape: 1, F5: 1 };
  const CTRL = { s: 1, z: 1, y: 1, a: 1, w: 1, "/": 1, q: 1, j: 1, "`": 1, arrowleft: 1, arrowright: 1, home: 1, end: 1 };

  els.input.addEventListener("keydown", (e) => {
    if (e.isComposing) return;
    const key = e.key.toLowerCase();
    if (e.ctrlKey || e.metaKey) {
      if (key === "c") { e.preventDefault(); send({ kind: "copy" }); return; }
      if (key === "x") { e.preventDefault(); send({ kind: "cut" }); return; }
      if (key === "v") return;
      if (CTRL[key]) { e.preventDefault(); send({ kind: "key", key, ctrl: true, shift: e.shiftKey, alt: e.altKey }); }
      return;
    }
    if (NAV[e.key]) { e.preventDefault(); send({ kind: "key", key, ctrl: false, shift: e.shiftKey, alt: e.altKey }); }
  });
  function flushTyped() {
    const t = els.input.value;
    els.input.value = "";
    if (t) send({ kind: "text", text: t });
  }
  els.input.addEventListener("input", (e) => {
    if (e.isComposing || e.inputType === "insertCompositionText") return;
    flushTyped();
  });
  els.input.addEventListener("compositionend", flushTyped);
  els.input.addEventListener("paste", (e) => {
    e.preventDefault();
    let t = e.clipboardData ? e.clipboardData.getData("text") : "";
    if (!t) t = internalClip;
    if (t) send({ kind: "paste", text: t.replace(/\r\n?/g, "\n") });
  });
  function focusInput() {
    if (document.activeElement !== els.input) els.input.focus({ preventScroll: true });
  }
  document.addEventListener("mousedown", () => setTimeout(focusInput, 0));

  // ---- mouse: a linha vem do y; a coluna, de caretPositionFromPoint.
  function lineFromY(y) {
    if (!frame || frame.tabs.length === 0 || frame.view.lines.length === 0) return -1;
    const top = els.text.getBoundingClientRect().top;
    const n = frame.view.top + Math.floor((y - top) / LINE_H);
    const last = frame.view.top + frame.view.lines.length - 1;
    return Math.max(frame.view.top, Math.min(n, last));
  }
  function posFromPoint(x, y) {
    const line = lineFromY(y);
    if (line < 0) return null;
    const lineEl = els.text.querySelector(`.line[data-n="${line}"]`);
    let col = 1000000;
    let node = null, off = 0;
    if (document.caretPositionFromPoint) {
      const c = document.caretPositionFromPoint(x, y);
      if (c) { node = c.offsetNode; off = c.offset; }
    } else if (document.caretRangeFromPoint) {
      const r = document.caretRangeFromPoint(x, y);
      if (r) { node = r.startContainer; off = r.startOffset; }
    }
    if (node && node.nodeType === Node.TEXT_NODE && lineEl && lineEl.contains(node)) {
      col = 0;
      const walker = document.createTreeWalker(lineEl, NodeFilter.SHOW_TEXT);
      let t;
      while ((t = walker.nextNode())) {
        if (t === node) { col += cp(t.data.slice(0, off)); break; }
        col += cp(t.data);
      }
    }
    return { line, col };
  }
  let dragging = false, dragEvent = null, dragRaf = 0;
  els.text.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const p = posFromPoint(e.clientX, e.clientY);
    if (!p) return;
    dragging = true;
    send({ kind: "click", line: p.line, col: p.col, shift: e.shiftKey });
  });
  els.gutter.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const line = lineFromY(e.clientY);
    if (line >= 0) send({ kind: "click", line, col: -1, shift: e.shiftKey });
  });
  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    dragEvent = e;
    if (!dragRaf) dragRaf = requestAnimationFrame(() => {
      dragRaf = 0;
      const p = posFromPoint(dragEvent.clientX, dragEvent.clientY);
      if (p) send({ kind: "drag", line: p.line, col: p.col });
    });
  });
  document.addEventListener("mouseup", () => { dragging = false; });
  els.text.addEventListener("dblclick", (e) => {
    const p = posFromPoint(e.clientX, e.clientY);
    if (p) send({ kind: "dblclick", line: p.line, col: p.col });
  });
  let wheelAcc = 0;
  els.editor.addEventListener("wheel", (e) => {
    if (!frame || frame.tabs.length === 0) return;
    e.preventDefault();
    wheelAcc += e.deltaMode === 1 ? e.deltaY * LINE_H : e.deltaY;
    const lines = Math.trunc(wheelAcc / LINE_H);
    if (lines !== 0) { wheelAcc -= lines * LINE_H; send({ kind: "scroll", delta: lines }); }
  }, { passive: false });

  // ---- painel de saida: altura inicial de 35% da area, divisor arrastavel,
  // altura lembrada por navegador (localStorage e conveniencia, nunca estado)
  const OUTPUT_H_KEY = "noxy-editor.output-h";
  let resizing = null;
  let outputH = 0;   // altura atual do painel em px; 0 = ainda nao dimensionado
  function clampOutputHeight(h) {
    const max = Math.floor(els.main.clientHeight * 0.8);
    return Math.max(100, Math.min(Math.round(h), max));
  }
  // a altura vive na variavel da grade: o editor (1fr) encolhe na mesma medida
  function setOutputHeight(h) {
    outputH = clampOutputHeight(h);
    els.main.style.setProperty("--output-h", outputH + "px");
  }
  // renderPanel: aberto ou fechado e a aba ativa vem do quadro; a altura e
  // conveniencia local
  function renderPanel(panel) {
    if (!panel.open) {
      els.output.classList.add("hidden");
      els.main.style.setProperty("--output-h", "0px");
      return;
    }
    if (outputH === 0) {
      let saved = null;
      try { saved = parseInt(localStorage.getItem(OUTPUT_H_KEY), 10); } catch (err) { saved = null; }
      setOutputHeight(saved > 0 ? saved : els.main.clientHeight * 0.35);
    } else {
      setOutputHeight(outputH);
    }
    els.output.classList.remove("hidden");
    for (const tab of els.panelTabs.querySelectorAll(".ptab")) tab.classList.toggle("active", tab.dataset.tab === panel.tab);
    els.outputText.classList.toggle("hidden", panel.tab !== "output");
    els.searchView.classList.toggle("hidden", panel.tab !== "search");
    els.termView.classList.toggle("hidden", panel.tab !== "terminal");
  }

  // ---- botoes, redimensionar, poll durante execucao, fechamento
  els.runBtn.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "run" }); });
  els.outputClose.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "panel_toggle" }); });
  for (const tab of els.panelTabs.querySelectorAll(".ptab")) {
    tab.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "panel_tab", key: tab.dataset.tab }); });
  }
  // o divisor e a barra "Saida" inteira redimensionam, com Pointer Events e
  // captura do ponteiro: uma vez iniciado, o arraste segue o divisor mesmo
  // passando pela barra de rolagem do editor ou saindo da janela
  function startResize(e) {
    if (e.button !== 0 || e.target.closest("#output-close")) return;
    e.preventDefault();
    resizing = { y: e.clientY, h: outputH, id: e.pointerId, el: e.currentTarget };
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (err) { /* sem captura: o movimento ainda chega enquanto o ponteiro estiver sobre o alvo */ }
    els.output.classList.add("resizing");
  }
  function moveResize(e) {
    if (!resizing) return;
    setOutputHeight(resizing.h + (resizing.y - e.clientY));
  }
  function endResize(e) {
    if (!resizing) return;
    try { resizing.el.releasePointerCapture(resizing.id); } catch (err) { /* ja liberado */ }
    resizing = null;
    els.output.classList.remove("resizing");
    try { localStorage.setItem(OUTPUT_H_KEY, String(outputH)); } catch (err) { /* sem storage: so nao lembra */ }
  }
  for (const el of [els.outputResize, els.outputHead]) {
    el.addEventListener("pointerdown", startResize);
    el.addEventListener("pointermove", moveResize);
    el.addEventListener("pointerup", endResize);
    el.addEventListener("pointercancel", endResize);
  }
  new ResizeObserver(() => {
    const r = rowsNow();
    if (r !== rows) { rows = r; send({ kind: "poll" }); }
  }).observe(els.editor);
  setInterval(() => { if (frame && frame.output.running) send({ kind: "poll" }); }, 250);
  window.addEventListener("pagehide", () => {
    navigator.sendBeacon("/event?t=" + encodeURIComponent(token), JSON.stringify({ kind: "bye", page: PAGE_ID, rows, tree_version: treeVersion }));
  });

  rows = rowsNow();
  send({ kind: "init" });
})();
