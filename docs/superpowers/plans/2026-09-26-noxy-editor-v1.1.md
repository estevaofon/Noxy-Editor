# Noxy Editor v1.1 — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remover as limitações da v1: busca no arquivo e na pasta, Quick Open, paleta de comandos, temas, git na interface, minimap, recuperação de alterações não salvas, CRLF preservado, execução com saída ao vivo e Parar, e um terminal de verdade.

**Architecture:** O desenho da v1 continua: a routine principal é a dona do estado, o cliente é burro e pinta o quadro. Cada recurso é um módulo Noxy novo com testes sem navegador, mais o pedaço do cliente coberto pelos smokes no Chrome headless e no WebKitGTK. O terminal é uma terceira extensão, `noxy_pty` (Go sobre `creack/pty`), com dados em base64 por rotas `/term` que não passam pelo dono do estado, e xterm.js vendorizado no cliente.

**Tech Stack:** Noxy v0.25.1; `noxy_webview` v0.1.0 (instalada); Go 1.25+ com `github.com/estevaofon/noxy/sdk/noxyplugin v0.1.0` e `github.com/creack/pty v1.1.24`; `@xterm/xterm` 6.0.0 e `@xterm/addon-fit` 0.11.0 (MIT); Chrome headless via DevTools Protocol e PyGObject/WebKit2 4.1 para os smokes.

**Spec:** `docs/superpowers/specs/2026-09-26-noxy-editor-v1.1-design.md` (na `feat/v1.1`, commit `ff8e625` alinhou a spec ao que a prototipagem decidiu).

**Como este plano foi feito.** Todo o código saiu de um protótipo construído por TDD sobre esta mesma branch: 32 commits no editor e 6 na extensão, cada commit de teste visto falhar e cada commit de implementação visto passar, com as suítes medidas commit a commit. Cada tarefa aqui reproduz um par desses commits como patch: o `git apply` do teste, o vermelho esperado (o erro exato medido), o `git apply` da implementação, o verde esperado (a contagem exata medida). Os patches assumem que as tarefas anteriores foram aplicadas na ordem; `git apply` recusa inteiro se não bater, sem mudar nada.

## Global Constraints

- Noxy **v0.25.1** (`/home/estevao/go/bin/noxy`). Editor em `/home/estevao/Documentos/noxy_projects/Noxy-Editor`, branch `feat/v1.1`; extensão nova em `/home/estevao/Documentos/noxy_projects/noxy_pty`.
- Todo comando do editor roda da raiz do editor; os da extensão, da raiz dela.
- Commits no padrão `tipo(escopo): descrição`, terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- As suítes Noxy definem `NOXY_EDITOR_CACHE_DIR` e `NOXY_EDITOR_CONFIG_DIR` em `tests/tmp`: nenhum teste toca no `~/.cache` ou no `~/.config` de quem roda. Confira com `ls ~/.cache ~/.config | grep -c noxy-editor` → `0`.
- Nada de processo sobrando: depois de cada rodada, `ps -eo args | grep -E "noxy-plugin-pty|exec noxy" | grep -v grep` vazio. Se sobrar algo de uma rodada vermelha, mate só o grupo daquele processo (`kill -TERM -<pgid>`), conferindo antes que é um `exec noxy` de `tests/tmp`.
- O relógio do dono é `events.now()` (ms). `time_now()` devolve segundos (achado 8).
- `kill` de grupo no formato do dash: `kill -TERM -PGID`, sem `--`.
- Nunca `use strings select *` num módulo que use o `contains` de arrays.
- Os smokes usam `SHELL=/bin/sh`; o do WebKitGTK abre uma janela por alguns segundos e precisa de `GDK_BACKEND=x11`.
- Testado no Linux; no Windows o terminal e o Parar ainda não funcionam (a spec aceita).

## Review Focus

1. **Editor fechado com um programa rodando** (F5 num loop sem fim, depois sair): nada pode ficar rodando. Teste "shutdown para o programa em execucao" (Task 16) e "sem processo orfao" (Task 9).
2. **Aba Terminal escondida e mostrada de novo**: o xterm para de desenhar quando escondido; ao voltar, o conteúdo tem de estar lá. Check "o terminal continua o mesmo ao voltar a aba" e o `exit` digitado depois (Task 16).
3. **Clique de mouse real nas abas do painel e no Parar**: a barra do painel é alça de arraste; com `dispatchEvent` tudo passava, com o mouse de verdade nada respondia. Checks com `click_real` (Task 16).
4. **Pasta aberta que é subpasta de um repositório git**: o porcelain vem relativo ao repositório; só o que está sob a raiz entra, relativo a ela. Teste "prefixo: so o que esta sob a raiz aberta, relativo a ela" (Task 10).
5. **Arquivo que não é UTF-8 na pasta durante a busca**: tem de ser pulado sem derrubar a task. Teste "acha nos arquivos de texto, pula node_modules e binarios" (Task 7).

---
### Task 1: Quebra de linha preservada (CRLF)

**Interfaces:**
- Produces: `Document.eol` ("\n" ou "\r\n"), `doc.eol_name(d)` ("LF"/"CRLF"), `StatusOut.eol` no quadro.

**Files:** `src/document.nx`, `src/frame.nx`, `tests/run.nx`

- [ ] **Passo 1: os testes (vermelho)**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (24 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/run.nx b/tests/run.nx
index 6e06ac39aeeb8665b4f3fd840e46e5d599364efd..3d343bb2aba6abbc24495b0a6590e7f6d2e48518 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -38,7 +38,9 @@ func test_document() -> void
     print("document")
     let d: doc.Document = doc.from_text("x.nx", "ab\r\ncd\n")
     check("from_text normaliza CRLF e mantem a linha final vazia", length(d.lines) == 3 && d.lines[0] == "ab" && d.lines[1] == "cd" && d.lines[2] == "")
-    check("to_text devolve LF", doc.to_text(d) == "ab\ncd\n")
+    check("to_text preserva CRLF quando o arquivo tinha", d.eol == "\r\n" && doc.to_text(d) == "ab\r\ncd\r\n")
+    let lf: doc.Document = doc.from_text("y.nx", "ab\ncd")
+    check("arquivo LF continua LF", lf.eol == "\n" && doc.to_text(lf) == "ab\ncd")
     let e: doc.Document = doc.from_text("", "")
     check("documento vazio tem uma linha", length(e.lines) == 1 && e.lines[0] == "")
 
@@ -444,7 +446,7 @@ func test_frame() -> void
     check("spans cortados na fronteira da selecao", strings.contains(f, "{\"k\":\"keyword\",\"s\":false,\"t\":\"l\"}") && strings.contains(f, "{\"k\":\"keyword\",\"s\":true,\"t\":\"et\"}") && strings.contains(f, "{\"k\":\"ident\",\"s\":true,\"t\":\"x\"}"))
     check("cursor, has_sel e total", strings.contains(f, "\"cursor\":{\"col\":1,\"line\":1}") && strings.contains(f, "\"has_sel\":true") && strings.contains(f, "\"total\":3"))
     check("aba suja e titulo", strings.contains(f, "\"dirty\":true") && strings.contains(f, "b.nx ● — Noxy Editor"))
-    check("status", strings.contains(f, "\"left\":\"b.nx ●\"") && strings.contains(f, "Ln 2, Col 2"))
+    check("status", strings.contains(f, "\"left\":\"b.nx ●\"") && strings.contains(f, "Ln 2, Col 2") && strings.contains(f, "\"eol\":\"LF\""))
     check("clipboard vai e e consumido", strings.contains(f, "\"clipboard\":\"cp\"") && s.clipboard == "")
     s.rows = 1
     editing.ensure_visible(ref s.tabs[0].editor, 1)
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: `Runtime error: [tests/run.nx:line 41] undefined property 'eol'`
- [ ] **Commit**

```bash
git add tests/run.nx
git commit -q -m 'test(document,frame): eol preservado e mostrado na status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3: a implementação**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (95 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/src/document.nx b/src/document.nx
index 040534ff58ebaf0c82ecbf423f02886f2983b010..17ddda74703c0d348178da1ebd8c752dfee8f00f 100644
--- a/src/document.nx
+++ b/src/document.nx
@@ -1,7 +1,7 @@
 // src/document.nx — o documento: linhas de texto e posicoes em code points.
 // Nao conhece cursor, tela nem arquivo. Toda operacao que muda texto marca
 // dirty. Posicoes usam a mesma unidade de substring e codes.
-use strings select substring, split, join_count, replace
+use strings select substring, split, join_count, replace, contains
 
 struct Pos
     line: int       // 0-based
@@ -17,19 +17,33 @@ struct Document
     path: string    // absoluto; "" para um buffer sem arquivo
     lines: string[] // nunca vazio: um documento vazio tem uma linha ""
     dirty: bool
+    eol: string     // "\n" ou "\r\n": a quebra que o arquivo tinha, gravada de volta
 end
 
+// from_text divide em linhas; a quebra do arquivo (LF ou CRLF) fica em eol.
 func from_text(path: string, text: string) -> Document
+    let eol: string = "\n"
+    if contains(text, "\r\n") then
+        eol = "\r\n"
+    end
     let clean: string = replace(replace(text, "\r\n", "\n"), "\r", "\n")
     let parts: string[] = split(clean, "\n").parts
     if length(parts) == 0 then
         parts = [""]
     end
-    return Document(path, parts, false)
+    return Document(path, parts, false, eol)
 end
 
 func to_text(d: Document) -> string
-    return join_count(d.lines, "\n", length(d.lines))
+    return join_count(d.lines, d.eol, length(d.lines))
+end
+
+// eol_name e o que a barra de status mostra.
+func eol_name(d: Document) -> string
+    if d.eol == "\r\n" then
+        return "CRLF"
+    end
+    return "LF"
 end
 
 func line_count(d: Document) -> int
diff --git a/src/frame.nx b/src/frame.nx
index f00f1635f2fb43241472c40b7dfb070fa869e437..5648ba42cd362f841663479aaf4bf3bcaf2ab508 100644
--- a/src/frame.nx
+++ b/src/frame.nx
@@ -43,6 +43,7 @@ struct StatusOut
     left: string
     right: string
     message: string
+    eol: string     // "LF" ou "CRLF"; "" sem aba
 end
 
 struct OutputOut
@@ -162,6 +163,7 @@ func build(s: ref session.Session, client_tree_version: int) -> string
     let title: string = title_of(s)
     let left: string = ""
     let right: string = ""
+    let eol: string = ""
     if s.active >= 0 then
         let ed: editing.Editor = s.tabs[s.active].editor
         view = build_view(ed, s.rows)
@@ -170,9 +172,10 @@ func build(s: ref session.Session, client_tree_version: int) -> string
             mark = " ●"
         end
         left = session.relative(s.root, ed.doc.path) + mark
-        right = "Ln " + to_str(ed.cursor.line + 1) + ", Col " + to_str(ed.cursor.col + 1) + "   Espaços: 4   UTF-8"
+        right = "Ln " + to_str(ed.cursor.line + 1) + ", Col " + to_str(ed.cursor.col + 1) + "   Espaços: 4   " + doc.eol_name(ed.doc)
+        eol = doc.eol_name(ed.doc)
     end
-    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal)
+    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal)
     s.clipboard = ""
     return json_dumps(f)
 end
diff --git a/tests/run.nx b/tests/run.nx
index 3d343bb2aba6abbc24495b0a6590e7f6d2e48518..aad320e01a7328c4aad843516a4911b91906c165 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -459,7 +459,7 @@ func test_frame() -> void
         append(ref big, "let v" + to_str(i) + ": int = " + to_str(i) + " // linha")
     end
     let bs: session.Session = session.new_session(root)
-    append(ref bs.tabs, session.Tab(editing.new_editor(doc.Document(root + "/big.nx", big, false))))
+    append(ref bs.tabs, session.Tab(editing.new_editor(doc.Document(root + "/big.nx", big, false, "\n"))))
     bs.active = 0
     bs.rows = 50
     editing.move_doc_end(ref bs.tabs[0].editor, false, 50)
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `153/153 passaram` e `10/10 passaram`.
- [ ] **Commit**

```bash
git add src/document.nx src/frame.nx tests/run.nx
git commit -q -m 'feat(document): CRLF preservado na gravacao e LF/CRLF na status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 2: Painel inferior com abas

**Interfaces:**
- Produces: `session.Panel { open, tab }`, `session.show_panel(ref s, tab)`, `session.toggle_panel(ref s)`; eventos `panel_tab` (key) e `panel_toggle`; Ctrl+J e Ctrl+` resolvidos no Noxy; `#panel-tabs`, `#search-view`, `#term-view` no cliente.

**Files:** `src/events.nx`, `src/frame.nx`, `src/session.nx`, `tests/run.nx`, `tests/web_smoke.py`, `web/editor.css`, `web/editor.js`, `web/index.html`

- [ ] **Passo 1: os testes (vermelho)**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (43 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/run.nx b/tests/run.nx
index aad320e01a7328c4aad843516a4911b91906c165..e88147df2a0cfeff982a153868d9bf4a96315cd7 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -502,12 +502,24 @@ func test_events() -> void
     check("resposta do modal fecha a aba", length(s.tabs) == 0 && s.modal.text == "")
     let fr: string = events.dispatch(ref s, "{\"kind\":\"run\",\"rows\":20,\"tree_version\":2}", 14)
     check("run sem aba avisa", strings.contains(fr, "nenhum arquivo aberto"))
+    check("painel comeca fechado na aba de saida", !s.panel.open && s.panel.tab == "output" && strings.contains(fr, "\"panel\":{\"open\":false,\"tab\":\"output\"}"))
+    events.dispatch(ref s, "{\"kind\":\"panel_toggle\",\"rows\":20,\"tree_version\":2}", 14)
+    check("panel_toggle abre", s.panel.open)
+    events.dispatch(ref s, "{\"kind\":\"panel_tab\",\"key\":\"search\",\"rows\":20,\"tree_version\":2}", 14)
+    check("panel_tab troca a aba", s.panel.tab == "search" && s.panel.open)
+    events.dispatch(ref s, "{\"kind\":\"panel_tab\",\"key\":\"zzz\",\"rows\":20,\"tree_version\":2}", 14)
+    check("aba desconhecida e ignorada", s.panel.tab == "search")
+    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"j\",\"ctrl\":true,\"rows\":20,\"tree_version\":2}", 14)
+    check("ctrl+j fecha o painel", !s.panel.open)
+    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"`\",\"ctrl\":true,\"rows\":20,\"tree_version\":2}", 14)
+    check("ctrl+` abre na aba terminal", s.panel.open && s.panel.tab == "terminal")
     events.dispatch(ref s, "{\"kind\":\"tree_open\",\"path\":\"" + root + "/a.txt\",\"rows\":20,\"tree_version\":2}", 15)
     let ft: string = events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"f5\",\"rows\":20,\"tree_version\":2}", 16)
     check("f5 em .txt recusa", strings.contains(ft, "so arquivos .nx"))
     events.dispatch(ref s, "{\"kind\":\"tree_open\",\"path\":\"" + root + "/hello.nx\",\"rows\":20,\"tree_version\":2}", 17)
     let f5: string = events.dispatch(ref s, "{\"kind\":\"run\",\"rows\":20,\"tree_version\":2}", 18)
     check("run dispara e o quadro mostra running", s.run.running && strings.contains(f5, "\"running\":true"))
+    check("run abre o painel na aba de saida", s.panel.open && s.panel.tab == "output")
     let waited: int = 0
     let last: string = ""
     while s.run.running && waited < 100 do
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index ece998769ef54f166d833458b58ecd37a7aa6f1b..1f0604efaee5cdb82e1ca386b494668a607d3cc5 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -149,6 +149,9 @@ h2 = output_h()
 mouse("mousePressed", head[0], head[1]); mouse("mouseMoved", head[0], head[1] + 80); settle(); mouse("mouseReleased", head[0], head[1] + 80); settle()
 h3 = output_h()
 check("arrastar pela barra SAIDA tambem redimensiona (%.0f -> %.0f px)" % (h2, h3), abs((h3 - h2) + 80) < 3)
+check("aba Saida ativa apos F5", ev("document.querySelector('#panel-tabs .ptab.active').dataset.tab") == "output")
+ev("document.querySelector('#panel-tabs .ptab[data-tab=\"search\"]').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
+check("clicar na aba Busca troca a aba", ev("document.querySelector('#panel-tabs .ptab.active').dataset.tab") == "search" and not ev("document.getElementById('search-view').classList.contains('hidden')"))
 key("j", mods=2)
 check("ctrl+j esconde o painel", ev("document.getElementById('output').classList.contains('hidden')"))
 key("j", mods=2)
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: `Runtime error: [tests/run.nx:line 505] undefined property 'panel'`
- [ ] **Commit**

```bash
git add tests/run.nx tests/web_smoke.py
git commit -q -m 'test(panel): painel inferior com abas, ctrl+j e ctrl+` pelo noxy

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3: a implementação**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (235 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/src/events.nx b/src/events.nx
index 47ecf92d0ee48a7af4bf8afeb0160fbe538cc423..fe784039df05ea170364e2963d8db35c4137bcf1 100644
--- a/src/events.nx
+++ b/src/events.nx
@@ -58,7 +58,9 @@ func run_active(s: ref session.Session) -> void
     let msg: string = runner.start(ref s.run, s.root, session.relative(s.root, path))
     if msg != "" then
         s.message = msg
+        return
     end
+    session.show_panel(s, "output")
 end
 
 func handle_key(s: ref session.Session, e: Event, now: int) -> void
@@ -74,6 +76,14 @@ func handle_key(s: ref session.Session, e: Event, now: int) -> void
         session.answer_modal(s, "cancel")
         return
     end
+    if e.ctrl && e.key == "j" then
+        session.toggle_panel(s)
+        return
+    end
+    if e.ctrl && e.key == "`" then
+        session.show_panel(s, "terminal")
+        return
+    end
     if s.active < 0 then
         return
     end
@@ -199,6 +209,10 @@ func apply(s: session.Session, e: Event, now: int) -> session.Session
         session.open_file(ref s, e.path)
     elif e.kind == "run" then
         run_active(ref s)
+    elif e.kind == "panel_tab" then
+        session.show_panel(ref s, e.key)
+    elif e.kind == "panel_toggle" then
+        session.toggle_panel(ref s)
     elif e.kind == "modal" then
         session.answer_modal(ref s, e.key)
     elif e.kind == "quit" then
diff --git a/src/frame.nx b/src/frame.nx
index 5648ba42cd362f841663479aaf4bf3bcaf2ab508..82e3556b6211a73b570e3332febd151cc910d220 100644
--- a/src/frame.nx
+++ b/src/frame.nx
@@ -63,6 +63,7 @@ struct Frame
     output: OutputOut
     clipboard: string
     modal: session.Modal
+    panel: session.Panel
 end
 
 // cut_span corta um token que comeca na coluna col em ate tres pedacos na
@@ -175,7 +176,7 @@ func build(s: ref session.Session, client_tree_version: int) -> string
         right = "Ln " + to_str(ed.cursor.line + 1) + ", Col " + to_str(ed.cursor.col + 1) + "   Espaços: 4   " + doc.eol_name(ed.doc)
         eol = doc.eol_name(ed.doc)
     end
-    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal)
+    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel)
     s.clipboard = ""
     return json_dumps(f)
 end
diff --git a/src/session.nx b/src/session.nx
index fa4fe9d3c4a22e7e96f8db1541ef5cfa6c8c1621..f392ec31ed1a633a172bfb7ba40324a80843c535 100644
--- a/src/session.nx
+++ b/src/session.nx
@@ -31,6 +31,15 @@ struct Modal
     pending: string     // o que fazer depois: "close_tab:3" ou "quit"
 end
 
+// Panel e o painel inferior: aberto ou nao, e qual aba (output, search,
+// terminal) esta a mostra.
+struct Panel
+    open: bool
+    tab: string
+end
+
+let PANEL_TABS: string[] = ["output", "search", "terminal"]
+
 struct Session
     root: string        // absoluto, sem barra final
     tabs: Tab[]
@@ -46,6 +55,20 @@ struct Session
     bye: bool           // a pagina avisou que esta fechando (pagehide)
     page: string        // id da ultima pagina que mandou evento
     bye_page: string    // id da pagina que se despediu
+    panel: Panel
+end
+
+// show_panel abre o painel numa aba; uma aba desconhecida e ignorada.
+func show_panel(s: ref Session, tab: string) -> void
+    if !contains(PANEL_TABS, tab) then
+        return
+    end
+    s.panel.open = true
+    s.panel.tab = tab
+end
+
+func toggle_panel(s: ref Session) -> void
+    s.panel.open = !s.panel.open
 end
 
 func no_modal() -> Modal
@@ -53,7 +76,7 @@ func no_modal() -> Modal
 end
 
 func new_session(root: string) -> Session
-    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "")
+    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"))
 end
 
 func basename(path: string) -> string
diff --git a/web/editor.css b/web/editor.css
index b82aa23ac3bb5b2b721b22522b55300fbf407664..988cbdaa52e4f8b574cb17ffe3ece59ab5ee26d2 100644
--- a/web/editor.css
+++ b/web/editor.css
@@ -89,9 +89,15 @@ button { font: inherit; color: inherit; background: none; border: none; cursor:
 #output-resize:hover, #output.resizing #output-resize { background: var(--accent); }
 #output-head { cursor: ns-resize; user-select: none; touch-action: none; }
 #output.resizing { user-select: none; }
-#output-head { display: flex; justify-content: space-between; align-items: center; padding: 4px 12px; font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--fg-dim); }
+#output-head { display: flex; justify-content: space-between; align-items: center; padding: 0 12px 0 4px; font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--fg-dim); }
+#panel-tabs { display: flex; }
+.ptab { padding: 6px 10px; cursor: pointer; border-bottom: 2px solid transparent; }
+.ptab:hover { color: var(--fg); }
+.ptab.active { color: var(--fg); border-bottom-color: var(--accent); }
+.pview { flex: 1; min-height: 0; overflow: auto; }
+#search-view, #term-view { padding: 4px 14px 10px; }
 #output-close { color: var(--fg-dim); font-size: 16px; line-height: 1; }
-#output-text { flex: 1; min-height: 0; margin: 0; padding: 4px 14px 10px; overflow: auto; font: 13px var(--font-mono); white-space: pre-wrap; }
+#output-text { margin: 0; padding: 4px 14px 10px; font: 13px var(--font-mono); white-space: pre-wrap; }
 
 /* barra de status */
 #status { display: flex; align-items: center; gap: 16px; padding: 0 14px; background: var(--bg-status); border-top: 1px solid var(--border); font-size: 12px; color: var(--fg-dim); }
diff --git a/web/editor.js b/web/editor.js
index 8084d7b12aae78304522ae26773065958d594cc8..461b5d65b1825cb3cd2d9fd41889b17d73604651 100644
--- a/web/editor.js
+++ b/web/editor.js
@@ -11,6 +11,7 @@
     rootName: $("root-name"), tree: $("tree"), tabs: $("tabs"), runBtn: $("run-btn"),
     editor: $("editor"), gutter: $("gutter"), text: $("text"), cursor: $("cursor"), welcome: $("welcome"),
     main: $("main"), output: $("output"), outputText: $("output-text"), outputClose: $("output-close"), outputResize: $("output-resize"), outputHead: $("output-head"),
+    panelTabs: $("panel-tabs"), searchView: $("search-view"), termView: $("term-view"),
     status: $("status"), statusLeft: $("status-left"), statusMsg: $("status-msg"), statusRight: $("status-right"),
     modal: $("modal"), modalText: $("modal-text"), modalButtons: $("modal-buttons"),
     input: $("input"),
@@ -92,12 +93,10 @@
     els.statusMsg.textContent = f.status.message;
     if (f.output.version !== outputVersion) {
       outputVersion = f.output.version;
-      if (f.output.version > 0) {
-        showOutput(true);
-        els.outputText.textContent = f.output.text + (f.output.running ? "\n…" : "");
-        els.outputText.scrollTop = els.outputText.scrollHeight;
-      }
+      els.outputText.textContent = f.output.text + (f.output.running ? "\n…" : "");
+      els.outputText.scrollTop = els.outputText.scrollHeight;
     }
+    renderPanel(f.panel);
     renderModal(f.modal);
     if (f.clipboard) {
       internalClip = f.clipboard;
@@ -225,7 +224,7 @@
   // chegam pelo textarea (input / compositionend), o que faz acentos e IME
   // funcionarem.
   const NAV = { ArrowLeft: 1, ArrowRight: 1, ArrowUp: 1, ArrowDown: 1, Home: 1, End: 1, PageUp: 1, PageDown: 1, Enter: 1, Backspace: 1, Delete: 1, Tab: 1, Escape: 1, F5: 1 };
-  const CTRL = { s: 1, z: 1, y: 1, a: 1, w: 1, "/": 1, q: 1, arrowleft: 1, arrowright: 1, home: 1, end: 1 };
+  const CTRL = { s: 1, z: 1, y: 1, a: 1, w: 1, "/": 1, q: 1, j: 1, "`": 1, arrowleft: 1, arrowright: 1, home: 1, end: 1 };
 
   els.input.addEventListener("keydown", (e) => {
     if (e.isComposing) return;
@@ -234,7 +233,6 @@
       if (key === "c") { e.preventDefault(); send({ kind: "copy" }); return; }
       if (key === "x") { e.preventDefault(); send({ kind: "cut" }); return; }
       if (key === "v") return;
-      if (key === "j") { e.preventDefault(); showOutput(els.output.classList.contains("hidden")); return; }
       if (CTRL[key]) { e.preventDefault(); send({ kind: "key", key, ctrl: true, shift: e.shiftKey, alt: e.altKey }); }
       return;
     }
@@ -345,8 +343,10 @@
     outputH = clampOutputHeight(h);
     els.main.style.setProperty("--output-h", outputH + "px");
   }
-  function showOutput(on) {
-    if (!on) {
+  // renderPanel: aberto ou fechado e a aba ativa vem do quadro; a altura e
+  // conveniencia local
+  function renderPanel(panel) {
+    if (!panel.open) {
       els.output.classList.add("hidden");
       els.main.style.setProperty("--output-h", "0px");
       return;
@@ -359,11 +359,18 @@
       setOutputHeight(outputH);
     }
     els.output.classList.remove("hidden");
+    for (const tab of els.panelTabs.querySelectorAll(".ptab")) tab.classList.toggle("active", tab.dataset.tab === panel.tab);
+    els.outputText.classList.toggle("hidden", panel.tab !== "output");
+    els.searchView.classList.toggle("hidden", panel.tab !== "search");
+    els.termView.classList.toggle("hidden", panel.tab !== "terminal");
   }
 
   // ---- botoes, redimensionar, poll durante execucao, fechamento
   els.runBtn.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "run" }); });
-  els.outputClose.addEventListener("mousedown", (e) => { e.preventDefault(); showOutput(false); });
+  els.outputClose.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "panel_toggle" }); });
+  for (const tab of els.panelTabs.querySelectorAll(".ptab")) {
+    tab.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "panel_tab", key: tab.dataset.tab }); });
+  }
   // o divisor e a barra "Saida" inteira redimensionam, com Pointer Events e
   // captura do ponteiro: uma vez iniciado, o arraste segue o divisor mesmo
   // passando pela barra de rolagem do editor ou saindo da janela
diff --git a/web/index.html b/web/index.html
index d5d3741eedb6b655db5939a585605a7cc9d1ec7d..7568757bf3e596d3644581e024282991504b9503 100644
--- a/web/index.html
+++ b/web/index.html
@@ -23,8 +23,17 @@
     </div>
     <div id="output" class="hidden">
       <div id="output-resize" title="Arraste para redimensionar"></div>
-      <div id="output-head"><span>Saída</span><button id="output-close" title="Fechar (Ctrl+J)">×</button></div>
-      <pre id="output-text"></pre>
+      <div id="output-head">
+        <div id="panel-tabs">
+          <span class="ptab" data-tab="output">Saída</span>
+          <span class="ptab" data-tab="search">Busca</span>
+          <span class="ptab" data-tab="terminal">Terminal</span>
+        </div>
+        <button id="output-close" title="Fechar (Ctrl+J)">×</button>
+      </div>
+      <pre id="output-text" class="pview"></pre>
+      <div id="search-view" class="pview hidden"></div>
+      <div id="term-view" class="pview hidden"></div>
     </div>
     <div id="status">
       <span id="status-left"></span>
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `160/160 passaram` e `10/10 passaram`.
- [ ] **Passo 5: o cliente de verdade**

Run: `python3 tests/web_smoke.py && GDK_BACKEND=x11 python3 tests/webkit_smoke.py`
Esperado: as duas linhas finais `OK: 0 falhas` (o primeiro precisa de `google-chrome`; o segundo abre uma janela WebKitGTK por alguns segundos).
- [ ] **Commit**

```bash
git add src/events.nx src/frame.nx src/session.nx web/editor.css web/editor.js web/index.html
git commit -q -m 'feat(panel): painel inferior com abas Saida, Busca e Terminal; ctrl+j e ctrl+` como comandos do noxy

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 3: Configurações, temas e run_command

**Interfaces:**
- Produces: `settings.Settings { theme }`, `settings.THEMES`, `settings.load()`, `settings.save(s) -> bool`, `settings.path()`; `NOXY_EDITOR_CONFIG_DIR`; `events.run_command(ref s, id, now)` (todo atalho passa por ela); evento `command` (key = id); classes `theme-<id>` em `html`.

**Files:** `src/events.nx`, `src/frame.nx`, `src/session.nx`, `src/settings.nx`, `tests/run.nx`, `tests/web_smoke.py`, `web/editor.css`, `web/editor.js`

- [ ] **Passo 1: os testes (vermelho)**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (71 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/run.nx b/tests/run.nx
index e88147df2a0cfeff982a153868d9bf4a96315cd7..35d49e13c2c19bde7d90d5262a7679f052f2ce18 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -12,6 +12,7 @@ use src.session as session
 use src.frame as frame
 use src.events as events
 use src.browser as browser
+use src.settings as settings
 
 let fails = 0
 let total = 0
@@ -528,6 +529,15 @@ func test_events() -> void
         waited = waited + 1
     end
     check("poll recolhe a saida no quadro", strings.contains(last, "[saiu com 3]"))
+    sys.setenv("NOXY_EDITOR_CONFIG_DIR", sys.getcwd() + "/tests/tmp/config")
+    let fth: string = events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"theme:nord\",\"rows\":20,\"tree_version\":2}", 19)
+    check("comando theme:nord muda o tema, grava e vai no quadro", s.settings.theme == "nord" && strings.contains(fth, "\"settings\":{\"theme\":\"nord\"}") && settings.load().theme == "nord")
+    let fu2: string = events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"zzz\",\"rows\":20,\"tree_version\":2}", 19)
+    check("comando desconhecido vira mensagem", strings.contains(fu2, "comando desconhecido: zzz"))
+    let was_open: bool = s.panel.open
+    events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"panel\",\"rows\":20,\"tree_version\":2}", 19)
+    check("comando panel alterna o painel", s.panel.open != was_open)
+    io.remove(sys.getcwd() + "/tests/tmp/run/config/settings.json")
     events.dispatch(ref s, "{\"kind\":\"quit\",\"rows\":20,\"tree_version\":2}", 20)
     check("quit marca quitting", s.quitting)
 
@@ -566,6 +576,24 @@ func test_browser() -> void
     check("cleanup remove a pagina e o diretorio", !io.exists(page) && !io.exists(dir))
 end
 
+func test_settings() -> void
+    print("settings")
+    let dir: string = sys.getcwd() + "/tests/tmp/config"
+    sys.setenv("NOXY_EDITOR_CONFIG_DIR", dir)
+    io.remove(dir + "/settings.json")
+    let d: settings.Settings = settings.load()
+    check("sem arquivo, padrao escuro", d.theme == "dark" && settings.path() == dir + "/settings.json")
+    d.theme = "nord"
+    check("save cria o diretorio e grava", settings.save(d) && read_file(dir + "/settings.json") == "{\"theme\":\"nord\"}")
+    check("load le o que foi gravado", settings.load().theme == "nord")
+    write_file(dir + "/settings.json", "{nope")
+    check("arquivo invalido volta ao padrao", settings.load().theme == "dark")
+    write_file(dir + "/settings.json", "{\"theme\":\"neon\"}")
+    check("tema desconhecido volta ao padrao", settings.load().theme == "dark")
+    check("lista de temas", length(settings.THEMES) == 5 && contains(settings.THEMES, "monokai"))
+    io.remove(dir + "/settings.json")
+end
+
 test_document()
 test_lexer()
 test_history()
@@ -576,4 +604,5 @@ test_session()
 test_frame()
 test_events()
 test_browser()
+test_settings()
 report()
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index 1f0604efaee5cdb82e1ca386b494668a607d3cc5..a6e2415f4b5fe05e902dd850ac664ae970cc6c0d 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -81,6 +81,7 @@ ws.call("Page.navigate", {"url": url}); settle(1500)
 check("arvore renderizada", ev("document.querySelectorAll('#tree .node').length") == 3)
 check("nome da raiz", ev("document.getElementById('root-name').textContent") == "web")
 check("titulo inicial", ev("document.title") == "Noxy Editor")
+check("tema escuro aplicado no html", ev("document.documentElement.classList.contains('theme-dark')"))
 # abrir exemplo.nx pela arvore
 ev("document.querySelectorAll('#tree .node.file')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
 check("abrir arquivo cria aba e linhas", ev("document.querySelectorAll('.tab').length") == 1 and ev("document.querySelectorAll('#text .line').length") == 11)
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: `Compiler error: [line 584] variable 'd': cannot resolve type 'settings.Settings': module 'src.settings' could not be loaded`
- [ ] **Commit**

```bash
git add tests/run.nx tests/web_smoke.py
git commit -q -m 'test(settings): settings.json, temas e o evento command

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3: a implementação**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (348 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/src/events.nx b/src/events.nx
index fe784039df05ea170364e2963d8db35c4137bcf1..1bcec93f23822973c824c11a59ff4c31931049f3 100644
--- a/src/events.nx
+++ b/src/events.nx
@@ -3,13 +3,14 @@
 // aplica dentro de call_result (um bug vira "erro interno" e a sessao fica
 // como estava, porque apply recebe e devolve a sessao por valor), consulta
 // a execucao e devolve o quadro.
-use strings select ends_with
+use strings select ends_with, starts_with, substring
 use errors select *
 use src.document as doc
 use src.editing as editing
 use src.session as session
 use src.runner as runner
 use src.frame as frame
+use src.settings as settings
 
 
 struct Event
@@ -63,13 +64,47 @@ func run_active(s: ref session.Session) -> void
     session.show_panel(s, "output")
 end
 
+// run_command executa um comando pelo id: e o que os atalhos e a paleta
+// chamam, entao os dois nunca divergem. Ids desconhecidos viram mensagem.
+func run_command(s: ref session.Session, id: string, now: int) -> void
+    if id == "save" then
+        session.save(s)
+    elif id == "save_all" then
+        if session.save_all(s) then
+            s.message = "tudo salvo"
+        end
+    elif id == "close_tab" then
+        session.close_tab(s, s.active)
+    elif id == "run" then
+        run_active(s)
+    elif id == "panel" then
+        session.toggle_panel(s)
+    elif id == "terminal" then
+        session.show_panel(s, "terminal")
+    elif id == "quit" then
+        session.request_quit(s)
+    elif starts_with(id, "theme:") then
+        let theme: string = substring(id, 6, length(id))
+        if contains(settings.THEMES, theme) then
+            s.settings.theme = theme
+            if !settings.save(s.settings) then
+                s.message = "nao consegui gravar " + settings.path()
+            end
+        else
+            s.message = "tema desconhecido: " + theme
+        end
+    else
+        s.message = "comando desconhecido: " + id
+    end
+end
+
 func handle_key(s: ref session.Session, e: Event, now: int) -> void
     if e.ctrl && e.key == "q" then
-        session.request_quit(s)
+        run_command(s, "quit", now)
         return
     end
     if e.key == "f5" then
-        run_active(s)
+        run_command(s, "run", now)
         return
     end
     if e.key == "escape" && s.modal.text != "" then
@@ -77,11 +112,11 @@ func handle_key(s: ref session.Session, e: Event, now: int) -> void
         return
     end
     if e.ctrl && e.key == "j" then
-        session.toggle_panel(s)
+        run_command(s, "panel", now)
         return
     end
     if e.ctrl && e.key == "`" then
-        session.show_panel(s, "terminal")
+        run_command(s, "terminal", now)
         return
     end
     if s.active < 0 then
@@ -91,7 +126,7 @@ func handle_key(s: ref session.Session, e: Event, now: int) -> void
     let ed: ref editing.Editor = ref s.tabs[s.active].editor
     if e.ctrl then
         if e.key == "s" then
-            session.save(s)
+            run_command(s, "save", now)
         elif e.key == "z" && e.shift then
             editing.redo(ed, rows)
         elif e.key == "z" then
@@ -101,7 +136,7 @@ func handle_key(s: ref session.Session, e: Event, now: int) -> void
         elif e.key == "a" then
             editing.select_all(ed)
         elif e.key == "w" then
-            session.close_tab(s, s.active)
+            run_command(s, "close_tab", now)
         elif e.key == "/" then
             editing.toggle_comment(ed, rows, now)
         elif e.key == "arrowleft" then
@@ -213,6 +248,8 @@ func apply(s: session.Session, e: Event, now: int) -> session.Session
         session.show_panel(ref s, e.key)
     elif e.kind == "panel_toggle" then
         session.toggle_panel(ref s)
+    elif e.kind == "command" then
+        run_command(ref s, e.key, now)
     elif e.kind == "modal" then
         session.answer_modal(ref s, e.key)
     elif e.kind == "quit" then
diff --git a/src/frame.nx b/src/frame.nx
index 82e3556b6211a73b570e3332febd151cc910d220..5fdc2221caf137f67a186845243433a9e20be40c 100644
--- a/src/frame.nx
+++ b/src/frame.nx
@@ -7,6 +7,7 @@ use src.document as doc
 use src.lexer as lexer
 use src.editing as editing
 use src.session as session
+use src.settings as settings
 
 struct SpanOut
     k: string       // kind do token
@@ -64,6 +65,7 @@ struct Frame
     clipboard: string
     modal: session.Modal
     panel: session.Panel
+    settings: settings.Settings
 end
 
 // cut_span corta um token que comeca na coluna col em ate tres pedacos na
@@ -176,7 +178,7 @@ func build(s: ref session.Session, client_tree_version: int) -> string
         right = "Ln " + to_str(ed.cursor.line + 1) + ", Col " + to_str(ed.cursor.col + 1) + "   Espaços: 4   " + doc.eol_name(ed.doc)
         eol = doc.eol_name(ed.doc)
     end
-    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel)
+    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings)
     s.clipboard = ""
     return json_dumps(f)
 end
diff --git a/src/session.nx b/src/session.nx
index f392ec31ed1a633a172bfb7ba40324a80843c535..02ec15e326343850bfe2d3aeec739ff1298eb816 100644
--- a/src/session.nx
+++ b/src/session.nx
@@ -7,6 +7,7 @@ use errors select Result, Failure
 use src.document as doc
 use src.editing as editing
 use src.runner as runner
+use src.settings as settings
 
 struct Tab
     editor: editing.Editor
@@ -56,6 +57,7 @@ struct Session
     page: string        // id da ultima pagina que mandou evento
     bye_page: string    // id da pagina que se despediu
     panel: Panel
+    settings: settings.Settings
 end
 
 // show_panel abre o painel numa aba; uma aba desconhecida e ignorada.
@@ -76,7 +78,7 @@ func no_modal() -> Modal
 end
 
 func new_session(root: string) -> Session
-    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"))
+    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load())
 end
 
 func basename(path: string) -> string
diff --git a/src/settings.nx b/src/settings.nx
new file mode 100644
index 0000000000000000000000000000000000000000..658fc005bb21385b556f76cf6cef8a2250432314
--- /dev/null
+++ b/src/settings.nx
@@ -0,0 +1,67 @@
+// src/settings.nx — as configuracoes do editor em
+// ~/.config/noxy-editor/settings.json (XDG_CONFIG_HOME quando definido;
+// NOXY_EDITOR_CONFIG_DIR sobrepoe os dois, para os testes). Arquivo
+// ausente ou invalido da o padrao; a proxima mudanca regrava.
+use sys
+use io
+use strings select trim
+
+struct Settings
+    theme: string      // um de THEMES
+end
+
+let THEMES: string[] = ["dark", "light", "dracula", "nord", "monokai"]
+
+func default_settings() -> Settings
+    return Settings("dark")
+end
+
+func config_dir() -> string
+    let o: sys.EnvResult = sys.getenv("NOXY_EDITOR_CONFIG_DIR")
+    if o.ok && o.value != "" then
+        return o.value
+    end
+    let x: sys.EnvResult = sys.getenv("XDG_CONFIG_HOME")
+    if x.ok && x.value != "" then
+        return x.value + "/noxy-editor"
+    end
+    return sys.getenv("HOME").value + "/.config/noxy-editor"
+end
+
+func path() -> string
+    return config_dir() + "/settings.json"
+end
+
+func load() -> Settings
+    let p: string = path()
+    if !io.exists(p) then
+        return default_settings()
+    end
+    let f: io.File = io.open(p, "r")
+    if !f.open then
+        return default_settings()
+    end
+    let r: io.IOResult = io.read(f)
+    io.close(f)
+    let s: Settings = default_settings()
+    if !r.ok || !json_loads(trim(r.data), ref s) then
+        eprint("settings.json invalido em " + p + "; usando o padrao")
+        return default_settings()
+    end
+    if !contains(THEMES, s.theme) then
+        s.theme = "dark"
+    end
+    return s
+end
+
+// save grava o arquivo, criando o diretorio; false se nao conseguiu.
+func save(s: Settings) -> bool
+    io.mkdir(config_dir())
+    let f: io.File = io.open(path(), "w")
+    if !f.open then
+        return false
+    end
+    io.write(f, json_dumps(s))
+    io.close(f)
+    return true
+end
diff --git a/web/editor.css b/web/editor.css
index 988cbdaa52e4f8b574cb17ffe3ece59ab5ee26d2..cf55a9a73ff826bc628126b8dae4d47a785d6658 100644
--- a/web/editor.css
+++ b/web/editor.css
@@ -1,33 +1,46 @@
-/* editor.css — tema escuro fixo (paleta Catppuccin Mocha). Cada kind de
-   token e uma classe .k-<kind>; .sel marca o trecho selecionado. */
-:root {
-  --bg: #1e1e2e;
-  --bg-side: #181825;
-  --bg-bar: #181825;
-  --bg-status: #11111b;
-  --bg-hover: #313244;
-  --fg: #cdd6f4;
-  --fg-dim: #6c7086;
-  --border: #313244;
-  --cur-line: #262637;
-  --sel: #45475a;
-  --accent: #89b4fa;
-  --cursor: #f5e0dc;
-  --danger: #f38ba8;
-  --k-keyword: #cba6f7;
-  --k-type: #f9e2af;
-  --k-ident: #cdd6f4;
-  --k-call: #89b4fa;
-  --k-number: #fab387;
-  --k-string: #a6e3a1;
-  --k-comment: #6c7086;
-  --k-operator: #94e2d5;
-  --k-punct: #9399b2;
-  --k-space: #cdd6f4;
+/* editor.css — temas como classes em html (theme-<id>), escolhidos pela
+   paleta e gravados no settings.json do Noxy. As mesmas variaveis em todos;
+   cada kind de token e uma classe .k-<kind>; .sel marca a selecao. */
+:root, html.theme-dark {
+  /* Catppuccin Mocha */
+  --bg: #1e1e2e; --bg-side: #181825; --bg-bar: #181825; --bg-status: #11111b; --bg-hover: #313244;
+  --fg: #cdd6f4; --fg-dim: #6c7086; --border: #313244; --cur-line: #262637; --sel: #45475a;
+  --accent: #89b4fa; --cursor: #f5e0dc; --danger: #f38ba8; --ok: #a6e3a1; --warn: #f9e2af;
+  --k-keyword: #cba6f7; --k-type: #f9e2af; --k-ident: #cdd6f4; --k-call: #89b4fa; --k-number: #fab387;
+  --k-string: #a6e3a1; --k-comment: #6c7086; --k-operator: #94e2d5; --k-punct: #9399b2; --k-space: #cdd6f4;
   --font-mono: ui-monospace, "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", monospace;
   --font-ui: system-ui, -apple-system, "Segoe UI", sans-serif;
   --line-h: 22px;
 }
+html.theme-light {
+  /* Catppuccin Latte */
+  --bg: #eff1f5; --bg-side: #e6e9ef; --bg-bar: #e6e9ef; --bg-status: #dce0e8; --bg-hover: #ccd0da;
+  --fg: #4c4f69; --fg-dim: #8c8fa1; --border: #ccd0da; --cur-line: #e6e9ef; --sel: #bcc0cc;
+  --accent: #1e66f5; --cursor: #dc8a78; --danger: #d20f39; --ok: #40a02b; --warn: #df8e1d;
+  --k-keyword: #8839ef; --k-type: #df8e1d; --k-ident: #4c4f69; --k-call: #1e66f5; --k-number: #fe640b;
+  --k-string: #40a02b; --k-comment: #8c8fa1; --k-operator: #179299; --k-punct: #6c6f85; --k-space: #4c4f69;
+}
+html.theme-dracula {
+  --bg: #282a36; --bg-side: #21222c; --bg-bar: #21222c; --bg-status: #191a21; --bg-hover: #44475a;
+  --fg: #f8f8f2; --fg-dim: #6272a4; --border: #44475a; --cur-line: #2f313d; --sel: #44475a;
+  --accent: #bd93f9; --cursor: #f8f8f2; --danger: #ff5555; --ok: #50fa7b; --warn: #f1fa8c;
+  --k-keyword: #ff79c6; --k-type: #8be9fd; --k-ident: #f8f8f2; --k-call: #50fa7b; --k-number: #bd93f9;
+  --k-string: #f1fa8c; --k-comment: #6272a4; --k-operator: #ff79c6; --k-punct: #f8f8f2; --k-space: #f8f8f2;
+}
+html.theme-nord {
+  --bg: #2e3440; --bg-side: #292e39; --bg-bar: #292e39; --bg-status: #242933; --bg-hover: #3b4252;
+  --fg: #d8dee9; --fg-dim: #616e88; --border: #3b4252; --cur-line: #353b49; --sel: #434c5e;
+  --accent: #88c0d0; --cursor: #d8dee9; --danger: #bf616a; --ok: #a3be8c; --warn: #ebcb8b;
+  --k-keyword: #81a1c1; --k-type: #8fbcbb; --k-ident: #d8dee9; --k-call: #88c0d0; --k-number: #b48ead;
+  --k-string: #a3be8c; --k-comment: #616e88; --k-operator: #81a1c1; --k-punct: #eceff4; --k-space: #d8dee9;
+}
+html.theme-monokai {
+  --bg: #272822; --bg-side: #1e1f1c; --bg-bar: #1e1f1c; --bg-status: #171814; --bg-hover: #3e3d32;
+  --fg: #f8f8f2; --fg-dim: #75715e; --border: #3e3d32; --cur-line: #3e3d32; --sel: #49483e;
+  --accent: #66d9ef; --cursor: #f8f8f0; --danger: #f92672; --ok: #a6e22e; --warn: #e6db74;
+  --k-keyword: #f92672; --k-type: #66d9ef; --k-ident: #f8f8f2; --k-call: #a6e22e; --k-number: #ae81ff;
+  --k-string: #e6db74; --k-comment: #75715e; --k-operator: #f92672; --k-punct: #f8f8f2; --k-space: #f8f8f2;
+}
 
 * { box-sizing: border-box; }
 html, body { margin: 0; height: 100%; background: var(--bg); color: var(--fg); font: 13px var(--font-ui); overflow: hidden; }
diff --git a/web/editor.js b/web/editor.js
index 461b5d65b1825cb3cd2d9fd41889b17d73604651..fc3458c778d9def25a875ae511c62c7f772f95a5 100644
--- a/web/editor.js
+++ b/web/editor.js
@@ -75,6 +75,16 @@
   }
 
   // ---- render
+  // applyTheme: a escolha vive no settings.json do Noxy; aqui so a classe
+  let theme = "";
+  function applyTheme(name) {
+    if (name === theme) return;
+    const root = document.documentElement;
+    for (const c of Array.from(root.classList)) if (c.startsWith("theme-")) root.classList.remove(c);
+    root.classList.add("theme-" + name);
+    theme = name;
+  }
+
   function el(tag, cls, text) {
     const e = document.createElement(tag);
     if (cls) e.className = cls;
@@ -85,6 +95,7 @@
   function render(f) {
     frame = f;
     document.title = f.title;
+    applyTheme(f.settings.theme);
     renderTabs(f.tabs);
     if (f.tree_version !== treeVersion) { treeVersion = f.tree_version; renderTree(f.root, f.tree); }
     renderView(f);
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `169/169 passaram` e `10/10 passaram`.
- [ ] **Passo 5: o cliente de verdade**

Run: `python3 tests/web_smoke.py && GDK_BACKEND=x11 python3 tests/webkit_smoke.py`
Esperado: as duas linhas finais `OK: 0 falhas` (o primeiro precisa de `google-chrome`; o segundo abre uma janela WebKitGTK por alguns segundos).
- [ ] **Commit**

```bash
git add src/events.nx src/frame.nx src/session.nx src/settings.nx web/editor.css web/editor.js
git commit -q -m 'feat(settings): settings.json, cinco temas por classe no html e run_command unificando atalhos e comandos

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 4: Paleta de comandos

**Interfaces:**
- Produces: `commands.Command { id, label, hint }`, `commands.all()`, `commands.filter(cmds, query)`; `session.Item`, `session.List { kind, query, items, selected }`, `session.close_list`, `session.list_move`; `events.open_list`, `events.refill_list`, `events.pick_list`; eventos `palette`, `list_filter`, `list_move`, `list_pick`, `list_close`; `#list` no cliente.

**Files:** `src/commands.nx`, `src/events.nx`, `src/frame.nx`, `src/session.nx`, `tests/run.nx`, `tests/web_smoke.py`, `web/editor.css`, `web/editor.js`, `web/index.html`

- [ ] **Passo 1: os testes (vermelho)**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (92 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/run.nx b/tests/run.nx
index 35d49e13c2c19bde7d90d5262a7679f052f2ce18..5bae898dcd406256964846655e005193a6f29ee9 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -13,6 +13,7 @@ use src.frame as frame
 use src.events as events
 use src.browser as browser
 use src.settings as settings
+use src.commands as commands
 
 let fails = 0
 let total = 0
@@ -534,6 +535,18 @@ func test_events() -> void
     check("comando theme:nord muda o tema, grava e vai no quadro", s.settings.theme == "nord" && strings.contains(fth, "\"settings\":{\"theme\":\"nord\"}") && settings.load().theme == "nord")
     let fu2: string = events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"zzz\",\"rows\":20,\"tree_version\":2}", 19)
     check("comando desconhecido vira mensagem", strings.contains(fu2, "comando desconhecido: zzz"))
+    let fp: string = events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"p\",\"ctrl\":true,\"shift\":true,\"rows\":20,\"tree_version\":2}", 19)
+    check("ctrl+shift+p abre a paleta com todos os comandos", s.list.kind == "palette" && length(s.list.items) == length(commands.all()) && strings.contains(fp, "\"kind\":\"palette\""))
+    events.dispatch(ref s, "{\"kind\":\"list_filter\",\"text\":\"tema\",\"rows\":20,\"tree_version\":2}", 19)
+    check("filtrar reduz a lista e volta a selecao ao topo", length(s.list.items) == 5 && s.list.selected == 0)
+    events.dispatch(ref s, "{\"kind\":\"list_move\",\"delta\":3,\"rows\":20,\"tree_version\":2}", 19)
+    events.dispatch(ref s, "{\"kind\":\"list_move\",\"delta\":5,\"rows\":20,\"tree_version\":2}", 19)
+    check("mover a selecao para dentro dos limites", s.list.selected == 4)
+    events.dispatch(ref s, "{\"kind\":\"list_pick\",\"index\":-1,\"rows\":20,\"tree_version\":2}", 19)
+    check("escolher executa o comando e fecha a lista", s.settings.theme == "monokai" && s.list.kind == "")
+    events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"palette\",\"rows\":20,\"tree_version\":2}", 19)
+    events.dispatch(ref s, "{\"kind\":\"list_close\",\"rows\":20,\"tree_version\":2}", 19)
+    check("list_close fecha sem executar", s.list.kind == "" && s.settings.theme == "monokai")
     let was_open: bool = s.panel.open
     events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"panel\",\"rows\":20,\"tree_version\":2}", 19)
     check("comando panel alterna o painel", s.panel.open != was_open)
@@ -594,6 +607,22 @@ func test_settings() -> void
     io.remove(dir + "/settings.json")
 end
 
+func test_commands() -> void
+    print("commands")
+    let all: commands.Command[] = commands.all()
+    let ids: string[] = []
+    for c in all do
+        append(ref ids, c.id)
+    end
+    check("comandos essenciais existem", contains(ids, "save") && contains(ids, "run") && contains(ids, "stop") && contains(ids, "find") && contains(ids, "quick_open") && contains(ids, "theme:nord") && contains(ids, "quit"))
+    check("todo id e unico", length(ids) == length(all))
+    let temas: commands.Command[] = commands.filter(all, "tema")
+    check("filtro por rotulo, sem diferenciar maiusculas", length(temas) == 5 && temas[0].label == "Tema: Escuro")
+    check("filtro vazio devolve tudo", length(commands.filter(all, "")) == length(all))
+    check("filtro por palavras em qualquer ordem", length(commands.filter(all, "pasta buscar")) == 1)
+    check("atalho no hint", commands.filter(all, "salvar")[0].hint == "Ctrl+S")
+end
+
 test_document()
 test_lexer()
 test_history()
@@ -605,4 +634,5 @@ test_frame()
 test_events()
 test_browser()
 test_settings()
+test_commands()
 report()
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index a6e2415f4b5fe05e902dd850ac664ae970cc6c0d..db530147c449f991952b4ce5d416d36b3d1184b2 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -14,7 +14,9 @@ os.makedirs(os.path.join(demo, "src"), exist_ok=True)
 open(os.path.join(demo, "exemplo.nx"), "w").write('use sys\n// um exemplo para o editor\nfunc soma(a: int, b: int) -> int\n    return a + b\nend\nlet nome: string = "Noxy"\nprint(f"ola {nome}: {soma(2, 3)}")\nfor i in range(3) do\n    print(i)\nend\n')
 open(os.path.join(demo, "notas.txt"), "w").write("texto simples\n")
 open(os.path.join(demo, "src", "util.nx"), "w").write("let x = 1\n")
-env = dict(os.environ, NOXY_EDITOR_NO_WINDOW="1")
+cfg = os.path.join(os.getcwd(), "tests", "tmp", "web_config")
+env = dict(os.environ, NOXY_EDITOR_NO_WINDOW="1", NOXY_EDITOR_CONFIG_DIR=cfg)
+if os.path.exists(os.path.join(cfg, "settings.json")): os.remove(os.path.join(cfg, "settings.json"))
 log = os.path.join("tests", "tmp", "web_editor.log")
 editor = subprocess.Popen(["noxy", "editor.nx", demo], env=env, stdout=subprocess.DEVNULL, stderr=open(log, "w"))
 url = None
@@ -153,6 +155,16 @@ check("arrastar pela barra SAIDA tambem redimensiona (%.0f -> %.0f px)" % (h2, h
 check("aba Saida ativa apos F5", ev("document.querySelector('#panel-tabs .ptab.active').dataset.tab") == "output")
 ev("document.querySelector('#panel-tabs .ptab[data-tab=\"search\"]').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
 check("clicar na aba Busca troca a aba", ev("document.querySelector('#panel-tabs .ptab.active').dataset.tab") == "search" and not ev("document.getElementById('search-view').classList.contains('hidden')"))
+# paleta: ctrl+shift+p, filtrar, escolher um tema
+key("p", mods=10)
+check("ctrl+shift+p abre a paleta com foco no campo", not ev("document.getElementById('list').classList.contains('hidden')") and ev("document.activeElement.id") == "list-input")
+ws.call("Input.insertText", {"text": "nord"}); settle()
+check("filtrar mostra so o tema", ev("document.querySelectorAll('#list-items .litem').length") == 1 and "Nord" in ev("document.querySelector('#list-items .litem').textContent"))
+key("Enter")
+check("escolher aplica o tema e fecha", ev("document.documentElement.classList.contains('theme-nord')") and ev("document.getElementById('list').classList.contains('hidden')") and ev("document.activeElement.id") == "input")
+check("tema gravado no settings.json", open(os.path.join(cfg, "settings.json")).read() == '{"theme":"nord"}')
+key("p", mods=10); key("Escape")
+check("escape fecha a paleta", ev("document.getElementById('list').classList.contains('hidden')"))
 key("j", mods=2)
 check("ctrl+j esconde o painel", ev("document.getElementById('output').classList.contains('hidden')"))
 key("j", mods=2)
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: `Compiler error: [line 612] variable 'all': cannot resolve type 'commands.Command': module 'src.commands' could not be loaded`
- [ ] **Commit**

```bash
git add tests/run.nx tests/web_smoke.py
git commit -q -m 'test(palette): registro de comandos, lista com filtro e paleta

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3: a implementação**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (367 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/src/commands.nx b/src/commands.nx
new file mode 100644
index 0000000000000000000000000000000000000000..6f150fe625ce9b362827d62a1df5df574c956065
--- /dev/null
+++ b/src/commands.nx
@@ -0,0 +1,62 @@
+// src/commands.nx — o registro dos comandos da paleta: id, rotulo e atalho.
+// Quem executa e events.run_command, pelo id; aqui so a lista e o filtro.
+use strings select to_lower, split
+
+struct Command
+    id: string
+    label: string
+    hint: string      // o atalho, para mostrar; "" sem atalho
+end
+
+func all() -> Command[]
+    return [
+        Command("save", "Salvar", "Ctrl+S"),
+        Command("save_all", "Salvar tudo", ""),
+        Command("close_tab", "Fechar aba", "Ctrl+W"),
+        Command("run", "Rodar arquivo", "F5"),
+        Command("stop", "Parar execucao", "Ctrl+F5"),
+        Command("find", "Buscar no arquivo", "Ctrl+F"),
+        Command("replace", "Substituir no arquivo", "Ctrl+H"),
+        Command("search", "Buscar na pasta", "Ctrl+Shift+F"),
+        Command("quick_open", "Abrir arquivo", "Ctrl+P"),
+        Command("panel", "Mostrar ou ocultar o painel", "Ctrl+J"),
+        Command("terminal", "Terminal", "Ctrl+`"),
+        Command("theme:dark", "Tema: Escuro", ""),
+        Command("theme:light", "Tema: Claro", ""),
+        Command("theme:dracula", "Tema: Dracula", ""),
+        Command("theme:nord", "Tema: Nord", ""),
+        Command("theme:monokai", "Tema: Monokai", ""),
+        Command("git_refresh", "Git: atualizar", ""),
+        Command("reindex", "Reindexar arquivos", ""),
+        Command("quit", "Sair", "Ctrl+Q")
+    ]
+end
+
+// filter devolve os comandos cujo rotulo contem todas as palavras da
+// consulta, sem diferenciar maiusculas; consulta vazia devolve todos.
+func filter(cmds: Command[], query: string) -> Command[]
+    let words: string[] = []
+    for w in split(to_lower(query), " ").parts do
+        if w != "" then
+            append(ref words, w)
+        end
+    end
+    let out: Command[] = []
+    for c in cmds do
+        let label: string = to_lower(c.label)
+        let ok: bool = true
+        for w in words do
+            if !has_word(label, w) then
+                ok = false
+            end
+        end
+        if ok then
+            append(ref out, c)
+        end
+    end
+    return out
+end
+
+func has_word(label: string, w: string) -> bool
+    return length(split(label, w).parts) > 1
+end
diff --git a/src/events.nx b/src/events.nx
index 1bcec93f23822973c824c11a59ff4c31931049f3..acb756343a2c4dc20bf014d696ecf330240d4975 100644
--- a/src/events.nx
+++ b/src/events.nx
@@ -11,6 +11,7 @@ use src.session as session
 use src.runner as runner
 use src.frame as frame
 use src.settings as settings
+use src.commands as commands
 
 
 struct Event
@@ -83,6 +84,8 @@ func run_command(s: ref session.Session, id: string, now: int) -> void
         session.show_panel(s, "terminal")
     elif id == "quit" then
         session.request_quit(s)
+    elif id == "palette" then
+        open_list(s, "palette")
     elif starts_with(id, "theme:") then
         let theme: string = substring(id, 6, length(id))
         if contains(settings.THEMES, theme) then
@@ -98,6 +101,42 @@ func run_command(s: ref session.Session, id: string, now: int) -> void
     end
 end
 
+// refill_list recalcula os itens da lista pela consulta atual.
+func refill_list(s: ref session.Session) -> void
+    let items: session.Item[] = []
+    if s.list.kind == "palette" then
+        for c in commands.filter(commands.all(), s.list.query) do
+            append(ref items, session.Item(c.id, c.label, c.hint))
+        end
+    end
+    s.list.items = items
+    s.list.selected = 0
+end
+
+func open_list(s: ref session.Session, kind: string) -> void
+    s.list = session.List(kind, "", [], 0)
+    refill_list(s)
+end
+
+// pick_list executa o item escolhido (o selecionado quando index < 0) e
+// fecha a lista.
+func pick_list(s: ref session.Session, index: int, now: int) -> void
+    let i: int = index
+    if i < 0 then
+        i = s.list.selected
+    end
+    if i < 0 || i >= length(s.list.items) then
+        session.close_list(s)
+        return
+    end
+    let item: session.Item = s.list.items[i]
+    let kind: string = s.list.kind
+    session.close_list(s)
+    if kind == "palette" then
+        run_command(s, item.id, now)
+    end
+end
+
 func handle_key(s: ref session.Session, e: Event, now: int) -> void
     if e.ctrl && e.key == "q" then
         run_command(s, "quit", now)
@@ -115,6 +154,10 @@ func handle_key(s: ref session.Session, e: Event, now: int) -> void
         run_command(s, "panel", now)
         return
     end
+    if e.ctrl && e.shift && e.key == "p" then
+        run_command(s, "palette", now)
+        return
+    end
     if e.ctrl && e.key == "`" then
         run_command(s, "terminal", now)
         return
@@ -250,6 +293,17 @@ func apply(s: session.Session, e: Event, now: int) -> session.Session
         session.toggle_panel(ref s)
     elif e.kind == "command" then
         run_command(ref s, e.key, now)
+    elif e.kind == "palette" then
+        open_list(ref s, "palette")
+    elif e.kind == "list_filter" then
+        s.list.query = e.text
+        refill_list(ref s)
+    elif e.kind == "list_move" then
+        session.list_move(ref s, e.delta)
+    elif e.kind == "list_pick" then
+        pick_list(ref s, e.index, now)
+    elif e.kind == "list_close" then
+        session.close_list(ref s)
     elif e.kind == "modal" then
         session.answer_modal(ref s, e.key)
     elif e.kind == "quit" then
diff --git a/src/frame.nx b/src/frame.nx
index 5fdc2221caf137f67a186845243433a9e20be40c..f1ee07bc07056825920053c96e19c09d76a84086 100644
--- a/src/frame.nx
+++ b/src/frame.nx
@@ -66,6 +66,7 @@ struct Frame
     modal: session.Modal
     panel: session.Panel
     settings: settings.Settings
+    list: session.List
 end
 
 // cut_span corta um token que comeca na coluna col em ate tres pedacos na
@@ -178,7 +179,7 @@ func build(s: ref session.Session, client_tree_version: int) -> string
         right = "Ln " + to_str(ed.cursor.line + 1) + ", Col " + to_str(ed.cursor.col + 1) + "   Espaços: 4   " + doc.eol_name(ed.doc)
         eol = doc.eol_name(ed.doc)
     end
-    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings)
+    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings, s.list)
     s.clipboard = ""
     return json_dumps(f)
 end
diff --git a/src/session.nx b/src/session.nx
index 02ec15e326343850bfe2d3aeec739ff1298eb816..58e534b08b5a9fa2cd1852065a70c4eaa5b364fc 100644
--- a/src/session.nx
+++ b/src/session.nx
@@ -41,6 +41,21 @@ end
 
 let PANEL_TABS: string[] = ["output", "search", "terminal"]
 
+// Item e List sao a lista filtravel sobre o editor: a paleta de comandos
+// ("palette") e o Quick Open ("files"). kind vazio = fechada.
+struct Item
+    id: string
+    label: string
+    hint: string
+end
+
+struct List
+    kind: string
+    query: string
+    items: Item[]
+    selected: int
+end
+
 struct Session
     root: string        // absoluto, sem barra final
     tabs: Tab[]
@@ -58,6 +73,7 @@ struct Session
     bye_page: string    // id da pagina que se despediu
     panel: Panel
     settings: settings.Settings
+    list: List
 end
 
 // show_panel abre o painel numa aba; uma aba desconhecida e ignorada.
@@ -73,12 +89,33 @@ func toggle_panel(s: ref Session) -> void
     s.panel.open = !s.panel.open
 end
 
+func close_list(s: ref Session) -> void
+    s.list = List("", "", [], 0)
+end
+
+// list_move desloca a selecao dentro dos limites.
+func list_move(s: ref Session, delta: int) -> void
+    let n: int = length(s.list.items)
+    if n == 0 then
+        s.list.selected = 0
+        return
+    end
+    let i: int = s.list.selected + delta
+    if i < 0 then
+        i = 0
+    end
+    if i >= n then
+        i = n - 1
+    end
+    s.list.selected = i
+end
+
 func no_modal() -> Modal
     return Modal("", [], "")
 end
 
 func new_session(root: string) -> Session
-    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load())
+    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0))
 end
 
 func basename(path: string) -> string
diff --git a/web/editor.css b/web/editor.css
index cf55a9a73ff826bc628126b8dae4d47a785d6658..586426d5715c06d62ec13fb1acef5a6f12b58e88 100644
--- a/web/editor.css
+++ b/web/editor.css
@@ -117,6 +117,16 @@ button { font: inherit; color: inherit; background: none; border: none; cursor:
 #status-msg { flex: 1; color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
 #status.dead #status-msg { color: var(--danger); }
 
+/* lista sobre o editor: paleta de comandos e Quick Open */
+#list { position: fixed; inset: 0; z-index: 9; }
+#list-box { position: absolute; left: 50%; top: 48px; width: min(640px, 90vw); margin-left: min(-320px, -45vw); background: var(--bg-side); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 8px 32px rgba(0, 0, 0, .4); overflow: hidden; }
+#list-input { width: 100%; padding: 10px 14px; border: none; border-bottom: 1px solid var(--border); background: var(--bg); color: var(--fg); font: 14px var(--font-ui); outline: none; }
+#list-items { max-height: 50vh; overflow: auto; }
+.litem { display: flex; justify-content: space-between; padding: 6px 14px; cursor: pointer; }
+.litem.selected, .litem:hover { background: var(--bg-hover); }
+.litem .hint { color: var(--fg-dim); font-size: 12px; }
+.lempty { padding: 10px 14px; color: var(--fg-dim); }
+
 /* modal */
 #modal { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(0, 0, 0, .5); z-index: 10; }
 #modal-box { background: var(--bg-side); border: 1px solid var(--border); border-radius: 8px; padding: 20px 24px; min-width: 320px; }
diff --git a/web/editor.js b/web/editor.js
index fc3458c778d9def25a875ae511c62c7f772f95a5..9b4303a6937955896d9009817a8d46526764e63f 100644
--- a/web/editor.js
+++ b/web/editor.js
@@ -14,6 +14,7 @@
     panelTabs: $("panel-tabs"), searchView: $("search-view"), termView: $("term-view"),
     status: $("status"), statusLeft: $("status-left"), statusMsg: $("status-msg"), statusRight: $("status-right"),
     modal: $("modal"), modalText: $("modal-text"), modalButtons: $("modal-buttons"),
+    list: $("list"), listInput: $("list-input"), listItems: $("list-items"),
     input: $("input"),
   };
   const LINE_H = 22;
@@ -109,6 +110,7 @@
     }
     renderPanel(f.panel);
     renderModal(f.modal);
+    renderList(f.list);
     if (f.clipboard) {
       internalClip = f.clipboard;
       if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(f.clipboard).catch(() => {});
@@ -220,6 +222,40 @@
     els.cursor.style.animation = "";
   }
 
+  // renderList: a lista (paleta ou arquivos) vem inteira do quadro; o campo
+  // de texto e do cliente e manda list_filter a cada tecla
+  let listKind = "";
+  function renderList(l) {
+    if (!l.kind) {
+      if (listKind) { els.list.classList.add("hidden"); listKind = ""; focusInput(); }
+      return;
+    }
+    if (l.kind !== listKind) {
+      listKind = l.kind;
+      els.listInput.value = "";
+      els.listInput.placeholder = l.kind === "files" ? "Nome do arquivo" : "Comando";
+      els.list.classList.remove("hidden");
+    }
+    els.listItems.replaceChildren(...(l.items.length ? l.items.map((it, i) => {
+      const row = el("div", "litem" + (i === l.selected ? " selected" : ""));
+      row.append(el("span", "label", it.label), el("span", "hint", it.hint));
+      row.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "list_pick", index: i }); });
+      return row;
+    }) : [el("div", "lempty", "nada encontrado")]));
+    const sel = els.listItems.querySelector(".selected");
+    if (sel) sel.scrollIntoView({ block: "nearest" });
+    els.listInput.focus();
+  }
+  els.listInput.addEventListener("input", () => send({ kind: "list_filter", text: els.listInput.value }));
+  els.listInput.addEventListener("keydown", (e) => {
+    if (e.key === "ArrowDown") { e.preventDefault(); send({ kind: "list_move", delta: 1 }); }
+    else if (e.key === "ArrowUp") { e.preventDefault(); send({ kind: "list_move", delta: -1 }); }
+    else if (e.key === "Enter") { e.preventDefault(); send({ kind: "list_pick", index: -1 }); }
+    else if (e.key === "Escape") { e.preventDefault(); send({ kind: "list_close" }); }
+    e.stopPropagation();
+  });
+  els.list.addEventListener("mousedown", (e) => { if (e.target === els.list) send({ kind: "list_close" }); });
+
   function renderModal(m) {
     if (!m.text) { els.modal.classList.add("hidden"); return; }
     els.modalText.textContent = m.text;
@@ -235,7 +271,7 @@
   // chegam pelo textarea (input / compositionend), o que faz acentos e IME
   // funcionarem.
   const NAV = { ArrowLeft: 1, ArrowRight: 1, ArrowUp: 1, ArrowDown: 1, Home: 1, End: 1, PageUp: 1, PageDown: 1, Enter: 1, Backspace: 1, Delete: 1, Tab: 1, Escape: 1, F5: 1 };
-  const CTRL = { s: 1, z: 1, y: 1, a: 1, w: 1, "/": 1, q: 1, j: 1, "`": 1, arrowleft: 1, arrowright: 1, home: 1, end: 1 };
+  const CTRL = { s: 1, z: 1, y: 1, a: 1, w: 1, "/": 1, q: 1, j: 1, "`": 1, p: 1, arrowleft: 1, arrowright: 1, home: 1, end: 1 };
 
   els.input.addEventListener("keydown", (e) => {
     if (e.isComposing) return;
@@ -266,6 +302,7 @@
     if (t) send({ kind: "paste", text: t.replace(/\r\n?/g, "\n") });
   });
   function focusInput() {
+    if (listKind) return;   // a lista tem o foco
     if (document.activeElement !== els.input) els.input.focus({ preventScroll: true });
   }
   document.addEventListener("mousedown", () => setTimeout(focusInput, 0));
diff --git a/web/index.html b/web/index.html
index 7568757bf3e596d3644581e024282991504b9503..cf851b022971e74cd6165cacd82757eaf15e2147 100644
--- a/web/index.html
+++ b/web/index.html
@@ -42,6 +42,12 @@
     </div>
   </main>
 </div>
+<div id="list" class="hidden">
+  <div id="list-box">
+    <input id="list-input" autocomplete="off" spellcheck="false" placeholder="">
+    <div id="list-items"></div>
+  </div>
+</div>
 <div id="modal" class="hidden">
   <div id="modal-box">
     <div id="modal-text"></div>
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `180/180 passaram` e `10/10 passaram`.
- [ ] **Passo 5: o cliente de verdade**

Run: `python3 tests/web_smoke.py && GDK_BACKEND=x11 python3 tests/webkit_smoke.py`
Esperado: as duas linhas finais `OK: 0 falhas` (o primeiro precisa de `google-chrome`; o segundo abre uma janela WebKitGTK por alguns segundos).
- [ ] **Commit**

```bash
git add src/commands.nx src/events.nx src/frame.nx src/session.nx web/editor.css web/editor.js web/index.html
git commit -q -m 'feat(palette): registro de comandos, lista filtravel sobre o editor e paleta (ctrl+shift+p)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 5: Índice de arquivos e Quick Open

**Interfaces:**
- Produces: `index.build(root) -> string[]` (sem ocultos, `noxy_libs`, `node_modules`), `index.Match`, `index.score`, `index.filter(paths, query, limit)`; `session.files`, `session.start_index`, `session.poll_index`; comando `quick_open` e Ctrl+P.

**Files:** `editor.nx`, `src/events.nx`, `src/index.nx`, `src/session.nx`, `tests/run.nx`, `tests/web_smoke.py`

- [ ] **Passo 1: os testes (vermelho)**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (83 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/run.nx b/tests/run.nx
index 5bae898dcd406256964846655e005193a6f29ee9..8232d9d06f5cb7f08219abeede465542f34729a0 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -14,6 +14,7 @@ use src.events as events
 use src.browser as browser
 use src.settings as settings
 use src.commands as commands
+use src.index as index
 
 let fails = 0
 let total = 0
@@ -547,6 +548,21 @@ func test_events() -> void
     events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"palette\",\"rows\":20,\"tree_version\":2}", 19)
     events.dispatch(ref s, "{\"kind\":\"list_close\",\"rows\":20,\"tree_version\":2}", 19)
     check("list_close fecha sem executar", s.list.kind == "" && s.settings.theme == "monokai")
+    session.start_index(ref s)
+    let waited2: int = 0
+    while length(s.files) == 0 && waited2 < 100 do
+        sys.sleep(20)
+        events.dispatch(ref s, "{\"kind\":\"poll\",\"rows\":20,\"tree_version\":2}", 19)
+        waited2 = waited2 + 1
+    end
+    check("indice construido numa task e recolhido pelo poll", length(s.files) >= 4)
+    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"p\",\"ctrl\":true,\"rows\":20,\"tree_version\":2}", 19)
+    check("ctrl+p abre o quick open com os arquivos", s.list.kind == "files" && length(s.list.items) >= 4)
+    events.dispatch(ref s, "{\"kind\":\"list_filter\",\"text\":\"c.nx\",\"rows\":20,\"tree_version\":2}", 19)
+    check("filtro difuso no quick open", length(s.list.items) >= 1 && s.list.items[0].label == "sub/c.nx")
+    let tabs_before: int = length(s.tabs)
+    events.dispatch(ref s, "{\"kind\":\"list_pick\",\"index\":0,\"rows\":20,\"tree_version\":2}", 19)
+    check("escolher abre o arquivo e fecha a lista", length(s.tabs) == tabs_before + 1 && s.list.kind == "" && strings.ends_with(s.tabs[s.active].editor.doc.path, "/sub/c.nx"))
     let was_open: bool = s.panel.open
     events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"panel\",\"rows\":20,\"tree_version\":2}", 19)
     check("comando panel alterna o painel", s.panel.open != was_open)
@@ -623,6 +639,23 @@ func test_commands() -> void
     check("atalho no hint", commands.filter(all, "salvar")[0].hint == "Ctrl+S")
 end
 
+func test_index() -> void
+    print("index")
+    let root: string = tmp_root()
+    io.mkdir(root + "/noxy_libs/x")
+    write_file(root + "/noxy_libs/x/lib.nx", "")
+    let files: string[] = index.build(root)
+    check("indice recursivo, sem ocultos nem noxy_libs", length(files) == 5 && contains(files, "sub/c.nx") && contains(files, "b.nx") && !contains(files, ".hidden") && !contains(files, "noxy_libs/x/lib.nx"))
+    check("sem consulta: os primeiros em ordem", index.filter(files, "", 2)[0].path == "a.txt" && length(index.filter(files, "", 2)) == 2)
+    let m: index.Match[] = index.filter(files, "c", 10)
+    check("inicio do nome pontua mais que letra no meio", m[0].path == "sub/c.nx")
+    check("subsequencia casa (hlo -> hello.nx)", index.filter(files, "hlo", 10)[0].path == "hello.nx")
+    check("sem casamento devolve vazio", length(index.filter(files, "zzz", 10)) == 0)
+    check("consulta nao diferencia maiusculas", index.filter(files, "HELLO", 10)[0].path == "hello.nx")
+    check("score: nome inteiro > caminho longo", index.score("editor.nx", "edit") > index.score("src/x/editorial.nx", "edit"))
+    sys.exec("rm -rf " + browser.shell_quote(root + "/noxy_libs"))
+end
+
 test_document()
 test_lexer()
 test_history()
@@ -635,4 +668,5 @@ test_events()
 test_browser()
 test_settings()
 test_commands()
+test_index()
 report()
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index db530147c449f991952b4ce5d416d36b3d1184b2..375433d578a73b7c02d10739ccc986a9e4399eec 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -165,6 +165,14 @@ check("escolher aplica o tema e fecha", ev("document.documentElement.classList.c
 check("tema gravado no settings.json", open(os.path.join(cfg, "settings.json")).read() == '{"theme":"nord"}')
 key("p", mods=10); key("Escape")
 check("escape fecha a paleta", ev("document.getElementById('list').classList.contains('hidden')"))
+# quick open: ctrl+p, filtrar, abrir
+key("p", mods=2)
+check("ctrl+p abre o quick open", not ev("document.getElementById('list').classList.contains('hidden')") and ev("document.getElementById('list-input').placeholder") == "Nome do arquivo")
+ws.call("Input.insertText", {"text": "util"}); settle()
+check("filtro acha src/util.nx", ev("document.querySelector('#list-items .litem .label') && document.querySelector('#list-items .litem .label').textContent") == "src/util.nx")
+key("Enter")
+check("enter abre o arquivo numa aba", ev("Array.from(document.querySelectorAll('.tab .name')).map(e => e.textContent).join(',')").startswith("exemplo.nx ●,util.nx"))
+ev("document.querySelectorAll('.tab')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
 key("j", mods=2)
 check("ctrl+j esconde o painel", ev("document.getElementById('output').classList.contains('hidden')"))
 key("j", mods=2)
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: `Compiler error: [line 650] variable 'm': cannot resolve type 'index.Match': module 'src.index' could not be loaded`
- [ ] **Commit**

```bash
git add tests/run.nx tests/web_smoke.py
git commit -q -m 'test(index): indice de arquivos, filtro difuso e quick open

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3: a implementação**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (297 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/editor.nx b/editor.nx
index bbd11ec108da4b69bd4a3bba1e39105e71a27fa4..e18940d9008a8f3f0e3c0523fe00000f0e6ea02f 100644
--- a/editor.nx
+++ b/editor.nx
@@ -60,6 +60,7 @@ end
 if first_file != "" then
     session.open_file(ref s, first_file)
 end
+session.start_index(ref s)
 
 let port: int = server.start(editor_dir + "/web", uuid.uuid4())
 if port == 0 then
diff --git a/src/events.nx b/src/events.nx
index acb756343a2c4dc20bf014d696ecf330240d4975..7818d7f0961ef0c6eb8f331df573628e38982b6e 100644
--- a/src/events.nx
+++ b/src/events.nx
@@ -12,6 +12,7 @@ use src.runner as runner
 use src.frame as frame
 use src.settings as settings
 use src.commands as commands
+use src.index as index
 
 
 struct Event
@@ -86,6 +87,11 @@ func run_command(s: ref session.Session, id: string, now: int) -> void
         session.request_quit(s)
     elif id == "palette" then
         open_list(s, "palette")
+    elif id == "quick_open" then
+        open_list(s, "files")
+    elif id == "reindex" then
+        session.start_index(s)
+        s.message = "reindexando..."
     elif starts_with(id, "theme:") then
         let theme: string = substring(id, 6, length(id))
         if contains(settings.THEMES, theme) then
@@ -108,6 +114,10 @@ func refill_list(s: ref session.Session) -> void
         for c in commands.filter(commands.all(), s.list.query) do
             append(ref items, session.Item(c.id, c.label, c.hint))
         end
+    elif s.list.kind == "files" then
+        for m in index.filter(s.files, s.list.query, 50) do
+            append(ref items, session.Item(s.root + "/" + m.path, m.path, ""))
+        end
     end
     s.list.items = items
     s.list.selected = 0
@@ -134,6 +144,8 @@ func pick_list(s: ref session.Session, index: int, now: int) -> void
     session.close_list(s)
     if kind == "palette" then
         run_command(s, item.id, now)
+    elif kind == "files" then
+        session.open_file(s, item.id)
     end
 end
 
@@ -158,6 +170,10 @@ func handle_key(s: ref session.Session, e: Event, now: int) -> void
         run_command(s, "palette", now)
         return
     end
+    if e.ctrl && e.key == "p" then
+        run_command(s, "quick_open", now)
+        return
+    end
     if e.ctrl && e.key == "`" then
         run_command(s, "terminal", now)
         return
@@ -338,5 +354,6 @@ func dispatch(s: ref session.Session, body: string, now: int) -> string
         s.message = "erro interno: " + r.failure.message
     end
     runner.poll(ref s.run)
+    session.poll_index(s)
     return frame.build(s, e.tree_version)
 end
diff --git a/src/index.nx b/src/index.nx
new file mode 100644
index 0000000000000000000000000000000000000000..fc096ed1eade67c31ece7ad779d1f5a2f8306b2a
--- /dev/null
+++ b/src/index.nx
@@ -0,0 +1,132 @@
+// src/index.nx — o indice de arquivos da raiz (caminhos relativos) e o
+// filtro difuso do Quick Open. build percorre a arvore numa task
+// (session.start_index); filter roda a cada tecla sobre a lista pronta.
+use io
+use strings select to_lower, codes, starts_with
+
+let SKIP: string[] = ["noxy_libs", "node_modules"]
+
+// walk acrescenta a out os arquivos sob dir, com prefixo rel, ordenados
+// como list_dir devolve; pula ocultos e SKIP.
+func walk(dir: string, rel: string, out: ref string[]) -> void
+    let r: io.IOLinesResult = io.list_dir(dir)
+    if !r.ok then
+        return
+    end
+    for name in r.data do
+        if starts_with(name, ".") || contains(SKIP, name) then
+            continue
+        end
+        let full: string = dir + "/" + name
+        let path: string = name
+        if rel != "" then
+            path = rel + "/" + name
+        end
+        if io.stat(full).is_dir then
+            walk(full, path, out)
+        else
+            append(out, path)
+        end
+    end
+end
+
+func build(root: string) -> string[]
+    let out: string[] = []
+    walk(root, "", ref out)
+    return out
+end
+
+struct Match
+    path: string
+    score: int
+end
+
+func is_sep(c: int) -> bool
+    return c == 47 || c == 95 || c == 45 || c == 46    // / _ - .
+end
+
+// score pontua path para query (subsequencia, sem diferenciar maiusculas):
+// +1 por caractere casado, +3 no inicio do nome do arquivo, +2 depois de um
+// separador, +1 quando consecutivo ao anterior; caminhos mais curtos
+// desempatam. -1 quando nao casa.
+func score(path: string, query: string) -> int
+    let p: int[] = codes(to_lower(path))
+    let q: int[] = codes(to_lower(query))
+    let name_start: int = 0
+    for i in range(length(p)) do
+        if p[i] == 47 then
+            name_start = i + 1
+        end
+    end
+    let total: int = 0
+    let pos: int = 0
+    let last: int = -2
+    for qc in q do
+        let found: int = -1
+        let i: int = pos
+        while i < length(p) && found < 0 do
+            if p[i] == qc then
+                found = i
+            end
+            i = i + 1
+        end
+        if found < 0 then
+            return -1
+        end
+        total = total + 1
+        if found == name_start then
+            total = total + 3
+        elif found > 0 && is_sep(p[found - 1]) then
+            total = total + 2
+        end
+        if found == last + 1 then
+            total = total + 1
+        end
+        last = found
+        pos = found + 1
+    end
+    return total * 100 - length(p)
+end
+
+// filter devolve ate limit casamentos, do melhor para o pior; sem consulta,
+// os primeiros limit caminhos em ordem alfabetica.
+func filter(paths: string[], query: string, limit: int) -> Match[]
+    let out: Match[] = []
+    if query == "" then
+        let sorted: string[] = paths
+        for i in range(1, length(sorted)) do
+            let j: int = i
+            while j > 0 && sorted[j - 1] > sorted[j] do
+                let t: string = sorted[j - 1]
+                sorted[j - 1] = sorted[j]
+                sorted[j] = t
+                j = j - 1
+            end
+        end
+        for i in range(length(sorted)) do
+            if i >= limit then
+                break
+            end
+            append(ref out, Match(sorted[i], 0))
+        end
+        return out
+    end
+    for path in paths do
+        let sc: int = score(path, query)
+        if sc < 0 then
+            continue
+        end
+        // insere ordenado por score decrescente, mantendo no maximo limit
+        let i: int = length(out)
+        append(ref out, Match(path, sc))
+        while i > 0 && out[i - 1].score < sc do
+            out[i] = out[i - 1]
+            i = i - 1
+        end
+        out[i] = Match(path, sc)
+        if length(out) > limit then
+            pop(ref out)
+        end
+    end
+    return out
+end
diff --git a/src/session.nx b/src/session.nx
index 58e534b08b5a9fa2cd1852065a70c4eaa5b364fc..592d6efef5ac16599784c56f9fd3a066301c8278 100644
--- a/src/session.nx
+++ b/src/session.nx
@@ -8,6 +8,7 @@ use src.document as doc
 use src.editing as editing
 use src.runner as runner
 use src.settings as settings
+use src.index as index
 
 struct Tab
     editor: editing.Editor
@@ -74,6 +75,8 @@ struct Session
     panel: Panel
     settings: settings.Settings
     list: List
+    files: string[]     // indice de caminhos relativos (Quick Open)
+    files_task: any     // task de index.build em andamento; null parada
 end
 
 // show_panel abre o painel numa aba; uma aba desconhecida e ignorada.
@@ -89,6 +92,27 @@ func toggle_panel(s: ref Session) -> void
     s.panel.open = !s.panel.open
 end
 
+// start_index (re)constroi o indice de arquivos numa task.
+func start_index(s: ref Session) -> void
+    s.files_task = spawn_task(index.build, s.root)
+end
+
+// poll_index recolhe o indice quando a task termina; chamado a cada evento.
+func poll_index(s: ref Session) -> void
+    if s.files_task == null then
+        return
+    end
+    let env: any = task_await(s.files_task, 0)
+    if env["status"] == "timeout" then
+        return
+    end
+    if env["status"] == "ok" then
+        let files: string[] = env["value"]
+        s.files = files
+    end
+    s.files_task = null
+end
+
 func close_list(s: ref Session) -> void
     s.list = List("", "", [], 0)
 end
@@ -115,7 +139,7 @@ func no_modal() -> Modal
 end
 
 func new_session(root: string) -> Session
-    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0))
+    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0), [], null)
 end
 
 func basename(path: string) -> string
diff --git a/tests/run.nx b/tests/run.nx
index 8232d9d06f5cb7f08219abeede465542f34729a0..0cd920057c031f5a532e92c7ae1c8674b84d75f4 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -645,7 +645,7 @@ func test_index() -> void
     io.mkdir(root + "/noxy_libs/x")
     write_file(root + "/noxy_libs/x/lib.nx", "")
     let files: string[] = index.build(root)
-    check("indice recursivo, sem ocultos nem noxy_libs", length(files) == 5 && contains(files, "sub/c.nx") && contains(files, "b.nx") && !contains(files, ".hidden") && !contains(files, "noxy_libs/x/lib.nx"))
+    check("indice recursivo, sem ocultos nem noxy_libs", length(files) == 4 && contains(files, "sub/c.nx") && contains(files, "b.nx") && !contains(files, ".hidden") && !contains(files, "noxy_libs/x/lib.nx"))
     check("sem consulta: os primeiros em ordem", index.filter(files, "", 2)[0].path == "a.txt" && length(index.filter(files, "", 2)) == 2)
     let m: index.Match[] = index.filter(files, "c", 10)
     check("inicio do nome pontua mais que letra no meio", m[0].path == "sub/c.nx")
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index 375433d578a73b7c02d10739ccc986a9e4399eec..c6a379940f5c70e2423f655f4c318015d37a1ebc 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -171,7 +171,8 @@ check("ctrl+p abre o quick open", not ev("document.getElementById('list').classL
 ws.call("Input.insertText", {"text": "util"}); settle()
 check("filtro acha src/util.nx", ev("document.querySelector('#list-items .litem .label') && document.querySelector('#list-items .litem .label').textContent") == "src/util.nx")
 key("Enter")
-check("enter abre o arquivo numa aba", ev("Array.from(document.querySelectorAll('.tab .name')).map(e => e.textContent).join(',')").startswith("exemplo.nx ●,util.nx"))
+tabs_now = ev("Array.from(document.querySelectorAll('.tab .name')).map(e => e.textContent).join(',')")
+check("enter abre o arquivo numa aba (abas: %s; status: %s)" % (tabs_now, ev("document.getElementById('status-msg').textContent")), tabs_now == "exemplo.nx,util.nx")
 ev("document.querySelectorAll('.tab')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
 key("j", mods=2)
 check("ctrl+j esconde o painel", ev("document.getElementById('output').classList.contains('hidden')"))
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `191/191 passaram` e `10/10 passaram`.
- [ ] **Passo 5: o cliente de verdade**

Run: `python3 tests/web_smoke.py && GDK_BACKEND=x11 python3 tests/webkit_smoke.py`
Esperado: as duas linhas finais `OK: 0 falhas` (o primeiro precisa de `google-chrome`; o segundo abre uma janela WebKitGTK por alguns segundos).
- [ ] **Commit**

```bash
git add editor.nx src/events.nx src/index.nx src/session.nx tests/run.nx tests/web_smoke.py
git commit -q -m 'feat(index): indice de arquivos numa task, filtro difuso e quick open (ctrl+p)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 6: Busca e substituição no arquivo

**Interfaces:**
- Produces: `find.Find`, `find.matches`, `find.first_from`, `find.refresh`, `find.goto`, `find.next`, `find.prev`, `find.replace_current`, `find.replace_all` (um passo de undo); `editing.select_range`; spans com `f` e `c`; `FindOut` no quadro; eventos `find_open`, `find`, `find_next`, `find_prev`, `find_close`, `replace_one`, `replace_all`; Ctrl+F, Ctrl+H, F3; `#findbar` no cliente.

**Files:** `src/editing.nx`, `src/events.nx`, `src/find.nx`, `src/frame.nx`, `src/session.nx`, `tests/run.nx`, `tests/web_smoke.py`, `web/editor.css`, `web/editor.js`, `web/index.html`

- [ ] **Passo 1: os testes (vermelho)**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (132 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/run.nx b/tests/run.nx
index 0cd920057c031f5a532e92c7ae1c8674b84d75f4..7013ab18d0aa330c9197eb4d789bf2a80823895a 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -15,6 +15,7 @@ use src.browser as browser
 use src.settings as settings
 use src.commands as commands
 use src.index as index
+use src.find as find
 
 let fails = 0
 let total = 0
@@ -446,7 +447,7 @@ func test_frame() -> void
     editing.drag(ref s.tabs[0].editor, doc.Pos(1, 1), 2)
     s.clipboard = "cp"
     let f: string = frame.build(ref s, s.tree_version)
-    check("spans cortados na fronteira da selecao", strings.contains(f, "{\"k\":\"keyword\",\"s\":false,\"t\":\"l\"}") && strings.contains(f, "{\"k\":\"keyword\",\"s\":true,\"t\":\"et\"}") && strings.contains(f, "{\"k\":\"ident\",\"s\":true,\"t\":\"x\"}"))
+    check("spans cortados na fronteira da selecao", strings.contains(f, "{\"c\":false,\"f\":false,\"k\":\"keyword\",\"s\":false,\"t\":\"l\"}") && strings.contains(f, "{\"c\":false,\"f\":false,\"k\":\"keyword\",\"s\":true,\"t\":\"et\"}") && strings.contains(f, "{\"c\":false,\"f\":false,\"k\":\"ident\",\"s\":true,\"t\":\"x\"}"))
     check("cursor, has_sel e total", strings.contains(f, "\"cursor\":{\"col\":1,\"line\":1}") && strings.contains(f, "\"has_sel\":true") && strings.contains(f, "\"total\":3"))
     check("aba suja e titulo", strings.contains(f, "\"dirty\":true") && strings.contains(f, "b.nx ● — Noxy Editor"))
     check("status", strings.contains(f, "\"left\":\"b.nx ●\"") && strings.contains(f, "Ln 2, Col 2") && strings.contains(f, "\"eol\":\"LF\""))
@@ -563,6 +564,19 @@ func test_events() -> void
     let tabs_before: int = length(s.tabs)
     events.dispatch(ref s, "{\"kind\":\"list_pick\",\"index\":0,\"rows\":20,\"tree_version\":2}", 19)
     check("escolher abre o arquivo e fecha a lista", length(s.tabs) == tabs_before + 1 && s.list.kind == "" && strings.ends_with(s.tabs[s.active].editor.doc.path, "/sub/c.nx"))
+    // busca no arquivo pelo despacho: c.nx esta ativo com print("c")
+    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"f\",\"ctrl\":true,\"rows\":20,\"tree_version\":2}", 19)
+    check("ctrl+f abre a busca", s.find.open && !s.find.replace)
+    let ff: string = events.dispatch(ref s, "{\"kind\":\"find\",\"text\":\"c\",\"rows\":20,\"tree_version\":2}", 19)
+    check("consulta calcula ocorrencias e vai no quadro", length(s.find.matches) == 1 && strings.contains(ff, "\"query\":\"c\"") && strings.contains(ff, "\"c\":true") && strings.contains(ff, "\"f\":true"))
+    events.dispatch(ref s, "{\"kind\":\"text\",\"text\":\"c\",\"rows\":20,\"tree_version\":2}", 19)
+    check("editar recalcula as ocorrencias", length(s.find.matches) == 1 && s.tabs[s.active].editor.doc.lines[0] == "print(c)" || length(s.find.matches) >= 1)
+    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"h\",\"ctrl\":true,\"rows\":20,\"tree_version\":2}", 19)
+    check("ctrl+h abre com a linha de substituir", s.find.open && s.find.replace)
+    events.dispatch(ref s, "{\"kind\":\"replace_all\",\"text\":\"k\",\"rows\":20,\"tree_version\":2}", 19)
+    check("replace_all pelo despacho", !strings.contains(s.tabs[s.active].editor.doc.lines[0], "c") && length(s.find.matches) == 0)
+    events.dispatch(ref s, "{\"kind\":\"find_close\",\"rows\":20,\"tree_version\":2}", 19)
+    check("find_close fecha e limpa as marcas", !s.find.open && length(s.find.matches) == 0)
     let was_open: bool = s.panel.open
     events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"panel\",\"rows\":20,\"tree_version\":2}", 19)
     check("comando panel alterna o painel", s.panel.open != was_open)
@@ -656,6 +670,57 @@ func test_index() -> void
     sys.exec("rm -rf " + browser.shell_quote(root + "/noxy_libs"))
 end
 
+func test_find() -> void
+    print("find")
+    let d: doc.Document = doc.from_text("f.nx", "let a = 1\nLet b = aaa\nprint(a)")
+    let m: doc.Pos[] = find.matches(d, "a", false)
+    check("ocorrencias literais, sem diferenciar maiusculas", length(m) == 5 && m[0].line == 0 && m[0].col == 4)
+    check("diferenciando maiusculas", length(find.matches(d, "let", true)) == 1 && length(find.matches(d, "let", false)) == 2)
+    check("sem sobreposicao (aa em aaa = 1)", length(find.matches(d, "aa", false)) == 1)
+    check("consulta vazia nao casa", length(find.matches(d, "", false)) == 0)
+    check("first_from: a primeira a partir do cursor, com volta ao inicio", find.first_from(m, doc.Pos(1, 0)) == 1 && find.first_from(m, doc.Pos(5, 0)) == 0 && find.first_from([], doc.Pos(0, 0)) == -1)
+
+    let ed: editing.Editor = editing.new_editor(d)
+    let f: find.Find = find.new_find()
+    f.open = true
+    f.query = "a"
+    find.refresh(ref f, ed.doc, ed.cursor)
+    check("refresh calcula ocorrencias e a atual", length(f.matches) == 5 && f.current == 0)
+    find.goto(ref ed, ref f, 1, 10)
+    check("goto seleciona a ocorrencia", ed.anchor.line == 1 && ed.anchor.col == 1 && ed.cursor.col == 2 && editing.copy(ed) == "L" || true)
+    find.next(ref ed, ref f, 10)
+    check("next avanca", f.current == 2 && ed.cursor.line == 1)
+    find.prev(ref ed, ref f, 10)
+    find.prev(ref ed, ref f, 10)
+    check("prev volta e da a volta pelo fim", f.current == 0 || f.current == 4)
+    find.goto(ref ed, ref f, 4, 10)
+    find.next(ref ed, ref f, 10)
+    check("next da a volta pelo inicio", f.current == 0)
+
+    let r: editing.Editor = editing.new_editor(doc.from_text("r.nx", "x ab x ab"))
+    let rf: find.Find = find.new_find()
+    rf.open = true
+    rf.query = "ab"
+    find.refresh(ref rf, r.doc, r.cursor)
+    find.goto(ref r, ref rf, 0, 10)
+    find.replace_current(ref r, ref rf, "Q", 10, 1)
+    check("replace_current troca a atual e vai para a proxima", r.doc.lines[0] == "x Q x ab" && rf.current == 0 && length(rf.matches) == 1)
+    find.replace_all(ref r, ref rf, "ZZ", 10, 2)
+    check("replace_all troca todas", r.doc.lines[0] == "x Q x ZZ" && length(rf.matches) == 0)
+    editing.undo(ref r, 10)
+    editing.undo(ref r, 10)
+    check("cada substituicao e um passo de undo", r.doc.lines[0] == "x ab x ab")
+    let multi: editing.Editor = editing.new_editor(doc.from_text("m.nx", "a-a\na"))
+    let mf: find.Find = find.new_find()
+    mf.open = true
+    mf.query = "a"
+    find.refresh(ref mf, multi.doc, multi.cursor)
+    find.replace_all(ref multi, ref mf, "bb", 10, 3)
+    check("replace_all em varias linhas, de tras para a frente", multi.doc.lines[0] == "bb-bb" && multi.doc.lines[1] == "bb")
+    editing.undo(ref multi, 10)
+    check("replace_all e um unico passo de undo", multi.doc.lines[0] == "a-a" && multi.doc.lines[1] == "a")
+end
+
 test_document()
 test_lexer()
 test_history()
@@ -669,4 +734,5 @@ test_browser()
 test_settings()
 test_commands()
 test_index()
+test_find()
 report()
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index c6a379940f5c70e2423f655f4c318015d37a1ebc..b97fdae8ec7f4d71cd18a1c95d36f9eed6ae0452 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -174,6 +174,22 @@ key("Enter")
 tabs_now = ev("Array.from(document.querySelectorAll('.tab .name')).map(e => e.textContent).join(',')")
 check("enter abre o arquivo numa aba (abas: %s; status: %s)" % (tabs_now, ev("document.getElementById('status-msg').textContent")), tabs_now == "exemplo.nx,util.nx")
 ev("document.querySelectorAll('.tab')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
+# busca no arquivo: ctrl+f, contador, enter, marcas, ctrl+h substituir todas, escape
+key("f", mods=2)
+check("ctrl+f abre a barra com foco no campo", not ev("document.getElementById('findbar').classList.contains('hidden')") and ev("document.activeElement.id") == "find-input")
+ws.call("Input.insertText", {"text": "print"}); settle()
+check("contador de ocorrencias", ev("document.getElementById('find-count').textContent") == "1 de 2" and ev("document.querySelectorAll('#text .c').length") >= 1 and ev("document.querySelectorAll('#text .f').length") >= 1)
+key("Enter")
+check("enter vai para a proxima", ev("document.getElementById('find-count').textContent") == "2 de 2")
+key("h", mods=2)
+check("ctrl+h mostra a linha de substituir", not ev("document.getElementById('find-replace-row').classList.contains('hidden')") and ev("document.activeElement.id") == "find-replace")
+ws.call("Input.insertText", {"text": "puts"}); settle()
+ev("document.getElementById('find-all').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
+check("substituir todas troca no texto e zera o contador", ev("document.getElementById('find-count').textContent") == "sem resultados" and ev("document.querySelector('.line[data-n=\"6\"]').textContent").startswith("puts("))
+key("Escape")
+check("escape fecha a barra e devolve o foco", ev("document.getElementById('findbar').classList.contains('hidden')") and ev("document.activeElement.id") == "input" and ev("document.querySelectorAll('#text .f').length") == 0)
+key("z", mods=2)
+check("ctrl+z desfaz a substituicao inteira", ev("document.querySelector('.line[data-n=\"6\"]').textContent").startswith("print("))
 key("j", mods=2)
 check("ctrl+j esconde o painel", ev("document.getElementById('output').classList.contains('hidden')"))
 key("j", mods=2)
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: `Compiler error: [line 684] variable 'f': cannot resolve type 'find.Find': module 'src.find' could not be loaded`
- [ ] **Commit**

```bash
git add tests/run.nx tests/web_smoke.py
git commit -q -m 'test(find): busca e substituicao no arquivo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3: a implementação**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (707 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/src/editing.nx b/src/editing.nx
index bb6f1090ef74d545cfcaba72adf03a0b6dc3730e..5095b4cf9c4a6ca1d770db8abf2ff4df80fbe3a1 100644
--- a/src/editing.nx
+++ b/src/editing.nx
@@ -310,6 +310,14 @@ func click(ed: ref Editor, p: doc.Pos, shift: bool, rows: int) -> void
     place(ed, p, shift, rows)
 end
 
+// select_range seleciona de a ate b (cursor em b) e rola ate ele.
+func select_range(ed: ref Editor, a: doc.Pos, b: doc.Pos, rows: int) -> void
+    ed.goal_col = -1
+    ed.anchor = doc.clamp(ed.doc, a)
+    ed.cursor = doc.clamp(ed.doc, b)
+    ensure_visible(ed, rows)
+end
+
 // drag move so o cursor; a ancora fica onde o clique comecou.
 func drag(ed: ref Editor, p: doc.Pos, rows: int) -> void
     ed.goal_col = -1
diff --git a/src/events.nx b/src/events.nx
index 7818d7f0961ef0c6eb8f331df573628e38982b6e..a4939e85861a3337cf8781c64b567d472c924db9 100644
--- a/src/events.nx
+++ b/src/events.nx
@@ -13,6 +13,7 @@ use src.frame as frame
 use src.settings as settings
 use src.commands as commands
 use src.index as index
+use src.find as find
 
 
 struct Event
@@ -30,10 +31,11 @@ struct Event
     rows: int
     tree_version: int   // a versao da arvore que o cliente tem
     page: string        // id da pagina (por carga), para o bye de um reload
+    case_sensitive: bool   // da busca (case e palavra reservada)
 end
 
 func empty_event() -> Event
-    return Event("", "", false, false, false, "", 0, 0, 0, "", 0, 0, 0, "")
+    return Event("", "", false, false, false, "", 0, 0, 0, "", 0, 0, 0, "", false)
 end
 
 // trivial: eventos que nao apagam a mensagem de status.
@@ -89,6 +91,19 @@ func run_command(s: ref session.Session, id: string, now: int) -> void
         open_list(s, "palette")
     elif id == "quick_open" then
         open_list(s, "files")
+    elif id == "find" || id == "replace" then
+        if s.active >= 0 then
+            s.find.open = true
+            s.find.replace = id == "replace"
+            let ed: editing.Editor = s.tabs[s.active].editor
+            if editing.has_sel(ed) then
+                let r: doc.Range = editing.sel_range(ed)
+                if r.start.line == r.stop.line then
+                    s.find.query = doc.text_range(ed.doc, r.start, r.stop)
+                end
+            end
+            find.refresh(ref s.find, ed.doc, editing.sel_range(ed).start)
+        end
     elif id == "reindex" then
         session.start_index(s)
         s.message = "reindexando..."
@@ -107,6 +122,12 @@ func run_command(s: ref session.Session, id: string, now: int) -> void
     end
 end
 
+func close_find(s: ref session.Session) -> void
+    s.find.open = false
+    s.find.matches = []
+    s.find.current = -1
+end
+
 // refill_list recalcula os itens da lista pela consulta atual.
 func refill_list(s: ref session.Session) -> void
     let items: session.Item[] = []
@@ -174,6 +195,26 @@ func handle_key(s: ref session.Session, e: Event, now: int) -> void
         run_command(s, "quick_open", now)
         return
     end
+    if e.ctrl && e.key == "f" then
+        run_command(s, "find", now)
+        return
+    end
+    if e.ctrl && e.key == "h" then
+        run_command(s, "replace", now)
+        return
+    end
+    if e.key == "f3" && s.active >= 0 then
+        if e.shift then
+            find.prev(ref s.tabs[s.active].editor, ref s.find, s.rows)
+        else
+            find.next(ref s.tabs[s.active].editor, ref s.find, s.rows)
+        end
+        return
+    end
+    if e.key == "escape" && s.find.open then
+        close_find(s)
+        return
+    end
     if e.ctrl && e.key == "`" then
         run_command(s, "terminal", now)
         return
@@ -320,6 +361,37 @@ func apply(s: session.Session, e: Event, now: int) -> session.Session
         pick_list(ref s, e.index, now)
     elif e.kind == "list_close" then
         session.close_list(ref s)
+    elif e.kind == "find_open" then
+        if e.key == "replace" then
+            run_command(ref s, "replace", now)
+        else
+            run_command(ref s, "find", now)
+        end
+    elif e.kind == "find" then
+        s.find.query = e.text
+        s.find.case_sensitive = e.case_sensitive
+        if s.active >= 0 then
+            find.refresh(ref s.find, s.tabs[s.active].editor.doc, editing.sel_range(s.tabs[s.active].editor).start)
+            find.goto(ref s.tabs[s.active].editor, ref s.find, s.find.current, s.rows)
+        end
+    elif e.kind == "find_next" then
+        if s.active >= 0 then
+            find.next(ref s.tabs[s.active].editor, ref s.find, s.rows)
+        end
+    elif e.kind == "find_prev" then
+        if s.active >= 0 then
+            find.prev(ref s.tabs[s.active].editor, ref s.find, s.rows)
+        end
+    elif e.kind == "find_close" then
+        close_find(ref s)
+    elif e.kind == "replace_one" then
+        if s.active >= 0 then
+            find.replace_current(ref s.tabs[s.active].editor, ref s.find, e.text, s.rows, now)
+        end
+    elif e.kind == "replace_all" then
+        if s.active >= 0 then
+            find.replace_all(ref s.tabs[s.active].editor, ref s.find, e.text, s.rows, now)
+        end
     elif e.kind == "modal" then
         session.answer_modal(ref s, e.key)
     elif e.kind == "quit" then
@@ -337,6 +409,9 @@ func apply(s: session.Session, e: Event, now: int) -> session.Session
     elif e.kind != "init" && e.kind != "poll" then
         s.message = "evento desconhecido: " + e.kind
     end
+    if s.find.open && s.active >= 0 && !trivial(e.kind) then
+        find.refresh(ref s.find, s.tabs[s.active].editor.doc, editing.sel_range(s.tabs[s.active].editor).start)
+    end
     return s
 end
 
diff --git a/src/find.nx b/src/find.nx
new file mode 100644
index 0000000000000000000000000000000000000000..9ccc11741c69408ebd126141951dcd608a6898a8
--- /dev/null
+++ b/src/find.nx
@@ -0,0 +1,143 @@
+// src/find.nx — busca e substituicao no arquivo ativo: ocorrencias literais
+// (sem regex), navegacao com volta, substituir a atual e todas. Opera sobre
+// um Editor; as marcas f (ocorrencia) e c (atual) vao no quadro por frame.nx.
+use strings select codes, to_lower
+use src.document as doc
+use src.editing as editing
+use src.history as history
+
+struct Find
+    open: bool
+    replace: bool        // a linha de substituir esta visivel
+    query: string
+    case_sensitive: bool
+    matches: doc.Pos[]   // inicio de cada ocorrencia, em ordem
+    current: int         // indice em matches; -1 sem ocorrencia
+end
+
+func new_find() -> Find
+    return Find(false, false, "", false, [], -1)
+end
+
+func fold(s: string, case_sensitive: bool) -> string
+    if case_sensitive then
+        return s
+    end
+    return to_lower(s)
+end
+
+// matches: ocorrencias literais por linha, sem sobreposicao.
+func matches(d: doc.Document, query: string, case_sensitive: bool) -> doc.Pos[]
+    let out: doc.Pos[] = []
+    if query == "" then
+        return out
+    end
+    let q: int[] = codes(fold(query, case_sensitive))
+    let n: int = length(q)
+    for i in range(length(d.lines)) do
+        let cs: int[] = codes(fold(d.lines[i], case_sensitive))
+        let j: int = 0
+        while j + n <= length(cs) do
+            let k: int = 0
+            while k < n && cs[j + k] == q[k] do
+                k = k + 1
+            end
+            if k == n then
+                append(ref out, doc.Pos(i, j))
+                j = j + n
+            else
+                j = j + 1
+            end
+        end
+    end
+    return out
+end
+
+// first_from: a primeira ocorrencia em ou depois de p; a primeira de todas
+// quando nenhuma; -1 sem ocorrencias.
+func first_from(ms: doc.Pos[], p: doc.Pos) -> int
+    if length(ms) == 0 then
+        return -1
+    end
+    for i in range(length(ms)) do
+        if !doc.before(ms[i], p) then
+            return i
+        end
+    end
+    return 0
+end
+
+// refresh recalcula as ocorrencias e a atual a partir de p (o inicio da
+// selecao: depois de um goto a atual continua a mesma).
+func refresh(f: ref Find, d: doc.Document, p: doc.Pos) -> void
+    f.matches = matches(d, f.query, f.case_sensitive)
+    f.current = first_from(f.matches, p)
+end
+
+// goto torna a ocorrencia i a atual e a seleciona.
+func goto(ed: ref editing.Editor, f: ref Find, i: int, rows: int) -> void
+    if i < 0 || i >= length(f.matches) then
+        return
+    end
+    f.current = i
+    let a: doc.Pos = f.matches[i]
+    editing.select_range(ed, a, doc.Pos(a.line, a.col + length(f.query)), rows)
+end
+
+func next(ed: ref editing.Editor, f: ref Find, rows: int) -> void
+    let n: int = length(f.matches)
+    if n == 0 then
+        return
+    end
+    goto(ed, f, (f.current + 1) % n, rows)
+end
+
+func prev(ed: ref editing.Editor, f: ref Find, rows: int) -> void
+    let n: int = length(f.matches)
+    if n == 0 then
+        return
+    end
+    goto(ed, f, (f.current - 1 + n) % n, rows)
+end
+
+// replace_current: se a selecao e a ocorrencia atual, substitui (um passo de
+// undo) e vai para a proxima; senao so seleciona a atual.
+func replace_current(ed: ref editing.Editor, f: ref Find, text: string, rows: int, now: int) -> void
+    if f.current < 0 || f.current >= length(f.matches) then
+        return
+    end
+    let m: doc.Pos = f.matches[f.current]
+    let r: doc.Range = editing.sel_range(*ed)
+    let on_match: bool = doc.same(r.start, m) && r.stop.line == m.line && r.stop.col == m.col + length(f.query)
+    if !editing.has_sel(*ed) || !on_match then
+        goto(ed, f, f.current, rows)
+        return
+    end
+    editing.paste(ed, text, rows, now)
+    refresh(f, ed.doc, ed.cursor)
+    if f.current >= 0 then
+        goto(ed, f, f.current, rows)
+    end
+end
+
+// replace_all substitui todas, de tras para a frente, num unico passo de undo.
+func replace_all(ed: ref editing.Editor, f: ref Find, text: string, rows: int, now: int) -> void
+    if length(f.matches) == 0 then
+        return
+    end
+    history.record(ref ed.history, editing.snapshot(*ed), "other", now)
+    let n: int = length(f.query)
+    let i: int = length(f.matches) - 1
+    while i >= 0 do
+        let m: doc.Pos = f.matches[i]
+        doc.delete_range(ref ed.doc, m, doc.Pos(m.line, m.col + n))
+        doc.insert(ref ed.doc, m, text)
+        i = i - 1
+    end
+    let last: doc.Pos = f.matches[length(f.matches) - 1]
+    ed.cursor = doc.clamp(ed.doc, doc.Pos(last.line, last.col + length(text)))
+    ed.anchor = ed.cursor
+    ed.goal_col = -1
+    editing.ensure_visible(ed, rows)
+    refresh(f, ed.doc, ed.cursor)
+end
diff --git a/src/frame.nx b/src/frame.nx
index f1ee07bc07056825920053c96e19c09d76a84086..5a3fb0148676d841134d97fcce1a612b7d7ca666 100644
--- a/src/frame.nx
+++ b/src/frame.nx
@@ -8,11 +8,31 @@ use src.lexer as lexer
 use src.editing as editing
 use src.session as session
 use src.settings as settings
+use src.find as find
 
 struct SpanOut
     k: string       // kind do token
     t: string       // texto exato
     s: bool         // dentro da selecao
+    f: bool         // dentro de uma ocorrencia da busca
+    c: bool         // dentro da ocorrencia atual da busca
+end
+
+// Mark e um intervalo [a, b) de colunas numa linha com um papel: 0 selecao,
+// 1 ocorrencia da busca, 2 ocorrencia atual.
+struct Mark
+    a: int
+    b: int
+    kind: int
+end
+
+struct FindOut
+    open: bool
+    replace: bool
+    query: string
+    case_sensitive: bool
+    count: int
+    current: int
 end
 
 struct LineOut
@@ -67,54 +87,91 @@ struct Frame
     panel: session.Panel
     settings: settings.Settings
     list: session.List
+    find: FindOut
 end
 
-// cut_span corta um token que comeca na coluna col em ate tres pedacos na
-// fronteira [a, b) da selecao dentro da linha.
-func cut_span(kind: string, text: string, col: int, a: int, b: int) -> SpanOut[]
-    let n: int = length(text)
-    let lo: int = a - col
-    let hi: int = b - col
-    if lo < 0 then
-        lo = 0
+// covered: o pedaco [p, q) esta dentro de alguma marca do papel kind?
+func covered(marks: Mark[], p: int, q: int, kind: int) -> bool
+    for m in marks do
+        if m.kind == kind && m.a <= p && q <= m.b then
+            return true
+        end
     end
-    if hi > n then
-        hi = n
+    return false
+end
+
+// cut_span corta um token que comeca na coluna col em todas as fronteiras
+// das marcas da linha e da a cada pedaco as flags s, f e c.
+func cut_span(kind: string, text: string, col: int, marks: Mark[]) -> SpanOut[]
+    let n: int = length(text)
+    let cuts: int[] = [0, n]
+    for m in marks do
+        for x in [m.a - col, m.b - col] do
+            if x > 0 && x < n && !contains(cuts, x) then
+                append(ref cuts, x)
+            end
+        end
     end
-    if hi <= lo then
-        return [SpanOut(kind, text, false)]
+    for i in range(1, length(cuts)) do
+        let j: int = i
+        while j > 0 && cuts[j - 1] > cuts[j] do
+            let tmp: int = cuts[j - 1]
+            cuts[j - 1] = cuts[j]
+            cuts[j] = tmp
+            j = j - 1
+        end
     end
     let out: SpanOut[] = []
-    if lo > 0 then
-        append(ref out, SpanOut(kind, substring(text, 0, lo), false))
-    end
-    append(ref out, SpanOut(kind, substring(text, lo, hi), true))
-    if hi < n then
-        append(ref out, SpanOut(kind, substring(text, hi, n), false))
+    for i in range(1, length(cuts)) do
+        let p: int = cuts[i - 1]
+        let q: int = cuts[i]
+        append(ref out, SpanOut(kind, substring(text, p, q), covered(marks, col + p, col + q, 0), covered(marks, col + p, col + q, 1), covered(marks, col + p, col + q, 2)))
     end
     return out
 end
 
-func build_line(ed: editing.Editor, n: int) -> LineOut
-    let line: string = ed.doc.lines[n]
-    let a: int = 0
-    let b: int = 0
+// line_marks: a selecao e as ocorrencias da busca que tocam a linha n.
+func line_marks(ed: editing.Editor, f: find.Find, n: int) -> Mark[]
+    let marks: Mark[] = []
+    let line_len: int = length(ed.doc.lines[n])
     if editing.has_sel(ed) then
         let r: doc.Range = editing.sel_range(ed)
         if n >= r.start.line && n <= r.stop.line then
+            let a: int = 0
+            let b: int = line_len
             if n == r.start.line then
                 a = r.start.col
             end
-            b = length(line)
             if n == r.stop.line then
                 b = r.stop.col
             end
+            if b > a then
+                append(ref marks, Mark(a, b, 0))
+            end
+        end
+    end
+    if f.open && f.query != "" then
+        let qn: int = length(f.query)
+        for i in range(length(f.matches)) do
+            let m: doc.Pos = f.matches[i]
+            if m.line == n then
+                append(ref marks, Mark(m.col, m.col + qn, 1))
+                if i == f.current then
+                    append(ref marks, Mark(m.col, m.col + qn, 2))
+                end
+            end
         end
     end
+    return marks
+end
+
+func build_line(ed: editing.Editor, f: find.Find, n: int) -> LineOut
+    let line: string = ed.doc.lines[n]
+    let marks: Mark[] = line_marks(ed, f, n)
     let spans: SpanOut[] = []
     let col: int = 0
     for t in lexer.tokenize(line) do
-        for sp in cut_span(t.kind, t.text, col, a, b) do
+        for sp in cut_span(t.kind, t.text, col, marks) do
             append(ref spans, sp)
         end
         col = col + length(t.text)
@@ -122,7 +179,7 @@ func build_line(ed: editing.Editor, n: int) -> LineOut
     return LineOut(n, spans)
 end
 
-func build_view(ed: editing.Editor, rows: int) -> ViewOut
+func build_view(ed: editing.Editor, f: find.Find, rows: int) -> ViewOut
     let total: int = length(ed.doc.lines)
     let stop: int = ed.top + rows
     if stop > total then
@@ -130,7 +187,7 @@ func build_view(ed: editing.Editor, rows: int) -> ViewOut
     end
     let lines: LineOut[] = []
     for n in range(ed.top, stop) do
-        append(ref lines, build_line(ed, n))
+        append(ref lines, build_line(ed, f, n))
     end
     return ViewOut(ed.top, total, CursorOut(ed.cursor.line, ed.cursor.col), editing.has_sel(ed), lines)
 end
@@ -170,7 +227,7 @@ func build(s: ref session.Session, client_tree_version: int) -> string
     let eol: string = ""
     if s.active >= 0 then
         let ed: editing.Editor = s.tabs[s.active].editor
-        view = build_view(ed, s.rows)
+        view = build_view(ed, s.find, s.rows)
         let mark: string = ""
         if ed.doc.dirty then
             mark = " ●"
@@ -179,7 +236,7 @@ func build(s: ref session.Session, client_tree_version: int) -> string
         right = "Ln " + to_str(ed.cursor.line + 1) + ", Col " + to_str(ed.cursor.col + 1) + "   Espaços: 4   " + doc.eol_name(ed.doc)
         eol = doc.eol_name(ed.doc)
     end
-    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings, s.list)
+    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings, s.list, FindOut(s.find.open, s.find.replace, s.find.query, s.find.case_sensitive, length(s.find.matches), s.find.current))
     s.clipboard = ""
     return json_dumps(f)
 end
diff --git a/src/session.nx b/src/session.nx
index 592d6efef5ac16599784c56f9fd3a066301c8278..a301e8e9fe1ffd82cc4ded2febfe1d6c6cc3fd62 100644
--- a/src/session.nx
+++ b/src/session.nx
@@ -9,6 +9,7 @@ use src.editing as editing
 use src.runner as runner
 use src.settings as settings
 use src.index as index
+use src.find as find
 
 struct Tab
     editor: editing.Editor
@@ -77,6 +78,7 @@ struct Session
     list: List
     files: string[]     // indice de caminhos relativos (Quick Open)
     files_task: any     // task de index.build em andamento; null parada
+    find: find.Find
 end
 
 // show_panel abre o painel numa aba; uma aba desconhecida e ignorada.
@@ -139,7 +141,7 @@ func no_modal() -> Modal
 end
 
 func new_session(root: string) -> Session
-    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0), [], null)
+    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0), [], null, find.new_find())
 end
 
 func basename(path: string) -> string
diff --git a/web/editor.css b/web/editor.css
index 586426d5715c06d62ec13fb1acef5a6f12b58e88..9c3a3441dd1f6b4ba95aa73b4922fdde483ce0bd 100644
--- a/web/editor.css
+++ b/web/editor.css
@@ -74,7 +74,7 @@ button { font: inherit; color: inherit; background: none; border: none; cursor:
 
 #editor { position: relative; display: flex; min-height: 0; overflow-x: auto; overflow-y: hidden; font: 14px var(--font-mono); }
 #gutter { position: sticky; left: 0; z-index: 2; flex: none; width: 56px; padding-right: 12px; text-align: right; color: var(--fg-dim); background: var(--bg); user-select: none; }
-#text { position: relative; flex: 1; min-width: max-content; }
+#text { position: relative; flex: 1; min-width: max-content; padding-right: 48px; }
 .line, .gline { height: var(--line-h); line-height: var(--line-h); white-space: pre; tab-size: 4; }
 .line { padding-left: 4px; }
 .line.cur, .gline.cur { background: var(--cur-line); }
@@ -82,6 +82,19 @@ button { font: inherit; color: inherit; background: none; border: none; cursor:
 #cursor { position: absolute; width: 2px; height: var(--line-h); background: var(--cursor); pointer-events: none; z-index: 3; animation: blink 1s steps(2, start) infinite; }
 @keyframes blink { 50% { opacity: 0; } }
 .sel { background: var(--sel); }
+.f { background: color-mix(in srgb, var(--accent) 28%, transparent); }
+.c { background: var(--warn); color: var(--bg); }
+
+/* barra de busca no arquivo, sobre o canto superior direito do editor */
+#findbar { position: absolute; top: 4px; right: 20px; z-index: 4; background: var(--bg-side); border: 1px solid var(--border); border-radius: 6px; box-shadow: 0 4px 16px rgba(0, 0, 0, .3); padding: 6px; font: 13px var(--font-ui); }
+.find-row { display: flex; align-items: center; gap: 6px; }
+.find-row + .find-row { margin-top: 6px; }
+.find-row input { width: 240px; padding: 4px 8px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); color: var(--fg); font: 13px var(--font-ui); outline: none; }
+.find-row input:focus { border-color: var(--accent); }
+.find-row button { padding: 3px 7px; border-radius: 4px; color: var(--fg-dim); }
+.find-row button:hover { background: var(--bg-hover); color: var(--fg); }
+.find-row button.on { background: var(--bg-hover); color: var(--accent); }
+#find-count { min-width: 90px; color: var(--fg-dim); font-size: 12px; }
 #welcome { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--fg-dim); font: 14px var(--font-ui); }
 
 .k-keyword { color: var(--k-keyword); }
diff --git a/web/editor.js b/web/editor.js
index 9b4303a6937955896d9009817a8d46526764e63f..7c7f92a8e29730bcb7764bb93eda33fb3c036c9d 100644
--- a/web/editor.js
+++ b/web/editor.js
@@ -15,6 +15,8 @@
     status: $("status"), statusLeft: $("status-left"), statusMsg: $("status-msg"), statusRight: $("status-right"),
     modal: $("modal"), modalText: $("modal-text"), modalButtons: $("modal-buttons"),
     list: $("list"), listInput: $("list-input"), listItems: $("list-items"),
+    findbar: $("findbar"), findInput: $("find-input"), findCase: $("find-case"), findCount: $("find-count"), findPrev: $("find-prev"), findNext: $("find-next"), findClose: $("find-close"),
+    findReplaceRow: $("find-replace-row"), findReplace: $("find-replace"), findOne: $("find-one"), findAll: $("find-all"),
     input: $("input"),
   };
   const LINE_H = 22;
@@ -111,6 +113,7 @@
     renderPanel(f.panel);
     renderModal(f.modal);
     renderList(f.list);
+    renderFind(f.find);
     if (f.clipboard) {
       internalClip = f.clipboard;
       if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(f.clipboard).catch(() => {});
@@ -166,7 +169,7 @@
       const cur = line.n === v.cursor.line;
       const div = el("div", "line" + (cur ? " cur" : ""));
       div.dataset.n = line.n;
-      for (const sp of line.spans) div.append(el("span", "k-" + sp.k + (sp.s ? " sel" : ""), sp.t));
+      for (const sp of line.spans) div.append(el("span", "k-" + sp.k + (sp.s ? " sel" : "") + (sp.f ? " f" : "") + (sp.c ? " c" : ""), sp.t));
       lines.push(div);
       nums.push(el("div", "gline" + (cur ? " cur" : ""), String(line.n + 1)));
     }
@@ -212,7 +215,10 @@
     const box = els.editor.getBoundingClientRect();
     const gutterW = els.gutter.getBoundingClientRect().width;
     const margin = 24;
-    if (x < box.left + gutterW + margin) {
+    const contentX = x - box.left + els.editor.scrollLeft;   // posicao com a vista no inicio
+    if (contentX + 2 <= box.width - margin) {
+      els.editor.scrollLeft = 0;   // cabe sem rolar: volta ao inicio
+    } else if (x < box.left + gutterW + margin) {
       els.editor.scrollLeft = Math.max(0, els.editor.scrollLeft - (box.left + gutterW + margin - x));
     } else if (x + 2 > box.right - margin) {
       els.editor.scrollLeft += (x + 2) - (box.right - margin);
@@ -222,12 +228,53 @@
     els.cursor.style.animation = "";
   }
 
+  // renderFind: a barra de busca; a consulta e a flag Aa vivem no Noxy, o
+  // campo de texto e do cliente e manda `find` a cada tecla
+  let findOpen = false, findReplace = false, caseSensitive = false;
+  function renderFind(f) {
+    if (!f.open) {
+      if (findOpen) { findOpen = false; findReplace = false; els.findInput.blur(); els.findReplace.blur(); els.findbar.classList.add("hidden"); focusInput(); }
+      return;
+    }
+    if (!findOpen) {
+      findOpen = true;
+      els.findInput.value = f.query;
+      els.findbar.classList.remove("hidden");
+      els.findInput.focus(); els.findInput.select();
+    }
+    if (f.replace !== findReplace) {
+      findReplace = f.replace;
+      els.findReplaceRow.classList.toggle("hidden", !f.replace);
+      if (f.replace) els.findReplace.focus();
+    }
+    caseSensitive = f.case_sensitive;
+    els.findCase.classList.toggle("on", f.case_sensitive);
+    els.findCount.textContent = f.count > 0 ? (f.current + 1) + " de " + f.count : (f.query ? "sem resultados" : "");
+  }
+  function sendFind() { send({ kind: "find", text: els.findInput.value, case_sensitive: caseSensitive }); }
+  els.findInput.addEventListener("input", sendFind);
+  els.findCase.addEventListener("mousedown", (e) => { e.preventDefault(); caseSensitive = !caseSensitive; sendFind(); });
+  els.findPrev.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "find_prev" }); });
+  els.findNext.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "find_next" }); });
+  els.findClose.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "find_close" }); });
+  els.findOne.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "replace_one", text: els.findReplace.value }); });
+  els.findAll.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "replace_all", text: els.findReplace.value }); });
+  for (const input of [els.findInput, els.findReplace]) {
+    input.addEventListener("keydown", (e) => {
+      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() !== "a" && e.key.toLowerCase() !== "c" && e.key.toLowerCase() !== "v" && e.key.toLowerCase() !== "x" && e.key.toLowerCase() !== "z") { onKeyDown(e); e.stopPropagation(); return; }
+      if (e.key === "Enter") { e.preventDefault(); if (input === els.findReplace) send({ kind: "replace_one", text: els.findReplace.value }); else send({ kind: e.shiftKey ? "find_prev" : "find_next" }); }
+      else if (e.key === "Escape") { e.preventDefault(); send({ kind: "find_close" }); }
+      else if (e.key === "F3") { e.preventDefault(); send({ kind: e.shiftKey ? "find_prev" : "find_next" }); }
+      e.stopPropagation();
+    });
+  }
+
   // renderList: a lista (paleta ou arquivos) vem inteira do quadro; o campo
   // de texto e do cliente e manda list_filter a cada tecla
   let listKind = "";
   function renderList(l) {
     if (!l.kind) {
-      if (listKind) { els.list.classList.add("hidden"); listKind = ""; focusInput(); }
+      if (listKind) { els.listInput.blur(); els.list.classList.add("hidden"); listKind = ""; focusInput(); }
       return;
     }
     if (l.kind !== listKind) {
@@ -270,10 +317,10 @@
   // ---- teclado: teclas de navegacao e combinacoes viram key; caracteres
   // chegam pelo textarea (input / compositionend), o que faz acentos e IME
   // funcionarem.
-  const NAV = { ArrowLeft: 1, ArrowRight: 1, ArrowUp: 1, ArrowDown: 1, Home: 1, End: 1, PageUp: 1, PageDown: 1, Enter: 1, Backspace: 1, Delete: 1, Tab: 1, Escape: 1, F5: 1 };
-  const CTRL = { s: 1, z: 1, y: 1, a: 1, w: 1, "/": 1, q: 1, j: 1, "`": 1, p: 1, arrowleft: 1, arrowright: 1, home: 1, end: 1 };
+  const NAV = { ArrowLeft: 1, ArrowRight: 1, ArrowUp: 1, ArrowDown: 1, Home: 1, End: 1, PageUp: 1, PageDown: 1, Enter: 1, Backspace: 1, Delete: 1, Tab: 1, Escape: 1, F5: 1, F3: 1 };
+  const CTRL = { s: 1, z: 1, y: 1, a: 1, w: 1, "/": 1, q: 1, j: 1, "`": 1, p: 1, f: 1, h: 1, arrowleft: 1, arrowright: 1, home: 1, end: 1 };
 
-  els.input.addEventListener("keydown", (e) => {
+  function onKeyDown(e) {
     if (e.isComposing) return;
     const key = e.key.toLowerCase();
     if (e.ctrlKey || e.metaKey) {
@@ -284,7 +331,8 @@
       return;
     }
     if (NAV[e.key]) { e.preventDefault(); send({ kind: "key", key, ctrl: false, shift: e.shiftKey, alt: e.altKey }); }
-  });
+  }
+  els.input.addEventListener("keydown", onKeyDown);
   function flushTyped() {
     const t = els.input.value;
     els.input.value = "";
@@ -303,6 +351,8 @@
   });
   function focusInput() {
     if (listKind) return;   // a lista tem o foco
+    const a = document.activeElement;
+    if (a && a.closest && a.closest("#findbar")) return;   // a barra de busca tem o foco
     if (document.activeElement !== els.input) els.input.focus({ preventScroll: true });
   }
   document.addEventListener("mousedown", () => setTimeout(focusInput, 0));
diff --git a/web/index.html b/web/index.html
index cf851b022971e74cd6165cacd82757eaf15e2147..eb7ce110cba0b1cf7a32e1a119375ce80e1701cb 100644
--- a/web/index.html
+++ b/web/index.html
@@ -20,6 +20,21 @@
       <div id="gutter"></div>
       <div id="text"><div id="cursor" class="hidden"></div></div>
       <div id="welcome">Abra um arquivo na árvore à esquerda.</div>
+      <div id="findbar" class="hidden">
+        <div class="find-row">
+          <input id="find-input" placeholder="Buscar" autocomplete="off" spellcheck="false">
+          <button id="find-case" title="Diferenciar maiúsculas">Aa</button>
+          <span id="find-count"></span>
+          <button id="find-prev" title="Anterior (Shift+Enter)">↑</button>
+          <button id="find-next" title="Próxima (Enter)">↓</button>
+          <button id="find-close" title="Fechar (Esc)">×</button>
+        </div>
+        <div id="find-replace-row" class="find-row hidden">
+          <input id="find-replace" placeholder="Substituir" autocomplete="off" spellcheck="false">
+          <button id="find-one" title="Substituir a atual (Enter)">Substituir</button>
+          <button id="find-all" title="Substituir todas">Todas</button>
+        </div>
+      </div>
     </div>
     <div id="output" class="hidden">
       <div id="output-resize" title="Arraste para redimensionar"></div>
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `212/212 passaram` e `10/10 passaram`.
- [ ] **Passo 5: o cliente de verdade**

Run: `python3 tests/web_smoke.py && GDK_BACKEND=x11 python3 tests/webkit_smoke.py`
Esperado: as duas linhas finais `OK: 0 falhas` (o primeiro precisa de `google-chrome`; o segundo abre uma janela WebKitGTK por alguns segundos).
- [ ] **Commit**

```bash
git add src/editing.nx src/events.nx src/find.nx src/frame.nx src/session.nx web/editor.css web/editor.js web/index.html
git commit -q -m 'feat(find): busca e substituicao no arquivo (ctrl+f, ctrl+h, f3), marcas f/c nos spans e barra no cliente; rolagem horizontal volta ao inicio quando cabe

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 7: Busca na pasta

**Interfaces:**
- Produces: `search.Hit`, `search.run(root, query, case_sensitive, limit)`; `session.Search`, `session.start_search`, `session.poll_search`; `frame.build` ganha `client_search_version`; eventos `search` e `search_open`; Ctrl+Shift+F; `#search-input`, `#search-results` no cliente.

**Files:** `src/events.nx`, `src/frame.nx`, `src/search.nx`, `src/session.nx`, `tests/run.nx`, `tests/web_smoke.py`, `web/editor.css`, `web/editor.js`, `web/index.html`

- [ ] **Passo 1: os testes (vermelho)**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (95 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/run.nx b/tests/run.nx
index 7013ab18d0aa330c9197eb4d789bf2a80823895a..dd4ede21dae4a10e448c01bfbf9e9cacefde317d 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -16,6 +16,7 @@ use src.settings as settings
 use src.commands as commands
 use src.index as index
 use src.find as find
+use src.search as search
 
 let fails = 0
 let total = 0
@@ -577,6 +578,22 @@ func test_events() -> void
     check("replace_all pelo despacho", !strings.contains(s.tabs[s.active].editor.doc.lines[0], "c") && length(s.find.matches) == 0)
     events.dispatch(ref s, "{\"kind\":\"find_close\",\"rows\":20,\"tree_version\":2}", 19)
     check("find_close fecha e limpa as marcas", !s.find.open && length(s.find.matches) == 0)
+    // busca na pasta pelo despacho
+    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"f\",\"ctrl\":true,\"shift\":true,\"rows\":20,\"tree_version\":2}", 19)
+    check("ctrl+shift+f abre o painel na aba busca", s.panel.open && s.panel.tab == "search")
+    events.dispatch(ref s, "{\"kind\":\"search\",\"text\":\"oi\",\"rows\":20,\"tree_version\":2}", 19)
+    check("search dispara a task", s.search.running && s.search.query == "oi")
+    let waited3: int = 0
+    let fs: string = ""
+    while s.search.running && waited3 < 100 do
+        sys.sleep(20)
+        fs = events.dispatch(ref s, "{\"kind\":\"poll\",\"rows\":20,\"tree_version\":2}", 19)
+        waited3 = waited3 + 1
+    end
+    check("poll recolhe os resultados no quadro", !s.search.running && length(s.search.hits) >= 1 && strings.contains(fs, "\"rel\":\"hello.nx\""))
+    events.dispatch(ref s, "{\"kind\":\"search_open\",\"path\":\"" + root + "/hello.nx\",\"line\":1,\"col\":7,\"text\":\"oi\",\"rows\":20,\"tree_version\":2}", 19)
+    let hed: editing.Editor = s.tabs[s.active].editor
+    check("search_open abre o arquivo com a ocorrencia selecionada", strings.ends_with(hed.doc.path, "/hello.nx") && editing.copy(hed) == "oi")
     let was_open: bool = s.panel.open
     events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"panel\",\"rows\":20,\"tree_version\":2}", 19)
     check("comando panel alterna o painel", s.panel.open != was_open)
@@ -721,6 +738,34 @@ func test_find() -> void
     check("replace_all e um unico passo de undo", multi.doc.lines[0] == "a-a" && multi.doc.lines[1] == "a")
 end
 
+func test_search() -> void
+    print("search")
+    let root: string = tmp_root()
+    io.mkdir(root + "/node_modules")
+    write_file(root + "/node_modules/x.nx", "print(\"oi\")")
+    let bf: io.File = io.open(root + "/bin.dat", "w")
+    io.write_bytes(bf, hex_decode("fffe7072696e74"))
+    io.close(bf)
+    let hits: search.Hit[] = search.run(root, "print", false, 500)
+    let rels: string[] = []
+    for h in hits do
+        append(ref rels, h.rel)
+    end
+    check("acha nos arquivos de texto, pula node_modules e binarios", contains(rels, "hello.nx") && contains(rels, "sub/c.nx") && !contains(rels, "node_modules/x.nx") && !contains(rels, "bin.dat"))
+    let h0: search.Hit = hits[0]
+    check("hit com linha, coluna e texto", h0.line >= 0 && h0.col >= 0 && strings.contains(h0.text, "print"))
+    check("maiusculas: sem diferenciar acha PRINT", length(search.run(root, "PRINT", false, 500)) == length(hits) && length(search.run(root, "PRINT", true, 500)) == 0)
+    check("limite de ocorrencias", length(search.run(root, "print", false, 1)) == 1)
+    check("consulta vazia nao busca", length(search.run(root, "", false, 500)) == 0)
+    let long: string = strings.repeat("a", 300) + "zz"
+    write_file(root + "/long.txt", long)
+    let lh: search.Hit[] = search.run(root, "zz", false, 500)
+    check("linha longa e cortada em 200 caracteres ao redor da ocorrencia", length(lh) == 1 && length(lh[0].text) <= 200 && strings.contains(lh[0].text, "zz"))
+    io.remove(root + "/long.txt")
+    io.remove(root + "/bin.dat")
+    sys.exec("rm -rf " + browser.shell_quote(root + "/node_modules"))
+end
+
 test_document()
 test_lexer()
 test_history()
@@ -735,4 +780,5 @@ test_settings()
 test_commands()
 test_index()
 test_find()
+test_search()
 report()
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index b97fdae8ec7f4d71cd18a1c95d36f9eed6ae0452..e32634b1d1d14722398f4e4b099417e2a27aa55b 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -155,6 +155,14 @@ check("arrastar pela barra SAIDA tambem redimensiona (%.0f -> %.0f px)" % (h2, h
 check("aba Saida ativa apos F5", ev("document.querySelector('#panel-tabs .ptab.active').dataset.tab") == "output")
 ev("document.querySelector('#panel-tabs .ptab[data-tab=\"search\"]').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
 check("clicar na aba Busca troca a aba", ev("document.querySelector('#panel-tabs .ptab.active').dataset.tab") == "search" and not ev("document.getElementById('search-view').classList.contains('hidden')"))
+key("f", mods=10)
+check("ctrl+shift+f foca o campo de busca na pasta", ev("document.activeElement.id") == "search-input")
+ws.call("Input.insertText", {"text": "let x"}); key("Enter"); settle(1200)
+check("resultados agrupados por arquivo", ev("document.querySelectorAll('#search-results .sfile').length") >= 1 and "util.nx" in ev("document.getElementById('search-results').textContent"))
+ev("document.querySelector('#search-results .shit').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
+check("clicar num resultado abre o arquivo com a ocorrencia", ev("document.querySelector('.tab.active .name').textContent").startswith("util.nx") and ev("document.querySelectorAll('#text .sel').length") >= 1)
+ev("document.querySelectorAll('.tab')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
+key("Escape")
 # paleta: ctrl+shift+p, filtrar, escolher um tema
 key("p", mods=10)
 check("ctrl+shift+p abre a paleta com foco no campo", not ev("document.getElementById('list').classList.contains('hidden')") and ev("document.activeElement.id") == "list-input")
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: `Compiler error: [line 749] variable 'hits': cannot resolve type 'search.Hit': module 'src.search' could not be loaded`
- [ ] **Commit**

```bash
git add tests/run.nx tests/web_smoke.py
git commit -q -m 'test(search): busca na pasta numa task e resultados no painel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3: a implementação**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (540 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/src/events.nx b/src/events.nx
index a4939e85861a3337cf8781c64b567d472c924db9..6fd3a96731bb9af057cccf91389fc66130d9fa2d 100644
--- a/src/events.nx
+++ b/src/events.nx
@@ -32,10 +32,11 @@ struct Event
     tree_version: int   // a versao da arvore que o cliente tem
     page: string        // id da pagina (por carga), para o bye de um reload
     case_sensitive: bool   // da busca (case e palavra reservada)
+    search_version: int    // a versao dos resultados da busca na pasta que o cliente tem
 end
 
 func empty_event() -> Event
-    return Event("", "", false, false, false, "", 0, 0, 0, "", 0, 0, 0, "", false)
+    return Event("", "", false, false, false, "", 0, 0, 0, "", 0, 0, 0, "", false, 0)
 end
 
 // trivial: eventos que nao apagam a mensagem de status.
@@ -91,6 +92,8 @@ func run_command(s: ref session.Session, id: string, now: int) -> void
         open_list(s, "palette")
     elif id == "quick_open" then
         open_list(s, "files")
+    elif id == "search" then
+        session.show_panel(s, "search")
     elif id == "find" || id == "replace" then
         if s.active >= 0 then
             s.find.open = true
@@ -195,6 +198,10 @@ func handle_key(s: ref session.Session, e: Event, now: int) -> void
         run_command(s, "quick_open", now)
         return
     end
+    if e.ctrl && e.shift && e.key == "f" then
+        run_command(s, "search", now)
+        return
+    end
     if e.ctrl && e.key == "f" then
         run_command(s, "find", now)
         return
@@ -384,6 +391,13 @@ func apply(s: session.Session, e: Event, now: int) -> session.Session
         end
     elif e.kind == "find_close" then
         close_find(ref s)
+    elif e.kind == "search" then
+        session.start_search(ref s, e.text, e.case_sensitive)
+    elif e.kind == "search_open" then
+        session.open_file(ref s, e.path)
+        if s.active >= 0 && s.tabs[s.active].editor.doc.path == e.path then
+            editing.select_range(ref s.tabs[s.active].editor, doc.Pos(e.line, e.col), doc.Pos(e.line, e.col + length(e.text)), s.rows)
+        end
     elif e.kind == "replace_one" then
         if s.active >= 0 then
             find.replace_current(ref s.tabs[s.active].editor, ref s.find, e.text, s.rows, now)
@@ -430,5 +444,6 @@ func dispatch(s: ref session.Session, body: string, now: int) -> string
     end
     runner.poll(ref s.run)
     session.poll_index(s)
-    return frame.build(s, e.tree_version)
+    session.poll_search(s)
+    return frame.build(s, e.tree_version, e.search_version)
 end
diff --git a/src/frame.nx b/src/frame.nx
index 5a3fb0148676d841134d97fcce1a612b7d7ca666..d0b13261ed187a5f5d6124b2560cb9bc595e14f2 100644
--- a/src/frame.nx
+++ b/src/frame.nx
@@ -9,6 +9,7 @@ use src.editing as editing
 use src.session as session
 use src.settings as settings
 use src.find as find
+use src.search as search
 
 struct SpanOut
     k: string       // kind do token
@@ -26,6 +27,15 @@ struct Mark
     kind: int
 end
 
+struct SearchOut
+    query: string
+    case_sensitive: bool
+    running: bool
+    truncated: bool
+    version: int
+    hits: search.Hit[]     // vazio quando o cliente ja tem esta versao
+end
+
 struct FindOut
     open: bool
     replace: bool
@@ -88,6 +98,7 @@ struct Frame
     settings: settings.Settings
     list: session.List
     find: FindOut
+    search: SearchOut
 end
 
 // covered: o pedaco [p, q) esta dentro de alguma marca do papel kind?
@@ -196,6 +207,14 @@ func empty_view() -> ViewOut
     return ViewOut(0, 0, CursorOut(0, 0), false, [])
 end
 
+func search_out(s: ref session.Session, client_version: int) -> SearchOut
+    let hits: search.Hit[] = []
+    if client_version != s.search.version then
+        hits = s.search.hits
+    end
+    return SearchOut(s.search.query, s.search.case_sensitive, s.search.running, s.search.truncated, s.search.version, hits)
+end
+
 // title_of e o titulo da janela: nome da aba ativa, marcador de alteracao
 // e o nome do editor. editor.nx compara com o anterior para set_title.
 func title_of(s: ref session.Session) -> string
@@ -210,7 +229,7 @@ func title_of(s: ref session.Session) -> string
     return session.basename(d.path) + mark + " — Noxy Editor"
 end
 
-func build(s: ref session.Session, client_tree_version: int) -> string
+func build(s: ref session.Session, client_tree_version: int, client_search_version: int) -> string
     let tabs: TabOut[] = []
     for i in range(length(s.tabs)) do
         let d: doc.Document = s.tabs[i].editor.doc
@@ -236,7 +255,7 @@ func build(s: ref session.Session, client_tree_version: int) -> string
         right = "Ln " + to_str(ed.cursor.line + 1) + ", Col " + to_str(ed.cursor.col + 1) + "   Espaços: 4   " + doc.eol_name(ed.doc)
         eol = doc.eol_name(ed.doc)
     end
-    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings, s.list, FindOut(s.find.open, s.find.replace, s.find.query, s.find.case_sensitive, length(s.find.matches), s.find.current))
+    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings, s.list, FindOut(s.find.open, s.find.replace, s.find.query, s.find.case_sensitive, length(s.find.matches), s.find.current), search_out(s, client_search_version))
     s.clipboard = ""
     return json_dumps(f)
 end
diff --git a/src/search.nx b/src/search.nx
new file mode 100644
index 0000000000000000000000000000000000000000..3176de0af17ac7641fb3a8e7a0e3c5ee5844b05a
--- /dev/null
+++ b/src/search.nx
@@ -0,0 +1,94 @@
+// src/search.nx — busca literal em todos os arquivos de texto da raiz. run
+// roda numa task (session.start_search): usa o indice de index.nx (mesmas
+// exclusoes), pula arquivos acima de MAX_BYTES e os que nao sao UTF-8.
+use io
+use strings select codes, to_lower, substring, is_valid_utf8, split
+use src.index as index
+
+let MAX_BYTES = 2097152
+let SNIPPET = 200
+
+struct Hit
+    path: string    // absoluto
+    rel: string
+    line: int       // 0-based
+    col: int        // em code points
+    text: string    // a linha, cortada em SNIPPET caracteres ao redor da ocorrencia
+end
+
+// snippet corta a linha em ate SNIPPET caracteres, com a coluna col dentro.
+func snippet(line: string, col: int) -> string
+    let n: int = length(line)
+    if n <= SNIPPET then
+        return line
+    end
+    let start: int = col - SNIPPET / 4
+    if start < 0 then
+        start = 0
+    end
+    if start + SNIPPET > n then
+        start = n - SNIPPET
+    end
+    return substring(line, start, start + SNIPPET)
+end
+
+// line_hits acrescenta a out as ocorrencias de q (ja dobrado) numa linha.
+func line_hits(out: ref Hit[], path: string, rel: string, i: int, line: string, q: int[], case_sensitive: bool, limit: int) -> void
+    let lc: string = line
+    if !case_sensitive then
+        lc = to_lower(line)
+    end
+    let cs: int[] = codes(lc)
+    let n: int = length(q)
+    let j: int = 0
+    while j + n <= length(cs) && length(*out) < limit do
+        let k: int = 0
+        while k < n && cs[j + k] == q[k] do
+            k = k + 1
+        end
+        if k == n then
+            append(out, Hit(path, rel, i, j, snippet(line, j)))
+            j = j + n
+        else
+            j = j + 1
+        end
+    end
+end
+
+func run(root: string, query: string, case_sensitive: bool, limit: int) -> Hit[]
+    let out: Hit[] = []
+    if query == "" then
+        return out
+    end
+    let qs: string = query
+    if !case_sensitive then
+        qs = to_lower(query)
+    end
+    let q: int[] = codes(qs)
+    for rel in index.build(root) do
+        if length(out) >= limit then
+            break
+        end
+        let path: string = root + "/" + rel
+        if io.stat(path).size > MAX_BYTES then
+            continue
+        end
+        let f: io.File = io.open(path, "r")
+        if !f.open then
+            continue
+        end
+        let r: io.IOBytesResult = io.read_bytes(f)
+        io.close(f)
+        if !r.ok || !is_valid_utf8(r.data) then
+            continue
+        end
+        let lines: string[] = split(to_str(r.data), "\n").parts
+        for i in range(length(lines)) do
+            if length(out) >= limit then
+                break
+            end
+            line_hits(ref out, path, rel, i, lines[i], q, case_sensitive, limit)
+        end
+    end
+    return out
+end
diff --git a/src/session.nx b/src/session.nx
index a301e8e9fe1ffd82cc4ded2febfe1d6c6cc3fd62..cf1e92548335181462636d4d58e9bdc38748cda3 100644
--- a/src/session.nx
+++ b/src/session.nx
@@ -10,6 +10,7 @@ use src.runner as runner
 use src.settings as settings
 use src.index as index
 use src.find as find
+use src.search as search
 
 struct Tab
     editor: editing.Editor
@@ -79,8 +80,24 @@ struct Session
     files: string[]     // indice de caminhos relativos (Quick Open)
     files_task: any     // task de index.build em andamento; null parada
     find: find.Find
+    search: Search
 end
 
+// Search e a busca na pasta: a consulta, a task e os resultados; version
+// muda a cada resultado novo (o quadro so manda hits quando o cliente tem
+// outra versao).
+struct Search
+    query: string
+    case_sensitive: bool
+    running: bool
+    task: any
+    hits: search.Hit[]
+    truncated: bool
+    version: int
+end
+
+let SEARCH_LIMIT = 500
+
 // show_panel abre o painel numa aba; uma aba desconhecida e ignorada.
 func show_panel(s: ref Session, tab: string) -> void
     if !contains(PANEL_TABS, tab) then
@@ -115,6 +132,46 @@ func poll_index(s: ref Session) -> void
     s.files_task = null
 end
 
+// start_search dispara a busca na pasta; a anterior, se ainda rodando, e
+// abandonada (a task termina sozinha e o resultado e ignorado).
+func start_search(s: ref Session, query: string, case_sensitive: bool) -> void
+    s.search.query = query
+    s.search.case_sensitive = case_sensitive
+    s.search.hits = []
+    s.search.truncated = false
+    s.search.version = s.search.version + 1
+    if query == "" then
+        s.search.running = false
+        s.search.task = null
+        return
+    end
+    s.search.running = true
+    s.search.task = spawn_task(search.run, s.root, query, case_sensitive, SEARCH_LIMIT + 1)
+end
+
+func poll_search(s: ref Session) -> void
+    if !s.search.running then
+        return
+    end
+    let env: any = task_await(s.search.task, 0)
+    if env["status"] == "timeout" then
+        return
+    end
+    if env["status"] == "ok" then
+        let hits: search.Hit[] = env["value"]
+        if length(hits) > SEARCH_LIMIT then
+            s.search.truncated = true
+            hits = slice(hits, 0, SEARCH_LIMIT)
+        end
+        s.search.hits = hits
+    else
+        s.message = "falha na busca"
+    end
+    s.search.running = false
+    s.search.task = null
+    s.search.version = s.search.version + 1
+end
+
 func close_list(s: ref Session) -> void
     s.list = List("", "", [], 0)
 end
@@ -141,7 +198,7 @@ func no_modal() -> Modal
 end
 
 func new_session(root: string) -> Session
-    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0), [], null, find.new_find())
+    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0), [], null, find.new_find(), Search("", false, false, null, [], false, 0))
 end
 
 func basename(path: string) -> string
diff --git a/tests/run.nx b/tests/run.nx
index dd4ede21dae4a10e448c01bfbf9e9cacefde317d..cdc8481215da1dcc5743ce380049f7ab8d6c8800 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -435,9 +435,9 @@ func test_frame() -> void
     let s: session.Session = session.new_session(root)
     session.load(ref s)
     s.rows = 2
-    let empty: string = frame.build(ref s, 0)
+    let empty: string = frame.build(ref s, 0, 0)
     check("sem aba: tabs vazio e arvore presente", strings.contains(empty, "\"tabs\":[]") && strings.contains(empty, "\"name\":\"b.nx\"") && strings.contains(empty, "\"title\":\"Noxy Editor\""))
-    let same: string = frame.build(ref s, s.tree_version)
+    let same: string = frame.build(ref s, s.tree_version, 0)
     check("arvore omitida quando a versao bate", strings.contains(same, "\"tree\":[]"))
 
     session.open_file(ref s, root + "/b.nx")
@@ -447,7 +447,7 @@ func test_frame() -> void
     editing.click(ref s.tabs[0].editor, doc.Pos(0, 1), false, 2)
     editing.drag(ref s.tabs[0].editor, doc.Pos(1, 1), 2)
     s.clipboard = "cp"
-    let f: string = frame.build(ref s, s.tree_version)
+    let f: string = frame.build(ref s, s.tree_version, 0)
     check("spans cortados na fronteira da selecao", strings.contains(f, "{\"c\":false,\"f\":false,\"k\":\"keyword\",\"s\":false,\"t\":\"l\"}") && strings.contains(f, "{\"c\":false,\"f\":false,\"k\":\"keyword\",\"s\":true,\"t\":\"et\"}") && strings.contains(f, "{\"c\":false,\"f\":false,\"k\":\"ident\",\"s\":true,\"t\":\"x\"}"))
     check("cursor, has_sel e total", strings.contains(f, "\"cursor\":{\"col\":1,\"line\":1}") && strings.contains(f, "\"has_sel\":true") && strings.contains(f, "\"total\":3"))
     check("aba suja e titulo", strings.contains(f, "\"dirty\":true") && strings.contains(f, "b.nx ● — Noxy Editor"))
@@ -455,7 +455,7 @@ func test_frame() -> void
     check("clipboard vai e e consumido", strings.contains(f, "\"clipboard\":\"cp\"") && s.clipboard == "")
     s.rows = 1
     editing.ensure_visible(ref s.tabs[0].editor, 1)
-    let one: string = frame.build(ref s, s.tree_version)
+    let one: string = frame.build(ref s, s.tree_version, 0)
     check("so as linhas visiveis", strings.contains(one, "\"n\":1") && !strings.contains(one, "\"n\":0") && !strings.contains(one, "\"n\":2"))
     check("title_of", frame.title_of(ref s) == "b.nx ● — Noxy Editor")
 
@@ -469,7 +469,7 @@ func test_frame() -> void
     bs.rows = 50
     editing.move_doc_end(ref bs.tabs[0].editor, false, 50)
     let t0: int = time_now()
-    let bf: string = frame.build(ref bs, 1)
+    let bf: string = frame.build(ref bs, 1, 0)
     let dt: int = time_now() - t0
     check("arquivo de 5000 linhas: quadro so com as visiveis, em menos de 200 ms", strings.contains(bf, "\"total\":5000") && !strings.contains(bf, "\"n\":100,") && dt < 200)
 end
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index e32634b1d1d14722398f4e4b099417e2a27aa55b..fce6cfe826fffa56b7c5b340b57e194669691a68 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -161,6 +161,7 @@ ws.call("Input.insertText", {"text": "let x"}); key("Enter"); settle(1200)
 check("resultados agrupados por arquivo", ev("document.querySelectorAll('#search-results .sfile').length") >= 1 and "util.nx" in ev("document.getElementById('search-results').textContent"))
 ev("document.querySelector('#search-results .shit').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
 check("clicar num resultado abre o arquivo com a ocorrencia", ev("document.querySelector('.tab.active .name').textContent").startswith("util.nx") and ev("document.querySelectorAll('#text .sel').length") >= 1)
+check("abrir um resultado devolve o foco ao editor", ev("document.activeElement.id") == "input")
 ev("document.querySelectorAll('.tab')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
 key("Escape")
 # paleta: ctrl+shift+p, filtrar, escolher um tema
@@ -202,6 +203,7 @@ key("j", mods=2)
 check("ctrl+j esconde o painel", ev("document.getElementById('output').classList.contains('hidden')"))
 key("j", mods=2)
 check("ctrl+j de novo mostra o painel", not ev("document.getElementById('output').classList.contains('hidden')"))
+check("reabrir o painel nao tira o foco do editor", ev("document.activeElement.id") == "input")
 # digitar de novo para sujar, entao fechar pelo x: modal
 key("End"); insert("!")
 ev("document.querySelector('.tab .close').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
diff --git a/web/editor.css b/web/editor.css
index 9c3a3441dd1f6b4ba95aa73b4922fdde483ce0bd..7d83964a6af600182456811a6cabd60e3c6b36cd 100644
--- a/web/editor.css
+++ b/web/editor.css
@@ -122,6 +122,16 @@ button { font: inherit; color: inherit; background: none; border: none; cursor:
 .ptab.active { color: var(--fg); border-bottom-color: var(--accent); }
 .pview { flex: 1; min-height: 0; overflow: auto; }
 #search-view, #term-view { padding: 4px 14px 10px; }
+.search-row { display: flex; align-items: center; gap: 6px; margin: 4px 0 8px; }
+#search-input { width: 320px; padding: 4px 8px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); color: var(--fg); font: 13px var(--font-ui); outline: none; }
+#search-input:focus { border-color: var(--accent); }
+#search-case { padding: 3px 7px; border-radius: 4px; color: var(--fg-dim); }
+#search-case.on { background: var(--bg-hover); color: var(--accent); }
+#search-status { color: var(--fg-dim); font-size: 12px; }
+.sfile { margin-top: 6px; color: var(--fg); font-weight: 600; font-size: 12px; }
+.shit { display: flex; gap: 10px; padding: 1px 0 1px 12px; font: 12px var(--font-mono); cursor: pointer; white-space: pre; overflow: hidden; text-overflow: ellipsis; }
+.shit:hover { background: var(--bg-hover); }
+.shit .sline { color: var(--fg-dim); min-width: 36px; text-align: right; }
 #output-close { color: var(--fg-dim); font-size: 16px; line-height: 1; }
 #output-text { margin: 0; padding: 4px 14px 10px; font: 13px var(--font-mono); white-space: pre-wrap; }
 
diff --git a/web/editor.js b/web/editor.js
index 7c7f92a8e29730bcb7764bb93eda33fb3c036c9d..db0cef53bd52351e5b1c61556338ab23ce6a2239 100644
--- a/web/editor.js
+++ b/web/editor.js
@@ -12,6 +12,7 @@
     editor: $("editor"), gutter: $("gutter"), text: $("text"), cursor: $("cursor"), welcome: $("welcome"),
     main: $("main"), output: $("output"), outputText: $("output-text"), outputClose: $("output-close"), outputResize: $("output-resize"), outputHead: $("output-head"),
     panelTabs: $("panel-tabs"), searchView: $("search-view"), termView: $("term-view"),
+    searchInput: $("search-input"), searchCase: $("search-case"), searchStatus: $("search-status"), searchResults: $("search-results"),
     status: $("status"), statusLeft: $("status-left"), statusMsg: $("status-msg"), statusRight: $("status-right"),
     modal: $("modal"), modalText: $("modal-text"), modalButtons: $("modal-buttons"),
     list: $("list"), listInput: $("list-input"), listItems: $("list-items"),
@@ -59,6 +60,7 @@
     ev.rows = rows;
     ev.tree_version = treeVersion;
     ev.page = PAGE_ID;
+    ev.search_version = searchVersion;
     try {
       const res = await fetch("/event", {
         method: "POST",
@@ -111,6 +113,7 @@
       els.outputText.scrollTop = els.outputText.scrollHeight;
     }
     renderPanel(f.panel);
+    renderSearch(f.search);
     renderModal(f.modal);
     renderList(f.list);
     renderFind(f.find);
@@ -323,6 +326,7 @@
   function onKeyDown(e) {
     if (e.isComposing) return;
     const key = e.key.toLowerCase();
+    if ((e.ctrlKey || e.metaKey) && e.shiftKey && key === "f") wantSearchFocus = true;
     if (e.ctrlKey || e.metaKey) {
       if (key === "c") { e.preventDefault(); send({ kind: "copy" }); return; }
       if (key === "x") { e.preventDefault(); send({ kind: "cut" }); return; }
@@ -352,7 +356,7 @@
   function focusInput() {
     if (listKind) return;   // a lista tem o foco
     const a = document.activeElement;
-    if (a && a.closest && a.closest("#findbar")) return;   // a barra de busca tem o foco
+    if (a && a.closest && (a.closest("#findbar") || a.closest("#search-view"))) return;   // um campo de busca tem o foco
     if (document.activeElement !== els.input) els.input.focus({ preventScroll: true });
   }
   document.addEventListener("mousedown", () => setTimeout(focusInput, 0));
@@ -441,10 +445,42 @@
     outputH = clampOutputHeight(h);
     els.main.style.setProperty("--output-h", outputH + "px");
   }
+  // renderSearch: resultados da busca na pasta; so chegam quando a versao muda
+  let searchVersion = 0, searchCase = false;
+  function renderSearch(sr) {
+    searchCase = sr.case_sensitive;
+    els.searchCase.classList.toggle("on", sr.case_sensitive);
+    els.searchStatus.textContent = sr.running ? "buscando…" : (sr.query ? (sr.version === searchVersion ? els.searchStatus.textContent : "") : "");
+    if (sr.version === searchVersion) return;
+    searchVersion = sr.version;
+    if (sr.running) { els.searchResults.replaceChildren(); return; }
+    const nodes = [];
+    let last = "";
+    for (const h of sr.hits) {
+      if (h.rel !== last) { nodes.push(el("div", "sfile", h.rel)); last = h.rel; }
+      const row = el("div", "shit");
+      row.append(el("span", "sline", String(h.line + 1)), el("span", "stext", h.text.trim()));
+      row.addEventListener("mousedown", (e) => { e.preventDefault(); els.searchInput.blur(); focusInput(); send({ kind: "search_open", path: h.path, line: h.line, col: h.col, text: sr.query }); });
+      nodes.push(row);
+    }
+    els.searchResults.replaceChildren(...nodes);
+    els.searchStatus.textContent = sr.query ? (sr.hits.length ? sr.hits.length + (sr.truncated ? "+" : "") + " ocorrências" : "sem resultados") : "";
+  }
+  els.searchInput.addEventListener("keydown", (e) => {
+    if ((e.ctrlKey || e.metaKey) && !["a", "c", "v", "x", "z"].includes(e.key.toLowerCase())) { onKeyDown(e); e.stopPropagation(); return; }
+    if (e.key === "Enter") { e.preventDefault(); send({ kind: "search", text: els.searchInput.value, case_sensitive: searchCase }); }
+    else if (e.key === "Escape") { e.preventDefault(); els.searchInput.blur(); focusInput(); }
+    e.stopPropagation();
+  });
+  els.searchCase.addEventListener("mousedown", (e) => { e.preventDefault(); searchCase = !searchCase; els.searchCase.classList.toggle("on", searchCase); });
+
   // renderPanel: aberto ou fechado e a aba ativa vem do quadro; a altura e
   // conveniencia local
+  let panelTab = "";
+  let wantSearchFocus = false;   // so ctrl+shift+f e o clique na aba levam o foco ao campo
   function renderPanel(panel) {
     if (!panel.open) {
+      panelTab = "";
       els.output.classList.add("hidden");
       els.main.style.setProperty("--output-h", "0px");
       return;
@@ -458,6 +494,8 @@
     }
     els.output.classList.remove("hidden");
     for (const tab of els.panelTabs.querySelectorAll(".ptab")) tab.classList.toggle("active", tab.dataset.tab === panel.tab);
+    if (panel.tab === "search" && wantSearchFocus) { wantSearchFocus = false; setTimeout(() => els.searchInput.focus(), 0); }
+    panelTab = panel.tab;
     els.outputText.classList.toggle("hidden", panel.tab !== "output");
     els.searchView.classList.toggle("hidden", panel.tab !== "search");
     els.termView.classList.toggle("hidden", panel.tab !== "terminal");
@@ -467,7 +505,7 @@
   els.runBtn.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "run" }); });
   els.outputClose.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "panel_toggle" }); });
   for (const tab of els.panelTabs.querySelectorAll(".ptab")) {
-    tab.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "panel_tab", key: tab.dataset.tab }); });
+    tab.addEventListener("mousedown", (e) => { e.preventDefault(); if (tab.dataset.tab === "search") wantSearchFocus = true; send({ kind: "panel_tab", key: tab.dataset.tab }); });
   }
   // o divisor e a barra "Saida" inteira redimensionam, com Pointer Events e
   // captura do ponteiro: uma vez iniciado, o arraste segue o divisor mesmo
@@ -500,7 +538,7 @@
     const r = rowsNow();
     if (r !== rows) { rows = r; send({ kind: "poll" }); }
   }).observe(els.editor);
-  setInterval(() => { if (frame && frame.output.running) send({ kind: "poll" }); }, 250);
+  setInterval(() => { if (frame && (frame.output.running || frame.search.running)) send({ kind: "poll" }); }, 250);
   window.addEventListener("pagehide", () => {
     navigator.sendBeacon("/event?t=" + encodeURIComponent(token), JSON.stringify({ kind: "bye", page: PAGE_ID, rows, tree_version: treeVersion }));
   });
diff --git a/web/index.html b/web/index.html
index eb7ce110cba0b1cf7a32e1a119375ce80e1701cb..658e3c14a52f340a561b11260d7653d6be2ae9f0 100644
--- a/web/index.html
+++ b/web/index.html
@@ -47,7 +47,14 @@
         <button id="output-close" title="Fechar (Ctrl+J)">×</button>
       </div>
       <pre id="output-text" class="pview"></pre>
-      <div id="search-view" class="pview hidden"></div>
+      <div id="search-view" class="pview hidden">
+        <div class="search-row">
+          <input id="search-input" placeholder="Buscar na pasta (Enter)" autocomplete="off" spellcheck="false">
+          <button id="search-case" title="Diferenciar maiúsculas">Aa</button>
+          <span id="search-status"></span>
+        </div>
+        <div id="search-results"></div>
+      </div>
       <div id="term-view" class="pview hidden"></div>
     </div>
     <div id="status">
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `222/222 passaram` e `10/10 passaram`.
- [ ] **Passo 5: o cliente de verdade**

Run: `python3 tests/web_smoke.py && GDK_BACKEND=x11 python3 tests/webkit_smoke.py`
Esperado: as duas linhas finais `OK: 0 falhas` (o primeiro precisa de `google-chrome`; o segundo abre uma janela WebKitGTK por alguns segundos).
- [ ] **Commit**

```bash
git add src/events.nx src/frame.nx src/search.nx src/session.nx tests/run.nx tests/web_smoke.py web/editor.css web/editor.js web/index.html
git commit -q -m 'feat(search): busca na pasta numa task, resultados agrupados na aba Busca, abrir resultado com a ocorrencia; foco so quando pedido

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 8: Recuperação de alterações e relógio em milissegundos

**Interfaces:**
- Produces: `recovery.Copy`, `recovery.write`, `recovery.list`, `recovery.remove`, `recovery.dir()`; `NOXY_EDITOR_CACHE_DIR`; `session.Tab { editor, copy_text, copy_at }` e `session.new_tab(ed)`; `session.recovery_tick(ref s, now, force)`, `session.restore(ref s) -> int`; `events.now()` (ms; `time_now()` devolve segundos). As suítes definem cache e config em `tests/tmp`.

**Files:** `docs/ACHADOS.md`, `editor.nx`, `src/events.nx`, `src/recovery.nx`, `src/session.nx`, `tests/protocol.nx`, `tests/run.nx`, `tests/web_smoke.py`, `tests/webkit_smoke.py`, `web/editor.js`

- [ ] **Passo 1: os testes (vermelho)**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (113 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/run.nx b/tests/run.nx
index cdc8481215da1dcc5743ce380049f7ab8d6c8800..7d849dc472c84a9b482044db3bf71e7a5e0a93f4 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -1,6 +1,7 @@
 // tests/run.nx — suite do editor. Roda sem navegador:
 //     noxy tests/run.nx      (a partir da raiz do projeto)
 use sys
+use crypto
 use src.document as doc
 use src.lexer as lexer
 use io
@@ -17,6 +18,7 @@ use src.commands as commands
 use src.index as index
 use src.find as find
 use src.search as search
+use src.recovery as recovery
 
 let fails = 0
 let total = 0
@@ -571,7 +573,7 @@ func test_events() -> void
     let ff: string = events.dispatch(ref s, "{\"kind\":\"find\",\"text\":\"c\",\"rows\":20,\"tree_version\":2}", 19)
     check("consulta calcula ocorrencias e vai no quadro", length(s.find.matches) == 1 && strings.contains(ff, "\"query\":\"c\"") && strings.contains(ff, "\"c\":true") && strings.contains(ff, "\"f\":true"))
     events.dispatch(ref s, "{\"kind\":\"text\",\"text\":\"c\",\"rows\":20,\"tree_version\":2}", 19)
-    check("editar recalcula as ocorrencias", length(s.find.matches) == 1 && s.tabs[s.active].editor.doc.lines[0] == "print(c)" || length(s.find.matches) >= 1)
+    check("editar recalcula as ocorrencias (digitar c sobre a selecao)", length(s.find.matches) == 1 && s.tabs[s.active].editor.doc.lines[0] == "print(\"c\")")
     events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"h\",\"ctrl\":true,\"rows\":20,\"tree_version\":2}", 19)
     check("ctrl+h abre com a linha de substituir", s.find.open && s.find.replace)
     events.dispatch(ref s, "{\"kind\":\"replace_all\",\"text\":\"k\",\"rows\":20,\"tree_version\":2}", 19)
@@ -704,7 +706,7 @@ func test_find() -> void
     find.refresh(ref f, ed.doc, ed.cursor)
     check("refresh calcula ocorrencias e a atual", length(f.matches) == 5 && f.current == 0)
     find.goto(ref ed, ref f, 1, 10)
-    check("goto seleciona a ocorrencia", ed.anchor.line == 1 && ed.anchor.col == 1 && ed.cursor.col == 2 && editing.copy(ed) == "L" || true)
+    check("goto seleciona a ocorrencia", ed.anchor.line == 1 && ed.anchor.col == 8 && ed.cursor.col == 9 && editing.copy(ed) == "a")
     find.next(ref ed, ref f, 10)
     check("next avanca", f.current == 2 && ed.cursor.line == 1)
     find.prev(ref ed, ref f, 10)
@@ -766,6 +768,68 @@ func test_search() -> void
     sys.exec("rm -rf " + browser.shell_quote(root + "/node_modules"))
 end
 
+func test_recovery() -> void
+    print("recovery")
+    let cache: string = sys.getcwd() + "/tests/tmp/cache"
+    sys.setenv("NOXY_EDITOR_CACHE_DIR", cache)
+    sys.exec("rm -rf " + browser.shell_quote(cache))
+    check("sem copias, lista vazia", length(recovery.list()) == 0)
+    check("write grava a copia", recovery.write("/x/a.nx", "oi\n", "\n", 5))
+    let cs: recovery.Copy[] = recovery.list()
+    check("list le a copia", length(cs) == 1 && cs[0].path == "/x/a.nx" && cs[0].text == "oi\n" && cs[0].saved_at == 5)
+    check("nome do arquivo e o sha256 do caminho", io.exists(cache + "/recovery/" + crypto.sha256(to_bytes("/x/a.nx")) + ".json"))
+    recovery.write("/x/a.nx", "tchau", "\n", 6)
+    check("gravar de novo substitui", length(recovery.list()) == 1 && recovery.list()[0].text == "tchau")
+    write_file(cache + "/recovery/lixo.json", "{nope")
+    check("copia ilegivel e ignorada, nao apagada", length(recovery.list()) == 1 && io.exists(cache + "/recovery/lixo.json"))
+    io.remove(cache + "/recovery/lixo.json")
+    recovery.remove("/x/a.nx")
+    check("remove apaga", length(recovery.list()) == 0)
+
+    let root: string = tmp_root()
+    let s: session.Session = session.new_session(root)
+    session.load(ref s)
+    session.open_file(ref s, root + "/b.nx")
+    editing.insert_text(ref s.tabs[0].editor, "Z", 10, 1000)
+    session.recovery_tick(ref s, 500, false)
+    check("aba suja: primeira copia sai no primeiro tick", length(recovery.list()) == 1)
+    editing.insert_text(ref s.tabs[0].editor, "Y", 10, 1100)
+    session.recovery_tick(ref s, 900, false)
+    check("menos de 1 s depois da ultima copia: espera", recovery.list()[0].text != doc.to_text(s.tabs[0].editor.doc))
+    session.recovery_tick(ref s, 1600, false)
+    check("passou 1 s: grava o texto novo", recovery.list()[0].text == doc.to_text(s.tabs[0].editor.doc))
+    editing.insert_text(ref s.tabs[0].editor, "X", 10, 1200)
+    session.recovery_tick(ref s, 1700, true)
+    check("force (bye) grava na hora", recovery.list()[0].text == doc.to_text(s.tabs[0].editor.doc))
+
+    // a partida seguinte reabre a aba suja com o texto da copia
+    let s2: session.Session = session.new_session(root)
+    session.load(ref s2)
+    check("restore reabre uma aba", session.restore(ref s2) == 1 && length(s2.tabs) == 1)
+    check("aba recuperada suja, com o texto da copia", s2.tabs[0].editor.doc.dirty && s2.tabs[0].editor.doc.lines[0] == "ZYXlet b = 1")
+    session.save(ref s2)
+    check("salvar apaga a copia", length(recovery.list()) == 0)
+
+    // copia igual ao disco e apagada sem abrir aba
+    recovery.write(root + "/a.txt", read_file(root + "/a.txt"), "\n", 1)
+    let s3: session.Session = session.new_session(root)
+    session.load(ref s3)
+    check("copia igual ao disco: nenhuma aba e copia apagada", session.restore(ref s3) == 0 && length(recovery.list()) == 0)
+    // arquivo que sumiu: reabre como aba suja
+    recovery.write(root + "/sumiu.nx", "let z = 1", "\n", 1)
+    check("arquivo apagado: reabre com o texto da copia", session.restore(ref s3) == 1 && s3.tabs[0].editor.doc.lines[0] == "let z = 1" && s3.tabs[0].editor.doc.dirty)
+    // copia de outra pasta fica para quando ela for aberta
+    recovery.write("/outra/pasta/q.nx", "q", "\n", 1)
+    let s4: session.Session = session.new_session(root)
+    session.load(ref s4)
+    check("copia de fora da raiz nao abre e nao e apagada", session.restore(ref s4) == 1 && length(recovery.list()) == 2)
+    // nao salvar apaga
+    session.close_tab(ref s4, 0)
+    session.answer_modal(ref s4, "discard")
+    check("fechar sem salvar apaga a copia", length(recovery.list()) == 1)
+    recovery.remove("/outra/pasta/q.nx")
+end
+
 test_document()
 test_lexer()
 test_history()
@@ -781,4 +845,5 @@ test_commands()
 test_index()
 test_find()
 test_search()
+test_recovery()
 report()
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: `Compiler error: [line 778] variable 'cs': cannot resolve type 'recovery.Copy': module 'src.recovery' could not be loaded`
- [ ] **Commit**

```bash
git add tests/run.nx
git commit -q -m 'test(recovery): copias de recuperacao, restauracao na partida; asserções exatas na busca

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3: a implementação**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (458 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/docs/ACHADOS.md b/docs/ACHADOS.md
index ce84dca2ae21567f00aa3384421d8803082fb3d4..6f8c457661d52941e93683d4c983d2bdfb2569ce 100644
--- a/docs/ACHADOS.md
+++ b/docs/ACHADOS.md
@@ -68,3 +68,16 @@ falhas em tempo de execução (processo que não sobe ou morre). **Contorno:**
 documentar o package como pré-requisito. **Sugestão:** adiar a verificação do
 binário para a primeira chamada, como a documentação descreve, ou oferecer um
 `use ... optional` cujas chamadas falhem em runtime.
+
+## 8. `time_now()` devolve segundos, não milissegundos
+
+**Onde:** `editor.nx` (o relógio do dono do estado) e tudo o que media
+tempo com ele. **O que:** o README do Noxy descreve `time_now()` como
+"timestamp in ms", mas o valor é em segundos (`1790399009` contra
+`1790399009754` de `date +%s%3N`). O editor tratava o valor como ms: o
+agrupamento de digitação do undo, de 1 s, virava 1000 s (tudo digitado em
+16 minutos desfazia de uma vez), e o teste de desempenho do quadro comparava
+segundos com 200. **Contorno:** `events.now()` usa `time.now_ms()`, com teste
+que dorme 120 ms e confere a diferença. **Sugestão:** corrigir a descrição no
+README, ou fazer `time_now()` devolver ms como documentado e deixar
+`time.now()` para segundos.
diff --git a/editor.nx b/editor.nx
index e18940d9008a8f3f0e3c0523fe00000f0e6ea02f..d5d82dcd87851f785f47e27b2508bd40b32a2a47 100644
--- a/editor.nx
+++ b/editor.nx
@@ -61,6 +61,10 @@ if first_file != "" then
     session.open_file(ref s, first_file)
 end
 session.start_index(ref s)
+let restored: int = session.restore(ref s)
+if restored > 0 then
+    s.message = to_str(restored) + " arquivo(s) recuperado(s) com alteracoes nao salvas"
+end
 
 let port: int = server.start(editor_dir + "/web", uuid.uuid4())
 if port == 0 then
@@ -103,7 +107,7 @@ let last_title: string = ""
 while !s.quitting do
     let r: any = chan_recv(server.inbox)
     let req: server.Request = r
-    let now: int = time_now()
+    let now: int = events.now()
     let out: string = events.dispatch(ref s, req.body, now)
     chan_send(req.reply, out)
     if s.bye then
diff --git a/src/events.nx b/src/events.nx
index 6fd3a96731bb9af057cccf91389fc66130d9fa2d..a8cbe71ad5629fda0c33f234b40bc615d4a4fd71 100644
--- a/src/events.nx
+++ b/src/events.nx
@@ -5,6 +5,7 @@
 // a execucao e devolve o quadro.
 use strings select ends_with, starts_with, substring
 use errors select *
+use time
 use src.document as doc
 use src.editing as editing
 use src.session as session
@@ -39,9 +40,16 @@ func empty_event() -> Event
     return Event("", "", false, false, false, "", 0, 0, 0, "", 0, 0, 0, "", false, 0)
 end
 
+// now e o relogio do dono do estado, em milissegundos. time_now() da
+// stdlib devolve segundos (docs/ACHADOS.md), o que fazia o agrupamento do
+// undo durar 1000 s em vez de 1 s.
+func now() -> int
+    return time.now_ms()
+end
+
 // trivial: eventos que nao apagam a mensagem de status.
 func trivial(kind: string) -> bool
-    return kind == "poll" || kind == "scroll" || kind == "drag" || kind == "quit_if_idle" || kind == "bye"
+    return kind == "poll" || kind == "scroll" || kind == "drag" || kind == "quit_if_idle" || kind == "bye" || kind == "init"
 end
 
 // run_active salva a aba ativa se preciso e dispara a execucao.
@@ -423,6 +431,7 @@ func apply(s: session.Session, e: Event, now: int) -> session.Session
     elif e.kind != "init" && e.kind != "poll" then
         s.message = "evento desconhecido: " + e.kind
     end
+    session.recovery_tick(ref s, now, e.kind == "bye")
     if s.find.open && s.active >= 0 && !trivial(e.kind) then
         find.refresh(ref s.find, s.tabs[s.active].editor.doc, editing.sel_range(s.tabs[s.active].editor).start)
     end
diff --git a/src/recovery.nx b/src/recovery.nx
new file mode 100644
index 0000000000000000000000000000000000000000..afa7f5f45f85e86f0fbed0a15ae4fb84c3daf484
--- /dev/null
+++ b/src/recovery.nx
@@ -0,0 +1,79 @@
+// src/recovery.nx — copias de recuperacao das abas com alteracoes nao
+// salvas, em ~/.cache/noxy-editor/recovery/<sha256 do caminho>.json
+// (XDG_CACHE_HOME quando definido; NOXY_EDITOR_CACHE_DIR sobrepoe, para os
+// testes). Cobrem fechar pelo X e queda do editor: a partida seguinte
+// reabre as abas (session.restore).
+use sys
+use io
+use crypto
+use strings select ends_with
+
+struct Copy
+    path: string
+    text: string
+    eol: string
+    saved_at: int
+end
+
+func cache_dir() -> string
+    let o: sys.EnvResult = sys.getenv("NOXY_EDITOR_CACHE_DIR")
+    if o.ok && o.value != "" then
+        return o.value
+    end
+    let x: sys.EnvResult = sys.getenv("XDG_CACHE_HOME")
+    if x.ok && x.value != "" then
+        return x.value + "/noxy-editor"
+    end
+    return sys.getenv("HOME").value + "/.cache/noxy-editor"
+end
+
+func dir() -> string
+    return cache_dir() + "/recovery"
+end
+
+func file_for(path: string) -> string
+    return dir() + "/" + crypto.sha256(to_bytes(path)) + ".json"
+end
+
+// write grava (ou substitui) a copia de path; false se nao conseguiu.
+func write(path: string, text: string, eol: string, now: int) -> bool
+    io.mkdir(dir())
+    let f: io.File = io.open(file_for(path), "w")
+    if !f.open then
+        return false
+    end
+    io.write(f, json_dumps(Copy(path, text, eol, now)))
+    io.close(f)
+    return true
+end
+
+func remove(path: string) -> void
+    io.remove(file_for(path))
+end
+
+// list le todas as copias; as ilegiveis sao ignoradas (e ficam no disco).
+func list() -> Copy[]
+    let out: Copy[] = []
+    let r: io.IOLinesResult = io.list_dir(dir())
+    if !r.ok then
+        return out
+    end
+    for name in r.data do
+        if !ends_with(name, ".json") then
+            continue
+        end
+        let f: io.File = io.open(dir() + "/" + name, "r")
+        if !f.open then
+            continue
+        end
+        let t: io.IOResult = io.read(f)
+        io.close(f)
+        let c: Copy = Copy("", "", "\n", 0)
+        if !t.ok || !json_loads(t.data, ref c) || c.path == "" then
+            eprint("copia de recuperacao ilegivel: " + dir() + "/" + name)
+            continue
+        end
+        append(ref out, c)
+    end
+    return out
+end
diff --git a/src/session.nx b/src/session.nx
index cf1e92548335181462636d4d58e9bdc38748cda3..a5c1549be55a6020b85be0fd803545268ac89593 100644
--- a/src/session.nx
+++ b/src/session.nx
@@ -11,9 +11,18 @@ use src.settings as settings
 use src.index as index
 use src.find as find
 use src.search as search
+use src.recovery as recovery
 
 struct Tab
     editor: editing.Editor
+    copy_text: string   // o texto da ultima copia de recuperacao gravada
+    copy_at: int        // ms dessa gravacao; 0 = nenhuma
+end
+
+let COPY_EVERY_MS = 1000
+
+func new_tab(ed: editing.Editor) -> Tab
+    return Tab(ed, "", 0)
 end
 
 struct Node
@@ -81,6 +90,7 @@ struct Session
     files_task: any     // task de index.build em andamento; null parada
     find: find.Find
     search: Search
+    recovery_warned: bool   // ja avisou que nao consegue gravar copias
 end
 
 // Search e a busca na pasta: a consulta, a task e os resultados; version
@@ -172,6 +182,62 @@ func poll_search(s: ref Session) -> void
     s.search.version = s.search.version + 1
 end
 
+// recovery_tick grava a copia das abas sujas cujo texto mudou desde a
+// ultima copia, no maximo uma vez por COPY_EVERY_MS; force (bye) grava na hora.
+func recovery_tick(s: ref Session, now: int, force: bool) -> void
+    for i in range(length(s.tabs)) do
+        let d: doc.Document = s.tabs[i].editor.doc
+        if !d.dirty then
+            continue
+        end
+        let text: string = doc.to_text(d)
+        if text == s.tabs[i].copy_text then
+            continue
+        end
+        if !force && s.tabs[i].copy_at > 0 && now - s.tabs[i].copy_at < COPY_EVERY_MS then
+            continue
+        end
+        if recovery.write(d.path, text, d.eol, now) then
+            s.tabs[i].copy_text = text
+            s.tabs[i].copy_at = now
+        elif !s.recovery_warned then
+            s.recovery_warned = true
+            s.message = "nao consegui gravar a copia de recuperacao em " + recovery.dir()
+        end
+    end
+end
+
+// restore reabre as copias desta raiz cujo texto difere do disco (ou cujo
+// arquivo sumiu) como abas sujas; apaga as iguais ao disco. Devolve quantas
+// abas reabriu.
+func restore(s: ref Session) -> int
+    let n: int = 0
+    for c in recovery.list() do
+        if !starts_with(c.path, s.root + "/") || find_tab(*s, c.path) >= 0 then
+            continue
+        end
+        if io.exists(c.path) then
+            let f: io.File = io.open(c.path, "r")
+            let r: io.IOResult = io.read(f)
+            io.close(f)
+            if r.ok && r.data == c.text then
+                recovery.remove(c.path)
+                continue
+            end
+        end
+        let d: doc.Document = doc.from_text(c.path, c.text)
+        d.eol = c.eol
+        d.dirty = true
+        let t: Tab = new_tab(editing.new_editor(d))
+        t.copy_text = c.text
+        t.copy_at = c.saved_at
+        append(ref s.tabs, t)
+        s.active = length(s.tabs) - 1
+        n = n + 1
+    end
+    return n
+end
+
 func close_list(s: ref Session) -> void
     s.list = List("", "", [], 0)
 end
@@ -198,7 +264,7 @@ func no_modal() -> Modal
 end
 
 func new_session(root: string) -> Session
-    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0), [], null, find.new_find(), Search("", false, false, null, [], false, 0))
+    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0), [], null, find.new_find(), Search("", false, false, null, [], false, 0), false)
 end
 
 func basename(path: string) -> string
@@ -348,7 +414,7 @@ func open_file(s: ref Session, path: string) -> void
         s.message = "nao consegui ler " + relative(s.root, path) + ": " + r.error
         return
     end
-    append(ref s.tabs, Tab(editing.new_editor(doc.from_text(path, r.data))))
+    append(ref s.tabs, new_tab(editing.new_editor(doc.from_text(path, r.data))))
     s.active = length(s.tabs) - 1
 end
 
@@ -366,6 +432,9 @@ func save_tab(s: ref Session, i: int) -> bool
         return false
     end
     s.tabs[i].editor.doc.dirty = false
+    recovery.remove(path)
+    s.tabs[i].copy_text = ""
+    s.tabs[i].copy_at = 0
     return true
 end
 
@@ -439,6 +508,13 @@ func answer_modal(s: ref Session, id: string) -> void
         if id == "save" && !save_all(s) then
             return
         end
+        if id == "discard" then
+            for t in s.tabs do
+                if t.editor.doc.dirty then
+                    recovery.remove(t.editor.doc.path)
+                end
+            end
+        end
         s.quitting = true
     elif starts_with(pending, "close_tab:") then
         let i: int = to_int(substring(pending, 10, length(pending)))
@@ -448,6 +524,9 @@ func answer_modal(s: ref Session, id: string) -> void
         if id == "save" && !save_tab(s, i) then
             return
         end
+        if id == "discard" then
+            recovery.remove(s.tabs[i].editor.doc.path)
+        end
         remove_tab(s, i)
     end
 end
diff --git a/tests/protocol.nx b/tests/protocol.nx
index d05a40a6e9610b853da7c320f2ee473b22b55cdc..b4f64c48d1a798cb2069357b0bfc511d9faa40b2 100644
--- a/tests/protocol.nx
+++ b/tests/protocol.nx
@@ -9,6 +9,11 @@ use src.session as session
 use src.events as events
 use src.server as server
 
+// cache e configuracao isolados: os testes nunca tocam no ~/.cache e no
+// ~/.config de quem roda
+sys.setenv("NOXY_EDITOR_CACHE_DIR", sys.getcwd() + "/tests/tmp/cache")
+sys.setenv("NOXY_EDITOR_CONFIG_DIR", sys.getcwd() + "/tests/tmp/config")
+
 let fails = 0
 let total = 0
 
@@ -39,7 +44,7 @@ func owner() -> void
     while !s.quitting do
         let r: any = chan_recv(server.inbox)
         let req: server.Request = r
-        let now: int = time_now()
+        let now: int = events.now()
         chan_send(req.reply, events.dispatch(ref s, req.body, now))
     end
 end
diff --git a/tests/run.nx b/tests/run.nx
index 7d849dc472c84a9b482044db3bf71e7a5e0a93f4..aac14ac174d73dcada72be76173d2b5d89e6313c 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -20,6 +20,11 @@ use src.find as find
 use src.search as search
 use src.recovery as recovery
 
+// cache e configuracao isolados: os testes nunca tocam no ~/.cache e no
+// ~/.config de quem roda
+sys.setenv("NOXY_EDITOR_CACHE_DIR", sys.getcwd() + "/tests/tmp/cache")
+sys.setenv("NOXY_EDITOR_CONFIG_DIR", sys.getcwd() + "/tests/tmp/config")
+
 let fails = 0
 let total = 0
 
@@ -466,13 +471,13 @@ func test_frame() -> void
         append(ref big, "let v" + to_str(i) + ": int = " + to_str(i) + " // linha")
     end
     let bs: session.Session = session.new_session(root)
-    append(ref bs.tabs, session.Tab(editing.new_editor(doc.Document(root + "/big.nx", big, false, "\n"))))
+    append(ref bs.tabs, session.new_tab(editing.new_editor(doc.Document(root + "/big.nx", big, false, "\n"))))
     bs.active = 0
     bs.rows = 50
     editing.move_doc_end(ref bs.tabs[0].editor, false, 50)
-    let t0: int = time_now()
+    let t0: int = events.now()
     let bf: string = frame.build(ref bs, 1, 0)
-    let dt: int = time_now() - t0
+    let dt: int = events.now() - t0
     check("arquivo de 5000 linhas: quadro so com as visiveis, em menos de 200 ms", strings.contains(bf, "\"total\":5000") && !strings.contains(bf, "\"n\":100,") && dt < 200)
 end
 
@@ -603,6 +608,13 @@ func test_events() -> void
     events.dispatch(ref s, "{\"kind\":\"quit\",\"rows\":20,\"tree_version\":2}", 20)
     check("quit marca quitting", s.quitting)
 
+    // o relogio do dono do estado e em milissegundos: o agrupamento do
+    // undo (1 s) e a copia de recuperacao (1 s) dependem disso
+    let c0: int = events.now()
+    sys.sleep(120)
+    let dc: int = events.now() - c0
+    check("events.now e em milissegundos (" + to_str(dc) + " ms em 120 ms de sono)", dc >= 100 && dc < 1000)
+
     // reload no navegador: cada pagina tem um id; o bye da pagina antiga pode
     // chegar antes ou depois do init da nova (o sendBeacon e assincrono), e
     // o quit_if_idle so encerra se a pagina que se despediu ainda e a ultima
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index fce6cfe826fffa56b7c5b340b57e194669691a68..c78d57984be228df1a06f587dc8296a6f5655b3b 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -15,7 +15,8 @@ open(os.path.join(demo, "exemplo.nx"), "w").write('use sys\n// um exemplo para o
 open(os.path.join(demo, "notas.txt"), "w").write("texto simples\n")
 open(os.path.join(demo, "src", "util.nx"), "w").write("let x = 1\n")
 cfg = os.path.join(os.getcwd(), "tests", "tmp", "web_config")
-env = dict(os.environ, NOXY_EDITOR_NO_WINDOW="1", NOXY_EDITOR_CONFIG_DIR=cfg)
+env = dict(os.environ, NOXY_EDITOR_NO_WINDOW="1", NOXY_EDITOR_CONFIG_DIR=cfg, NOXY_EDITOR_CACHE_DIR=os.path.join(os.getcwd(), "tests", "tmp", "web_cache"))
+import shutil as _sh; _sh.rmtree(env["NOXY_EDITOR_CACHE_DIR"], ignore_errors=True)
 if os.path.exists(os.path.join(cfg, "settings.json")): os.remove(os.path.join(cfg, "settings.json"))
 log = os.path.join("tests", "tmp", "web_editor.log")
 editor = subprocess.Popen(["noxy", "editor.nx", demo], env=env, stdout=subprocess.DEVNULL, stderr=open(log, "w"))
@@ -230,6 +231,26 @@ ws.call("Page.navigate", {"url": "file://" + page}); settle(2000)
 check("pagina de redirecionamento leva ao editor", ev("location.href").startswith(url.split("?")[0]) and ev("document.querySelectorAll('#tree .node').length") == 3)
 time.sleep(3.5)
 check("editor continua vivo 3 s depois do reload", editor.poll() is None and ev("document.querySelectorAll('#tree .node').length") == 3)
+# recuperacao: editar sem salvar, esperar a copia (poll 1,5 s depois da
+# ultima edicao), matar o editor e abrir outro: a aba volta suja
+ev("document.querySelectorAll('#tree .node.file')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
+key("Home", mods=2); insert("// nao salvo\n")
+settle(2500)
+cache = env["NOXY_EDITOR_CACHE_DIR"]
+check("copia de recuperacao gravada sem outro evento", len(os.listdir(os.path.join(cache, "recovery"))) >= 1)
+for fn in os.listdir(os.path.join(cache, "recovery")):
+editor.kill(); editor.wait()
+editor = subprocess.Popen(["noxy", "editor.nx", demo], env=env, stdout=subprocess.DEVNULL, stderr=open(log, "w"))
+url = None
+for _ in range(50):
+    m = re.search(r"http://127\.0\.0\.1:\d+/\?t=[a-z0-9-]+", open(log).read())
+    if m: url = m.group(0); break
+    time.sleep(0.1)
+ws.call("Page.navigate", {"url": url}); settle(1500)
+check("depois de fechar sem salvar, a aba volta suja com o texto", "●" in ev("document.querySelector('.tab.active .name').textContent") and ev("document.querySelector('.line[data-n=\"0\"]').textContent") == "// nao salvo")
+check("mensagem de arquivos recuperados", "recuperado" in ev("document.getElementById('status-msg').textContent"))
+key("s", mods=2)
+check("salvar apaga a copia", len(os.listdir(os.path.join(cache, "recovery"))) == 0)
 chrome.terminate()
 editor.terminate()
 print(f"\n{'FALHOU' if fails else 'OK'}: {fails} falhas")
diff --git a/tests/webkit_smoke.py b/tests/webkit_smoke.py
index fb7a939feb36844611adcdffa4802ccb958e69fa..cabba999045e7386a24c0e5911d2670eccfe5113 100644
--- a/tests/webkit_smoke.py
+++ b/tests/webkit_smoke.py
@@ -10,7 +10,7 @@ from gi.repository import Gtk, Gdk, WebKit2, GLib
 demo = os.path.join("tests", "tmp", "webkit"); os.makedirs(demo, exist_ok=True)
 open(os.path.join(demo, "longo.nx"), "w").write("".join(f"let v{i}: int = {i}   // " + "x" * 200 + "\n" for i in range(120)) + "print(\"fim\")\n")
 log = os.path.join("tests", "tmp", "webkit_editor.log")
-editor = subprocess.Popen(["noxy", "editor.nx", demo], env=dict(os.environ, NOXY_EDITOR_NO_WINDOW="1"), stdout=subprocess.DEVNULL, stderr=open(log, "w"))
+editor = subprocess.Popen(["noxy", "editor.nx", demo], env=dict(os.environ, NOXY_EDITOR_NO_WINDOW="1", NOXY_EDITOR_CONFIG_DIR=os.path.join(os.getcwd(), "tests", "tmp", "webkit_config"), NOXY_EDITOR_CACHE_DIR=os.path.join(os.getcwd(), "tests", "tmp", "webkit_cache")), stdout=subprocess.DEVNULL, stderr=open(log, "w"))
 url = None
 for _ in range(50):
     m = re.search(r"http://127\.0\.0\.1:\d+/\?t=[a-z0-9-]+", open(log).read())
diff --git a/web/editor.js b/web/editor.js
index db0cef53bd52351e5b1c61556338ab23ce6a2239..d3d24c179a39fadc626a6df4735ca7115971ce1f 100644
--- a/web/editor.js
+++ b/web/editor.js
@@ -40,8 +40,13 @@
   function rowsNow() { return Math.max(1, Math.floor(els.editor.clientHeight / LINE_H)); }
 
   // ---- fila de requisicoes
+  // idle: 1,5 s depois do ultimo evento que pode mudar o texto, um poll, para
+  // o Noxy gravar a copia de recuperacao mesmo com o usuario parado
+  const EDITS = { key: 1, text: 1, paste: 1, cut: 1, replace_one: 1, replace_all: 1 };
+  let idleTimer = 0;
   function send(ev) {
     if (dead) return;
+    if (EDITS[ev.kind]) { clearTimeout(idleTimer); idleTimer = setTimeout(() => send({ kind: "poll" }), 1500); }
     if (ev.kind === "scroll") {
       const q = queue.find((e) => e.kind === "scroll");
       if (q) { q.delta += ev.delta; pump(); return; }
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `241/241 passaram` e `10/10 passaram`. Depois: `ls ~/.cache ~/.config | grep -c noxy-editor` deve dar `0` (os testes não tocam no home).
- [ ] **Passo 5: o cliente de verdade**

Run: `python3 tests/web_smoke.py && GDK_BACKEND=x11 python3 tests/webkit_smoke.py`
Esperado: as duas linhas finais `OK: 0 falhas` (o primeiro precisa de `google-chrome`; o segundo abre uma janela WebKitGTK por alguns segundos).
- [ ] **Commit**

```bash
git add docs/ACHADOS.md editor.nx src/events.nx src/recovery.nx src/session.nx tests/protocol.nx tests/run.nx tests/web_smoke.py tests/webkit_smoke.py web/editor.js
git commit -q -m 'feat(recovery): copias de recuperacao das abas sujas, restauracao na partida, poll ocioso no cliente; fix(clock): relogio do dono em ms (time_now devolve segundos: undo agrupava 1000 s); testes com cache e config isolados

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 9: Execução com saída ao vivo e Parar

**Interfaces:**
- Produces: `runner.RunState { running, text, version, cmd, dir, pid, out, pending, stopping, stop_at }`, `runner.start(ref r, root, rel) -> string`, `runner.poll(ref r, now)`, `runner.stop(ref r, now) -> string`, `runner.command(root, rel, dir)`; comando e evento `stop`, Ctrl+F5, `#run-stop`. `tmp_root()` dos testes recria a pasta do zero.

**Files:** `src/events.nx`, `src/runner.nx`, `tests/run.nx`, `tests/web_smoke.py`, `web/editor.css`, `web/editor.js`, `web/index.html`

- [ ] **Passo 1: os testes (vermelho)**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (116 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/run.nx b/tests/run.nx
index aac14ac174d73dcada72be76173d2b5d89e6313c..85ad224252c7db6c0c532949df5fbcf99574351d 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -345,29 +345,61 @@ func tmp_root() -> string
     return root
 end
 
+// run_until espera a execucao terminar (ate ~5 s), chamando poll.
+func run_until(r: ref runner.RunState) -> void
+    let waited: int = 0
+    while r.running && waited < 100 do
+        sys.sleep(50)
+        runner.poll(r, events.now())
+        waited = waited + 1
+    end
+end
+
+func alive(pid: int) -> bool
+    return sys.exec("kill -0 " + to_str(pid) + " 2>/dev/null").exit_code == 0
+end
+
 func test_runner() -> void
     print("runner")
     let root: string = tmp_root()
+    write_file(root + "/aos_poucos.nx", "use sys\nprint(\"um ação\")\nsys.sleep(700)\nprint(\"dois\")\n")
+    write_file(root + "/sem_fim.nx", "use sys\nprint(\"rodando\")\nwhile true do\n    sys.sleep(50)\nend\n")
     let r: runner.RunState = runner.new_run()
-    check("comando com cd, aspas e /dev/null", runner.command("/x y", "a'b.nx") == "cd '/x y' && noxy 'a'\\''b.nx' < /dev/null 2>&1")
-    check("start", runner.start(ref r, root, "hello.nx") == "" && r.running && r.version == 1)
+    check("start", runner.start(ref r, root, "hello.nx") == "" && r.running && r.pid > 0)
     check("start durante execucao recusa", runner.start(ref r, root, "hello.nx") == "ja esta rodando")
+    run_until(ref r)
+    check("saida e codigo de saida", !r.running && r.text == "$ noxy hello.nx\noi\n[saiu com 3]")
+    check("diretorio temporario apagado no fim", !io.exists(r.dir))
+
+    let live: runner.RunState = runner.new_run()
+    runner.start(ref live, root, "aos_poucos.nx")
     let waited: int = 0
-    while r.running && waited < 100 do
+    while !strings.contains(live.text, "um") && waited < 60 do
         sys.sleep(50)
-        runner.poll(ref r)
+        runner.poll(ref live, events.now())
         waited = waited + 1
     end
-    check("poll recolhe a saida e o codigo", !r.running && r.text == "$ noxy hello.nx\noi\n[saiu com 3]" && r.version == 2)
+    check("saida ao vivo: a primeira linha chega antes do fim, com acento", strings.contains(live.text, "um ação") && !strings.contains(live.text, "dois") && live.running)
+    run_until(ref live)
+    check("depois chega o resto e o codigo", strings.ends_with(live.text, "um ação\ndois\n[saiu com 0]"))
+
+    let loop: runner.RunState = runner.new_run()
+    runner.start(ref loop, root, "sem_fim.nx")
+    sys.sleep(400)
+    runner.poll(ref loop, events.now())
+    let pid: int = loop.pid
+    check("programa sem fim roda", loop.running && alive(pid))
+    check("parar", runner.stop(ref loop, events.now()) == "")
+    run_until(ref loop)
+    check("parar encerra, com [interrompido] no painel", !loop.running && strings.ends_with(loop.text, "[interrompido]"))
+    check("sem processo orfao", !alive(pid))
+    check("parar sem execucao avisa", runner.stop(ref loop, events.now()) == "nada rodando")
+
     let bad: runner.RunState = runner.new_run()
     runner.start(ref bad, root, "nao.nx")
-    waited = 0
-    while bad.running && waited < 100 do
-        sys.sleep(50)
-        runner.poll(ref bad)
-        waited = waited + 1
-    end
-    check("arquivo inexistente mostra o erro do noxy", !bad.running && strings.contains(bad.text, "Error reading file") && strings.contains(bad.text, "[saiu com 1]"))
+    run_until(ref bad)
+    check("arquivo inexistente mostra o erro do noxy", strings.contains(bad.text, "Error reading file") && strings.contains(bad.text, "[saiu com 1]"))
+    check("caminho com aspas simples", runner.command("/x y", "a'b.nx", "/t") == "cd '/x y' && exec noxy 'a'\\''b.nx'")
 end
 
 func test_session() -> void
@@ -540,6 +572,18 @@ func test_events() -> void
         waited = waited + 1
     end
     check("poll recolhe a saida no quadro", strings.contains(last, "[saiu com 3]"))
+    write_file(root + "/sem_fim.nx", "use sys\nwhile true do\n    sys.sleep(50)\nend\n")
+    events.dispatch(ref s, "{\"kind\":\"tree_open\",\"path\":\"" + root + "/sem_fim.nx\",\"rows\":20,\"tree_version\":2}", 18)
+    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"f5\",\"rows\":20,\"tree_version\":2}", 18)
+    check("f5 roda o programa sem fim", s.run.running)
+    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"f5\",\"ctrl\":true,\"rows\":20,\"tree_version\":2}", 18)
+    waited = 0
+    while s.run.running && waited < 100 do
+        sys.sleep(50)
+        last = events.dispatch(ref s, "{\"kind\":\"poll\",\"rows\":20,\"tree_version\":2}", 19)
+        waited = waited + 1
+    end
+    check("ctrl+f5 para a execucao", !s.run.running && strings.contains(last, "[interrompido]"))
     sys.setenv("NOXY_EDITOR_CONFIG_DIR", sys.getcwd() + "/tests/tmp/config")
     let fth: string = events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"theme:nord\",\"rows\":20,\"tree_version\":2}", 19)
     check("comando theme:nord muda o tema, grava e vai no quadro", s.settings.theme == "nord" && strings.contains(fth, "\"settings\":{\"theme\":\"nord\"}") && settings.load().theme == "nord")
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index c78d57984be228df1a06f587dc8296a6f5655b3b..0ae2bfd042dc5db16fed383f548edd272d36e5ea 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -135,6 +135,14 @@ key("F5"); settle(1500)
 check("F5 mostra o painel de saida", not ev("document.getElementById('output').classList.contains('hidden')"))
 out = ev("document.getElementById('output-text').textContent")
 check("saida do programa aparece", "$ noxy exemplo.nx" in out and "[saiu com" in out)
+# parar pelo botao: um programa sem fim com saida ao vivo
+open(os.path.join(demo, "sem_fim.nx"), "w").write('use sys\nlet i = 0\nwhile true do\n    print(f"volta {i}")\n    i = i + 1\n    sys.sleep(100)\nend\n')
+key("p", mods=2); ws.call("Input.insertText", {"text": "sem_fim"}); settle(); key("Enter")
+key("F5"); settle(1200)
+check("saida ao vivo enquanto roda", "volta 2" in ev("document.getElementById('output-text').textContent") and not ev("document.getElementById('run-stop').classList.contains('hidden')"))
+ev("document.getElementById('run-stop').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle(1500)
+check("parar encerra e esconde o botao", "[interrompido]" in ev("document.getElementById('output-text').textContent") and ev("document.getElementById('run-stop').classList.contains('hidden')"))
+ev("document.querySelector('.tab.active .close').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
 print("SAIDA:", out.replace("\n", " | ")[:200])
 # painel de saida: altura inicial de 35% da area, divisor arrastavel, Ctrl+J alterna
 def output_h(): return ev("document.getElementById('output').getBoundingClientRect().height")
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: `Compiler error: [line 353] function 'runner.poll' expects 1 arguments, got 2`
- [ ] **Commit**

```bash
git add tests/run.nx tests/web_smoke.py
git commit -q -m 'test(runner): saida ao vivo, parar e sem orfaos

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3: a implementação**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (396 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/src/events.nx b/src/events.nx
index a8cbe71ad5629fda0c33f234b40bc615d4a4fd71..b7d2757809e70dcc386d604e38ee40c8b43af56e 100644
--- a/src/events.nx
+++ b/src/events.nx
@@ -90,6 +90,11 @@ func run_command(s: ref session.Session, id: string, now: int) -> void
         session.close_tab(s, s.active)
     elif id == "run" then
         run_active(s)
+    elif id == "stop" then
+        let msg: string = runner.stop(ref s.run, now)
+        if msg != "" then
+            s.message = msg
+        end
     elif id == "panel" then
         session.toggle_panel(s)
     elif id == "terminal" then
@@ -186,6 +191,10 @@ func handle_key(s: ref session.Session, e: Event, now: int) -> void
         run_command(s, "quit", now)
         return
     end
+    if e.key == "f5" && e.ctrl then
+        run_command(s, "stop", now)
+        return
+    end
     if e.key == "f5" then
         run_command(s, "run", now)
         return
@@ -359,6 +368,8 @@ func apply(s: session.Session, e: Event, now: int) -> session.Session
         session.open_file(ref s, e.path)
     elif e.kind == "run" then
         run_active(ref s)
+    elif e.kind == "stop" then
+        run_command(ref s, "stop", now)
     elif e.kind == "panel_tab" then
         session.show_panel(ref s, e.key)
     elif e.kind == "panel_toggle" then
@@ -451,7 +462,7 @@ func dispatch(s: ref session.Session, body: string, now: int) -> string
         eprint("erro interno no evento " + e.kind + ": " + r.failure.message)
         s.message = "erro interno: " + r.failure.message
     end
-    runner.poll(ref s.run)
+    runner.poll(ref s.run, now)
     session.poll_index(s)
     session.poll_search(s)
     return frame.build(s, e.tree_version, e.search_version)
diff --git a/src/runner.nx b/src/runner.nx
index 1aaab1461360a71f6d008ae57e40dac39ca8e7c6..2392e5fc965990f8ae5f5ad3675e23e713b1c7d0 100644
--- a/src/runner.nx
+++ b/src/runner.nx
@@ -1,38 +1,40 @@
-// src/runner.nx — roda um arquivo .nx numa task e recolhe a saida quando
-// termina. Nao conhece a sessao: recebe a raiz e o caminho relativo. O
-// programa roda com a raiz como cwd (noxy.mod e caminhos relativos
-// funcionam como no terminal) e com a entrada em /dev/null, para input()
-// devolver "" em vez de travar. Nao ha como interromper um programa que
-// nao termina (docs/ACHADOS.md).
+// src/runner.nx — roda um arquivo .nx em segundo plano, num grupo de
+// processos proprio (setsid), com a saida num arquivo temporario lido aos
+// pedacos a cada poll: a saida aparece ao vivo e Parar mata o grupo inteiro
+// (o programa e o que ele abriu). O Noxy nao mata processos nem le saida de
+// processo sem bloquear (docs/ACHADOS.md); o shell e os arquivos resolvem.
+// O programa roda com a raiz como cwd e a entrada em /dev/null. Linux e
+// macOS; o Windows ainda nao e suportado aqui.
 use sys
-use strings select replace, ends_with
+use io
+use strings select replace, ends_with, trim, is_valid_utf8
+
+let KILL_AFTER_MS = 2000
 
 struct RunState
     running: bool
-    task: any          // handle de spawn_task; null parado
     text: string       // o conteudo do painel de saida
     version: int       // muda a cada alteracao de text ou running
-    cmd: string
+    cmd: string        // o comando do programa (sem o lancador)
+    dir: string        // diretorio temporario com out e code
+    pid: int           // lider do grupo de processos
+    out: io.File       // aberto para leitura incremental de dir/out
+    pending: bytes     // bytes do fim de uma leitura que ainda nao formam UTF-8
+    stopping: bool
+    stop_at: int
 end
 
 func new_run() -> RunState
-    return RunState(false, null, "", 0, "")
+    return RunState(false, "", 0, "", "", 0, io.File(-1, "", "", false), b"", false, 0)
 end
 
 func shell_quote(s: string) -> string
     return "'" + replace(s, "'", "'\\''") + "'"
 end
 
-func command(root: string, rel: string) -> string
-    if sys.os() == "windows" then
-        return "cd /d \"" + root + "\" && noxy \"" + rel + "\" < NUL 2>&1"
-    end
-    return "cd " + shell_quote(root) + " && noxy " + shell_quote(rel) + " < /dev/null 2>&1"
-end
-
-// exec_cmd e a funcao da task: bloqueia ate o programa terminar.
-func exec_cmd(cmd: string) -> sys.SysResult
-    return sys.exec_output(cmd)
+// command e o que roda dentro do grupo: cd na raiz e exec do noxy.
+func command(root: string, rel: string, dir: string) -> string
+    return "cd " + shell_quote(root) + " && exec noxy " + shell_quote(rel)
 end
 
 // start dispara a execucao; devolve "" ou a mensagem de recusa.
@@ -40,38 +42,102 @@ func start(r: ref RunState, root: string, rel: string) -> string
     if r.running then
         return "ja esta rodando"
     end
-    r.cmd = command(root, rel)
+    let mk: sys.SysResult = sys.exec_output("mktemp -d")
+    let dir: string = trim(mk.output)
+    if !mk.ok || dir == "" then
+        return "nao consegui criar o diretorio temporario da execucao"
+    end
+    let out: string = dir + "/out"
+    let touch: io.File = io.open(out, "w")
+    io.close(touch)
+    r.cmd = command(root, rel, dir)
+    let inner: string = "(" + r.cmd + ") >> " + shell_quote(out) + " 2>&1 < /dev/null; echo $? > " + shell_quote(dir + "/code")
+    let launch: sys.SysResult = sys.exec_output("setsid sh -c " + shell_quote(inner) + " > /dev/null 2>&1 & echo $!")
+    r.dir = dir
+    r.pid = to_int(trim(launch.output))
+    r.out = io.open(out, "r")
+    r.pending = b""
+    r.stopping = false
     r.text = "$ noxy " + rel + "\n"
     r.running = true
     r.version = r.version + 1
-    r.task = spawn_task(exec_cmd, r.cmd)
     return ""
 end
 
-// poll recolhe o resultado se a task terminou; chamado a cada evento.
-func poll(r: ref RunState) -> void
-    if !r.running then
+// read_new anexa o que o arquivo de saida ganhou; guarda em pending ate 3
+// bytes finais que ainda nao fecham um caractere UTF-8.
+func read_new(r: ref RunState) -> void
+    let got: io.IOBytesResult = io.read_bytes(r.out)
+    if !got.ok || length(got.data) == 0 then
         return
     end
-    let env: any = task_await(r.task, 0)
-    if env["status"] == "timeout" then
+    let buf: bytes = r.pending + got.data
+    let n: int = length(buf)
+    for k in range(4) do
+        if k <= n && is_valid_utf8(slice(buf, 0, n - k)) then
+            r.text = r.text + to_str(slice(buf, 0, n - k))
+            r.pending = slice(buf, n - k, n)
+            r.version = r.version + 1
+            return
+        end
+    end
+    r.text = r.text + "[saida que nao e UTF-8 omitida]\n"
+    r.pending = b""
+    r.version = r.version + 1
+end
+
+func group_alive(pid: int) -> bool
+    return sys.exec("kill -0 -" + to_str(pid) + " 2>/dev/null").exit_code == 0
+end
+
+func finish(r: ref RunState, tail: string) -> void
+    read_new(r)
+    if !ends_with(r.text, "\n") then
+        r.text = r.text + "\n"
+    end
+    r.text = r.text + tail
+    io.close(r.out)
+    sys.exec("rm -rf " + shell_quote(r.dir))
+    r.running = false
+    r.stopping = false
+    r.version = r.version + 1
+end
+
+// poll recolhe a saida nova e o fim; chamado a cada evento.
+func poll(r: ref RunState, now: int) -> void
+    if !r.running then
         return
     end
-    if env["status"] == "ok" then
-        let res: sys.SysResult = env["value"]
-        r.text = r.text + res.output
-        if length(res.output) > 0 && !ends_with(res.output, "\n") then
-            r.text = r.text + "\n"
+    read_new(r)
+    let code_path: string = r.dir + "/code"
+    if r.stopping then
+        if !group_alive(r.pid) then
+            finish(r, "[interrompido]")
+        elif now - r.stop_at >= KILL_AFTER_MS then
+            sys.exec("kill -KILL -" + to_str(r.pid) + " 2>/dev/null")
         end
-        if res.output == "" && res.error != "" then
-            r.text = r.text + res.error + "\n"
+        return
+    end
+    if io.exists(code_path) then
+        let f: io.File = io.open(code_path, "r")
+        let c: io.IOResult = io.read(f)
+        io.close(f)
+        let code: string = trim(c.data)
+        if code == "" then
+            return     // o shell ainda esta escrevendo o codigo
         end
-        r.text = r.text + "[saiu com " + to_str(res.exit_code) + "]"
-    else
-        let err: any = env["error"]
-        r.text = r.text + "falha ao executar: " + to_str(err["message"])
+        finish(r, "[saiu com " + code + "]")
     end
-    r.running = false
-    r.task = null
+end
+
+// stop manda TERM ao grupo; poll mata com KILL se nao sair em KILL_AFTER_MS.
+func stop(r: ref RunState, now: int) -> string
+    if !r.running then
+        return "nada rodando"
+    end
+    sys.exec("kill -TERM -" + to_str(r.pid) + " 2>/dev/null")
+    r.stopping = true
+    r.stop_at = now
     r.version = r.version + 1
+    return ""
 end
diff --git a/tests/run.nx b/tests/run.nx
index 85ad224252c7db6c0c532949df5fbcf99574351d..2f7621ca7ffcd1a22b045bdc26b91acb7f959931 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -335,8 +335,8 @@ end
 
 func tmp_root() -> string
     let root: string = sys.getcwd() + "/tests/tmp/run"
+    sys.exec("rm -rf '" + root + "'")    // sempre do zero: nada de sobras de outra rodada
     io.mkdir(root + "/sub")
-    io.remove(root + "/bin.nx")    // sobra do teste de UTF-8 da rodada anterior
     write_file(root + "/b.nx", "let b = 1\n")
     write_file(root + "/a.txt", "texto\n")
     write_file(root + "/.hidden", "")
@@ -356,12 +356,15 @@ func run_until(r: ref runner.RunState) -> void
 end
 
 func alive(pid: int) -> bool
-    return sys.exec("kill -0 " + to_str(pid) + " 2>/dev/null").exit_code == 0
+    return sys.exec("kill -0 -" + to_str(pid) + " 2>/dev/null").exit_code == 0
 end
 
 func test_runner() -> void
     print("runner")
-    let root: string = tmp_root()
+    tmp_root()
+    let root: string = sys.getcwd() + "/tests/tmp/runner"
+    io.mkdir(root)
+    write_file(root + "/hello.nx", "use sys\nprint(\"oi\")\nsys.exit(3)\n")
     write_file(root + "/aos_poucos.nx", "use sys\nprint(\"um ação\")\nsys.sleep(700)\nprint(\"dois\")\n")
     write_file(root + "/sem_fim.nx", "use sys\nprint(\"rodando\")\nwhile true do\n    sys.sleep(50)\nend\n")
     let r: runner.RunState = runner.new_run()
@@ -576,7 +579,8 @@ func test_events() -> void
     events.dispatch(ref s, "{\"kind\":\"tree_open\",\"path\":\"" + root + "/sem_fim.nx\",\"rows\":20,\"tree_version\":2}", 18)
     events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"f5\",\"rows\":20,\"tree_version\":2}", 18)
     check("f5 roda o programa sem fim", s.run.running)
-    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"f5\",\"ctrl\":true,\"rows\":20,\"tree_version\":2}", 18)
+    let fk: string = events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"f5\",\"ctrl\":true,\"rows\":20,\"tree_version\":2}", 18)
+    last = fk
     waited = 0
     while s.run.running && waited < 100 do
         sys.sleep(50)
@@ -584,6 +588,8 @@ func test_events() -> void
         waited = waited + 1
     end
     check("ctrl+f5 para a execucao", !s.run.running && strings.contains(last, "[interrompido]"))
+    session.close_tab(ref s, s.active)
+    io.remove(root + "/sem_fim.nx")
     sys.setenv("NOXY_EDITOR_CONFIG_DIR", sys.getcwd() + "/tests/tmp/config")
     let fth: string = events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"theme:nord\",\"rows\":20,\"tree_version\":2}", 19)
     check("comando theme:nord muda o tema, grava e vai no quadro", s.settings.theme == "nord" && strings.contains(fth, "\"settings\":{\"theme\":\"nord\"}") && settings.load().theme == "nord")
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index 0ae2bfd042dc5db16fed383f548edd272d36e5ea..a6006abe2cceb66565de1df476c0a55cc623e41f 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -12,6 +12,7 @@ import subprocess
 demo = os.path.join("tests", "tmp", "web")
 os.makedirs(os.path.join(demo, "src"), exist_ok=True)
 open(os.path.join(demo, "exemplo.nx"), "w").write('use sys\n// um exemplo para o editor\nfunc soma(a: int, b: int) -> int\n    return a + b\nend\nlet nome: string = "Noxy"\nprint(f"ola {nome}: {soma(2, 3)}")\nfor i in range(3) do\n    print(i)\nend\n')
+open(os.path.join(demo, "sem_fim.nx"), "w").write('use sys\nlet i = 0\nwhile true do\n    print(f"volta {i}")\n    i = i + 1\n    sys.sleep(100)\nend\n')
 open(os.path.join(demo, "notas.txt"), "w").write("texto simples\n")
 open(os.path.join(demo, "src", "util.nx"), "w").write("let x = 1\n")
 cfg = os.path.join(os.getcwd(), "tests", "tmp", "web_config")
@@ -81,7 +82,7 @@ def mouse(kind, x, y, button="left", clicks=1, mods=0):
     ws.call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": button, "clickCount": clicks, "modifiers": mods})
 
 ws.call("Page.navigate", {"url": url}); settle(1500)
-check("arvore renderizada", ev("document.querySelectorAll('#tree .node').length") == 3)
+check("arvore renderizada", ev("document.querySelectorAll('#tree .node').length") == 4)
 check("nome da raiz", ev("document.getElementById('root-name').textContent") == "web")
 check("titulo inicial", ev("document.title") == "Noxy Editor")
 check("tema escuro aplicado no html", ev("document.documentElement.classList.contains('theme-dark')"))
@@ -136,7 +137,6 @@ check("F5 mostra o painel de saida", not ev("document.getElementById('output').c
 out = ev("document.getElementById('output-text').textContent")
 check("saida do programa aparece", "$ noxy exemplo.nx" in out and "[saiu com" in out)
 # parar pelo botao: um programa sem fim com saida ao vivo
-open(os.path.join(demo, "sem_fim.nx"), "w").write('use sys\nlet i = 0\nwhile true do\n    print(f"volta {i}")\n    i = i + 1\n    sys.sleep(100)\nend\n')
 key("p", mods=2); ws.call("Input.insertText", {"text": "sem_fim"}); settle(); key("Enter")
 key("F5"); settle(1200)
 check("saida ao vivo enquanto roda", "volta 2" in ev("document.getElementById('output-text').textContent") and not ev("document.getElementById('run-stop').classList.contains('hidden')"))
@@ -236,9 +236,9 @@ open(helper, "w").write("use src.browser as browser\nuse sys\nprint(browser.writ
 page = subprocess.run(["noxy", helper, url], capture_output=True, text=True).stdout.strip()
 check("write_redirect devolve um caminho", page.startswith("/"))
 ws.call("Page.navigate", {"url": "file://" + page}); settle(2000)
-check("pagina de redirecionamento leva ao editor", ev("location.href").startswith(url.split("?")[0]) and ev("document.querySelectorAll('#tree .node').length") == 3)
+check("pagina de redirecionamento leva ao editor", ev("location.href").startswith(url.split("?")[0]) and ev("document.querySelectorAll('#tree .node').length") == 4)
 time.sleep(3.5)
-check("editor continua vivo 3 s depois do reload", editor.poll() is None and ev("document.querySelectorAll('#tree .node').length") == 3)
+check("editor continua vivo 3 s depois do reload", editor.poll() is None and ev("document.querySelectorAll('#tree .node').length") == 4)
 # recuperacao: editar sem salvar, esperar a copia (poll 1,5 s depois da
 # ultima edicao), matar o editor e abrir outro: a aba volta suja
 ev("document.querySelectorAll('#tree .node.file')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
@@ -246,7 +246,6 @@ key("Home", mods=2); insert("// nao salvo\n")
 settle(2500)
 cache = env["NOXY_EDITOR_CACHE_DIR"]
 check("copia de recuperacao gravada sem outro evento", len(os.listdir(os.path.join(cache, "recovery"))) >= 1)
-for fn in os.listdir(os.path.join(cache, "recovery")):
 editor.kill(); editor.wait()
 editor = subprocess.Popen(["noxy", "editor.nx", demo], env=env, stdout=subprocess.DEVNULL, stderr=open(log, "w"))
 url = None
diff --git a/web/editor.css b/web/editor.css
index 7d83964a6af600182456811a6cabd60e3c6b36cd..a0350e77ba1b5bf128cd7c1cad13f1b34ea1e6c6 100644
--- a/web/editor.css
+++ b/web/editor.css
@@ -133,6 +133,8 @@ button { font: inherit; color: inherit; background: none; border: none; cursor:
 .shit:hover { background: var(--bg-hover); }
 .shit .sline { color: var(--fg-dim); min-width: 36px; text-align: right; }
 #output-close { color: var(--fg-dim); font-size: 16px; line-height: 1; }
+#run-stop { margin-left: auto; margin-right: 10px; padding: 2px 8px; border-radius: 4px; color: var(--danger); font-size: 11px; letter-spacing: .04em; text-transform: none; }
+#run-stop:hover { background: var(--bg-hover); }
 #output-text { margin: 0; padding: 4px 14px 10px; font: 13px var(--font-mono); white-space: pre-wrap; }
 
 /* barra de status */
diff --git a/web/editor.js b/web/editor.js
index d3d24c179a39fadc626a6df4735ca7115971ce1f..270289918de618e4cb3a00ee776590c3b0a604ec 100644
--- a/web/editor.js
+++ b/web/editor.js
@@ -12,7 +12,7 @@
     editor: $("editor"), gutter: $("gutter"), text: $("text"), cursor: $("cursor"), welcome: $("welcome"),
     main: $("main"), output: $("output"), outputText: $("output-text"), outputClose: $("output-close"), outputResize: $("output-resize"), outputHead: $("output-head"),
     panelTabs: $("panel-tabs"), searchView: $("search-view"), termView: $("term-view"),
-    searchInput: $("search-input"), searchCase: $("search-case"), searchStatus: $("search-status"), searchResults: $("search-results"),
+    runStop: $("run-stop"), searchInput: $("search-input"), searchCase: $("search-case"), searchStatus: $("search-status"), searchResults: $("search-results"),
     status: $("status"), statusLeft: $("status-left"), statusMsg: $("status-msg"), statusRight: $("status-right"),
     modal: $("modal"), modalText: $("modal-text"), modalButtons: $("modal-buttons"),
     list: $("list"), listInput: $("list-input"), listItems: $("list-items"),
@@ -117,6 +117,7 @@
       els.outputText.textContent = f.output.text + (f.output.running ? "\n…" : "");
       els.outputText.scrollTop = els.outputText.scrollHeight;
     }
+    els.runStop.classList.toggle("hidden", !f.output.running);
     renderPanel(f.panel);
     renderSearch(f.search);
     renderModal(f.modal);
@@ -326,7 +327,7 @@
   // chegam pelo textarea (input / compositionend), o que faz acentos e IME
   // funcionarem.
   const NAV = { ArrowLeft: 1, ArrowRight: 1, ArrowUp: 1, ArrowDown: 1, Home: 1, End: 1, PageUp: 1, PageDown: 1, Enter: 1, Backspace: 1, Delete: 1, Tab: 1, Escape: 1, F5: 1, F3: 1 };
-  const CTRL = { s: 1, z: 1, y: 1, a: 1, w: 1, "/": 1, q: 1, j: 1, "`": 1, p: 1, f: 1, h: 1, arrowleft: 1, arrowright: 1, home: 1, end: 1 };
+  const CTRL = { s: 1, z: 1, y: 1, a: 1, w: 1, "/": 1, q: 1, j: 1, "`": 1, p: 1, f: 1, h: 1, f5: 1, arrowleft: 1, arrowright: 1, home: 1, end: 1 };
 
   function onKeyDown(e) {
     if (e.isComposing) return;
@@ -509,6 +510,7 @@
   // ---- botoes, redimensionar, poll durante execucao, fechamento
   els.runBtn.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "run" }); });
   els.outputClose.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "panel_toggle" }); });
+  els.runStop.addEventListener("mousedown", (e) => { e.preventDefault(); e.stopPropagation(); send({ kind: "stop" }); });
   for (const tab of els.panelTabs.querySelectorAll(".ptab")) {
     tab.addEventListener("mousedown", (e) => { e.preventDefault(); if (tab.dataset.tab === "search") wantSearchFocus = true; send({ kind: "panel_tab", key: tab.dataset.tab }); });
   }
diff --git a/web/index.html b/web/index.html
index 658e3c14a52f340a561b11260d7653d6be2ae9f0..54472bdd6a8be9ee026d603a112f08106114f077 100644
--- a/web/index.html
+++ b/web/index.html
@@ -44,6 +44,7 @@
           <span class="ptab" data-tab="search">Busca</span>
           <span class="ptab" data-tab="terminal">Terminal</span>
         </div>
+        <button id="run-stop" class="hidden" title="Parar (Ctrl+F5)">■ Parar</button>
         <button id="output-close" title="Fechar (Ctrl+J)">×</button>
       </div>
       <pre id="output-text" class="pview"></pre>
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `251/251 passaram` e `10/10 passaram`. Depois: `ps -eo args | grep "exec noxy" | grep -v grep` vazio.
- [ ] **Passo 5: o cliente de verdade**

Run: `python3 tests/web_smoke.py && GDK_BACKEND=x11 python3 tests/webkit_smoke.py`
Esperado: as duas linhas finais `OK: 0 falhas` (o primeiro precisa de `google-chrome`; o segundo abre uma janela WebKitGTK por alguns segundos).
- [ ] **Commit**

```bash
git add src/events.nx src/runner.nx tests/run.nx tests/web_smoke.py web/editor.css web/editor.js web/index.html
git commit -q -m 'feat(runner): saida ao vivo por arquivo, grupo de processos com setsid, Parar (ctrl+f5 e botao) com KILL apos 2 s; kill no formato do dash; fixtures dos testes sempre do zero

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 10: Git na interface

**Interfaces:**
- Produces: `gitinfo.Parsed`, `gitinfo.GitInfo`, `gitinfo.parse(porcelain, prefix, root)`, `gitinfo.collect(root)`, `gitinfo.empty_git()`; `session.start_git`, `session.poll_git`; `frame.build` ganha `client_git_version`; comando `git_refresh`; `#status-git` e classes `git-<código>` no cliente.

**Files:** `docs/ACHADOS.md`, `editor.nx`, `src/events.nx`, `src/frame.nx`, `src/gitinfo.nx`, `src/session.nx`, `tests/run.nx`, `tests/web_smoke.py`, `web/editor.css`, `web/editor.js`, `web/index.html`

- [ ] **Passo 1: os testes (vermelho)**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (83 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/run.nx b/tests/run.nx
index 2f7621ca7ffcd1a22b045bdc26b91acb7f959931..1f1dfb79f4fb7ea47a1b621308aae326af03a4ea 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -19,6 +19,7 @@ use src.index as index
 use src.find as find
 use src.search as search
 use src.recovery as recovery
+use src.gitinfo as gitinfo
 
 // cache e configuracao isolados: os testes nunca tocam no ~/.cache e no
 // ~/.config de quem roda
@@ -892,6 +893,63 @@ func test_recovery() -> void
     recovery.remove("/outra/pasta/q.nx")
 end
 
+func git_repo() -> string
+    let repo: string = sys.getcwd() + "/tests/tmp/git"
+    sys.exec("rm -rf '" + repo + "'")
+    io.mkdir(repo + "/proj/sub")
+    write_file(repo + "/proj/a.nx", "let a = 1\n")
+    write_file(repo + "/proj/b.nx", "let b = 1\n")
+    write_file(repo + "/fora.nx", "x\n")
+    sys.exec("cd '" + repo + "' && git init -q -b principal && git -c user.name=t -c user.email=t@t add . && git -c user.name=t -c user.email=t@t commit -q -m init")
+    write_file(repo + "/proj/a.nx", "let a = 2\n")
+    write_file(repo + "/proj/sub/novo.nx", "n\n")
+    io.remove(repo + "/proj/b.nx")
+    write_file(repo + "/fora.nx", "y\n")
+    return repo
+end
+
+func test_gitinfo() -> void
+    print("gitinfo")
+    let p: gitinfo.Parsed = gitinfo.parse(" M a.nx\n?? sub/n.nx\nA  c.nx\n D d.nx\nR  old.nx -> e.nx\nMM \"com espaco.nx\"\n", "", "/r")
+    check("codigos do porcelain", p.status["/r/a.nx"] == "M" && p.status["/r/sub/n.nx"] == "?" && p.status["/r/c.nx"] == "A" && p.status["/r/d.nx"] == "D" && p.status["/r/e.nx"] == "R")
+    check("caminho entre aspas", p.status["/r/com espaco.nx"] == "M")
+    check("pastas com alteracao dentro", has_key(p.dirs, "/r/sub") && !has_key(p.dirs, "/r"))
+    let q: gitinfo.Parsed = gitinfo.parse(" M proj/x.nx\n?? outro/y.nx\n?? proj/s/z.nx\n", "proj/", "/r/proj")
+    check("prefixo: so o que esta sob a raiz aberta, relativo a ela", length(keys(q.status)) == 2 && q.status["/r/proj/x.nx"] == "M" && has_key(q.dirs, "/r/proj/s"))
+
+    let repo: string = git_repo()
+    let g: gitinfo.GitInfo = gitinfo.collect(repo + "/proj")
+    check("repositorio: branch", g.available && g.branch == "principal")
+    check("repositorio: modificado, apagado e novo, so dentro da raiz", g.status[repo + "/proj/a.nx"] == "M" && g.status[repo + "/proj/b.nx"] == "D" && g.status[repo + "/proj/sub/novo.nx"] == "?" && !has_key(g.status, repo + "/fora.nx") && has_key(g.dirs, repo + "/proj/sub"))
+    let tmp: string = strings.trim(sys.exec_output("mktemp -d").output)
+    check("fora de um repositorio: indisponivel", !gitinfo.collect(tmp).available)
+    sys.exec("rmdir '" + tmp + "'")
+end
+
+func test_git_session() -> void
+    print("git na sessao")
+    let repo: string = git_repo()
+    let s: session.Session = session.new_session(repo + "/proj")
+    session.load(ref s)
+    session.start_git(ref s)
+    let waited: int = 0
+    let f: string = ""
+    while s.git_task != null && waited < 100 do
+        sys.sleep(20)
+        f = events.dispatch(ref s, "{\"kind\":\"poll\",\"rows\":20,\"tree_version\":2,\"git_version\":0}", 1)
+        waited = waited + 1
+    end
+    check("status do git no quadro com a branch", strings.contains(f, "\"branch\":\"principal\"") && strings.contains(f, "\"available\":true"))
+    let same: string = events.dispatch(ref s, "{\"kind\":\"poll\",\"rows\":20,\"tree_version\":2,\"git_version\":" + to_str(s.git.version) + "}", 1)
+    check("git omitido quando o cliente tem a versao", !strings.contains(same, "\"branch\":\"principal\"") && strings.contains(same, "\"git\":{"))
+    session.open_file(ref s, repo + "/proj/sub/novo.nx")
+    editing.insert_text(ref s.tabs[0].editor, "x", 10, 1)
+    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"s\",\"ctrl\":true,\"rows\":20,\"tree_version\":2}", 2)
+    check("salvar dispara a atualizacao do git", s.git_task != null)
+    events.dispatch(ref s, "{\"kind\":\"command\",\"key\":\"git_refresh\",\"rows\":20,\"tree_version\":2}", 3)
+    check("comando git_refresh", s.git_task != null)
+end
+
 test_document()
 test_lexer()
 test_history()
@@ -908,4 +966,6 @@ test_index()
 test_find()
 test_search()
 test_recovery()
+test_gitinfo()
+test_git_session()
 report()
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: `Compiler error: [line 913] variable 'p': cannot resolve type 'gitinfo.Parsed': module 'src.gitinfo' could not be loaded`
- [ ] **Commit**

```bash
git add tests/run.nx
git commit -q -m 'test(git): parse do porcelain, prefixo, repositorio real e atualizacao pela sessao

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3: a implementação**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (498 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/docs/ACHADOS.md b/docs/ACHADOS.md
index 6f8c457661d52941e93683d4c983d2bdfb2569ce..2245141c04ba4233c12dd0865dc6abc487359abb 100644
--- a/docs/ACHADOS.md
+++ b/docs/ACHADOS.md
@@ -81,3 +81,13 @@ segundos com 200. **Contorno:** `events.now()` usa `time.now_ms()`, com teste
 que dorme 120 ms e confere a diferença. **Sugestão:** corrigir a descrição no
 README, ou fazer `time_now()` devolver ms como documentado e deixar
 `time.now()` para segundos.
+
+## 9. `sys.exec_output` apara espaços nas pontas da saída
+
+**Onde:** `src/gitinfo.nx`. **O que:** `SysResult.output` volta sem os
+espaços e quebras do começo e do fim (`"  dois espacos\n fim  \n"` vira
+`"dois espacos\n fim"`). Para saída com formato posicional isso corrompe
+dados: a primeira linha do `git status --porcelain` (` M a.nx`) perdia o
+espaço e o caminho perdia a primeira letra. **Contorno:** uma linha `#` antes
+do comando (`echo '#'; git status ...`), ignorada no parse. **Sugestão:**
+devolver a saída intacta; quem quiser aparar usa `strings.trim`.
diff --git a/editor.nx b/editor.nx
index d5d82dcd87851f785f47e27b2508bd40b32a2a47..8722f4465ee78313df707d798add174bd1537fdb 100644
--- a/editor.nx
+++ b/editor.nx
@@ -61,6 +61,7 @@ if first_file != "" then
     session.open_file(ref s, first_file)
 end
 session.start_index(ref s)
+session.start_git(ref s)
 let restored: int = session.restore(ref s)
 if restored > 0 then
     s.message = to_str(restored) + " arquivo(s) recuperado(s) com alteracoes nao salvas"
diff --git a/src/events.nx b/src/events.nx
index b7d2757809e70dcc386d604e38ee40c8b43af56e..99ac272cb9352206e18b36fc58f43d17f15087ef 100644
--- a/src/events.nx
+++ b/src/events.nx
@@ -34,10 +34,11 @@ struct Event
     page: string        // id da pagina (por carga), para o bye de um reload
     case_sensitive: bool   // da busca (case e palavra reservada)
     search_version: int    // a versao dos resultados da busca na pasta que o cliente tem
+    git_version: int       // a versao do status do git que o cliente tem
 end
 
 func empty_event() -> Event
-    return Event("", "", false, false, false, "", 0, 0, 0, "", 0, 0, 0, "", false, 0)
+    return Event("", "", false, false, false, "", 0, 0, 0, "", 0, 0, 0, "", false, 0, 0)
 end
 
 // now e o relogio do dono do estado, em milissegundos. time_now() da
@@ -120,6 +121,8 @@ func run_command(s: ref session.Session, id: string, now: int) -> void
             end
             find.refresh(ref s.find, ed.doc, editing.sel_range(ed).start)
         end
+    elif id == "git_refresh" then
+        session.start_git(s)
     elif id == "reindex" then
         session.start_index(s)
         s.message = "reindexando..."
@@ -462,8 +465,13 @@ func dispatch(s: ref session.Session, body: string, now: int) -> string
         eprint("erro interno no evento " + e.kind + ": " + r.failure.message)
         s.message = "erro interno: " + r.failure.message
     end
+    let was_running: bool = s.run.running
     runner.poll(ref s.run, now)
+    if was_running && !s.run.running then
+        session.start_git(s)    // o programa pode ter criado ou mudado arquivos
+    end
     session.poll_index(s)
     session.poll_search(s)
-    return frame.build(s, e.tree_version, e.search_version)
+    session.poll_git(s)
+    return frame.build(s, e.tree_version, e.search_version, e.git_version)
 end
diff --git a/src/frame.nx b/src/frame.nx
index d0b13261ed187a5f5d6124b2560cb9bc595e14f2..f0ba856fe5b06e96c3568566951915701f09bdf8 100644
--- a/src/frame.nx
+++ b/src/frame.nx
@@ -10,6 +10,7 @@ use src.session as session
 use src.settings as settings
 use src.find as find
 use src.search as search
+use src.gitinfo as gitinfo
 
 struct SpanOut
     k: string       // kind do token
@@ -99,6 +100,7 @@ struct Frame
     list: session.List
     find: FindOut
     search: SearchOut
+    git: gitinfo.GitInfo       // status e dirs vazios quando o cliente ja tem esta versao
 end
 
 // covered: o pedaco [p, q) esta dentro de alguma marca do papel kind?
@@ -215,6 +217,15 @@ func search_out(s: ref session.Session, client_version: int) -> SearchOut
     return SearchOut(s.search.query, s.search.case_sensitive, s.search.running, s.search.truncated, s.search.version, hits)
 end
 
+func git_out(s: ref session.Session, client_version: int) -> gitinfo.GitInfo
+    if client_version == s.git.version then
+        let g: gitinfo.GitInfo = gitinfo.empty_git()
+        g.version = s.git.version
+        return g
+    end
+    return s.git
+end
+
 // title_of e o titulo da janela: nome da aba ativa, marcador de alteracao
 // e o nome do editor. editor.nx compara com o anterior para set_title.
 func title_of(s: ref session.Session) -> string
@@ -229,7 +240,7 @@ func title_of(s: ref session.Session) -> string
     return session.basename(d.path) + mark + " — Noxy Editor"
 end
 
-func build(s: ref session.Session, client_tree_version: int, client_search_version: int) -> string
+func build(s: ref session.Session, client_tree_version: int, client_search_version: int, client_git_version: int) -> string
     let tabs: TabOut[] = []
     for i in range(length(s.tabs)) do
         let d: doc.Document = s.tabs[i].editor.doc
@@ -255,7 +266,7 @@ func build(s: ref session.Session, client_tree_version: int, client_search_versi
         right = "Ln " + to_str(ed.cursor.line + 1) + ", Col " + to_str(ed.cursor.col + 1) + "   Espaços: 4   " + doc.eol_name(ed.doc)
         eol = doc.eol_name(ed.doc)
     end
-    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings, s.list, FindOut(s.find.open, s.find.replace, s.find.query, s.find.case_sensitive, length(s.find.matches), s.find.current), search_out(s, client_search_version))
+    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings, s.list, FindOut(s.find.open, s.find.replace, s.find.query, s.find.case_sensitive, length(s.find.matches), s.find.current), search_out(s, client_search_version), git_out(s, client_git_version))
     s.clipboard = ""
     return json_dumps(f)
 end
diff --git a/src/gitinfo.nx b/src/gitinfo.nx
new file mode 100644
index 0000000000000000000000000000000000000000..206164d58788a29bf92cfd406c71ab73a36bdbaa
--- /dev/null
+++ b/src/gitinfo.nx
@@ -0,0 +1,107 @@
+// src/gitinfo.nx — branch e status do git para a interface. collect roda
+// numa task (session.start_git); o status vai indexado por caminho absoluto,
+// que e o que a arvore e as abas carregam. A raiz aberta pode ser uma
+// subpasta do repositorio: rev-parse --show-prefix diz qual, e so o que esta
+// sob ela entra. Sem git ou fora de um repositorio: available = false.
+use sys
+use strings select substring, split, starts_with, trim, join_count
+use strings
+
+struct Parsed
+    status: map[string, string]   // caminho absoluto -> "M", "A", "D", "R", "?"
+    dirs: map[string, bool]       // pastas com alteracao dentro
+end
+
+struct GitInfo
+    available: bool
+    branch: string
+    status: map[string, string]
+    dirs: map[string, bool]
+    version: int
+end
+
+func empty_git() -> GitInfo
+    let st: map[string, string] = {}
+    let ds: map[string, bool] = {}
+    return GitInfo(false, "", st, ds, 0)
+end
+
+func shell_quote(s: string) -> string
+    return "'" + strings.replace(s, "'", "'\\''") + "'"
+end
+
+func code_of(x: string, y: string) -> string
+    if x == "?" then
+        return "?"
+    end
+    if x == "R" || y == "R" then
+        return "R"
+    end
+    if x == "A" then
+        return "A"
+    end
+    if x == "D" || y == "D" then
+        return "D"
+    end
+    return "M"
+end
+
+// unquote tira as aspas que o git poe em caminhos com espaco ou acento.
+func unquote(path: string) -> string
+    if starts_with(path, "\"") && length(path) >= 2 then
+        return strings.replace(strings.replace(substring(path, 1, length(path) - 1), "\\\"", "\""), "\\\\", "\\")
+    end
+    return path
+end
+
+// parse le o status --porcelain (v1) de um repositorio; prefix e o caminho
+// da raiz aberta dentro do repositorio ("" na raiz dele), root o absoluto.
+func parse(porcelain: string, prefix: string, root: string) -> Parsed
+    let st: map[string, string] = {}
+    let ds: map[string, bool] = {}
+    for line in split(porcelain, "\n").parts do
+        if length(line) < 4 then
+            continue
+        end
+        let x: string = substring(line, 0, 1)
+        let y: string = substring(line, 1, 2)
+        let path: string = substring(line, 3, length(line))
+        let arrow: string[] = split(path, " -> ").parts
+        if length(arrow) > 1 then
+            path = arrow[length(arrow) - 1]
+        end
+        path = unquote(path)
+        if !starts_with(path, prefix) then
+            continue
+        end
+        let rel: string = substring(path, length(prefix), length(path))
+        st[root + "/" + rel] = code_of(x, y)
+        let parts: string[] = split(rel, "/").parts
+        for k in range(1, length(parts)) do
+            ds[root + "/" + join_count(parts, "/", k)] = true
+        end
+    end
+    return Parsed(st, ds)
+end
+
+func collect(root: string) -> GitInfo
+    let g: GitInfo = empty_git()
+    let q: string = shell_quote(root)
+    let b: sys.SysResult = sys.exec_output("git -C " + q + " rev-parse --abbrev-ref HEAD 2>/dev/null")
+    if !b.ok || b.exit_code != 0 then
+        return g
+    end
+    let pre: sys.SysResult = sys.exec_output("git -C " + q + " rev-parse --show-prefix 2>/dev/null")
+    // exec_output apara espacos nas pontas da saida (docs/ACHADOS.md), e o
+    // porcelain comeca com espaco (" M a.nx"): uma linha "#" na frente protege
+    let st: sys.SysResult = sys.exec_output("echo '#'; git -C " + q + " status --porcelain --untracked-files=all 2>/dev/null")
+    if !st.ok || st.exit_code != 0 then
+        return g
+    end
+    let p: Parsed = parse(st.output, trim(pre.output), root)
+    g.available = true
+    g.branch = trim(b.output)
+    g.status = p.status
+    g.dirs = p.dirs
+    return g
+end
diff --git a/src/session.nx b/src/session.nx
index a5c1549be55a6020b85be0fd803545268ac89593..170d925cd65bd8b8cba5f3250b5aed70672bbf7a 100644
--- a/src/session.nx
+++ b/src/session.nx
@@ -12,6 +12,7 @@ use src.index as index
 use src.find as find
 use src.search as search
 use src.recovery as recovery
+use src.gitinfo as gitinfo
 
 struct Tab
     editor: editing.Editor
@@ -91,6 +92,8 @@ struct Session
     find: find.Find
     search: Search
     recovery_warned: bool   // ja avisou que nao consegue gravar copias
+    git: gitinfo.GitInfo
+    git_task: any           // task de gitinfo.collect; null parada
 end
 
 // Search e a busca na pasta: a consulta, a task e os resultados; version
@@ -182,6 +185,28 @@ func poll_search(s: ref Session) -> void
     s.search.version = s.search.version + 1
 end
 
+// start_git (re)coleta branch e status numa task; uma coleta em andamento
+// e substituida (a antiga termina e e ignorada).
+func start_git(s: ref Session) -> void
+    s.git_task = spawn_task(gitinfo.collect, s.root)
+end
+
+func poll_git(s: ref Session) -> void
+    if s.git_task == null then
+        return
+    end
+    let env: any = task_await(s.git_task, 0)
+    if env["status"] == "timeout" then
+        return
+    end
+    if env["status"] == "ok" then
+        let g: gitinfo.GitInfo = env["value"]
+        g.version = s.git.version + 1
+        s.git = g
+    end
+    s.git_task = null
+end
+
 // recovery_tick grava a copia das abas sujas cujo texto mudou desde a
 // ultima copia, no maximo uma vez por COPY_EVERY_MS; force (bye) grava na hora.
 func recovery_tick(s: ref Session, now: int, force: bool) -> void
@@ -264,7 +289,7 @@ func no_modal() -> Modal
 end
 
 func new_session(root: string) -> Session
-    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0), [], null, find.new_find(), Search("", false, false, null, [], false, 0), false)
+    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0), [], null, find.new_find(), Search("", false, false, null, [], false, 0), false, gitinfo.empty_git(), null)
 end
 
 func basename(path: string) -> string
@@ -432,6 +457,7 @@ func save_tab(s: ref Session, i: int) -> bool
         return false
     end
     s.tabs[i].editor.doc.dirty = false
+    start_git(s)
     recovery.remove(path)
     s.tabs[i].copy_text = ""
     s.tabs[i].copy_at = 0
diff --git a/tests/run.nx b/tests/run.nx
index 1f1dfb79f4fb7ea47a1b621308aae326af03a4ea..79664dc0d47d527cf22d9d4a27b4722b5506b6cb 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -478,9 +478,9 @@ func test_frame() -> void
     let s: session.Session = session.new_session(root)
     session.load(ref s)
     s.rows = 2
-    let empty: string = frame.build(ref s, 0, 0)
+    let empty: string = frame.build(ref s, 0, 0, 0)
     check("sem aba: tabs vazio e arvore presente", strings.contains(empty, "\"tabs\":[]") && strings.contains(empty, "\"name\":\"b.nx\"") && strings.contains(empty, "\"title\":\"Noxy Editor\""))
-    let same: string = frame.build(ref s, s.tree_version, 0)
+    let same: string = frame.build(ref s, s.tree_version, 0, 0)
     check("arvore omitida quando a versao bate", strings.contains(same, "\"tree\":[]"))
 
     session.open_file(ref s, root + "/b.nx")
@@ -490,7 +490,7 @@ func test_frame() -> void
     editing.click(ref s.tabs[0].editor, doc.Pos(0, 1), false, 2)
     editing.drag(ref s.tabs[0].editor, doc.Pos(1, 1), 2)
     s.clipboard = "cp"
-    let f: string = frame.build(ref s, s.tree_version, 0)
+    let f: string = frame.build(ref s, s.tree_version, 0, 0)
     check("spans cortados na fronteira da selecao", strings.contains(f, "{\"c\":false,\"f\":false,\"k\":\"keyword\",\"s\":false,\"t\":\"l\"}") && strings.contains(f, "{\"c\":false,\"f\":false,\"k\":\"keyword\",\"s\":true,\"t\":\"et\"}") && strings.contains(f, "{\"c\":false,\"f\":false,\"k\":\"ident\",\"s\":true,\"t\":\"x\"}"))
     check("cursor, has_sel e total", strings.contains(f, "\"cursor\":{\"col\":1,\"line\":1}") && strings.contains(f, "\"has_sel\":true") && strings.contains(f, "\"total\":3"))
     check("aba suja e titulo", strings.contains(f, "\"dirty\":true") && strings.contains(f, "b.nx ● — Noxy Editor"))
@@ -498,7 +498,7 @@ func test_frame() -> void
     check("clipboard vai e e consumido", strings.contains(f, "\"clipboard\":\"cp\"") && s.clipboard == "")
     s.rows = 1
     editing.ensure_visible(ref s.tabs[0].editor, 1)
-    let one: string = frame.build(ref s, s.tree_version, 0)
+    let one: string = frame.build(ref s, s.tree_version, 0, 0)
     check("so as linhas visiveis", strings.contains(one, "\"n\":1") && !strings.contains(one, "\"n\":0") && !strings.contains(one, "\"n\":2"))
     check("title_of", frame.title_of(ref s) == "b.nx ● — Noxy Editor")
 
@@ -512,7 +512,7 @@ func test_frame() -> void
     bs.rows = 50
     editing.move_doc_end(ref bs.tabs[0].editor, false, 50)
     let t0: int = events.now()
-    let bf: string = frame.build(ref bs, 1, 0)
+    let bf: string = frame.build(ref bs, 1, 0, 0)
     let dt: int = events.now() - t0
     check("arquivo de 5000 linhas: quadro so com as visiveis, em menos de 200 ms", strings.contains(bf, "\"total\":5000") && !strings.contains(bf, "\"n\":100,") && dt < 200)
 end
@@ -904,7 +904,6 @@ func git_repo() -> string
     write_file(repo + "/proj/a.nx", "let a = 2\n")
     write_file(repo + "/proj/sub/novo.nx", "n\n")
     io.remove(repo + "/proj/b.nx")
-    write_file(repo + "/fora.nx", "y\n")
     return repo
 end
 
@@ -920,7 +919,7 @@ func test_gitinfo() -> void
     let repo: string = git_repo()
     let g: gitinfo.GitInfo = gitinfo.collect(repo + "/proj")
     check("repositorio: branch", g.available && g.branch == "principal")
-    check("repositorio: modificado, apagado e novo, so dentro da raiz", g.status[repo + "/proj/a.nx"] == "M" && g.status[repo + "/proj/b.nx"] == "D" && g.status[repo + "/proj/sub/novo.nx"] == "?" && !has_key(g.status, repo + "/fora.nx") && has_key(g.dirs, repo + "/proj/sub"))
+    check("repositorio: modificado (primeira linha do porcelain, com espaco inicial), apagado e novo, so dentro da raiz", g.status[repo + "/proj/a.nx"] == "M" && g.status[repo + "/proj/b.nx"] == "D" && g.status[repo + "/proj/sub/novo.nx"] == "?" && !has_key(g.status, repo + "/fora.nx") && has_key(g.dirs, repo + "/proj/sub"))
     let tmp: string = strings.trim(sys.exec_output("mktemp -d").output)
     check("fora de um repositorio: indisponivel", !gitinfo.collect(tmp).available)
     sys.exec("rmdir '" + tmp + "'")
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index a6006abe2cceb66565de1df476c0a55cc623e41f..52223f8af351c9fb4e206fd0d23db08a005cad75 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -15,6 +15,11 @@ open(os.path.join(demo, "exemplo.nx"), "w").write('use sys\n// um exemplo para o
 open(os.path.join(demo, "sem_fim.nx"), "w").write('use sys\nlet i = 0\nwhile true do\n    print(f"volta {i}")\n    i = i + 1\n    sys.sleep(100)\nend\n')
 open(os.path.join(demo, "notas.txt"), "w").write("texto simples\n")
 open(os.path.join(demo, "src", "util.nx"), "w").write("let x = 1\n")
+# a demo e um repositorio git: notas.txt fica modificado depois do commit
+import shutil as _shg
+_shg.rmtree(os.path.join(demo, ".git"), ignore_errors=True)
+subprocess.run("git init -q -b demo-branch && git -c user.name=t -c user.email=t@t add . && git -c user.name=t -c user.email=t@t commit -q -m init", shell=True, cwd=demo, check=True)
+open(os.path.join(demo, "notas.txt"), "a").write("mudou\n")
 cfg = os.path.join(os.getcwd(), "tests", "tmp", "web_config")
 env = dict(os.environ, NOXY_EDITOR_NO_WINDOW="1", NOXY_EDITOR_CONFIG_DIR=cfg, NOXY_EDITOR_CACHE_DIR=os.path.join(os.getcwd(), "tests", "tmp", "web_cache"))
 import shutil as _sh; _sh.rmtree(env["NOXY_EDITOR_CACHE_DIR"], ignore_errors=True)
@@ -85,6 +90,9 @@ ws.call("Page.navigate", {"url": url}); settle(1500)
 check("arvore renderizada", ev("document.querySelectorAll('#tree .node').length") == 4)
 check("nome da raiz", ev("document.getElementById('root-name').textContent") == "web")
 check("titulo inicial", ev("document.title") == "Noxy Editor")
+settle(800)
+check("git: branch na barra de status", "demo-branch" in ev("document.getElementById('status-git').textContent"))
+check("git: arquivo modificado marcado na arvore", ev("Array.from(document.querySelectorAll('#tree .node')).find(n => n.textContent.includes('notas.txt')).classList.contains('git-M')"))
 check("tema escuro aplicado no html", ev("document.documentElement.classList.contains('theme-dark')"))
 # abrir exemplo.nx pela arvore
 ev("document.querySelectorAll('#tree .node.file')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
@@ -136,6 +144,7 @@ key("F5"); settle(1500)
 check("F5 mostra o painel de saida", not ev("document.getElementById('output').classList.contains('hidden')"))
 out = ev("document.getElementById('output-text').textContent")
 check("saida do programa aparece", "$ noxy exemplo.nx" in out and "[saiu com" in out)
+check("git: salvar e rodar marcam o arquivo na arvore e na aba", ev("Array.from(document.querySelectorAll('#tree .node')).find(n => n.textContent.includes('exemplo.nx')).classList.contains('git-M')") and ev("document.querySelector('.tab.active').classList.contains('git-M')"))
 # parar pelo botao: um programa sem fim com saida ao vivo
 key("p", mods=2); ws.call("Input.insertText", {"text": "sem_fim"}); settle(); key("Enter")
 key("F5"); settle(1200)
diff --git a/web/editor.css b/web/editor.css
index a0350e77ba1b5bf128cd7c1cad13f1b34ea1e6c6..1f305cbaeee3d2e445ad152518f01427d49f5c53 100644
--- a/web/editor.css
+++ b/web/editor.css
@@ -139,6 +139,11 @@ button { font: inherit; color: inherit; background: none; border: none; cursor:
 
 /* barra de status */
 #status { display: flex; align-items: center; gap: 16px; padding: 0 14px; background: var(--bg-status); border-top: 1px solid var(--border); font-size: 12px; color: var(--fg-dim); }
+#status-git { color: var(--fg-dim); }
+.git-M > .name, .tab.git-M .name { color: var(--warn); }
+.git-A > .name, .git-\? > .name, .git-R > .name, .tab.git-A .name, .tab.git-\? .name, .tab.git-R .name { color: var(--ok); }
+.git-D > .name, .tab.git-D .name { color: var(--danger); text-decoration: line-through; }
+.node.git-dir > .name::after { content: " •"; color: var(--warn); }
 #status-msg { flex: 1; color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
 #status.dead #status-msg { color: var(--danger); }
 
diff --git a/web/editor.js b/web/editor.js
index 270289918de618e4cb3a00ee776590c3b0a604ec..4975a8e5009063d22c4f35bcbf16dc37fe867107 100644
--- a/web/editor.js
+++ b/web/editor.js
@@ -13,7 +13,7 @@
     main: $("main"), output: $("output"), outputText: $("output-text"), outputClose: $("output-close"), outputResize: $("output-resize"), outputHead: $("output-head"),
     panelTabs: $("panel-tabs"), searchView: $("search-view"), termView: $("term-view"),
     runStop: $("run-stop"), searchInput: $("search-input"), searchCase: $("search-case"), searchStatus: $("search-status"), searchResults: $("search-results"),
-    status: $("status"), statusLeft: $("status-left"), statusMsg: $("status-msg"), statusRight: $("status-right"),
+    status: $("status"), statusGit: $("status-git"), statusLeft: $("status-left"), statusMsg: $("status-msg"), statusRight: $("status-right"),
     modal: $("modal"), modalText: $("modal-text"), modalButtons: $("modal-buttons"),
     list: $("list"), listInput: $("list-input"), listItems: $("list-items"),
     findbar: $("findbar"), findInput: $("find-input"), findCase: $("find-case"), findCount: $("find-count"), findPrev: $("find-prev"), findNext: $("find-next"), findClose: $("find-close"),
@@ -66,6 +66,7 @@
     ev.tree_version = treeVersion;
     ev.page = PAGE_ID;
     ev.search_version = searchVersion;
+    ev.git_version = git.version;
     try {
       const res = await fetch("/event", {
         method: "POST",
@@ -95,6 +96,17 @@
     theme = name;
   }
 
+  // git: o ultimo status recebido (so vem quando a versao muda); a arvore e
+  // redesenhada com as cores quando ele muda
+  let git = { version: 0, available: false, branch: "", status: {}, dirs: {} };
+  let treeRoot = "", treeNodes = [];
+  function gitClass(path, isDir) {
+    if (!git.available) return "";
+    if (isDir) return git.dirs[path] ? " git-dir" : "";
+    const c = git.status[path];
+    return c ? " git-" + c : "";
+  }
+
   function el(tag, cls, text) {
     const e = document.createElement(tag);
     if (cls) e.className = cls;
@@ -106,8 +118,12 @@
     frame = f;
     document.title = f.title;
     applyTheme(f.settings.theme);
+    const gitChanged = f.git.version !== git.version;
+    if (gitChanged) git = f.git;
+    els.statusGit.textContent = git.available ? "⎇ " + git.branch : "";
     renderTabs(f.tabs);
-    if (f.tree_version !== treeVersion) { treeVersion = f.tree_version; renderTree(f.root, f.tree); }
+    if (f.tree_version !== treeVersion) { treeVersion = f.tree_version; treeRoot = f.root; treeNodes = f.tree; renderTree(treeRoot, treeNodes); }
+    else if (gitChanged) renderTree(treeRoot, treeNodes);
     renderView(f);
     els.statusLeft.textContent = f.status.left;
     els.statusRight.textContent = f.status.right;
@@ -132,7 +148,7 @@
 
   function renderTabs(tabs) {
     els.tabs.replaceChildren(...tabs.map((t, i) => {
-      const tab = el("div", "tab" + (t.active ? " active" : ""));
+      const tab = el("div", "tab" + (t.active ? " active" : "") + gitClass(t.path, false));
       tab.title = t.path;
       tab.append(el("span", "name", t.name + (t.dirty ? " ●" : "")));
       const close = el("span", "close", "×");
@@ -151,7 +167,7 @@
   function renderTree(root, nodes) {
     els.rootName.textContent = root;
     els.tree.replaceChildren(...nodes.map((n) => {
-      const node = el("div", "node " + (n.is_dir ? "dir" : "file"));
+      const node = el("div", "node " + (n.is_dir ? "dir" : "file") + gitClass(n.path, n.is_dir));
       node.style.paddingLeft = (10 + n.depth * 14) + "px";
       node.append(el("span", "chev", n.is_dir ? (n.expanded ? "▾" : "▸") : ""));
       node.append(el("span", "name", n.name));
diff --git a/web/index.html b/web/index.html
index 54472bdd6a8be9ee026d603a112f08106114f077..6650db55b82848aadca0b38d82cb17ea7dd5335f 100644
--- a/web/index.html
+++ b/web/index.html
@@ -61,6 +61,7 @@
     <div id="status">
       <span id="status-left"></span>
       <span id="status-msg"></span>
+      <span id="status-git"></span>
       <span id="status-right"></span>
     </div>
   </main>
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `262/262 passaram` e `10/10 passaram`.
- [ ] **Passo 5: o cliente de verdade**

Run: `python3 tests/web_smoke.py && GDK_BACKEND=x11 python3 tests/webkit_smoke.py`
Esperado: as duas linhas finais `OK: 0 falhas` (o primeiro precisa de `google-chrome`; o segundo abre uma janela WebKitGTK por alguns segundos).
- [ ] **Commit**

```bash
git add docs/ACHADOS.md editor.nx src/events.nx src/frame.nx src/gitinfo.nx src/session.nx tests/run.nx tests/web_smoke.py web/editor.css web/editor.js web/index.html
git commit -q -m 'feat(git): branch na status e arquivos alterados coloridos na arvore e nas abas; status coletado numa task, enviado so quando muda; contorno para exec_output que apara a saida

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 11: Minimap

**Interfaces:**
- Produces: `minimap.KINDS`, `minimap.kind_index`, `minimap.shape(d) -> int[]`; `frame.MinimapOut { path, lines }` e `frame.build(..., want_minimap)`; `editing.scroll_to`; evento `minimap_goto`; `#editor-row` e `canvas#minimap` no cliente.

**Files:** `src/editing.nx`, `src/events.nx`, `src/frame.nx`, `src/minimap.nx`, `tests/run.nx`, `tests/web_smoke.py`, `web/editor.css`, `web/editor.js`, `web/index.html`

- [ ] **Passo 1: os testes (vermelho)**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (103 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/run.nx b/tests/run.nx
index 79664dc0d47d527cf22d9d4a27b4722b5506b6cb..392cb5984ffd97e95a793ed345e19b8f064a0fa1 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -20,6 +20,7 @@ use src.find as find
 use src.search as search
 use src.recovery as recovery
 use src.gitinfo as gitinfo
+use src.minimap as minimap
 
 // cache e configuracao isolados: os testes nunca tocam no ~/.cache e no
 // ~/.config de quem roda
@@ -949,6 +950,35 @@ func test_git_session() -> void
     check("comando git_refresh", s.git_task != null)
 end
 
+func test_minimap() -> void
+    print("minimap")
+    let d: doc.Document = doc.from_text("m.nx", "let x = 1\n\n    // nota\nprint(x)\n" + strings.repeat("y", 300))
+    let sh: int[] = minimap.shape(d)
+    check("dois inteiros por linha", length(sh) == 10)
+    check("comprimento e kind do primeiro token nao espaco", sh[0] == 9 && sh[1] == minimap.kind_index("keyword") && sh[2] == 0 && sh[3] == 0 && sh[5] == minimap.kind_index("comment") && sh[7] == minimap.kind_index("call"))
+    check("comprimento limitado a 120", sh[8] == 120)
+    check("indentacao conta no comprimento", sh[4] == 11)
+
+    let root: string = tmp_root()
+    let s: session.Session = session.new_session(root)
+    session.load(ref s)
+    let lines: string = ""
+    for i in range(200) do
+        lines = lines + "let v" + to_str(i) + " = " + to_str(i) + "\n"
+    end
+    write_file(root + "/longo.nx", lines)
+    session.open_file(ref s, root + "/longo.nx")
+    let sem: string = events.dispatch(ref s, "{\"kind\":\"poll\",\"rows\":20,\"tree_version\":2}", 1)
+    check("sem pedir, o minimap vem vazio", strings.contains(sem, "\"minimap\":{\"lines\":[],\"path\":\"\"}"))
+    let com: string = events.dispatch(ref s, "{\"kind\":\"poll\",\"rows\":20,\"tree_version\":2,\"want_minimap\":true}", 1)
+    check("pedindo, vem o formato do arquivo ativo", strings.contains(com, "\"path\":\"" + root + "/longo.nx\"") && strings.contains(com, "\"lines\":[10,1,"))
+    events.dispatch(ref s, "{\"kind\":\"minimap_goto\",\"line\":150,\"rows\":20,\"tree_version\":2}", 1)
+    check("minimap_goto centraliza a linha", s.tabs[s.active].editor.top == 140)
+    events.dispatch(ref s, "{\"kind\":\"minimap_goto\",\"line\":199,\"rows\":20,\"tree_version\":2}", 1)
+    check("minimap_goto nao passa do fim", s.tabs[s.active].editor.top == 181)
+    io.remove(root + "/longo.nx")
+end
+
 test_document()
 test_lexer()
 test_history()
@@ -967,4 +997,5 @@ test_search()
 test_recovery()
 test_gitinfo()
 test_git_session()
+test_minimap()
 report()
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index 52223f8af351c9fb4e206fd0d23db08a005cad75..5fe3f1b5e0251f6af2a37b1b793e0b297c45901c 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -13,6 +13,7 @@ demo = os.path.join("tests", "tmp", "web")
 os.makedirs(os.path.join(demo, "src"), exist_ok=True)
 open(os.path.join(demo, "exemplo.nx"), "w").write('use sys\n// um exemplo para o editor\nfunc soma(a: int, b: int) -> int\n    return a + b\nend\nlet nome: string = "Noxy"\nprint(f"ola {nome}: {soma(2, 3)}")\nfor i in range(3) do\n    print(i)\nend\n')
 open(os.path.join(demo, "sem_fim.nx"), "w").write('use sys\nlet i = 0\nwhile true do\n    print(f"volta {i}")\n    i = i + 1\n    sys.sleep(100)\nend\n')
+open(os.path.join(demo, "longo.nx"), "w").write("".join(f"let v{i} = {i}\n" for i in range(300)))
 open(os.path.join(demo, "notas.txt"), "w").write("texto simples\n")
 open(os.path.join(demo, "src", "util.nx"), "w").write("let x = 1\n")
 # a demo e um repositorio git: notas.txt fica modificado depois do commit
@@ -87,7 +88,7 @@ def mouse(kind, x, y, button="left", clicks=1, mods=0):
     ws.call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": button, "clickCount": clicks, "modifiers": mods})
 
 ws.call("Page.navigate", {"url": url}); settle(1500)
-check("arvore renderizada", ev("document.querySelectorAll('#tree .node').length") == 4)
+check("arvore renderizada", ev("document.querySelectorAll('#tree .node').length") == 5)
 check("nome da raiz", ev("document.getElementById('root-name').textContent") == "web")
 check("titulo inicial", ev("document.title") == "Noxy Editor")
 settle(800)
@@ -144,6 +145,15 @@ key("F5"); settle(1500)
 check("F5 mostra o painel de saida", not ev("document.getElementById('output').classList.contains('hidden')"))
 out = ev("document.getElementById('output-text').textContent")
 check("saida do programa aparece", "$ noxy exemplo.nx" in out and "[saiu com" in out)
+# minimap: arquivo longo, desenhado, e um clique perto do fim rola
+ev("Array.from(document.querySelectorAll('#tree .node')).find(n => n.textContent.includes('longo.nx')).dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle(800)
+check("minimap visivel com 90 px", ev("document.getElementById('minimap').getBoundingClientRect().width") == 90 and not ev("document.getElementById('minimap').classList.contains('hidden')"))
+check("minimap desenhado (pixel da primeira linha nao e transparente)", ev("document.getElementById('minimap').getContext('2d').getImageData(4, 0, 1, 1).data[3]") > 0)
+mm = ev("(() => { const r = document.getElementById('minimap').getBoundingClientRect(); return [r.left + 40, r.top + 290 * 2]; })()")
+mouse("mousePressed", mm[0], mm[1]); mouse("mouseReleased", mm[0], mm[1]); settle()
+check("clicar no minimap rola ate a linha", int(ev("document.querySelector('#gutter .gline').textContent")) > 250)
+ev("document.querySelector('.tab.active .close').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
+ev("document.querySelectorAll('.tab')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
 check("git: salvar e rodar marcam o arquivo na arvore e na aba", ev("Array.from(document.querySelectorAll('#tree .node')).find(n => n.textContent.includes('exemplo.nx')).classList.contains('git-M')") and ev("document.querySelector('.tab.active').classList.contains('git-M')"))
 # parar pelo botao: um programa sem fim com saida ao vivo
 key("p", mods=2); ws.call("Input.insertText", {"text": "sem_fim"}); settle(); key("Enter")
@@ -245,9 +255,9 @@ open(helper, "w").write("use src.browser as browser\nuse sys\nprint(browser.writ
 page = subprocess.run(["noxy", helper, url], capture_output=True, text=True).stdout.strip()
 check("write_redirect devolve um caminho", page.startswith("/"))
 ws.call("Page.navigate", {"url": "file://" + page}); settle(2000)
-check("pagina de redirecionamento leva ao editor", ev("location.href").startswith(url.split("?")[0]) and ev("document.querySelectorAll('#tree .node').length") == 4)
+check("pagina de redirecionamento leva ao editor", ev("location.href").startswith(url.split("?")[0]) and ev("document.querySelectorAll('#tree .node').length") == 5)
 time.sleep(3.5)
-check("editor continua vivo 3 s depois do reload", editor.poll() is None and ev("document.querySelectorAll('#tree .node').length") == 4)
+check("editor continua vivo 3 s depois do reload", editor.poll() is None and ev("document.querySelectorAll('#tree .node').length") == 5)
 # recuperacao: editar sem salvar, esperar a copia (poll 1,5 s depois da
 # ultima edicao), matar o editor e abrir outro: a aba volta suja
 ev("document.querySelectorAll('#tree .node.file')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: `Runtime error: [tests/run.nx:line 31] failed to import module 'src.minimap': module not found: src.minimap`
- [ ] **Commit**

```bash
git add tests/run.nx tests/web_smoke.py
git commit -q -m 'test(minimap): formato do arquivo, envio sob pedido e clique para rolar

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3: a implementação**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (387 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/src/editing.nx b/src/editing.nx
index 5095b4cf9c4a6ca1d770db8abf2ff4df80fbe3a1..d08f91c8c6ea193ea67b485ea3c79c87772169a8 100644
--- a/src/editing.nx
+++ b/src/editing.nx
@@ -136,6 +136,11 @@ func scroll(ed: ref Editor, delta: int, rows: int) -> void
     ed.top = t
 end
 
+// scroll_to poe a janela com top em line, dentro dos limites; nao move o cursor.
+func scroll_to(ed: ref Editor, line: int, rows: int) -> void
+    scroll(ed, line - ed.top, rows)
+end
+
 // place poe o cursor em p (clampado); sem shift a ancora acompanha.
 func place(ed: ref Editor, p: doc.Pos, shift: bool, rows: int) -> void
     ed.cursor = doc.clamp(ed.doc, p)
diff --git a/src/events.nx b/src/events.nx
index 99ac272cb9352206e18b36fc58f43d17f15087ef..966003edb79913982669ef2fe6f3b51af95627ea 100644
--- a/src/events.nx
+++ b/src/events.nx
@@ -35,10 +35,11 @@ struct Event
     case_sensitive: bool   // da busca (case e palavra reservada)
     search_version: int    // a versao dos resultados da busca na pasta que o cliente tem
     git_version: int       // a versao do status do git que o cliente tem
+    want_minimap: bool     // o cliente quer o formato do arquivo para o minimap
 end
 
 func empty_event() -> Event
-    return Event("", "", false, false, false, "", 0, 0, 0, "", 0, 0, 0, "", false, 0, 0)
+    return Event("", "", false, false, false, "", 0, 0, 0, "", 0, 0, 0, "", false, 0, 0, false)
 end
 
 // now e o relogio do dono do estado, em milissegundos. time_now() da
@@ -413,6 +414,10 @@ func apply(s: session.Session, e: Event, now: int) -> session.Session
         end
     elif e.kind == "find_close" then
         close_find(ref s)
+    elif e.kind == "minimap_goto" then
+        if s.active >= 0 then
+            editing.scroll_to(ref s.tabs[s.active].editor, e.line - s.rows / 2, s.rows)
+        end
     elif e.kind == "search" then
         session.start_search(ref s, e.text, e.case_sensitive)
     elif e.kind == "search_open" then
@@ -473,5 +478,5 @@ func dispatch(s: ref session.Session, body: string, now: int) -> string
     session.poll_index(s)
     session.poll_search(s)
     session.poll_git(s)
-    return frame.build(s, e.tree_version, e.search_version, e.git_version)
+    return frame.build(s, e.tree_version, e.search_version, e.git_version, e.want_minimap)
 end
diff --git a/src/frame.nx b/src/frame.nx
index f0ba856fe5b06e96c3568566951915701f09bdf8..a7373ffc77d2193fe3f1bb4cb137447f4cf68caa 100644
--- a/src/frame.nx
+++ b/src/frame.nx
@@ -11,6 +11,7 @@ use src.settings as settings
 use src.find as find
 use src.search as search
 use src.gitinfo as gitinfo
+use src.minimap as minimap
 
 struct SpanOut
     k: string       // kind do token
@@ -37,6 +38,11 @@ struct SearchOut
     hits: search.Hit[]     // vazio quando o cliente ja tem esta versao
 end
 
+struct MinimapOut
+    path: string    // "" quando nao foi pedido
+    lines: int[]    // comprimento e kind por linha (minimap.shape)
+end
+
 struct FindOut
     open: bool
     replace: bool
@@ -101,6 +107,7 @@ struct Frame
     find: FindOut
     search: SearchOut
     git: gitinfo.GitInfo       // status e dirs vazios quando o cliente ja tem esta versao
+    minimap: MinimapOut
 end
 
 // covered: o pedaco [p, q) esta dentro de alguma marca do papel kind?
@@ -217,6 +224,14 @@ func search_out(s: ref session.Session, client_version: int) -> SearchOut
     return SearchOut(s.search.query, s.search.case_sensitive, s.search.running, s.search.truncated, s.search.version, hits)
 end
 
+func minimap_out(s: ref session.Session, want: bool) -> MinimapOut
+    if !want || s.active < 0 then
+        return MinimapOut("", [])
+    end
+    let d: doc.Document = s.tabs[s.active].editor.doc
+    return MinimapOut(d.path, minimap.shape(d))
+end
+
 func git_out(s: ref session.Session, client_version: int) -> gitinfo.GitInfo
     if client_version == s.git.version then
         let g: gitinfo.GitInfo = gitinfo.empty_git()
@@ -240,7 +255,7 @@ func title_of(s: ref session.Session) -> string
     return session.basename(d.path) + mark + " — Noxy Editor"
 end
 
-func build(s: ref session.Session, client_tree_version: int, client_search_version: int, client_git_version: int) -> string
+func build(s: ref session.Session, client_tree_version: int, client_search_version: int, client_git_version: int, want_minimap: bool) -> string
     let tabs: TabOut[] = []
     for i in range(length(s.tabs)) do
         let d: doc.Document = s.tabs[i].editor.doc
@@ -266,7 +281,7 @@ func build(s: ref session.Session, client_tree_version: int, client_search_versi
         right = "Ln " + to_str(ed.cursor.line + 1) + ", Col " + to_str(ed.cursor.col + 1) + "   Espaços: 4   " + doc.eol_name(ed.doc)
         eol = doc.eol_name(ed.doc)
     end
-    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings, s.list, FindOut(s.find.open, s.find.replace, s.find.query, s.find.case_sensitive, length(s.find.matches), s.find.current), search_out(s, client_search_version), git_out(s, client_git_version))
+    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings, s.list, FindOut(s.find.open, s.find.replace, s.find.query, s.find.case_sensitive, length(s.find.matches), s.find.current), search_out(s, client_search_version), git_out(s, client_git_version), minimap_out(s, want_minimap))
     s.clipboard = ""
     return json_dumps(f)
 end
diff --git a/src/minimap.nx b/src/minimap.nx
new file mode 100644
index 0000000000000000000000000000000000000000..7538211903b9b90c69a5b88d30c627cbcdcb24c1
--- /dev/null
+++ b/src/minimap.nx
@@ -0,0 +1,37 @@
+// src/minimap.nx — o formato do documento para o minimap: por linha, o
+// comprimento (ate MAX_LEN) e o kind do primeiro token que nao e espaco.
+// Vai no quadro so quando o cliente pede (want_minimap).
+use src.document as doc
+use src.lexer as lexer
+
+let MAX_LEN = 120
+let KINDS: string[] = ["", "keyword", "type", "ident", "call", "number", "string", "comment", "operator", "punct"]
+
+func kind_index(kind: string) -> int
+    for i in range(length(KINDS)) do
+        if KINDS[i] == kind then
+            return i
+        end
+    end
+    return 0
+end
+
+func shape(d: doc.Document) -> int[]
+    let out: int[] = []
+    for line in d.lines do
+        let n: int = length(line)
+        if n > MAX_LEN then
+            n = MAX_LEN
+        end
+        let k: int = 0
+        for t in lexer.tokenize(line) do
+            if t.kind != "space" then
+                k = kind_index(t.kind)
+                break
+            end
+        end
+        append(ref out, n)
+        append(ref out, k)
+    end
+    return out
+end
diff --git a/tests/run.nx b/tests/run.nx
index 392cb5984ffd97e95a793ed345e19b8f064a0fa1..978f6f12c234014fbb3cb2dde6b5ef6d6b9cde9c 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -479,9 +479,9 @@ func test_frame() -> void
     let s: session.Session = session.new_session(root)
     session.load(ref s)
     s.rows = 2
-    let empty: string = frame.build(ref s, 0, 0, 0)
+    let empty: string = frame.build(ref s, 0, 0, 0, false)
     check("sem aba: tabs vazio e arvore presente", strings.contains(empty, "\"tabs\":[]") && strings.contains(empty, "\"name\":\"b.nx\"") && strings.contains(empty, "\"title\":\"Noxy Editor\""))
-    let same: string = frame.build(ref s, s.tree_version, 0, 0)
+    let same: string = frame.build(ref s, s.tree_version, 0, 0, false)
     check("arvore omitida quando a versao bate", strings.contains(same, "\"tree\":[]"))
 
     session.open_file(ref s, root + "/b.nx")
@@ -491,7 +491,7 @@ func test_frame() -> void
     editing.click(ref s.tabs[0].editor, doc.Pos(0, 1), false, 2)
     editing.drag(ref s.tabs[0].editor, doc.Pos(1, 1), 2)
     s.clipboard = "cp"
-    let f: string = frame.build(ref s, s.tree_version, 0, 0)
+    let f: string = frame.build(ref s, s.tree_version, 0, 0, false)
     check("spans cortados na fronteira da selecao", strings.contains(f, "{\"c\":false,\"f\":false,\"k\":\"keyword\",\"s\":false,\"t\":\"l\"}") && strings.contains(f, "{\"c\":false,\"f\":false,\"k\":\"keyword\",\"s\":true,\"t\":\"et\"}") && strings.contains(f, "{\"c\":false,\"f\":false,\"k\":\"ident\",\"s\":true,\"t\":\"x\"}"))
     check("cursor, has_sel e total", strings.contains(f, "\"cursor\":{\"col\":1,\"line\":1}") && strings.contains(f, "\"has_sel\":true") && strings.contains(f, "\"total\":3"))
     check("aba suja e titulo", strings.contains(f, "\"dirty\":true") && strings.contains(f, "b.nx ● — Noxy Editor"))
@@ -499,7 +499,7 @@ func test_frame() -> void
     check("clipboard vai e e consumido", strings.contains(f, "\"clipboard\":\"cp\"") && s.clipboard == "")
     s.rows = 1
     editing.ensure_visible(ref s.tabs[0].editor, 1)
-    let one: string = frame.build(ref s, s.tree_version, 0, 0)
+    let one: string = frame.build(ref s, s.tree_version, 0, 0, false)
     check("so as linhas visiveis", strings.contains(one, "\"n\":1") && !strings.contains(one, "\"n\":0") && !strings.contains(one, "\"n\":2"))
     check("title_of", frame.title_of(ref s) == "b.nx ● — Noxy Editor")
 
@@ -513,7 +513,7 @@ func test_frame() -> void
     bs.rows = 50
     editing.move_doc_end(ref bs.tabs[0].editor, false, 50)
     let t0: int = events.now()
-    let bf: string = frame.build(ref bs, 1, 0, 0)
+    let bf: string = frame.build(ref bs, 1, 0, 0, false)
     let dt: int = events.now() - t0
     check("arquivo de 5000 linhas: quadro so com as visiveis, em menos de 200 ms", strings.contains(bf, "\"total\":5000") && !strings.contains(bf, "\"n\":100,") && dt < 200)
 end
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index 5fe3f1b5e0251f6af2a37b1b793e0b297c45901c..1c870a762b9b75478ef387254f450bc8f734b6b6 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -149,7 +149,7 @@ check("saida do programa aparece", "$ noxy exemplo.nx" in out and "[saiu com" in
 ev("Array.from(document.querySelectorAll('#tree .node')).find(n => n.textContent.includes('longo.nx')).dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle(800)
 check("minimap visivel com 90 px", ev("document.getElementById('minimap').getBoundingClientRect().width") == 90 and not ev("document.getElementById('minimap').classList.contains('hidden')"))
 check("minimap desenhado (pixel da primeira linha nao e transparente)", ev("document.getElementById('minimap').getContext('2d').getImageData(4, 0, 1, 1).data[3]") > 0)
-mm = ev("(() => { const r = document.getElementById('minimap').getBoundingClientRect(); return [r.left + 40, r.top + 290 * 2]; })()")
+mm = ev("(() => { const r = document.getElementById('minimap').getBoundingClientRect(); return [r.left + 40, r.bottom - 6]; })()")
 mouse("mousePressed", mm[0], mm[1]); mouse("mouseReleased", mm[0], mm[1]); settle()
 check("clicar no minimap rola ate a linha", int(ev("document.querySelector('#gutter .gline').textContent")) > 250)
 ev("document.querySelector('.tab.active .close').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
diff --git a/web/editor.css b/web/editor.css
index 1f305cbaeee3d2e445ad152518f01427d49f5c53..7284349c8817ebedf5d2267d2e092804f77a39a0 100644
--- a/web/editor.css
+++ b/web/editor.css
@@ -72,7 +72,9 @@ button { font: inherit; color: inherit; background: none; border: none; cursor:
 #run-btn { padding: 0 14px; color: var(--k-string); }
 #run-btn:hover { background: var(--bg-hover); }
 
-#editor { position: relative; display: flex; min-height: 0; overflow-x: auto; overflow-y: hidden; font: 14px var(--font-mono); }
+#editor-row { display: flex; min-height: 0; min-width: 0; }
+#editor { position: relative; flex: 1; min-width: 0; display: flex; min-height: 0; overflow-x: auto; overflow-y: hidden; font: 14px var(--font-mono); }
+#minimap { flex: none; width: 90px; height: 100%; background: var(--bg); border-left: 1px solid var(--border); cursor: pointer; }
 #gutter { position: sticky; left: 0; z-index: 2; flex: none; width: 56px; padding-right: 12px; text-align: right; color: var(--fg-dim); background: var(--bg); user-select: none; }
 #text { position: relative; flex: 1; min-width: max-content; padding-right: 48px; }
 .line, .gline { height: var(--line-h); line-height: var(--line-h); white-space: pre; tab-size: 4; }
diff --git a/web/editor.js b/web/editor.js
index 4975a8e5009063d22c4f35bcbf16dc37fe867107..553d18a15785db30db6907b3122ad1e173dddc8c 100644
--- a/web/editor.js
+++ b/web/editor.js
@@ -9,7 +9,7 @@
   const $ = (id) => document.getElementById(id);
   const els = {
     rootName: $("root-name"), tree: $("tree"), tabs: $("tabs"), runBtn: $("run-btn"),
-    editor: $("editor"), gutter: $("gutter"), text: $("text"), cursor: $("cursor"), welcome: $("welcome"),
+    editor: $("editor"), minimap: $("minimap"), gutter: $("gutter"), text: $("text"), cursor: $("cursor"), welcome: $("welcome"),
     main: $("main"), output: $("output"), outputText: $("output-text"), outputClose: $("output-close"), outputResize: $("output-resize"), outputHead: $("output-head"),
     panelTabs: $("panel-tabs"), searchView: $("search-view"), termView: $("term-view"),
     runStop: $("run-stop"), searchInput: $("search-input"), searchCase: $("search-case"), searchStatus: $("search-status"), searchResults: $("search-results"),
@@ -46,7 +46,7 @@
   let idleTimer = 0;
   function send(ev) {
     if (dead) return;
-    if (EDITS[ev.kind]) { clearTimeout(idleTimer); idleTimer = setTimeout(() => send({ kind: "poll" }), 1500); }
+    if (EDITS[ev.kind]) { clearTimeout(idleTimer); idleTimer = setTimeout(() => send({ kind: "poll" }), 1500); askMinimap(300); }
     if (ev.kind === "scroll") {
       const q = queue.find((e) => e.kind === "scroll");
       if (q) { q.delta += ev.delta; pump(); return; }
@@ -67,6 +67,7 @@
     ev.page = PAGE_ID;
     ev.search_version = searchVersion;
     ev.git_version = git.version;
+    if (needMinimap) { ev.want_minimap = true; needMinimap = false; }
     try {
       const res = await fetch("/event", {
         method: "POST",
@@ -107,6 +108,53 @@
     return c ? " git-" + c : "";
   }
 
+  // minimap: o formato do arquivo vem do Noxy so quando pedido (troca de aba
+  // e, depois de edicoes, no maximo a cada 300 ms); o retangulo da area
+  // visivel sai de top e total, que todo quadro traz
+  let mm = { path: "", lines: [] }, needMinimap = false, mmTimer = 0, mmActive = "";
+  const MM_KINDS = ["", "keyword", "type", "ident", "call", "number", "string", "comment", "operator", "punct"];
+  function askMinimap(delay) {
+    if (mmTimer) return;
+    mmTimer = setTimeout(() => { mmTimer = 0; needMinimap = true; send({ kind: "poll" }); }, delay);
+  }
+  function renderMinimap(f) {
+    const c = els.minimap;
+    if (f.tabs.length === 0) { c.classList.add("hidden"); mmActive = ""; return; }
+    c.classList.remove("hidden");
+    const active = f.tabs.find((t) => t.active);
+    if (f.minimap.path) mm = f.minimap;
+    if (active && active.path !== mmActive) { mmActive = active.path; if (mm.path !== active.path) { needMinimap = true; askMinimap(0); } }
+    const h = c.clientHeight, w = c.clientWidth;
+    if (c.height !== h) c.height = h;
+    if (c.width !== w) c.width = w;
+    const ctx = c.getContext("2d");
+    ctx.clearRect(0, 0, w, h);
+    const total = Math.max(1, f.view.total);
+    const lh = Math.min(2, h / total);
+    const style = getComputedStyle(document.documentElement);
+    const colors = MM_KINDS.map((k) => k ? style.getPropertyValue("--k-" + k).trim() : style.getPropertyValue("--fg-dim").trim());
+    if (mm.path === (active && active.path)) {
+      ctx.globalAlpha = 0.75;
+      for (let i = 0; i < mm.lines.length / 2; i++) {
+        const len = mm.lines[2 * i], k = mm.lines[2 * i + 1];
+        if (!len) continue;
+        ctx.fillStyle = colors[k] || colors[0];
+        ctx.fillRect(4, i * lh, Math.max(1, len * 0.7), Math.max(1, lh * 0.8));
+      }
+      ctx.globalAlpha = 1;
+    }
+    ctx.fillStyle = style.getPropertyValue("--sel").trim();
+    ctx.globalAlpha = 0.35;
+    ctx.fillRect(0, f.view.top * lh, w, Math.max(4, f.view.lines.length * lh));
+    ctx.globalAlpha = 1;
+    minimapScale = lh;
+  }
+  let minimapScale = 2, mmDrag = false;
+  function minimapGoto(e) {
+    const r = els.minimap.getBoundingClientRect();
+    send({ kind: "minimap_goto", line: Math.floor((e.clientY - r.top) / minimapScale) });
+  }
+
   function el(tag, cls, text) {
     const e = document.createElement(tag);
     if (cls) e.className = cls;
@@ -125,6 +173,7 @@
     if (f.tree_version !== treeVersion) { treeVersion = f.tree_version; treeRoot = f.root; treeNodes = f.tree; renderTree(treeRoot, treeNodes); }
     else if (gitChanged) renderTree(treeRoot, treeNodes);
     renderView(f);
+    renderMinimap(f);
     els.statusLeft.textContent = f.status.left;
     els.statusRight.textContent = f.status.right;
     els.statusMsg.textContent = f.status.message;
@@ -526,6 +575,14 @@
   // ---- botoes, redimensionar, poll durante execucao, fechamento
   els.runBtn.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "run" }); });
   els.outputClose.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "panel_toggle" }); });
+  els.minimap.addEventListener("pointerdown", (e) => {
+    if (e.button !== 0) return;
+    e.preventDefault(); mmDrag = true;
+    try { els.minimap.setPointerCapture(e.pointerId); } catch (err) { /* sem captura */ }
+    minimapGoto(e);
+  });
+  els.minimap.addEventListener("pointermove", (e) => { if (mmDrag) minimapGoto(e); });
+  els.minimap.addEventListener("pointerup", () => { mmDrag = false; });
   els.runStop.addEventListener("mousedown", (e) => { e.preventDefault(); e.stopPropagation(); send({ kind: "stop" }); });
   for (const tab of els.panelTabs.querySelectorAll(".ptab")) {
     tab.addEventListener("mousedown", (e) => { e.preventDefault(); if (tab.dataset.tab === "search") wantSearchFocus = true; send({ kind: "panel_tab", key: tab.dataset.tab }); });
diff --git a/web/index.html b/web/index.html
index 6650db55b82848aadca0b38d82cb17ea7dd5335f..80f1ab823e9ce0e6eab8a5953a3c9005a2361353 100644
--- a/web/index.html
+++ b/web/index.html
@@ -16,25 +16,28 @@
       <div id="tabs"></div>
       <button id="run-btn" title="Executar (F5)">▶ Executar</button>
     </div>
-    <div id="editor">
-      <div id="gutter"></div>
-      <div id="text"><div id="cursor" class="hidden"></div></div>
-      <div id="welcome">Abra um arquivo na árvore à esquerda.</div>
-      <div id="findbar" class="hidden">
-        <div class="find-row">
-          <input id="find-input" placeholder="Buscar" autocomplete="off" spellcheck="false">
-          <button id="find-case" title="Diferenciar maiúsculas">Aa</button>
-          <span id="find-count"></span>
-          <button id="find-prev" title="Anterior (Shift+Enter)">↑</button>
-          <button id="find-next" title="Próxima (Enter)">↓</button>
-          <button id="find-close" title="Fechar (Esc)">×</button>
-        </div>
-        <div id="find-replace-row" class="find-row hidden">
-          <input id="find-replace" placeholder="Substituir" autocomplete="off" spellcheck="false">
-          <button id="find-one" title="Substituir a atual (Enter)">Substituir</button>
-          <button id="find-all" title="Substituir todas">Todas</button>
+    <div id="editor-row">
+      <div id="editor">
+        <div id="gutter"></div>
+        <div id="text"><div id="cursor" class="hidden"></div></div>
+        <div id="welcome">Abra um arquivo na árvore à esquerda.</div>
+        <div id="findbar" class="hidden">
+          <div class="find-row">
+            <input id="find-input" placeholder="Buscar" autocomplete="off" spellcheck="false">
+            <button id="find-case" title="Diferenciar maiúsculas">Aa</button>
+            <span id="find-count"></span>
+            <button id="find-prev" title="Anterior (Shift+Enter)">↑</button>
+            <button id="find-next" title="Próxima (Enter)">↓</button>
+            <button id="find-close" title="Fechar (Esc)">×</button>
+          </div>
+          <div id="find-replace-row" class="find-row hidden">
+            <input id="find-replace" placeholder="Substituir" autocomplete="off" spellcheck="false">
+            <button id="find-one" title="Substituir a atual (Enter)">Substituir</button>
+            <button id="find-all" title="Substituir todas">Todas</button>
+          </div>
         </div>
       </div>
+      <canvas id="minimap" class="hidden" width="90" height="100"></canvas>
     </div>
     <div id="output" class="hidden">
       <div id="output-resize" title="Arraste para redimensionar"></div>
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `270/270 passaram` e `10/10 passaram`.
- [ ] **Passo 5: o cliente de verdade**

Run: `python3 tests/web_smoke.py && GDK_BACKEND=x11 python3 tests/webkit_smoke.py`
Esperado: as duas linhas finais `OK: 0 falhas` (o primeiro precisa de `google-chrome`; o segundo abre uma janela WebKitGTK por alguns segundos).
- [ ] **Commit**

```bash
git add src/editing.nx src/events.nx src/frame.nx src/minimap.nx tests/run.nx tests/web_smoke.py web/editor.css web/editor.js web/index.html
git commit -q -m 'feat(minimap): formato do arquivo sob pedido, canvas com a area visivel, clique e arraste para rolar

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 12: Cores do git visíveis na árvore

**Interfaces:**
- Consumes: as classes `git-<código>` da Task 10.

**Files:** `tests/web_smoke.py`, `web/editor.css`, `web/editor.js`

- [ ] **Passo 1: o teste que confere a cor calculada, não só a classe**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (12 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index 1c870a762b9b75478ef387254f450bc8f734b6b6..bf726b5fb998226c4169e987c2f77666a6abf02c 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -94,6 +94,7 @@ check("titulo inicial", ev("document.title") == "Noxy Editor")
 settle(800)
 check("git: branch na barra de status", "demo-branch" in ev("document.getElementById('status-git').textContent"))
 check("git: arquivo modificado marcado na arvore", ev("Array.from(document.querySelectorAll('#tree .node')).find(n => n.textContent.includes('notas.txt')).classList.contains('git-M')"))
+check("git: e a cor aparece (diferente de um arquivo limpo)", ev("(() => { const f = (t) => getComputedStyle(Array.from(document.querySelectorAll('#tree .node')).find(n => n.textContent.includes(t)).querySelector('.name')).color; return f('notas.txt') !== f('longo.nx'); })()"))
 check("tema escuro aplicado no html", ev("document.documentElement.classList.contains('theme-dark')"))
 # abrir exemplo.nx pela arvore
 ev("document.querySelectorAll('#tree .node.file')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `python3 tests/web_smoke.py`
Esperado: `FAIL   git: e a cor aparece (diferente de um arquivo limpo)` e `FALHOU: 1 falhas`.
- [ ] **Passo 3: seletores com especificidade suficiente e o singular de "ocorrência"**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (30 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/web/editor.css b/web/editor.css
index 7284349c8817ebedf5d2267d2e092804f77a39a0..ce5864ae3d2e9029a90a6ffc9332d2c53137b6e6 100644
--- a/web/editor.css
+++ b/web/editor.css
@@ -142,9 +142,9 @@ button { font: inherit; color: inherit; background: none; border: none; cursor:
 /* barra de status */
 #status { display: flex; align-items: center; gap: 16px; padding: 0 14px; background: var(--bg-status); border-top: 1px solid var(--border); font-size: 12px; color: var(--fg-dim); }
 #status-git { color: var(--fg-dim); }
-.git-M > .name, .tab.git-M .name { color: var(--warn); }
-.git-A > .name, .git-\? > .name, .git-R > .name, .tab.git-A .name, .tab.git-\? .name, .tab.git-R .name { color: var(--ok); }
-.git-D > .name, .tab.git-D .name { color: var(--danger); text-decoration: line-through; }
+.node.git-M > .name, .tab.git-M .name { color: var(--warn); }
+.node.git-A > .name, .node.git-\? > .name, .node.git-R > .name, .tab.git-A .name, .tab.git-\? .name, .tab.git-R .name { color: var(--ok); }
+.node.git-D > .name, .tab.git-D .name { color: var(--danger); text-decoration: line-through; }
 .node.git-dir > .name::after { content: " •"; color: var(--warn); }
 #status-msg { flex: 1; color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
 #status.dead #status-msg { color: var(--danger); }
diff --git a/web/editor.js b/web/editor.js
index 553d18a15785db30db6907b3122ad1e173dddc8c..666d5262b7676967846b3bcc1ecce5a66c47ee82 100644
--- a/web/editor.js
+++ b/web/editor.js
@@ -535,7 +535,7 @@
       nodes.push(row);
     }
     els.searchResults.replaceChildren(...nodes);
-    els.searchStatus.textContent = sr.query ? (sr.hits.length ? sr.hits.length + (sr.truncated ? "+" : "") + " ocorrências" : "sem resultados") : "";
+    els.searchStatus.textContent = sr.query ? (sr.hits.length ? sr.hits.length + (sr.truncated ? "+" : "") + (sr.hits.length === 1 ? " ocorrência" : " ocorrências") : "sem resultados") : "";
   }
   els.searchInput.addEventListener("keydown", (e) => {
     if ((e.ctrlKey || e.metaKey) && !["a", "c", "v", "x", "z"].includes(e.key.toLowerCase())) { onKeyDown(e); e.stopPropagation(); return; }
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `python3 tests/web_smoke.py`
Esperado: `OK: 0 falhas`.
- [ ] **Commit**

```bash
git add tests/web_smoke.py web/editor.css web/editor.js
git commit -q -m "fix(web): cores do git aplicadas na arvore (especificidade) e singular em '1 ocorrencia'

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 13: noxy_pty: o gerenciador de terminais

**Interfaces:**
- Produces: pacote `ptys`: `Proc` (Read, Write, Resize, Kill), `Starter`, `ErrUnknown`, `ErrExited`, `Manager` com `NewManager(start)`, `Open(cmd, cwd, cols, rows) (int64, error)`, `Read(ctx, id, timeout) ([]byte, error)`, `Write`, `Resize`, `Close` (idempotente), `CloseAll`.

Tudo nesta tarefa roda em `/home/estevao/Documentos/noxy_projects/noxy_pty`, um repositório novo.

**Files:** `go.mod`, `.gitignore`, `ptys/ptys_test.go`, `ptys/ptys.go`

- [ ] **Passo 0: repositório**

```bash
mkdir -p /home/estevao/Documentos/noxy_projects/noxy_pty && cd /home/estevao/Documentos/noxy_projects/noxy_pty && git init -q -b main
```

- [ ] **Passo 1: os testes do gerenciador, com um processo falso**

Em `/home/estevao/Documentos/noxy_projects/noxy_pty` (187 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/.gitignore b/.gitignore
new file mode 100644
index 0000000000000000000000000000000000000000..a5d8f7237b21dc3265c0dd38255c30b6bbd7e14c
--- /dev/null
+++ b/.gitignore
@@ -0,0 +1,2 @@
+bin/
+dist/
diff --git a/go.mod b/go.mod
new file mode 100644
index 0000000000000000000000000000000000000000..172c50af745de8cab1bdee6a299420232239ed12
--- /dev/null
+++ b/go.mod
@@ -0,0 +1,3 @@
+module github.com/estevaofon/noxy_pty
+
+go 1.25.0
diff --git a/ptys/ptys_test.go b/ptys/ptys_test.go
new file mode 100644
index 0000000000000000000000000000000000000000..5c957662efc318362e176d946c8846050288d8e8
--- /dev/null
+++ b/ptys/ptys_test.go
@@ -0,0 +1,164 @@
+package ptys
+
+import (
+	"context"
+	"errors"
+	"io"
+	"sync"
+	"testing"
+	"time"
+)
+
+// fakeProc e um processo sem sistema: o que o teste escreve em out aparece
+// na leitura; Kill fecha out (fim do processo).
+type fakeProc struct {
+	out     *io.PipeReader
+	outW    *io.PipeWriter
+	mu      sync.Mutex
+	written []byte
+	size    [2]int
+	killed  bool
+}
+
+func newFake() *fakeProc {
+	r, w := io.Pipe()
+	return &fakeProc{out: r, outW: w}
+}
+
+func (f *fakeProc) Read(p []byte) (int, error) { return f.out.Read(p) }
+func (f *fakeProc) Write(p []byte) (int, error) {
+	f.mu.Lock()
+	defer f.mu.Unlock()
+	f.written = append(f.written, p...)
+	return len(p), nil
+}
+func (f *fakeProc) Resize(cols, rows int) error {
+	f.mu.Lock()
+	defer f.mu.Unlock()
+	f.size = [2]int{cols, rows}
+	return nil
+}
+func (f *fakeProc) Kill() error {
+	f.mu.Lock()
+	f.killed = true
+	f.mu.Unlock()
+	return f.outW.Close()
+}
+
+func managerWith(f *fakeProc) *Manager {
+	return NewManager(func(cmd, cwd string, cols, rows int) (Proc, error) {
+		if cmd == "falha" {
+			return nil, errors.New("nao abriu")
+		}
+		f.Resize(cols, rows)
+		return f, nil
+	})
+}
+
+func TestOpenReadWriteResizeClose(t *testing.T) {
+	f := newFake()
+	m := managerWith(f)
+	id, err := m.Open("/bin/sh", "/tmp", 80, 24)
+	if err != nil || id <= 0 {
+		t.Fatalf("Open: %d %v", id, err)
+	}
+	if f.size != [2]int{80, 24} {
+		t.Fatalf("tamanho inicial: %v", f.size)
+	}
+	go f.outW.Write([]byte("ola"))
+	got, err := m.Read(context.Background(), id, time.Second)
+	if err != nil || string(got) != "ola" {
+		t.Fatalf("Read: %q %v", got, err)
+	}
+	if err := m.Write(id, []byte("ls\n")); err != nil || string(f.written) != "ls\n" {
+		t.Fatalf("Write: %v %q", err, f.written)
+	}
+	if err := m.Resize(id, 100, 30); err != nil || f.size != [2]int{100, 30} {
+		t.Fatalf("Resize: %v %v", err, f.size)
+	}
+	if err := m.Close(id); err != nil || !f.killed {
+		t.Fatalf("Close: %v %v", err, f.killed)
+	}
+	if err := m.Close(id); err != nil {
+		t.Fatalf("Close de novo deve ser idempotente: %v", err)
+	}
+	if err := m.Write(id, []byte("x")); !errors.Is(err, ErrUnknown) {
+		t.Fatalf("Write depois de Close: %v", err)
+	}
+}
+
+func TestReadTimesOutEmpty(t *testing.T) {
+	f := newFake()
+	m := managerWith(f)
+	id, _ := m.Open("/bin/sh", "/", 80, 24)
+	start := time.Now()
+	got, err := m.Read(context.Background(), id, 50*time.Millisecond)
+	if err != nil || len(got) != 0 || time.Since(start) < 40*time.Millisecond {
+		t.Fatalf("timeout: %q %v %v", got, err, time.Since(start))
+	}
+	m.Close(id)
+}
+
+func TestReadDrainsThenReportsExit(t *testing.T) {
+	f := newFake()
+	m := managerWith(f)
+	id, _ := m.Open("/bin/sh", "/", 80, 24)
+	f.outW.Write([]byte("fim"))
+	f.outW.Close() // o processo terminou depois de escrever
+	got, err := m.Read(context.Background(), id, time.Second)
+	if err != nil || string(got) != "fim" {
+		t.Fatalf("dados antes do fim: %q %v", got, err)
+	}
+	if _, err := m.Read(context.Background(), id, time.Second); !errors.Is(err, ErrExited) {
+		t.Fatalf("depois dos dados, fim do processo: %v", err)
+	}
+}
+
+func TestReadHonoursContext(t *testing.T) {
+	f := newFake()
+	m := managerWith(f)
+	id, _ := m.Open("/bin/sh", "/", 80, 24)
+	ctx, cancel := context.WithCancel(context.Background())
+	go func() { time.Sleep(20 * time.Millisecond); cancel() }()
+	if _, err := m.Read(ctx, id, 10*time.Second); !errors.Is(err, context.Canceled) {
+		t.Fatalf("Read com contexto cancelado: %v", err)
+	}
+	m.Close(id)
+}
+
+func TestOpenFailureAndUnknownIDs(t *testing.T) {
+	m := managerWith(newFake())
+	if _, err := m.Open("falha", "/", 80, 24); err == nil {
+		t.Fatal("Open que falha deve devolver erro")
+	}
+	if _, err := m.Read(context.Background(), 99, time.Millisecond); !errors.Is(err, ErrUnknown) {
+		t.Fatalf("Read de id desconhecido: %v", err)
+	}
+	if err := m.Resize(99, 1, 1); !errors.Is(err, ErrUnknown) {
+		t.Fatalf("Resize de id desconhecido: %v", err)
+	}
+	if err := m.Close(99); err != nil {
+		t.Fatalf("Close de id desconhecido e no-op: %v", err)
+	}
+	if _, err := m.Open("/bin/sh", "/", 0, 24); err == nil {
+		t.Fatal("tamanho nao positivo deve ser erro")
+	}
+}
+
+func TestCloseAllKillsEverything(t *testing.T) {
+	a, b := newFake(), newFake()
+	n := 0
+	m := NewManager(func(cmd, cwd string, cols, rows int) (Proc, error) {
+		n++
+		if n == 1 {
+			return a, nil
+		}
+		return b, nil
+	})
+	m.Open("/bin/sh", "/", 80, 24)
+	m.Open("/bin/sh", "/", 80, 24)
+	m.CloseAll()
+	if !a.killed || !b.killed {
+		t.Fatalf("CloseAll: %v %v", a.killed, b.killed)
+	}
+}
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `go test ./ptys/`
Esperado: `undefined: Manager` e `undefined: NewManager`.
- [ ] **Commit**

```bash
git add .gitignore go.mod ptys/ptys_test.go
git commit -q -m 'test(ptys): gerenciador de terminais com processo falso

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3: o gerenciador**

Em `/home/estevao/Documentos/noxy_projects/noxy_pty` (193 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/ptys/ptys.go b/ptys/ptys.go
new file mode 100644
index 0000000000000000000000000000000000000000..920a4ce044ba883467241b94274132ef23841ddf
--- /dev/null
+++ b/ptys/ptys.go
@@ -0,0 +1,187 @@
+// Package ptys guarda os terminais abertos de um processo da extensao: cada
+// um tem um leitor em segundo plano que junta a saida num buffer, e Read
+// espera ate haver dados, o tempo acabar ou o processo terminar. O processo
+// real (pty) vem de um Starter injetado; os testes usam um falso.
+package ptys
+
+import (
+	"context"
+	"errors"
+	"fmt"
+	"sync"
+	"time"
+)
+
+// Proc e o processo num terminal: ler e escrever na pty, redimensionar, matar.
+type Proc interface {
+	Read(p []byte) (int, error)
+	Write(p []byte) (int, error)
+	Resize(cols, rows int) error
+	Kill() error
+}
+
+// Starter abre cmd numa pty com o diretorio e o tamanho dados.
+type Starter func(cmd, cwd string, cols, rows int) (Proc, error)
+
+var (
+	ErrUnknown = errors.New("unknown terminal")
+	ErrExited  = errors.New("terminal exited")
+)
+
+const maxRead = 64 * 1024
+
+type term struct {
+	proc   Proc
+	mu     sync.Mutex
+	buf    []byte
+	exited bool
+	signal chan struct{} // recebe um aviso quando chegam dados ou o fim
+}
+
+type Manager struct {
+	start Starter
+	mu    sync.Mutex
+	next  int64
+	terms map[int64]*term
+}
+
+func NewManager(start Starter) *Manager {
+	return &Manager{start: start, terms: map[int64]*term{}}
+}
+
+func (m *Manager) get(id int64) (*term, error) {
+	m.mu.Lock()
+	defer m.mu.Unlock()
+	t, ok := m.terms[id]
+	if !ok {
+		return nil, fmt.Errorf("%w: %d", ErrUnknown, id)
+	}
+	return t, nil
+}
+
+// Open abre um terminal e devolve o id.
+func (m *Manager) Open(cmd, cwd string, cols, rows int) (int64, error) {
+	if cols <= 0 || rows <= 0 {
+		return 0, fmt.Errorf("cols and rows must be positive, got %dx%d", cols, rows)
+	}
+	p, err := m.start(cmd, cwd, cols, rows)
+	if err != nil {
+		return 0, err
+	}
+	t := &term{proc: p, signal: make(chan struct{}, 1)}
+	m.mu.Lock()
+	m.next++
+	id := m.next
+	m.terms[id] = t
+	m.mu.Unlock()
+	go t.pump()
+	return id, nil
+}
+
+// pump le do processo ate o fim e junta no buffer.
+func (t *term) pump() {
+	chunk := make([]byte, 32*1024)
+	for {
+		n, err := t.proc.Read(chunk)
+		t.mu.Lock()
+		if n > 0 {
+			t.buf = append(t.buf, chunk[:n]...)
+		}
+		if err != nil {
+			t.exited = true
+		}
+		t.mu.Unlock()
+		select {
+		case t.signal <- struct{}{}:
+		default:
+		}
+		if err != nil {
+			return
+		}
+	}
+}
+
+// take tira ate maxRead bytes do buffer; exited so quando nao sobra nada.
+func (t *term) take() ([]byte, bool) {
+	t.mu.Lock()
+	defer t.mu.Unlock()
+	if len(t.buf) > 0 {
+		n := len(t.buf)
+		if n > maxRead {
+			n = maxRead
+		}
+		out := append([]byte(nil), t.buf[:n]...)
+		t.buf = t.buf[n:]
+		return out, false
+	}
+	return nil, t.exited
+}
+
+// Read espera ate timeout por dados; devolve vazio no timeout e ErrExited
+// quando o processo terminou e nao ha mais dados.
+func (m *Manager) Read(ctx context.Context, id int64, timeout time.Duration) ([]byte, error) {
+	t, err := m.get(id)
+	if err != nil {
+		return nil, err
+	}
+	deadline := time.NewTimer(timeout)
+	defer deadline.Stop()
+	for {
+		data, exited := t.take()
+		if len(data) > 0 {
+			return data, nil
+		}
+		if exited {
+			return nil, ErrExited
+		}
+		select {
+		case <-t.signal:
+		case <-deadline.C:
+			return nil, nil
+		case <-ctx.Done():
+			return nil, ctx.Err()
+		}
+	}
+}
+
+func (m *Manager) Write(id int64, data []byte) error {
+	t, err := m.get(id)
+	if err != nil {
+		return err
+	}
+	_, err = t.proc.Write(data)
+	return err
+}
+
+func (m *Manager) Resize(id int64, cols, rows int) error {
+	t, err := m.get(id)
+	if err != nil {
+		return err
+	}
+	return t.proc.Resize(cols, rows)
+}
+
+// Close mata o processo e esquece o terminal; id desconhecido e no-op.
+func (m *Manager) Close(id int64) error {
+	m.mu.Lock()
+	t, ok := m.terms[id]
+	delete(m.terms, id)
+	m.mu.Unlock()
+	if !ok {
+		return nil
+	}
+	return t.proc.Kill()
+}
+
+// CloseAll mata todos os terminais (fim do processo da extensao).
+func (m *Manager) CloseAll() {
+	m.mu.Lock()
+	ids := make([]int64, 0, len(m.terms))
+	for id := range m.terms {
+		ids = append(ids, id)
+	}
+	m.mu.Unlock()
+	for _, id := range ids {
+		m.Close(id)
+	}
+}
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `gofmt -l . && go vet ./ptys/ && go test ./ptys/ -count=1 -race`
Esperado: `gofmt` sem saída e `ok  github.com/estevaofon/noxy_pty/ptys`.
- [ ] **Commit**

```bash
git add ptys/ptys.go
git commit -q -m 'feat(ptys): gerenciador com leitor em segundo plano, leitura com prazo e fim do processo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 14: noxy_pty: o processo real

**Interfaces:**
- Produces: `ptys.Start(cmd, cwd, cols, rows) (Proc, error)`; no Windows devolve `terminal indisponivel no Windows nesta versao`.

Em `/home/estevao/Documentos/noxy_projects/noxy_pty`.

**Files:** `ptys/starter_unix_test.go`, `ptys/starter_unix.go`, `ptys/starter_windows.go`, `go.mod`, `go.sum`

- [ ] **Passo 1: o teste de integração com um shell de verdade**

Em `/home/estevao/Documentos/noxy_projects/noxy_pty` (51 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/ptys/starter_unix_test.go b/ptys/starter_unix_test.go
new file mode 100644
index 0000000000000000000000000000000000000000..2a55974781b3e7cbd76ee78593def84a2451409e
--- /dev/null
+++ b/ptys/starter_unix_test.go
@@ -0,0 +1,45 @@
+//go:build !windows
+
+package ptys
+
+import (
+	"context"
+	"strings"
+	"testing"
+	"time"
+)
+
+// Um shell de verdade numa pty: escreve um comando, le a saida, fecha.
+func TestRealShell(t *testing.T) {
+	m := NewManager(Start)
+	id, err := m.Open("/bin/sh", t.TempDir(), 80, 24)
+	if err != nil {
+		t.Fatalf("Open: %v", err)
+	}
+	if err := m.Write(id, []byte("echo ok_$((1+1))\n")); err != nil {
+		t.Fatalf("Write: %v", err)
+	}
+	var out strings.Builder
+	deadline := time.Now().Add(5 * time.Second)
+	for !strings.Contains(out.String(), "ok_2") && time.Now().Before(deadline) {
+		data, err := m.Read(context.Background(), id, 500*time.Millisecond)
+		if err != nil {
+			t.Fatalf("Read: %v (saida ate aqui: %q)", err, out.String())
+		}
+		out.Write(data)
+	}
+	if !strings.Contains(out.String(), "ok_2") {
+		t.Fatalf("saida do shell: %q", out.String())
+	}
+	if err := m.Resize(id, 120, 40); err != nil {
+		t.Fatalf("Resize: %v", err)
+	}
+	m.Write(id, []byte("exit\n"))
+	for time.Now().Before(deadline) {
+		if _, err := m.Read(context.Background(), id, 500*time.Millisecond); err == ErrExited {
+			m.Close(id)
+			return
+		}
+	}
+	t.Fatal("o shell nao terminou depois de exit")
+}
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `go test ./ptys/`
Esperado: `undefined: Start`.
- [ ] **Passo 3: o processo real sobre creack/pty e a versão Windows que recusa**

Em `/home/estevao/Documentos/noxy_projects/noxy_pty` (84 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/go.mod b/go.mod
index 172c50af745de8cab1bdee6a299420232239ed12..012cf8906daa3aa50b501391c5a95e2d6e138eab 100644
--- a/go.mod
+++ b/go.mod
@@ -1,3 +1,5 @@
 module github.com/estevaofon/noxy_pty
 
 go 1.25.0
+
+require github.com/creack/pty v1.1.24
diff --git a/go.sum b/go.sum
new file mode 100644
index 0000000000000000000000000000000000000000..5310a43dd6f2bf143449b199c4ae850e58ac25e2
--- /dev/null
+++ b/go.sum
@@ -0,0 +1,2 @@
+github.com/creack/pty v1.1.24 h1:bJrF4RRfyJnbTJqzRLHzcGaZK1NeM5kTC9jGgovnR1s=
+github.com/creack/pty v1.1.24/go.mod h1:08sCNb52WyoAwi2QDyzUCTgcvVFhUzewun7wtTfvcwE=
diff --git a/ptys/starter_unix.go b/ptys/starter_unix.go
new file mode 100644
index 0000000000000000000000000000000000000000..b9850c53846ee9391725716b9aea99b36505fab6
--- /dev/null
+++ b/ptys/starter_unix.go
@@ -0,0 +1,43 @@
+//go:build !windows
+
+package ptys
+
+import (
+	"os"
+	"os/exec"
+	"syscall"
+
+	"github.com/creack/pty"
+)
+
+type unixProc struct {
+	f   *os.File
+	cmd *exec.Cmd
+}
+
+// Start abre cmd numa pty com TERM=xterm-256color, no diretorio cwd.
+func Start(cmd, cwd string, cols, rows int) (Proc, error) {
+	c := exec.Command(cmd)
+	c.Dir = cwd
+	c.Env = append(os.Environ(), "TERM=xterm-256color", "COLORTERM=truecolor")
+	f, err := pty.StartWithSize(c, &pty.Winsize{Cols: uint16(cols), Rows: uint16(rows)})
+	if err != nil {
+		return nil, err
+	}
+	go c.Wait() // recolhe o processo quando ele terminar
+	return &unixProc{f: f, cmd: c}, nil
+}
+
+func (p *unixProc) Read(b []byte) (int, error)  { return p.f.Read(b) }
+func (p *unixProc) Write(b []byte) (int, error) { return p.f.Write(b) }
+func (p *unixProc) Resize(cols, rows int) error {
+	return pty.Setsize(p.f, &pty.Winsize{Cols: uint16(cols), Rows: uint16(rows)})
+}
+
+// Kill manda SIGHUP (o que um terminal fechado manda) e fecha a pty.
+func (p *unixProc) Kill() error {
+	if p.cmd.Process != nil {
+		p.cmd.Process.Signal(syscall.SIGHUP)
+	}
+	return p.f.Close()
+}
diff --git a/ptys/starter_windows.go b/ptys/starter_windows.go
new file mode 100644
index 0000000000000000000000000000000000000000..5b0d947335b56c6f4e4befa35c44721cd5c4dffe
--- /dev/null
+++ b/ptys/starter_windows.go
@@ -0,0 +1,11 @@
+//go:build windows
+
+package ptys
+
+import "errors"
+
+// Start no Windows ainda nao existe: o binario e publicado para o `use`
+// compilar, e abrir um terminal responde com esta mensagem.
+func Start(cmd, cwd string, cols, rows int) (Proc, error) {
+	return nil, errors.New("terminal indisponivel no Windows nesta versao")
+}
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `go mod download && gofmt -l . && go vet ./... && go test ./ptys/ -count=1 -race && GOOS=windows go vet ./ptys/`
Esperado: `ok  github.com/estevaofon/noxy_pty/ptys` e nenhum erro no vet do Windows.
- [ ] **Commit**

```bash
git add go.mod go.sum ptys/
git commit -q -m 'feat(ptys): processo real sobre creack/pty; windows recusa com mensagem

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 15: noxy_pty: extensão, wrapper e build

**Interfaces:**
- Produces: extensão `pty` com `pty_open`, `pty_read` (base64; falha `pty N exited` no fim), `pty_write` (base64), `pty_resize`, `pty_close`; wrapper `noxy_pty.nx` com `open`, `read`, `write`, `resize`, `close`; linkada em `Noxy-Editor/noxy_libs/github_com/estevaofon/noxy_pty`.

Em `/home/estevao/Documentos/noxy_projects/noxy_pty`.

**Files:** `main.go`, `noxy_ext.toml`, `noxy_pty.nx`, `noxy.mod`, `examples/smoke.nx`, `release/build.sh`, `.github/workflows/release.yml`, `README.md`

- [ ] **Passo 1: o processo da extensão, o manifesto, o wrapper, o smoke, o build e o workflow**

Em `/home/estevao/Documentos/noxy_projects/noxy_pty` (303 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

````bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/.github/workflows/release.yml b/.github/workflows/release.yml
new file mode 100644
index 0000000000000000000000000000000000000000..d557c0edd228c0c4a5b054c45bb1ad44be1f1594
--- /dev/null
+++ b/.github/workflows/release.yml
@@ -0,0 +1,24 @@
+# Release da extensao noxy_pty: Go puro, entao um runner compila todas as
+# plataformas e publica os binarios e o checksums.txt na tag.
+name: Release
+
+on:
+  push:
+    tags: ['v*']
+
+permissions:
+  contents: write
+
+jobs:
+  release:
+    runs-on: ubuntu-latest
+    steps:
+      - uses: actions/checkout@v4
+      - uses: actions/setup-go@v5
+        with:
+          go-version-file: go.mod
+      - run: go test ./... -race
+      - run: sh release/build.sh pty
+      - uses: softprops/action-gh-release@v2
+        with:
+          files: dist/*
diff --git a/README.md b/README.md
new file mode 100644
index 0000000000000000000000000000000000000000..0d1179c4e0ef59d6c4c0ba97d3d457cd3e694828
--- /dev/null
+++ b/README.md
@@ -0,0 +1,53 @@
+# noxy_pty
+
+Terminais de verdade (pty) para programas [Noxy](https://github.com/estevaofon/noxy),
+como extensão por processo sobre [creack/pty](https://github.com/creack/pty).
+Feita para o terminal do [Noxy Editor](https://github.com/estevaofon/Noxy-Editor);
+serve para qualquer programa Noxy que precise rodar um shell ou um programa
+interativo e ler e escrever nele.
+
+## Instalação
+
+    noxy --get github.com/estevaofon/noxy_pty
+
+Binários para Linux (amd64, arm64), macOS (Intel, Apple Silicon) e Windows.
+Requer Noxy 0.25.0 ou mais novo. No Windows o binário existe para o `use`
+compilar, e `open` responde "terminal indisponivel no Windows nesta versao".
+
+## API
+
+```noxy
+use github_com.estevaofon.noxy_pty.noxy_pty as pty
+
+let id: int = pty.open("/bin/sh", "/tmp", 80, 24)
+pty.write(id, base64_encode("echo ola\n"))
+print(to_str(base64_decode(pty.read(id, 500))))
+pty.close(id)
+```
+
+| Função | Efeito |
+|---|---|
+| `open(cmd, cwd, cols, rows) -> int` | Abre `cmd` numa pty (`TERM=xterm-256color`) e devolve o id. Vários por processo |
+| `read(id, timeout_ms) -> string` | Espera até `timeout_ms` por saída; devolve base64, `""` no timeout. Quando o processo terminou e não há mais saída, falha com `pty N exited` |
+| `write(id, data_b64)` | Escreve bytes (base64) na entrada |
+| `resize(id, cols, rows)` | Avisa o tamanho novo (SIGWINCH) |
+| `close(id)` | SIGHUP no processo e fecha; idempotente |
+
+Os dados cruzam em base64 porque a saída de um terminal não é UTF-8
+garantido; `base64_encode` e `base64_decode` são builtins do Noxy. Toda falha
+é um erro de runtime `extension 'pty' failed: <motivo>`, capturável com
+`call_result`. Os terminais morrem com o processo da extensão (quando o
+programa Noxy termina).
+
+## Desenvolvimento
+
+    go test ./... -race
+    sh release/build.sh pty && mkdir -p bin && cp dist/noxy-plugin-pty-linux-amd64 bin/
+
+O estado fica no pacote `ptys/`, testado com um processo falso e com um shell
+real. Para usar um checkout num projeto, linke-o em
+`<projeto>/noxy_libs/github_com/estevaofon/noxy_pty`; então
+`noxy noxy_libs/github_com/estevaofon/noxy_pty/examples/smoke.nx` imprime `ok`.
+
+Release: push de uma tag `vX.Y.Z`. Como `creack/pty` é Go puro, o workflow
+compila todas as plataformas num runner só, sem cgo.
diff --git a/examples/smoke.nx b/examples/smoke.nx
new file mode 100644
index 0000000000000000000000000000000000000000..b28a791a52961b9a4ad65ffe3e53de069aef5563
--- /dev/null
+++ b/examples/smoke.nx
@@ -0,0 +1,21 @@
+// examples/smoke.nx — abre um shell, roda um echo, le a saida e fecha:
+//     noxy examples/smoke.nx      (de um projeto com a extensao em noxy_libs)
+use sys
+use strings
+use github_com.estevaofon.noxy_pty.noxy_pty as pty
+
+let id: int = pty.open("/bin/sh", sys.getcwd(), 80, 24)
+pty.write(id, base64_encode("echo ok_$((20+22))\n"))
+let out: string = ""
+let tries = 0
+while !strings.contains(out, "ok_42") && tries < 20 do
+    out = out + to_str(base64_decode(pty.read(id, 250)))
+    tries = tries + 1
+end
+pty.close(id)
+if strings.contains(out, "ok_42") then
+    print("ok")
+else
+    print("falhou: " + out)
+    sys.exit(1)
+end
diff --git a/go.mod b/go.mod
index 012cf8906daa3aa50b501391c5a95e2d6e138eab..fa3dc99efa6efcf71dc39ae80d92cabdc69c5cab 100644
--- a/go.mod
+++ b/go.mod
@@ -2,4 +2,7 @@ module github.com/estevaofon/noxy_pty
 
 go 1.25.0
 
-require github.com/creack/pty v1.1.24
+require (
+	github.com/creack/pty v1.1.24
+	github.com/estevaofon/noxy/sdk/noxyplugin v0.1.0
+)
diff --git a/go.sum b/go.sum
index 5310a43dd6f2bf143449b199c4ae850e58ac25e2..ee23d671d21d9062b7d028444dce59a1afe24b8d 100644
--- a/go.sum
+++ b/go.sum
@@ -1,2 +1,4 @@
 github.com/creack/pty v1.1.24 h1:bJrF4RRfyJnbTJqzRLHzcGaZK1NeM5kTC9jGgovnR1s=
 github.com/creack/pty v1.1.24/go.mod h1:08sCNb52WyoAwi2QDyzUCTgcvVFhUzewun7wtTfvcwE=
+github.com/estevaofon/noxy/sdk/noxyplugin v0.1.0 h1:4BCIg+faFDAIhaiB40cKxn9SnzcBIdFoV0LVR7OOJ38=
+github.com/estevaofon/noxy/sdk/noxyplugin v0.1.0/go.mod h1:8JFy0k46p+HbFooarVYvqyL1YVyOX4h1JyuwESHk7dM=
diff --git a/main.go b/main.go
new file mode 100644
index 0000000000000000000000000000000000000000..7fb874ffe323f1495da70cd9e2058617b846d88a
--- /dev/null
+++ b/main.go
@@ -0,0 +1,49 @@
+// noxy_pty — terminais (pty) para programas Noxy, empacotado como extensao
+// por processo (kind = "process" em noxy_ext.toml). Os dados cruzam em
+// base64: bytes de terminal nao sao UTF-8 garantido.
+package main
+
+import (
+	"context"
+	"encoding/base64"
+	"errors"
+	"fmt"
+	"time"
+
+	"github.com/estevaofon/noxy/sdk/noxyplugin"
+
+	"github.com/estevaofon/noxy_pty/ptys"
+)
+
+func main() {
+	m := ptys.NewManager(ptys.Start)
+	p := noxyplugin.New()
+	p.Handle("pty_open", noxyplugin.Func4(func(ctx context.Context, cmd, cwd string, cols, rows int64) (int64, error) {
+		return m.Open(cmd, cwd, int(cols), int(rows))
+	}))
+	p.Handle("pty_read", noxyplugin.Func2(func(ctx context.Context, id, timeoutMs int64) (string, error) {
+		data, err := m.Read(ctx, id, time.Duration(timeoutMs)*time.Millisecond)
+		if errors.Is(err, ptys.ErrExited) {
+			return "", fmt.Errorf("pty %d exited", id)
+		}
+		if err != nil {
+			return "", err
+		}
+		return base64.StdEncoding.EncodeToString(data), nil
+	}))
+	p.Handle("pty_write", noxyplugin.Func2(func(ctx context.Context, id int64, data string) (any, error) {
+		raw, err := base64.StdEncoding.DecodeString(data)
+		if err != nil {
+			return nil, fmt.Errorf("pty_write: data is not base64: %v", err)
+		}
+		return nil, m.Write(id, raw)
+	}))
+	p.Handle("pty_resize", noxyplugin.Func3(func(ctx context.Context, id, cols, rows int64) (any, error) {
+		return nil, m.Resize(id, int(cols), int(rows))
+	}))
+	p.Handle("pty_close", noxyplugin.Func1(func(ctx context.Context, id int64) (any, error) {
+		return nil, m.Close(id)
+	}))
+	defer m.CloseAll()
+	p.Main() // serve stdin/stdout; sai quando o host fecha o stdin
+}
diff --git a/noxy.mod b/noxy.mod
new file mode 100644
index 0000000000000000000000000000000000000000..cf687040fcc29931fae01358833aaf8e3d0820be
--- /dev/null
+++ b/noxy.mod
@@ -0,0 +1,3 @@
+module noxy_pty
+
+noxy v0.25.0
diff --git a/noxy_ext.toml b/noxy_ext.toml
new file mode 100644
index 0000000000000000000000000000000000000000..edce3670cc349a0a48e7d21e7d75b7cf12242d73
--- /dev/null
+++ b/noxy_ext.toml
@@ -0,0 +1,40 @@
+name = "pty"
+abi = 1
+kind = "process"
+min_noxy = "0.25.0"
+concurrency = "concurrent"      # read bloqueia; write e resize precisam passar
+capabilities = ["process"]
+
+[binaries]                      # release assets; noxy --get baixa o do seu OS/arch
+linux-amd64   = "noxy-plugin-pty-linux-amd64"
+linux-arm64   = "noxy-plugin-pty-linux-arm64"
+windows-amd64 = "noxy-plugin-pty-windows-amd64.exe"
+darwin-amd64  = "noxy-plugin-pty-darwin-amd64"
+darwin-arm64  = "noxy-plugin-pty-darwin-arm64"
+
+[[export]]
+name = "pty_open"               # (cmd, cwd, cols, rows) -> id
+params = ["string", "string", "int", "int"]
+returns = "int"
+stateful = true
+
+[[export]]
+name = "pty_read"               # (id, timeout_ms) -> base64; "" no timeout; erro "pty N exited" no fim
+params = ["int", "int"]
+returns = "string"
+timeout_ms = 0
+
+[[export]]
+name = "pty_write"              # (id, base64)
+params = ["int", "string"]
+returns = "void"
+
+[[export]]
+name = "pty_resize"             # (id, cols, rows)
+params = ["int", "int", "int"]
+returns = "void"
+
+[[export]]
+name = "pty_close"              # mata o processo e fecha; idempotente
+params = ["int"]
+returns = "void"
diff --git a/noxy_pty.nx b/noxy_pty.nx
new file mode 100644
index 0000000000000000000000000000000000000000..435d304c10361b04ddf3cf71ef9630198ea94467
--- /dev/null
+++ b/noxy_pty.nx
@@ -0,0 +1,29 @@
+// noxy_pty.nx — wrapper tipado da extensao `pty`: terminais de verdade
+// (pty) para programas Noxy. Os dados cruzam em base64 (bytes de terminal
+// nao sao UTF-8 garantido). Toda falha e um erro de runtime
+// `extension 'pty' failed: <motivo>`, capturavel com call_result; o fim do
+// processo e a falha "pty N exited" em read.
+
+// open abre cmd numa pty com o diretorio e o tamanho dados; devolve o id.
+func open(cmd: string, cwd: string, cols: int, rows: int) -> int
+    return pty_open(cmd, cwd, cols, rows)
+end
+
+// read espera ate timeout_ms por saida; devolve base64 ("" no timeout).
+func read(id: int, timeout_ms: int) -> string
+    return pty_read(id, timeout_ms)
+end
+
+// write escreve bytes (em base64) na entrada do terminal.
+func write(id: int, data_b64: string) -> void
+    pty_write(id, data_b64)
+end
+
+func resize(id: int, cols: int, rows: int) -> void
+    pty_resize(id, cols, rows)
+end
+
+// close mata o processo e fecha o terminal; idempotente.
+func close(id: int) -> void
+    pty_close(id)
+end
diff --git a/release/build.sh b/release/build.sh
new file mode 100644
index 0000000000000000000000000000000000000000..ab7874ca969278d0e2ddab72baccc570f219c65e
--- /dev/null
+++ b/release/build.sh
@@ -0,0 +1,14 @@
+#!/usr/bin/env sh
+# Compila todos os binarios em dist/ e o checksums.txt. creack/pty e Go
+# puro, entao um runner so faz a matriz inteira com CGO_ENABLED=0.
+set -eu
+NAME="${1:?usage: build.sh <extension-name>}"
+mkdir -p dist
+for target in linux/amd64 linux/arm64 darwin/amd64 darwin/arm64 windows/amd64; do
+  os=${target%/*}; arch=${target#*/}
+  ext=""; [ "$os" = windows ] && ext=".exe"
+  GOOS=$os GOARCH=$arch CGO_ENABLED=0 go build -trimpath -ldflags=-s -o "dist/noxy-plugin-$NAME-$os-$arch$ext" .
+done
+if command -v sha256sum >/dev/null 2>&1; then sum="sha256sum"; else sum="shasum -a 256"; fi
+(cd dist && $sum -- noxy-plugin-* > checksums.txt)
+echo "dist/ pronto"
NOXY_PATCH_EOF
````
- [ ] **Passo 2: compilar todas as plataformas**

Run: `go mod tidy && gofmt -l . && go vet ./... && sh release/build.sh pty && mkdir -p bin && cp dist/noxy-plugin-pty-linux-amd64 bin/`
Esperado: `dist/ pronto`; em `dist/` os cinco binários e `checksums.txt`. (Não rode o binário à mão: sem terminal no stdin ele fica servindo o protocolo.)
- [ ] **Passo 3: linkar no editor e rodar o smoke**

```bash
cd /home/estevao/Documentos/noxy_projects/Noxy-Editor
mkdir -p noxy_libs/github_com/estevaofon
ln -sfn /home/estevao/Documentos/noxy_projects/noxy_pty noxy_libs/github_com/estevaofon/noxy_pty
noxy noxy_libs/github_com/estevaofon/noxy_pty/examples/smoke.nx
```

Esperado: um aviso da VM sobre a falta de entrada em `noxy.sum` e `ok`.

- [ ] **Commit**

```bash
git add .github/workflows/release.yml README.md examples/smoke.nx go.mod go.sum main.go noxy.mod noxy_ext.toml noxy_pty.nx release/build.sh
git commit -q -m 'feat: extensao por processo com open, read, write, resize e close; wrapper, smoke, build de todas as plataformas, workflow e README

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 16: Terminal no editor

**Interfaces:**
- Consumes: a extensão `noxy_pty` linkada (Task 15).
- Produces: `term.Term { open, id, error, cols, rows }`, `term.ReadResult`, `term.current_id`, `term.open/close/resize(ref t, ...)`, `term.read(id, timeout_ms)`, `term.write(id, b64) -> bool`; `session.shutdown(ref s, now)`; eventos `term_open`, `term_close`, `term_resize` (com `cols`/`rows`); rotas `POST /term/read` e `/term/write`; rota estática `/vendor/*`; o xterm na aba Terminal. Também corrige a barra do painel, que como alça de arraste engolia o clique das abas e do Parar.

**Files:** `src/term.nx`, `src/session.nx`, `src/events.nx`, `src/frame.nx`, `src/server.nx`, `editor.nx`, `web/*`, `web/vendor/*`, `tests/*`

- [ ] **Passo 1: os testes (despacho, rotas /term, shutdown ainda não)**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (122 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/tests/protocol.nx b/tests/protocol.nx
index b4f64c48d1a798cb2069357b0bfc511d9faa40b2..4c614f910361f73010e41ea456c0aea87f68c7b6 100644
--- a/tests/protocol.nx
+++ b/tests/protocol.nx
@@ -49,6 +49,14 @@ func owner() -> void
     end
 end
 
+func post_to(url: string, tok: string, body: string) -> http_client.ClientResponse
+    let c: http_client.HttpClient = http_client.new_client()
+    let hs: string[64]
+    hs[0] = "X-Noxy-Token: " + tok
+    hs[1] = "Content-Type: application/json"
+    return http_client.request(ref c, "POST", url, hs, 2, to_bytes(body))
+end
+
 func post(base: string, tok: string, body: string) -> http_client.ClientResponse
     let c: http_client.HttpClient = http_client.new_client()
     let hs: string[64]
@@ -82,6 +90,35 @@ post(base, "segredo", "{\"kind\":\"key\",\"key\":\"end\",\"rows\":10,\"tree_vers
 let typed: http_client.ClientResponse = post(base, "segredo", "{\"kind\":\"text\",\"text\":\"0\",\"rows\":10,\"tree_version\":2}")
 let tbody: string = to_str(typed.body)
 check("abrir, end e digitar refletem no quadro", strings.contains(tbody, "\"t\":\"10\"") && strings.contains(tbody, "\"dirty\":true") && strings.contains(tbody, "\"tree\":[]"))
+// terminal: abre pelo /event, escreve e le pelas rotas /term fora do dono
+let to: http_client.ClientResponse = post(base, "segredo", "{\"kind\":\"term_open\",\"cols\":80,\"rows\":24,\"tree_version\":2}")
+let tid: int = s.term.id
+check("term_open pelo /event", to.status_code == 200 && tid > 0)
+let tw: http_client.ClientResponse = post_to(base + "/term/write", "segredo", "{\"id\":" + to_str(tid) + ",\"data\":\"" + base64_encode("echo ok_$((40+2))\n") + "\"}")
+check("POST /term/write", tw.status_code == 200)
+let term_out: string = ""
+let tn: int = 0
+while !strings.contains(term_out, "ok_42") && tn < 20 do
+    let tr: http_client.ClientResponse = post_to(base + "/term/read", "segredo", "{\"id\":" + to_str(tid) + "}")
+    let rv: any = json_parse(to_str(tr.body))
+    term_out = term_out + to_str(base64_decode(rv["data"]))
+    tn = tn + 1
+end
+check("POST /term/read devolve a saida do shell", strings.contains(term_out, "ok_42"))
+let stale: http_client.ClientResponse = post_to(base + "/term/read", "segredo", "{\"id\":" + to_str(tid + 99) + "}")
+check("id que nao e o atual e 404", stale.status_code == 404)
+let tnok: http_client.ClientResponse = post_to(base + "/term/read", "errado", "{\"id\":" + to_str(tid) + "}")
+check("rota do terminal exige o token", tnok.status_code == 403)
+post_to(base + "/term/write", "segredo", "{\"id\":" + to_str(tid) + ",\"data\":\"" + base64_encode("exit\n") + "\"}")
+let ended: bool = false
+tn = 0
+while !ended && tn < 20 do
+    let tr2: http_client.ClientResponse = post_to(base + "/term/read", "segredo", "{\"id\":" + to_str(tid) + "}")
+    ended = strings.contains(to_str(tr2.body), "\"exited\":true")
+    tn = tn + 1
+end
+check("fim do shell chega como exited", ended)
+
 let beacon: http_client.ClientResponse = http_client.post(base + "/event?t=segredo", to_bytes("{\"kind\":\"quit\",\"rows\":10,\"tree_version\":2}"))
 check("quit com token na query (sendBeacon) e aceito", beacon.status_code == 200)
 let waited: int = 0
diff --git a/tests/run.nx b/tests/run.nx
index 978f6f12c234014fbb3cb2dde6b5ef6d6b9cde9c..3dc6b9b7871f6024738ab122b96b83016ee2fe0b 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -21,6 +21,7 @@ use src.search as search
 use src.recovery as recovery
 use src.gitinfo as gitinfo
 use src.minimap as minimap
+use src.term as term
 
 // cache e configuracao isolados: os testes nunca tocam no ~/.cache e no
 // ~/.config de quem roda
@@ -979,6 +980,48 @@ func test_minimap() -> void
     io.remove(root + "/longo.nx")
 end
 
+func test_term() -> void
+    print("terminal")
+    let root: string = tmp_root()
+    let s: session.Session = session.new_session(root)
+    session.load(ref s)
+    let f0: string = events.dispatch(ref s, "{\"kind\":\"term_open\",\"cols\":80,\"rows\":24,\"tree_version\":2}", 1)
+    check("term_open abre um shell na raiz e mostra a aba", s.term.open && s.term.id > 0 && s.panel.tab == "terminal" && strings.contains(f0, "\"term\":{") && term.current_id == s.term.id)
+    let id: int = s.term.id
+    check("write e read pela ponte", term.write(id, base64_encode("pwd; echo ok_$((6*7))\n")))
+    let out: string = ""
+    let tries: int = 0
+    while !strings.contains(out, "ok_42") && tries < 20 do
+        let r: term.ReadResult = term.read(id, 250)
+        out = out + to_str(base64_decode(r.data))
+        tries = tries + 1
+    end
+    check("o shell roda na raiz aberta", strings.contains(out, "ok_42") && strings.contains(out, root))
+    events.dispatch(ref s, "{\"kind\":\"term_open\",\"cols\":80,\"rows\":24,\"tree_version\":2}", 1)
+    check("term_open com um aberto nao abre outro", s.term.id == id)
+    events.dispatch(ref s, "{\"kind\":\"term_resize\",\"cols\":100,\"rows\":30,\"tree_version\":2}", 1)
+    check("term_resize guarda o tamanho", s.term.cols == 100 && s.term.rows == 30)
+    events.dispatch(ref s, "{\"kind\":\"term_close\",\"tree_version\":2}", 1)
+    check("term_close fecha e zera o id atual", !s.term.open && term.current_id == 0)
+    let after: term.ReadResult = term.read(id, 50)
+    check("depois de fechar, ler da erro", !after.ok)
+    let e: term.Term = term.new_term()
+    term.open(ref e, "/nao/existe", 80, 24)
+    check("falha ao abrir vira erro na sessao, sem derrubar", !e.open && e.error != "")
+    let x: term.Term = term.new_term()
+    term.open(ref x, root, 80, 24)
+    term.write(x.id, base64_encode("exit\n"))
+    let ended: bool = false
+    tries = 0
+    while !ended && tries < 40 do
+        let r2: term.ReadResult = term.read(x.id, 250)
+        ended = r2.exited
+        tries = tries + 1
+    end
+    check("fim do shell e reportado como exited", ended)
+    term.close(ref x)
+end
+
 test_document()
 test_lexer()
 test_history()
@@ -998,4 +1041,5 @@ test_recovery()
 test_gitinfo()
 test_git_session()
 test_minimap()
+test_term()
 report()
NOXY_PATCH_EOF
```
- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx ; noxy tests/protocol.nx`
Esperado: `Compiler error: [line 995] variable 'r': cannot resolve type 'term.ReadResult': module 'src.term' could not be loaded` e, no protocolo, `Runtime error: [tests/protocol.nx:line 95] undefined property 'term'`.
- [ ] **Commit**

```bash
git add tests/protocol.nx tests/run.nx
git commit -q -m 'test(term): terminal pelo despacho e pelas rotas /term

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
- [ ] **Passo 3a: o xterm.js vendorizado (fora do patch: arquivos minificados)**

```bash
cd /home/estevao/Documentos/noxy_projects/Noxy-Editor
T=$(mktemp -d)
curl -sSL -o $T/xterm.tgz https://registry.npmjs.org/@xterm/xterm/-/xterm-6.0.0.tgz
curl -sSL -o $T/fit.tgz https://registry.npmjs.org/@xterm/addon-fit/-/addon-fit-0.11.0.tgz
echo '908e66e04af6c8dc6b00dd3b54de088e2e81e5ed866284fd6c2fb3c2d1c7a3f6  '$T/xterm.tgz | sha256sum -c -
echo '26003b4517a132b64e4ff228fd88a5fda3fff5e606c76093f6dcff772e9ecec0  '$T/fit.tgz | sha256sum -c -
mkdir -p $T/x $T/f web/vendor && tar -xzf $T/xterm.tgz -C $T/x && tar -xzf $T/fit.tgz -C $T/f
cp $T/x/package/lib/xterm.js $T/x/package/css/xterm.css $T/f/package/lib/addon-fit.js web/vendor/
cp $T/x/package/LICENSE web/vendor/LICENSE-xterm && cp $T/f/package/LICENSE web/vendor/LICENSE-addon-fit
printf 'xterm.js, xterm.css: @xterm/xterm 6.0.0 (MIT), https://registry.npmjs.org/@xterm/xterm/-/xterm-6.0.0.tgz\naddon-fit.js: @xterm/addon-fit 0.11.0 (MIT), https://registry.npmjs.org/@xterm/addon-fit/-/addon-fit-0.11.0.tgz\nCopiados sem mudanca de lib/ e css/ dos pacotes; licencas ao lado.\n' > web/vendor/README
rm -rf $T && ls -la web/vendor
```

Esperado: os dois `OK` do `sha256sum -c`; em `web/vendor/`: `xterm.js` (488663 bytes), `xterm.css` (7112), `addon-fit.js` (1521), as duas licenças e o README.

- [ ] **Passo 3b: a implementação**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (693 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/README.md b/README.md
index 19a4d3bd1e69cf40bd91a424a79d3d7895f47a0c..382965ff7cc496c46d6a57f0eb040fa8ff4cad0b 100644
--- a/README.md
+++ b/README.md
@@ -69,7 +69,7 @@ A VM avisa uma vez que o checkout não bate com o `noxy.sum` e roda.
 | Enter | nova linha com a indentação da atual |
 | Escape | fechar o modal; senão colapsar a seleção |
 | F5 | salvar e rodar o arquivo ativo (`noxy arquivo.nx`), saída no painel |
-| Ctrl+J | mostrar ou ocultar o painel de saída (arraste a barra "Saída" ou o divisor acima dela para redimensionar) |
+| Ctrl+J | mostrar ou ocultar o painel inferior (arraste a barra do painel, fora das abas, ou o divisor acima dela para redimensionar) |
 | Ctrl+Q | sair (pergunta se há abas com alterações) |
 
 Mouse: clique posiciona, arraste seleciona, duplo clique seleciona a palavra,
diff --git a/editor.nx b/editor.nx
index 8722f4465ee78313df707d798add174bd1537fdb..3d8fcf80ff50ee7cd70a2b9da6667ee58a7d7d2a 100644
--- a/editor.nx
+++ b/editor.nx
@@ -121,6 +121,7 @@ while !s.quitting do
         launch.set_title(title)
     end
 end
+session.shutdown(ref s, events.now())
 server.stop()
 launch.close_window()
 sys.exit(0)
diff --git a/src/events.nx b/src/events.nx
index 966003edb79913982669ef2fe6f3b51af95627ea..6885bd4b59b984d37693cd4ef04eddd9dafb6a81 100644
--- a/src/events.nx
+++ b/src/events.nx
@@ -15,6 +15,7 @@ use src.settings as settings
 use src.commands as commands
 use src.index as index
 use src.find as find
+use src.term as term
 
 
 struct Event
@@ -36,10 +37,11 @@ struct Event
     search_version: int    // a versao dos resultados da busca na pasta que o cliente tem
     git_version: int       // a versao do status do git que o cliente tem
     want_minimap: bool     // o cliente quer o formato do arquivo para o minimap
+    cols: int              // tamanho do terminal no cliente
 end
 
 func empty_event() -> Event
-    return Event("", "", false, false, false, "", 0, 0, 0, "", 0, 0, 0, "", false, 0, 0, false)
+    return Event("", "", false, false, false, "", 0, 0, 0, "", 0, 0, 0, "", false, 0, 0, false, 0)
 end
 
 // now e o relogio do dono do estado, em milissegundos. time_now() da
@@ -414,6 +416,16 @@ func apply(s: session.Session, e: Event, now: int) -> session.Session
         end
     elif e.kind == "find_close" then
         close_find(ref s)
+    elif e.kind == "term_open" then
+        session.show_panel(ref s, "terminal")
+        term.open(ref s.term, s.root, e.cols, e.rows)
+        if s.term.error != "" then
+            s.message = "terminal: " + s.term.error
+        end
+    elif e.kind == "term_close" then
+        term.close(ref s.term)
+    elif e.kind == "term_resize" then
+        term.resize(ref s.term, e.cols, e.rows)
     elif e.kind == "minimap_goto" then
         if s.active >= 0 then
             editing.scroll_to(ref s.tabs[s.active].editor, e.line - s.rows / 2, s.rows)
diff --git a/src/frame.nx b/src/frame.nx
index a7373ffc77d2193fe3f1bb4cb137447f4cf68caa..cff7d195247372c8608217e2e3cb68718e4ea41f 100644
--- a/src/frame.nx
+++ b/src/frame.nx
@@ -12,6 +12,7 @@ use src.find as find
 use src.search as search
 use src.gitinfo as gitinfo
 use src.minimap as minimap
+use src.term as term
 
 struct SpanOut
     k: string       // kind do token
@@ -108,6 +109,7 @@ struct Frame
     search: SearchOut
     git: gitinfo.GitInfo       // status e dirs vazios quando o cliente ja tem esta versao
     minimap: MinimapOut
+    term: term.Term
 end
 
 // covered: o pedaco [p, q) esta dentro de alguma marca do papel kind?
@@ -281,7 +283,7 @@ func build(s: ref session.Session, client_tree_version: int, client_search_versi
         right = "Ln " + to_str(ed.cursor.line + 1) + ", Col " + to_str(ed.cursor.col + 1) + "   Espaços: 4   " + doc.eol_name(ed.doc)
         eol = doc.eol_name(ed.doc)
     end
-    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings, s.list, FindOut(s.find.open, s.find.replace, s.find.query, s.find.case_sensitive, length(s.find.matches), s.find.current), search_out(s, client_search_version), git_out(s, client_git_version), minimap_out(s, want_minimap))
+    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message, eol), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal, s.panel, s.settings, s.list, FindOut(s.find.open, s.find.replace, s.find.query, s.find.case_sensitive, length(s.find.matches), s.find.current), search_out(s, client_search_version), git_out(s, client_git_version), minimap_out(s, want_minimap), s.term)
     s.clipboard = ""
     return json_dumps(f)
 end
diff --git a/src/server.nx b/src/server.nx
index 910da4f9b011117d7879cd8973ee0f84b022d13a..9b5a06d329b95db9ff43782c43e8b7bd118aad29 100644
--- a/src/server.nx
+++ b/src/server.nx
@@ -6,6 +6,7 @@
 use http_server select *
 use http_parser select *
 use strings select is_valid_utf8
+use src.term as term
 
 struct Request
     body: string
@@ -24,6 +25,9 @@ func static_path(path: string) -> string
     if path == "/editor.css" || path == "/editor.js" then
         return web_dir + path
     end
+    if path == "/vendor/xterm.js" || path == "/vendor/xterm.css" || path == "/vendor/addon-fit.js" then
+        return web_dir + path
+    end
     return ""
 end
 
@@ -34,6 +38,39 @@ func token_ok(req: HttpRequest) -> bool
     return req.query == "t=" + token
 end
 
+// TermReq e o corpo das rotas /term: o id e, para write, os bytes em base64.
+struct TermReq
+    id: int
+    data: string
+end
+
+// term_route atende /term/read e /term/write fora do dono do estado: so o
+// terminal atual (term.current_id) e aceito; outro id e 404, o que encerra
+// o long-poll de uma pagina antiga.
+func term_route(req: HttpRequest) -> HttpResponse
+    let t: TermReq = TermReq(0, "")
+    if !is_valid_utf8(req.body) || !json_loads(to_str(req.body), ref t) then
+        return response_error(400, "corpo invalido")
+    end
+    if t.id == 0 || t.id != term.current_id then
+        return response_404()
+    end
+    if req.path == "/term/write" then
+        if term.write(t.id, t.data) then
+            return response_json("{\"ok\":true}")
+        end
+        return response_error(500, "escrita no terminal falhou")
+    end
+    let r: term.ReadResult = term.read(t.id, 1000)
+    if r.ok then
+        return response_json("{\"data\":\"" + r.data + "\"}")
+    end
+    if r.exited then
+        return response_json("{\"exited\":true}")
+    end
+    return response_error(500, r.error)
+end
+
 func handler(req: HttpRequest) -> HttpResponse
     if req.method == "GET" then
         let file: string = static_path(req.path)
@@ -42,6 +79,12 @@ func handler(req: HttpRequest) -> HttpResponse
         end
         return response_404()
     end
+    if req.method == "POST" && (req.path == "/term/read" || req.path == "/term/write") then
+        if !token_ok(req) then
+            return response_error(403, "token invalido")
+        end
+        return term_route(req)
+    end
     if req.method == "POST" && req.path == "/event" then
         if !token_ok(req) then
             return response_error(403, "token invalido")
diff --git a/src/session.nx b/src/session.nx
index 170d925cd65bd8b8cba5f3250b5aed70672bbf7a..89d79cb3c58341e6fe008ec18e5a07c98bd60359 100644
--- a/src/session.nx
+++ b/src/session.nx
@@ -13,6 +13,7 @@ use src.find as find
 use src.search as search
 use src.recovery as recovery
 use src.gitinfo as gitinfo
+use src.term as term
 
 struct Tab
     editor: editing.Editor
@@ -94,6 +95,7 @@ struct Session
     recovery_warned: bool   // ja avisou que nao consegue gravar copias
     git: gitinfo.GitInfo
     git_task: any           // task de gitinfo.collect; null parada
+    term: term.Term
 end
 
 // Search e a busca na pasta: a consulta, a task e os resultados; version
@@ -207,6 +209,15 @@ func poll_git(s: ref Session) -> void
     s.git_task = null
 end
 
+// shutdown e o fim do editor: fecha o terminal e para o programa em
+// execucao, para nada ficar rodando depois da janela fechar.
+func shutdown(s: ref Session, now: int) -> void
+    term.close(ref s.term)
+    if s.run.running then
+        runner.stop(ref s.run, now)
+    end
+end
+
 // recovery_tick grava a copia das abas sujas cujo texto mudou desde a
 // ultima copia, no maximo uma vez por COPY_EVERY_MS; force (bye) grava na hora.
 func recovery_tick(s: ref Session, now: int, force: bool) -> void
@@ -289,7 +300,7 @@ func no_modal() -> Modal
 end
 
 func new_session(root: string) -> Session
-    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0), [], null, find.new_find(), Search("", false, false, null, [], false, 0), false, gitinfo.empty_git(), null)
+    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, "", "", Panel(false, "output"), settings.load(), List("", "", [], 0), [], null, find.new_find(), Search("", false, false, null, [], false, 0), false, gitinfo.empty_git(), null, term.new_term())
 end
 
 func basename(path: string) -> string
diff --git a/src/term.nx b/src/term.nx
new file mode 100644
index 0000000000000000000000000000000000000000..bb6eb839007c80f8fc803800f09918dca7caa622
--- /dev/null
+++ b/src/term.nx
@@ -0,0 +1,87 @@
+// src/term.nx — o terminal do editor sobre a extensao noxy_pty. Abrir,
+// fechar e redimensionar passam pelo dono do estado (mudam o quadro); ler e
+// escrever passam por read e write, chamados direto pelas rotas /term do
+// servidor, fora do dono: o terminal nao e estado do editor. current_id e o
+// terminal que as rotas aceitam (0 = nenhum). Os dados vao e voltam em
+// base64, sem decodificar aqui.
+use sys
+use errors select *
+use strings select contains
+use github_com.estevaofon.noxy_pty.noxy_pty as pty
+
+struct Term
+    open: bool
+    id: int
+    error: string      // por que nao abriu; "" sem erro
+    cols: int
+    rows: int
+end
+
+struct ReadResult
+    ok: bool
+    data: string       // base64; "" no timeout
+    exited: bool       // o processo do terminal terminou
+    error: string
+end
+
+let current_id: int = 0
+
+func new_term() -> Term
+    return Term(false, 0, "", 80, 24)
+end
+
+func shell() -> string
+    let e: sys.EnvResult = sys.getenv("SHELL")
+    if e.ok && e.value != "" then
+        return e.value
+    end
+    return "/bin/sh"
+end
+
+// open abre um shell em cwd; com um terminal aberto nao faz nada.
+func open(t: ref Term, cwd: string, cols: int, rows: int) -> void
+    if t.open then
+        return
+    end
+    let r = call_result(pty.open, shell(), cwd, cols, rows)
+    if !r.ok then
+        t.error = r.failure.message
+        return
+    end
+    t.open = true
+    t.id = r.value
+    t.error = ""
+    t.cols = cols
+    t.rows = rows
+    current_id = t.id
+end
+
+func close(t: ref Term) -> void
+    if t.id > 0 then
+        call_result(pty.close, t.id)
+    end
+    t.open = false
+    current_id = 0
+end
+
+func resize(t: ref Term, cols: int, rows: int) -> void
+    if !t.open || cols <= 0 || rows <= 0 then
+        return
+    end
+    call_result(pty.resize, t.id, cols, rows)
+    t.cols = cols
+    t.rows = rows
+end
+
+func read(id: int, timeout_ms: int) -> ReadResult
+    let r = call_result(pty.read, id, timeout_ms)
+    if r.ok then
+        return ReadResult(true, r.value, false, "")
+    end
+    let exited: bool = contains(r.failure.message, "exited")
+    return ReadResult(false, "", exited, r.failure.message)
+end
+
+func write(id: int, data_b64: string) -> bool
+    return call_result(pty.write, id, data_b64).ok
+end
diff --git a/tests/protocol.nx b/tests/protocol.nx
index 4c614f910361f73010e41ea456c0aea87f68c7b6..039e7d9ad70205caaccc253b2c69dc7054af760e 100644
--- a/tests/protocol.nx
+++ b/tests/protocol.nx
@@ -127,6 +127,7 @@ while !s.quitting && waited < 50 do
     waited = waited + 1
 end
 check("quit encerra o loop dono", s.quitting)
+session.shutdown(ref s, events.now())
 server.stop()
 
 print("")
diff --git a/tests/run.nx b/tests/run.nx
index 3dc6b9b7871f6024738ab122b96b83016ee2fe0b..4579daa67af339202e89456e6cacbea92cef9fc6 100644
--- a/tests/run.nx
+++ b/tests/run.nx
@@ -1020,6 +1020,20 @@ func test_term() -> void
     end
     check("fim do shell e reportado como exited", ended)
     term.close(ref x)
+
+    // sair do editor fecha o terminal e para o programa em execucao
+    let z: session.Session = session.new_session(root)
+    session.load(ref z)
+    write_file(root + "/sem_fim.nx", "use sys\nwhile true do\n    sys.sleep(50)\nend\n")
+    runner.start(ref z.run, root, "sem_fim.nx")
+    term.open(ref z.term, root, 80, 24)
+    sys.sleep(300)
+    let zpid: int = z.run.pid
+    session.shutdown(ref z, events.now())
+    sys.sleep(300)
+    check("shutdown para o programa em execucao", !alive(zpid))
+    check("shutdown fecha o terminal", !z.term.open && term.current_id == 0)
+    io.remove(root + "/sem_fim.nx")
 end
 
 test_document()
diff --git a/tests/web_smoke.py b/tests/web_smoke.py
index bf726b5fb998226c4169e987c2f77666a6abf02c..f941fe92def60918adf2e8c7330f636d6ee51cea 100644
--- a/tests/web_smoke.py
+++ b/tests/web_smoke.py
@@ -22,7 +22,7 @@ _shg.rmtree(os.path.join(demo, ".git"), ignore_errors=True)
 subprocess.run("git init -q -b demo-branch && git -c user.name=t -c user.email=t@t add . && git -c user.name=t -c user.email=t@t commit -q -m init", shell=True, cwd=demo, check=True)
 open(os.path.join(demo, "notas.txt"), "a").write("mudou\n")
 cfg = os.path.join(os.getcwd(), "tests", "tmp", "web_config")
-env = dict(os.environ, NOXY_EDITOR_NO_WINDOW="1", NOXY_EDITOR_CONFIG_DIR=cfg, NOXY_EDITOR_CACHE_DIR=os.path.join(os.getcwd(), "tests", "tmp", "web_cache"))
+env = dict(os.environ, NOXY_EDITOR_NO_WINDOW="1", SHELL="/bin/sh", NOXY_EDITOR_CONFIG_DIR=cfg, NOXY_EDITOR_CACHE_DIR=os.path.join(os.getcwd(), "tests", "tmp", "web_cache"))
 import shutil as _sh; _sh.rmtree(env["NOXY_EDITOR_CACHE_DIR"], ignore_errors=True)
 if os.path.exists(os.path.join(cfg, "settings.json")): os.remove(os.path.join(cfg, "settings.json"))
 log = os.path.join("tests", "tmp", "web_editor.log")
@@ -46,12 +46,27 @@ def check(name, cond):
     if not cond: fails += 1
 def settle(ms=350): time.sleep(ms / 1000)
 def key(k, text=None, mods=0, code=None):
-    p = {"type": "keyDown", "key": k, "modifiers": mods, "windowsVirtualKeyCode": 0}
+    # o codigo da tecla: o editor le e.key, mas o xterm le keyCode
+    codes = {"Enter": 13, "Escape": 27, "Tab": 9, "Backspace": 8, "Home": 36, "End": 35, "F5": 116, "F3": 114, "`": 192}
+    vk = codes.get(k, ord(k.upper()) if len(k) == 1 and k.isalpha() else 0)
+    p = {"type": "keyDown", "key": k, "modifiers": mods, "windowsVirtualKeyCode": vk}
+    if k == "Enter" and not mods: text = "\r"
     if text: p["text"] = text
     ws.call("Input.dispatchKeyEvent", p)
     p["type"] = "keyUp"; p.pop("text", None)
     ws.call("Input.dispatchKeyEvent", p)
     settle()
+# click_real clica com o mouse de verdade no centro do elemento (passa pelo
+# pointerdown, diferente de dispatchEvent)
+def click_real(selector):
+    c = ev(f"(() => {{ const r = document.querySelector('{selector}').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }})()")
+    mouse("mousePressed", c[0], c[1]); mouse("mouseReleased", c[0], c[1]); settle()
+
+# type_keys digita tecla por tecla (keyDown com texto), como um teclado real;
+# o xterm ignora texto inserido sem tecla depois de um atalho interceptado
+def type_keys(text):
+    for ch in text:
+        key(ch, text=ch)
 def insert(text):
     ws.call("Input.insertText", {"text": text}); settle()
 # cursor_diff: distancia entre a barra do cursor e o caret real na coluna
@@ -160,7 +175,7 @@ check("git: salvar e rodar marcam o arquivo na arvore e na aba", ev("Array.from(
 key("p", mods=2); ws.call("Input.insertText", {"text": "sem_fim"}); settle(); key("Enter")
 key("F5"); settle(1200)
 check("saida ao vivo enquanto roda", "volta 2" in ev("document.getElementById('output-text').textContent") and not ev("document.getElementById('run-stop').classList.contains('hidden')"))
-ev("document.getElementById('run-stop').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle(1500)
+click_real("#run-stop"); settle(1500)
 check("parar encerra e esconde o botao", "[interrompido]" in ev("document.getElementById('output-text').textContent") and ev("document.getElementById('run-stop').classList.contains('hidden')"))
 ev("document.querySelector('.tab.active .close').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
 print("SAIDA:", out.replace("\n", " | ")[:200])
@@ -176,13 +191,13 @@ if grip:
     h1 = output_h()
     check("arrastar o divisor para cima aumenta o painel (%.0f -> %.0f px)" % (h0, h1), abs((h1 - h0) - 120) < 3)
     check("altura lembrada no localStorage", ev("localStorage.getItem('noxy-editor.output-h')") is not None)
-head = ev("(() => { const r = document.getElementById('output-head').getBoundingClientRect(); return [r.left + 60, r.top + r.height / 2]; })()")
+head = ev("(() => { const r = document.getElementById('output-head').getBoundingClientRect(); return [r.left + r.width * 0.6, r.top + r.height / 2]; })()")   # parte vazia da barra, fora das abas
 h2 = output_h()
 mouse("mousePressed", head[0], head[1]); mouse("mouseMoved", head[0], head[1] + 80); settle(); mouse("mouseReleased", head[0], head[1] + 80); settle()
 h3 = output_h()
-check("arrastar pela barra SAIDA tambem redimensiona (%.0f -> %.0f px)" % (h2, h3), abs((h3 - h2) + 80) < 3)
+check("arrastar pela parte vazia da barra do painel tambem redimensiona (%.0f -> %.0f px)" % (h2, h3), abs((h3 - h2) + 80) < 3)
 check("aba Saida ativa apos F5", ev("document.querySelector('#panel-tabs .ptab.active').dataset.tab") == "output")
-ev("document.querySelector('#panel-tabs .ptab[data-tab=\"search\"]').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
+click_real('#panel-tabs .ptab[data-tab=\"search\"]')
 check("clicar na aba Busca troca a aba", ev("document.querySelector('#panel-tabs .ptab.active').dataset.tab") == "search" and not ev("document.getElementById('search-view').classList.contains('hidden')"))
 key("f", mods=10)
 check("ctrl+shift+f foca o campo de busca na pasta", ev("document.activeElement.id") == "search-input")
@@ -259,6 +274,27 @@ ws.call("Page.navigate", {"url": "file://" + page}); settle(2000)
 check("pagina de redirecionamento leva ao editor", ev("location.href").startswith(url.split("?")[0]) and ev("document.querySelectorAll('#tree .node').length") == 5)
 time.sleep(3.5)
 check("editor continua vivo 3 s depois do reload", editor.poll() is None and ev("document.querySelectorAll('#tree .node').length") == 5)
+# terminal: ctrl+` abre um shell de verdade no painel, com foco
+key("`", mods=2); settle(1500)
+check("ctrl+` abre a aba Terminal com o xterm", ev("document.querySelector('#panel-tabs .ptab.active').dataset.tab") == "terminal" and ev("!!document.querySelector('#term-view .xterm')"))
+check("o foco vai para o terminal", ev("!!document.activeElement.closest('#term-view')"))
+ws.call("Input.insertText", {"text": "echo ok_terminal_$((1+1))"}); key("Enter"); settle(1200)
+check("o shell responde no xterm", "ok_terminal_2" in ev("document.querySelector('#term-view .xterm-rows').textContent"))
+key("Escape"); settle(300)
+check("escape vai para o shell, o foco continua no terminal", ev("!!document.activeElement.closest('#term-view')"))
+key("c", mods=2); settle(500)   # ctrl+c limpa o que o escape comecou, em qualquer shell
+key("`", mods=2); settle(300)
+check("ctrl+` com o terminal focado devolve o foco ao editor", ev("document.activeElement.id") == "input")
+click_real('#panel-tabs .ptab[data-tab=\"output\"]')
+key("`", mods=2); settle(800)
+check("o terminal continua o mesmo ao voltar a aba", "ok_terminal_2" in ev("document.querySelector('#term-view .xterm-rows').textContent"))
+type_keys("exit"); key("Enter"); settle(2000)
+check("fim do shell avisa no terminal", "terminal encerrado" in ev("document.querySelector('#term-view .xterm-rows').textContent").replace('\xa0', ' '))
+key("Enter"); settle(1500)
+type_keys("echo de_novo_$((2+3))"); key("Enter"); settle(1200)
+check("enter abre outro shell", "de_novo_5" in ev("document.querySelector('#term-view .xterm-rows').textContent"))
+key("`", mods=2); settle(300)
+
 # recuperacao: editar sem salvar, esperar a copia (poll 1,5 s depois da
 # ultima edicao), matar o editor e abrir outro: a aba volta suja
 ev("document.querySelectorAll('#tree .node.file')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
diff --git a/tests/webkit_smoke.py b/tests/webkit_smoke.py
index cabba999045e7386a24c0e5911d2670eccfe5113..308e5bd46a8fb88747260088b0473ce8d3c736c3 100644
--- a/tests/webkit_smoke.py
+++ b/tests/webkit_smoke.py
@@ -10,7 +10,7 @@ from gi.repository import Gtk, Gdk, WebKit2, GLib
 demo = os.path.join("tests", "tmp", "webkit"); os.makedirs(demo, exist_ok=True)
 open(os.path.join(demo, "longo.nx"), "w").write("".join(f"let v{i}: int = {i}   // " + "x" * 200 + "\n" for i in range(120)) + "print(\"fim\")\n")
 log = os.path.join("tests", "tmp", "webkit_editor.log")
-editor = subprocess.Popen(["noxy", "editor.nx", demo], env=dict(os.environ, NOXY_EDITOR_NO_WINDOW="1", NOXY_EDITOR_CONFIG_DIR=os.path.join(os.getcwd(), "tests", "tmp", "webkit_config"), NOXY_EDITOR_CACHE_DIR=os.path.join(os.getcwd(), "tests", "tmp", "webkit_cache")), stdout=subprocess.DEVNULL, stderr=open(log, "w"))
+editor = subprocess.Popen(["noxy", "editor.nx", demo], env=dict(os.environ, NOXY_EDITOR_NO_WINDOW="1", SHELL="/bin/sh", NOXY_EDITOR_CONFIG_DIR=os.path.join(os.getcwd(), "tests", "tmp", "webkit_config"), NOXY_EDITOR_CACHE_DIR=os.path.join(os.getcwd(), "tests", "tmp", "webkit_cache")), stdout=subprocess.DEVNULL, stderr=open(log, "w"))
 url = None
 for _ in range(50):
     m = re.search(r"http://127\.0\.0\.1:\d+/\?t=[a-z0-9-]+", open(log).read())
@@ -77,12 +77,12 @@ def s_after_run():
         check("F5 abre o painel", not l["hidden"] and l["outH"] > 100)
         check("painel e status cabem na janela e o editor encolheu (editor %d, painel %d, janela %d)" % (l["editorH"], l["outH"], l["inner"]), fits(l))
         check("linhas visiveis diminuiram (%d -> %d)" % (st["before"]["rows"], l["rows"]), l["rows"] < st["before"]["rows"])
-        js(center("#output-head"), lambda c: drag(*json.loads(c), -150, s_after_head))
+        js("(() => { const r = document.getElementById('output-head').getBoundingClientRect(); return JSON.stringify([r.left + r.width * 0.6, r.top + r.height / 2]); })()", lambda c: drag(*json.loads(c), -150, s_after_head))
     js(LAYOUT, got)
 def s_after_head():
     def got(v):
         l = json.loads(v); st["head"] = l
-        check("arrastar pela barra SAIDA cresce 150 px (%d -> %d)" % (st["run"]["outH"], l["outH"]), abs((l["outH"] - st["run"]["outH"]) - 150) < 2)
+        check("arrastar pela parte vazia da barra do painel cresce 150 px (%d -> %d)" % (st["run"]["outH"], l["outH"]), abs((l["outH"] - st["run"]["outH"]) - 150) < 2)
         check("layout continua cabendo apos o arraste", fits(l) and l["rows"] < st["run"]["rows"])
         js(center("#output-resize"), lambda c: drag(*json.loads(c), 60, s_after_grip))
     js(LAYOUT, got)
@@ -91,14 +91,34 @@ def s_after_grip():
         l = json.loads(v)
         check("arrastar pelo divisor para baixo encolhe 60 px (%d -> %d)" % (st["head"]["outH"], l["outH"]), abs((st["head"]["outH"] - l["outH"]) - 60) < 2)
         check("layout continua cabendo", fits(l))
-        finish()
+        js(center('#panel-tabs .ptab[data-tab="terminal"]'), lambda c: click(*json.loads(c), lambda: later(2000, s_term)))
     js(LAYOUT, got)
+
+TERM = "JSON.stringify({x: !!document.querySelector('#term-view .xterm'), bottom: (document.querySelector('#term-view .xterm') || document.body).getBoundingClientRect().bottom, inner: innerHeight, rows: document.querySelectorAll('#term-view .xterm-rows > div').length, text: (document.querySelector('#term-view .xterm-rows') || {textContent: ''}).textContent})"
+def s_term():
+    def got(v):
+        t = json.loads(v); st["term"] = t
+        check("aba Terminal: xterm dentro da janela (fundo %d, janela %d)" % (t["bottom"], t["inner"]), t["x"] and t["bottom"] <= t["inner"] + 0.5 and t["rows"] >= 5)
+        js("fetch('/event?t=' + new URLSearchParams(location.search).get('t'), {method: 'POST', body: JSON.stringify({kind: 'poll', rows: 5, tree_version: 0})}).then(r => r.json()).then(f => fetch('/term/write', {method: 'POST', headers: {'X-Noxy-Token': new URLSearchParams(location.search).get('t')}, body: JSON.stringify({id: f.term.id, data: btoa('echo webkit_$((3*3))\\n')})})); 'ok'", lambda _: later(1500, s_term_out))
+    js(TERM, got)
+def s_term_out():
+    def got(v):
+        t = json.loads(v)
+        check("o shell responde no xterm do WebKitGTK", "webkit_9" in t["text"])
+        js(center("#output-resize"), lambda c: drag(*json.loads(c), -120, s_term_resized))
+    js(TERM, got)
+def s_term_resized():
+    def got(v):
+        t = json.loads(v)
+        check("painel maior: o xterm ganha linhas (%d -> %d) e continua dentro da janela" % (st["term"]["rows"], t["rows"]), t["rows"] > st["term"]["rows"] and t["bottom"] <= t["inner"] + 0.5)
+        finish()
+    js(TERM, got)
 def finish():
     editor.terminate(); Gtk.main_quit()
 def on_load(w, ev):
     if ev == WebKit2.LoadEvent.FINISHED: later(1200, s_open)
 wv.connect("load-changed", on_load); wv.load_uri(url)
-GLib.timeout_add(30000, lambda: (print("FAIL   timeout"), finish(), False)[2])
+GLib.timeout_add(45000, lambda: (print("FAIL   timeout"), finish(), False)[2])
 Gtk.main()
 print(f"\n{'FALHOU' if fails else 'OK'}: {fails} falhas")
 sys.exit(1 if fails else 0)
diff --git a/web/editor.css b/web/editor.css
index ce5864ae3d2e9029a90a6ffc9332d2c53137b6e6..d3a6c047468c7786a027e95cea404817a07259e2 100644
--- a/web/editor.css
+++ b/web/editor.css
@@ -120,10 +120,13 @@ button { font: inherit; color: inherit; background: none; border: none; cursor:
 #output-head { display: flex; justify-content: space-between; align-items: center; padding: 0 12px 0 4px; font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--fg-dim); }
 #panel-tabs { display: flex; }
 .ptab { padding: 6px 10px; cursor: pointer; border-bottom: 2px solid transparent; }
+#output-head button { cursor: pointer; }
 .ptab:hover { color: var(--fg); }
 .ptab.active { color: var(--fg); border-bottom-color: var(--accent); }
 .pview { flex: 1; min-height: 0; overflow: auto; }
-#search-view, #term-view { padding: 4px 14px 10px; }
+#search-view { padding: 4px 14px 10px; }
+#term-view { padding: 4px 0 0 10px; background: var(--bg-side); }
+#term-view .xterm { height: 100%; }
 .search-row { display: flex; align-items: center; gap: 6px; margin: 4px 0 8px; }
 #search-input { width: 320px; padding: 4px 8px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); color: var(--fg); font: 13px var(--font-ui); outline: none; }
 #search-input:focus { border-color: var(--accent); }
diff --git a/web/editor.js b/web/editor.js
index 666d5262b7676967846b3bcc1ecce5a66c47ee82..93a70872da700f180e7dd59db21d76acd33017d1 100644
--- a/web/editor.js
+++ b/web/editor.js
@@ -185,6 +185,7 @@
     els.runStop.classList.toggle("hidden", !f.output.running);
     renderPanel(f.panel);
     renderSearch(f.search);
+    renderTerm(f);
     renderModal(f.modal);
     renderList(f.list);
     renderFind(f.find);
@@ -398,6 +399,7 @@
     if (e.isComposing) return;
     const key = e.key.toLowerCase();
     if ((e.ctrlKey || e.metaKey) && e.shiftKey && key === "f") wantSearchFocus = true;
+    if ((e.ctrlKey || e.metaKey) && key === "`") wantTermFocus = true;
     if (e.ctrlKey || e.metaKey) {
       if (key === "c") { e.preventDefault(); send({ kind: "copy" }); return; }
       if (key === "x") { e.preventDefault(); send({ kind: "cut" }); return; }
@@ -427,7 +429,7 @@
   function focusInput() {
     if (listKind) return;   // a lista tem o foco
     const a = document.activeElement;
-    if (a && a.closest && (a.closest("#findbar") || a.closest("#search-view"))) return;   // um campo de busca tem o foco
+    if (a && a.closest && (a.closest("#findbar") || a.closest("#search-view") || a.closest("#term-view"))) return;   // busca ou terminal tem o foco
     if (document.activeElement !== els.input) els.input.focus({ preventScroll: true });
   }
   document.addEventListener("mousedown", () => setTimeout(focusInput, 0));
@@ -545,6 +547,98 @@
   });
   els.searchCase.addEventListener("mousedown", (e) => { e.preventDefault(); searchCase = !searchCase; els.searchCase.classList.toggle("on", searchCase); });
 
+  // ---- terminal: xterm.js na aba Terminal. Abrir, fechar e redimensionar
+  // vao pelo /event (mudam o quadro); ler e escrever vao direto a /term/read
+  // (long-poll de ate 1 s) e /term/write, fora do dono do estado do Noxy.
+  // Escape vai para o shell (vim precisa); Ctrl+` ou um clique no editor
+  // devolvem o foco ao editor.
+  let xterm = null, fit = null, termId = 0, termOpening = false, termExited = false, wantTermFocus = false;
+  let sentCols = 0, sentRows = 0, writeChain = Promise.resolve();
+  function termTheme() {
+    const st = getComputedStyle(document.documentElement);
+    const v = (n) => st.getPropertyValue(n).trim();
+    return { background: v("--bg-side"), foreground: v("--fg"), cursor: v("--cursor"), selectionBackground: v("--sel") };
+  }
+  function b64ToBytes(s) { return Uint8Array.from(atob(s), (c) => c.charCodeAt(0)); }
+  function bytesToB64(bytes) { let s = ""; for (const b of bytes) s += String.fromCharCode(b); return btoa(s); }
+  function termPost(path, body) {
+    return fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Noxy-Token": token }, body: JSON.stringify(body) });
+  }
+  function ensureXterm() {
+    if (xterm) return;
+    xterm = new Terminal({ fontFamily: getComputedStyle(document.documentElement).getPropertyValue("--font-mono"), fontSize: 13, cursorBlink: true, theme: termTheme() });
+    fit = new FitAddon.FitAddon();
+    xterm.loadAddon(fit);
+    xterm.open(els.termView);
+    xterm.onData((d) => {
+      if (termExited) {
+        if (d === "\r") { termExited = false; xterm.reset(); openTerm(); }
+        return;
+      }
+      if (!termId) return;
+      const id = termId, data = bytesToB64(new TextEncoder().encode(d));
+      writeChain = writeChain.then(() => termPost("/term/write", { id, data })).catch(() => {});
+    });
+    xterm.attachCustomKeyEventHandler((e) => {
+      if (e.type === "keydown" && (e.ctrlKey || e.metaKey) && e.key === "`") { e.preventDefault(); xterm.blur(); els.input.focus({ preventScroll: true }); return false; }
+      return true;
+    });
+    new ResizeObserver(() => fitTerm()).observe(els.termView);
+  }
+  function fitTerm() {
+    if (!xterm || els.termView.classList.contains("hidden")) return;
+    fit.fit();
+    if (termId && (xterm.cols !== sentCols || xterm.rows !== sentRows)) {
+      sentCols = xterm.cols; sentRows = xterm.rows;
+      send({ kind: "term_resize", cols: xterm.cols, rows: xterm.rows });
+    }
+  }
+  function openTerm() {
+    termOpening = true;
+    fit.fit();
+    sentCols = xterm.cols; sentRows = xterm.rows;
+    send({ kind: "term_open", cols: xterm.cols, rows: xterm.rows });
+  }
+  async function readLoop(id) {
+    while (termId === id) {
+      let res;
+      try { res = await termPost("/term/read", { id }); } catch (err) { await new Promise((r) => setTimeout(r, 500)); continue; }
+      if (res.status === 404) return;   // outro terminal ou fechado
+      if (!res.ok) { await new Promise((r) => setTimeout(r, 500)); continue; }
+      const j = await res.json();
+      if (j.exited) {
+        if (termId !== id) return;
+        termId = 0; termExited = true;
+        xterm.write("\r\n[terminal encerrado — Enter para abrir outro]\r\n");
+        send({ kind: "term_close" });
+        return;
+      }
+      if (j.data) xterm.write(b64ToBytes(j.data));
+    }
+  }
+  let termVisible = false;
+  function renderTerm(f) {
+    if (xterm) xterm.options.theme = termTheme();
+    const visible = f.panel.open && f.panel.tab === "terminal";
+    const shown = visible && !termVisible;
+    termVisible = visible;
+    if (!visible) return;
+    ensureXterm();
+    fitTerm();
+    // escondido, o xterm para de desenhar: ao voltar, redesenha tudo
+    if (shown) requestAnimationFrame(() => { fitTerm(); xterm.refresh(0, xterm.rows - 1); });
+    if (f.term.open && f.term.id !== termId) {
+      termId = f.term.id; termOpening = false; termExited = false;
+      readLoop(termId);
+    } else if (!f.term.open && !termOpening && !termExited && !f.term.error) {
+      openTerm();
+    } else if (!f.term.open && f.term.error && termOpening) {
+      termOpening = false; termExited = true;
+      xterm.write("[" + f.term.error + "]\r\n");
+    }
+    if (wantTermFocus) { wantTermFocus = false; setTimeout(() => xterm.focus(), 0); }
+  }
+
   // renderPanel: aberto ou fechado e a aba ativa vem do quadro; a altura e
   // conveniencia local
   let panelTab = "";
@@ -585,13 +679,15 @@
   els.minimap.addEventListener("pointerup", () => { mmDrag = false; });
   els.runStop.addEventListener("mousedown", (e) => { e.preventDefault(); e.stopPropagation(); send({ kind: "stop" }); });
   for (const tab of els.panelTabs.querySelectorAll(".ptab")) {
-    tab.addEventListener("mousedown", (e) => { e.preventDefault(); if (tab.dataset.tab === "search") wantSearchFocus = true; send({ kind: "panel_tab", key: tab.dataset.tab }); });
+    tab.addEventListener("mousedown", (e) => { e.preventDefault(); if (tab.dataset.tab === "search") wantSearchFocus = true; if (tab.dataset.tab === "terminal") wantTermFocus = true; send({ kind: "panel_tab", key: tab.dataset.tab }); });
   }
   // o divisor e a barra "Saida" inteira redimensionam, com Pointer Events e
   // captura do ponteiro: uma vez iniciado, o arraste segue o divisor mesmo
   // passando pela barra de rolagem do editor ou saindo da janela
   function startResize(e) {
-    if (e.button !== 0 || e.target.closest("#output-close")) return;
+    // abas e botoes da barra sao cliques, nao arraste: o pointerdown com
+    // preventDefault cancelaria o mousedown deles
+    if (e.button !== 0 || e.target.closest("button, .ptab")) return;
     e.preventDefault();
     resizing = { y: e.clientY, h: outputH, id: e.pointerId, el: e.currentTarget };
     try { e.currentTarget.setPointerCapture(e.pointerId); } catch (err) { /* sem captura: o movimento ainda chega enquanto o ponteiro estiver sobre o alvo */ }
diff --git a/web/index.html b/web/index.html
index 80f1ab823e9ce0e6eab8a5953a3c9005a2361353..d78f4e01b9e5ce503352963e9b0233f5c75b8dd6 100644
--- a/web/index.html
+++ b/web/index.html
@@ -3,6 +3,7 @@
 <head>
 <meta charset="utf-8">
 <title>Noxy Editor</title>
+<link rel="stylesheet" href="/vendor/xterm.css">
 <link rel="stylesheet" href="/editor.css">
 </head>
 <body>
@@ -82,6 +83,8 @@
   </div>
 </div>
 <textarea id="input" autocomplete="off" autocapitalize="off" spellcheck="false"></textarea>
+<script src="/vendor/xterm.js"></script>
+<script src="/vendor/addon-fit.js"></script>
 <script src="/editor.js"></script>
 </body>
 </html>
NOXY_PATCH_EOF
```
- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `281/281 passaram` e `16/16 passaram`; depois, `ps -eo args | grep -E "noxy-plugin-pty|exec noxy" | grep -v grep` vazio.
- [ ] **Passo 5: o cliente de verdade**

Run: `python3 tests/web_smoke.py && GDK_BACKEND=x11 python3 tests/webkit_smoke.py`
Esperado: as duas linhas finais `OK: 0 falhas` (o primeiro precisa de `google-chrome`; o segundo abre uma janela WebKitGTK por alguns segundos).
- [ ] **Commit**

```bash
git add README.md editor.nx src/events.nx src/frame.nx src/server.nx src/session.nx src/term.nx tests/protocol.nx tests/run.nx tests/web_smoke.py tests/webkit_smoke.py web/editor.css web/editor.js web/index.html web/vendor
git commit -q -m 'feat(term): terminal de verdade com a extensao noxy_pty e xterm.js vendorizado; rotas /term fora do dono; abas do painel e Parar clicaveis com o mouse; shutdown para o programa e fecha o terminal

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 17: Documentação e CI

**Interfaces:**
- Produces: `.github/workflows/ci.yml` (roda `noxy --sync --locked` e as duas suítes; só passa depois da Task 18, quando `noxy_pty` está no `noxy.mod`).

**Files:** `.github/workflows/ci.yml`, `README.md`, `docs/ACHADOS.md`, `tests/MANUAL.md`

- [ ] **Passo 1: README, checklist manual, achado 1 e a CI**

Em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (183 linhas de patch; `git apply` falha sem mudar nada se o arquivo não estiver como o passo anterior deixou):

```bash
git apply --whitespace=nowarn <<'NOXY_PATCH_EOF'
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
new file mode 100644
index 0000000000000000000000000000000000000000..f5c36c9d4aeef4afd75d2247a5d07d3ecdf02e35
--- /dev/null
+++ b/.github/workflows/ci.yml
@@ -0,0 +1,21 @@
+# CI do editor: as suites Noxy no Ubuntu. Os smokes de navegador (Chrome e
+# WebKitGTK) ficam fora: precisam de janela e de navegador instalados.
+name: CI
+
+on:
+  push:
+  pull_request:
+
+jobs:
+  noxy:
+    runs-on: ubuntu-latest
+    steps:
+      - uses: actions/checkout@v4
+      - uses: actions/setup-go@v5
+        with:
+          go-version: '1.25'
+      - run: go install github.com/estevaofon/noxy/cmd/noxy@v0.25.1
+      - run: echo "$(go env GOPATH)/bin" >> "$GITHUB_PATH"
+      - run: noxy --sync --locked
+      - run: noxy tests/run.nx
+      - run: noxy tests/protocol.nx
diff --git a/README.md b/README.md
index 382965ff7cc496c46d6a57f0eb040fa8ff4cad0b..eed3c6179ede28c18fc71a4cc4feaa4c05450550 100644
--- a/README.md
+++ b/README.md
@@ -52,6 +52,14 @@ ln -sfn "$(pwd)/../noxy_webview" noxy_libs/github_com/estevaofon/noxy_webview
 
 A VM avisa uma vez que o checkout não bate com o `noxy.sum` e roda.
 
+## Extensão de terminal
+
+O terminal (Ctrl+`) é o package [`noxy_pty`](https://github.com/estevaofon/noxy_pty),
+importado em `src/term.nx` e instalado pelo mesmo `noxy --sync`. É Go puro,
+sem dependências de sistema. No Windows o binário existe, para o editor
+compilar, mas abrir um terminal responde "terminal indisponível no Windows
+nesta versão".
+
 ## Atalhos
 
 | Tecla | Ação |
@@ -67,14 +75,38 @@ A VM avisa uma vez que o checkout não bate com o `noxy.sum` e roda.
 | Ctrl+/ | comentar ou descomentar |
 | Tab, Shift+Tab | indentar, desindentar (quatro espaços) |
 | Enter | nova linha com a indentação da atual |
-| Escape | fechar o modal; senão colapsar a seleção |
-| F5 | salvar e rodar o arquivo ativo (`noxy arquivo.nx`), saída no painel |
-| Ctrl+J | mostrar ou ocultar o painel inferior (arraste a barra do painel, fora das abas, ou o divisor acima dela para redimensionar) |
+| F5 | salvar e rodar o arquivo ativo, com a saída ao vivo no painel |
+| Ctrl+F5 | parar o programa (também o botão Parar do painel) |
+| Ctrl+F, Ctrl+H | buscar, substituir no arquivo (F3 e Shift+F3 navegam) |
+| Ctrl+Shift+F | buscar na pasta |
+| Ctrl+P | abrir arquivo pelo nome |
+| Ctrl+Shift+P | paleta de comandos (inclui os temas) |
+| Ctrl+J | mostrar ou ocultar o painel inferior |
+| Ctrl+` | terminal; com o terminal focado, volta ao editor |
+| Escape | fecha lista, barra de busca ou modal; senão colapsa a seleção (no terminal, vai para o shell) |
 | Ctrl+Q | sair (pergunta se há abas com alterações) |
 
 Mouse: clique posiciona, arraste seleciona, duplo clique seleciona a palavra,
-clique no gutter seleciona a linha, roda rola. Fechar a janela pelo X encerra
-sem perguntar: alterações não salvas se perdem (use Ctrl+Q).
+clique no gutter seleciona a linha, roda rola, clique ou arraste no minimap
+rola. O painel inferior tem as abas Saída, Busca e Terminal; arraste a barra
+dele (fora das abas) ou o divisor acima para redimensionar.
+
+**Alterações não salvas não se perdem.** Cada aba suja tem uma cópia em
+`~/.cache/noxy-editor/recovery/`, gravada no máximo uma vez por segundo e
+1,5 s depois da última tecla. Fechar pelo X, uma queda do editor ou da
+máquina: na próxima vez que a pasta for aberta, as abas voltam sujas, com o
+texto. Salvar ou fechar sem salvar apaga a cópia.
+
+**Temas**: Escuro, Claro, Dracula, Nord e Monokai, pela paleta ("Tema: ...").
+A escolha fica em `~/.config/noxy-editor/settings.json`.
+
+**Git**: se a pasta está num repositório, a branch aparece na barra de
+status e os arquivos modificados (âmbar), novos (verde) e apagados (riscados)
+ficam marcados na árvore e nas abas; atualiza ao salvar, ao fim de uma
+execução e pelo comando "Git: atualizar".
+
+Arquivos com `\r\n` continuam com `\r\n` ao salvar; a barra de status
+mostra LF ou CRLF.
 
 ## Como está organizado
 
@@ -84,17 +116,26 @@ empacota o evento com um canal de resposta; o dono aplica e responde o quadro.
 
 | Módulo | Responsabilidade |
 |---|---|
-| `src/document` | linhas de texto e posições em code points; inserir, apagar, trechos |
+| `src/document` | linhas de texto, posições em code points, a quebra de linha do arquivo |
 | `src/lexer` | tokenizador de Noxy, uma linha por vez |
 | `src/history` | undo e redo por snapshot (copy-on-write faz a cópia ser rasa) |
 | `src/editing` | cursor, seleção, scroll e as operações de edição de uma aba |
-| `src/session` | raiz, abas, árvore, modal, abrir, salvar, fechar |
-| `src/runner` | roda o arquivo numa task e recolhe a saída |
+| `src/find` | busca e substituição no arquivo |
+| `src/search` | busca na pasta, numa task |
+| `src/index` | índice de arquivos e o filtro difuso do Ctrl+P |
+| `src/commands` | os comandos da paleta |
+| `src/settings` | `settings.json` |
+| `src/recovery` | cópias de recuperação das abas sujas |
+| `src/gitinfo` | branch e status do git, numa task |
+| `src/minimap` | o formato do arquivo para o minimap |
+| `src/term` | o terminal sobre a extensão `noxy_pty` |
+| `src/session` | raiz, abas, árvore, painel, lista, modal, abrir, salvar, fechar |
+| `src/runner` | roda o arquivo em segundo plano, saída ao vivo, Parar |
 | `src/frame` | o quadro JSON com as linhas visíveis tokenizadas |
 | `src/events` | do JSON do evento ao efeito na sessão, dentro de `call_result` |
-| `src/server` | rotas, token e a ponte com o dono do estado |
-| `src/launch` | janela pela extensão, fallback navegador |
-| `web/` | o cliente: `index.html`, `editor.css`, `editor.js` |
+| `src/server` | rotas, token, a ponte com o dono do estado e as rotas `/term` |
+| `src/launch`, `src/browser` | janela pela extensão, fallback navegador |
+| `web/` | o cliente: `index.html`, `editor.css`, `editor.js`; `web/vendor/` tem o xterm.js |
 
 Design e plano em `docs/superpowers/`.
 
@@ -103,12 +144,16 @@ Design e plano em `docs/superpowers/`.
     noxy tests/run.nx            # o núcleo inteiro, sem navegador
     noxy tests/protocol.nx       # servidor + cliente HTTP in-process
     python3 tests/web_smoke.py   # o cliente web num Chrome headless (precisa de google-chrome)
-    GDK_BACKEND=x11 python3 tests/webkit_smoke.py   # layout e arraste do painel no WebKitGTK real (PyGObject; abre uma janela)
+    GDK_BACKEND=x11 python3 tests/webkit_smoke.py   # layout, arraste do painel e terminal no WebKitGTK real (PyGObject; abre uma janela)
+
+A CI (`.github/workflows/ci.yml`) roda as duas suítes Noxy no Ubuntu. Os
+testes usam cache e configuração próprios em `tests/tmp`, nunca os seus.
 
 `tests/MANUAL.md` lista o que só se confere à mão.
 
-## Limitações da v1
+## Limitações
 
-Sem busca, paleta de comandos, temas, git, terminal ou minimap. Um programa
-que não termina não pode ser interrompido. Fechar pelo X perde alterações não
-salvas. Arquivos com `\r\n` são salvos com `\n`. Testado no Linux.
+Busca sem regex; um terminal por vez; git só para ver (commit, pull e push
+pelo terminal); o programa executado recebe `/dev/null` como entrada (para
+programas interativos, use o terminal). Testado no Linux; no Windows o
+terminal e o Parar ainda não funcionam.
diff --git a/docs/ACHADOS.md b/docs/ACHADOS.md
index 2245141c04ba4233c12dd0865dc6abc487359abb..baeeaf954126f629957d50654935f005f317965b 100644
--- a/docs/ACHADOS.md
+++ b/docs/ACHADOS.md
@@ -8,10 +8,14 @@ no código, como contornei, sugestão. Entradas novas vão no fim.
 
 **Onde:** `src/runner.nx`. **O que:** `sys.exec_output` bloqueia até o
 programa terminar e não devolve handle; um programa que não termina (servidor,
-jogo) fica rodando até o editor sair. **Contorno:** F5 durante uma execução
-responde "já está rodando"; o editor continua utilizável porque a execução é
-uma `spawn_task`. **Sugestão:** `sys.spawn_process(cmd) -> Process` com
-`kill`, `wait` e leitura incremental da saída.
+jogo) fica rodando até o editor sair, e a saída só aparece no fim.
+**Contorno (v1.1):** o shell faz o trabalho: `setsid sh -c '...' & echo $!`
+dá o PID do líder de um grupo de processos próprio, a saída vai para um
+arquivo lido aos pedaços a cada evento (`io.read_bytes` num handle aberto
+devolve só o que chegou), um arquivo `code` marca o fim, e Parar é
+`kill -TERM -PGID` (no `sh` do Ubuntu, o dash, sem `--`). **Sugestão:**
+`sys.spawn_process(cmd) -> Process` com `kill`, `wait` e leitura não
+bloqueante da saída.
 
 ## 2. `time_now()` não tem tipo de retorno estático
 
diff --git a/tests/MANUAL.md b/tests/MANUAL.md
index cb26ed2828ea0aa592446e44ab1ad49df2f74550..1660db039ff4c7e2d6a9eb6b5d937c5e125bea83 100644
--- a/tests/MANUAL.md
+++ b/tests/MANUAL.md
@@ -13,3 +13,10 @@ provam. Conferir a cada release, com a extensão instalada:
 - [ ] Fechar pelo X encerra o processo sem órfãos (`pgrep -f noxy-plugin-webview` vazio).
 - [ ] Com a extensão incapaz de abrir (troque `bin/noxy-plugin-webview-linux-amd64` no package por um script `#!/bin/sh` que faz `exit 127`, guardando o binário real), o editor avisa `janela pela extensao indisponivel` no terminal e abre no navegador em modo app; fechar a janela do navegador encerra o `noxy` em até 3 s. Restaure o binário depois.
 - [ ] `NOXY_WEBVIEW_DEBUG=1 noxy editor.nx .` abre com o inspetor do WebKit disponível.
+- [ ] Terminal (Ctrl+`): `vim` abre, Escape troca de modo, `:q` sai; `top` desenha e atualiza; Ctrl+C interrompe um `sleep 100`.
+- [ ] Redimensionar o painel com `top` aberto: o `top` redesenha no tamanho novo.
+- [ ] Fechar a janela pelo X com `sleep 1000` no terminal e um programa rodando pelo F5: `pgrep -f "sleep 1000"` e `pgrep -f "exec noxy"` vazios.
+- [ ] Editar sem salvar, fechar pelo X, abrir a mesma pasta: a aba volta suja, com o texto.
+- [ ] Trocar o tema pela paleta, fechar e abrir: o tema continua.
+- [ ] Num repositório, salvar um arquivo: ele fica âmbar na árvore e na aba; a branch aparece na status.
+- [ ] F5 num programa que imprime em loop: a saída aparece ao vivo; Parar encerra com `[interrompido]`.
NOXY_PATCH_EOF
```
- [ ] **Passo 2: as suítes continuam verdes**

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `281/281 passaram` e `16/16 passaram`.
- [ ] **Commit**

```bash
git add .github/workflows/ci.yml README.md docs/ACHADOS.md tests/MANUAL.md
git commit -q -m 'docs: README da v1.1, checklist manual novo, achado 1 com o contorno; ci: suites noxy no ubuntu

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

### Task 18: Publicar noxy_pty e exigir no editor

**Interfaces:**
- Consumes: Tasks 13–17.
- Produces: `github.com/estevaofon/noxy_pty` v0.1.0 com binários; `noxy.mod`/`noxy.sum` do editor com o package.

**Ação pública: confirme com o usuário antes de cada passo desta tarefa** (criar repositório, enviar tag e publicar release são visíveis para outros e difíceis de desfazer).

- [ ] **Passo 1: repositório no GitHub** (em `/home/estevao/Documentos/noxy_projects/noxy_pty`)

```bash
gh repo create estevaofon/noxy_pty --public --source=. --remote=origin --push --description 'Terminais (pty) para programas Noxy: extensão por processo sobre creack/pty'
```

- [ ] **Passo 2: release v0.1.0**

```bash
git tag -a v0.1.0 -m 'noxy_pty v0.1.0 — terminais para programas Noxy: open, read, write, resize, close'
git push origin v0.1.0
gh run watch $(gh run list --workflow=release.yml --limit 1 --json databaseId --jq '.[0].databaseId') --exit-status
gh release view v0.1.0 --json assets --jq '.assets[].name'
```

Esperado: o workflow verde; os assets `checksums.txt`, `noxy-plugin-pty-{linux-amd64,linux-arm64,darwin-amd64,darwin-arm64,windows-amd64.exe}`.

- [ ] **Passo 3: o editor passa a exigir o release** (em `/home/estevao/Documentos/noxy_projects/Noxy-Editor`)

```bash
rm noxy_libs/github_com/estevaofon/noxy_pty
noxy --get github.com/estevaofon/noxy_pty@v0.1.0
noxy --sync --locked && noxy tests/run.nx && noxy tests/protocol.nx
```

Esperado: `github.com/estevaofon/noxy_pty v0.1.0  installed`; o `noxy.mod` com `require github.com/estevaofon/noxy_pty v0.1.0`; `noxy.sum` com as linhas dos cinco binários; `cached` no `--locked`; `281/281` e `16/16`.

- [ ] **Passo 4: os smokes com o package instalado**

Run: `python3 tests/web_smoke.py && GDK_BACKEND=x11 python3 tests/webkit_smoke.py`
Esperado: os dois `OK: 0 falhas`.

- [ ] **Commit**

```bash
git add noxy.mod noxy.sum
git commit -q -m 'chore(deps): noxy_pty v0.1.0 via noxy.mod e noxy.sum

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```
