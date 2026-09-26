# Noxy Editor — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um editor de código para arquivos Noxy, escrito em Noxy, com a UI numa janela nativa (extensão `noxy_webview`) e o modelo inteiro no Noxy: abrir pasta, árvore, abas, editar com cursor, seleção, clipboard, undo, highlighting, salvar e rodar o arquivo (F5) com a saída num painel.

**Architecture:** A routine principal de `editor.nx` é dona de todo o estado (`Session`); o servidor HTTP da stdlib roda cada requisição numa routine e só empacota o evento com um canal de resposta. O navegador é um cliente burro: manda teclado e mouse como JSON para `POST /event` e recebe um quadro com as linhas visíveis já tokenizadas, cursor, seleção, abas, status e saída. A janela é a extensão por processo `noxy_webview` (Go + webview_go), com fallback para o navegador em modo app.

**Tech Stack:** Noxy v0.25.1 (stdlib `http_server`, `http_client`, `io`, `sys`, `strings`, `uuid`, `json_loads`/`json_dumps`, `spawn`/`spawn_task`, canais); HTML/CSS/JS puro; Go 1.25+ com `github.com/estevaofon/noxy/sdk/noxyplugin v0.1.0` e `github.com/webview/webview_go v0.0.0-20240831120633-6173450d4dd6`; Chrome headless + DevTools Protocol para o smoke do cliente.

**Spec:** `docs/superpowers/specs/2026-09-25-noxy-editor-design.md` (neste repositório). O plano cobre os dois repositórios da spec: `Noxy-Editor` (Tarefas 1 a 13 e 16) e `noxy_webview` (Tarefas 14 e 15).

**Todo o código deste plano foi executado e testado antes de ser escrito aqui**, num protótipo com o `noxy` v0.25.1 desta máquina: `tests/run.nx` (141 checks), `tests/protocol.nx` (10), `tests/web_smoke.py` num Chrome headless (23) e `go test -race ./window/`. Copie os blocos exatamente; onde um passo diz "Esperado", é o que o protótipo produziu.

## Global Constraints

- Noxy **v0.25.1** (`noxy --version`); o binário está em `/home/estevao/go/bin/noxy`, no PATH.
- Repositórios: editor em `/home/estevao/Documentos/noxy_projects/Noxy-Editor` (já é um repositório git com a spec); extensão em `/home/estevao/Documentos/noxy_projects/noxy_webview` (criar). Todo comando do editor roda **a partir da raiz do Noxy-Editor**; todo comando da extensão, da raiz dela.
- Identificadores em inglês; comentários de código em português **sem acentos** (convenção dos outros projetos Noxy do autor); README, spec e docs em português com acentos.
- Commits no padrão `tipo(escopo): descrição em português`, terminando com a linha `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Nunca `use strings select *` num módulo que use o builtin `contains` de arrays: o `contains` de strings o sombreia. Importe por nome (`use strings select substring, codes`).
- `time_now()` não tem tipo estático: sempre `let t: int = time_now()`.
- `ref` exige uma variável: `session.load(ref x)` com `x` declarado antes, nunca `ref f()`.
- Um parâmetro `ref T` é passado adiante sem `ref` (`place(ed, ...)` dentro de `move_left(ed: ref Editor, ...)`) e lido por valor com `*ed`.
- A stdlib não tem `sort`: ordenação é por inserção em Noxy.
- Plataforma testada: Linux (Ubuntu 26.04, Wayland). A janela pela extensão precisa de `libgtk-3-dev` e `libwebkit2gtk-4.1-dev` para compilar (instalação com sudo, pedida ao usuário na Tarefa 15) e de `google-chrome` no PATH para o smoke do cliente.
- O servidor escuta só em `127.0.0.1`, porta efêmera, com token na URL e no cabeçalho `X-Noxy-Token` (ou em `?t=` para o `sendBeacon`).

## Review Focus

Entradas que a spec implica mas nenhum requisito nomeia, com o teste que as prende à tarefa dona do código:

1. **Arquivo que não é UTF-8** aberto pela árvore: mensagem no status, nenhuma aba, editor segue vivo. Teste "arquivo que nao e UTF-8 vira mensagem, sem aba" (Tarefa 8).
2. **Salvar quando o caminho não pode ser gravado** (diretório removido, sem permissão): mensagem, a aba continua suja, nada é perdido. Teste "salvar num caminho que nao existe vira mensagem e a aba continua suja" (Tarefa 8).
3. **Evento com campo de tipo errado** (`"line": "x"`): 400, sem mudar a sessão, sem derrubar o dono. Teste "campo com tipo errado devolve vazio" (Tarefa 10) e "POST com JSON invalido e 400" (Tarefa 11).
4. **Clique além do fim** (abaixo da última linha, à direita do texto): o cursor vai para o fim da última linha e a janela rola até ele. Teste "clique alem do fim vai para o fim da ultima linha" (Tarefa 5).
5. **Arquivo grande** (5000 linhas): o quadro só carrega as linhas visíveis e sai em menos de 200 ms, senão cada tecla trava. Teste "arquivo de 5000 linhas: quadro so com as visiveis, em menos de 200 ms" (Tarefa 9).

## Mapa de arquivos

```
Noxy-Editor/
├── editor.nx                 # T12 (fallback), T16 (extensão): entrada, loop dono
├── src/document.nx           # T2
├── src/lexer.nx              # T3
├── src/history.nx            # T4
├── src/editing.nx            # T5 (movimento, seleção, scroll) + T6 (texto, undo, clipboard)
├── src/runner.nx             # T7
├── src/session.nx            # T8
├── src/frame.nx              # T9
├── src/events.nx             # T10
├── src/server.nx             # T11
├── src/launch.nx             # T12 (fallback), T16 (extensão)
├── web/index.html, editor.css, editor.js   # T11 (index mínimo), T12
├── tests/run.nx              # T1 harness; cada tarefa acrescenta a sua função
├── tests/protocol.nx         # T11
├── tests/cdp.py, web_smoke.py  # T12
├── tests/MANUAL.md, README.md, docs/ACHADOS.md   # T1 (inicial), T13
└── noxy.mod, .gitignore      # T1

noxy_webview/
├── go.mod, window/window.go, window/window_test.go   # T14
├── main.go, noxy_ext.toml, noxy_webview.nx, noxy.mod # T15
├── examples/smoke.nx, release/build.sh, .github/workflows/release.yml, README.md  # T15
└── bin/ (compilado, ignorado)                        # T15
```

Cada tarefa do editor termina com `noxy tests/run.nx` passando (o número esperado de checks está em cada uma) e um commit.

---

### Tarefa 1: Esqueleto do Noxy-Editor

**Files:**
- Create: `noxy.mod`
- Create: `.gitignore`
- Create: `tests/run.nx`
- Create: `docs/ACHADOS.md`

**Interfaces:**
- Consumes: nada.
- Produces: o harness `check(name, cond)` / `report()` em `tests/run.nx` que toda tarefa seguinte estende; `noxy.mod` com `module noxy_editor`.

- [ ] **Passo 1: `noxy.mod` e `.gitignore`**

```
module noxy_editor

noxy v0.25.1
```

```
# Dependências resolvidas a partir de noxy.mod / noxy.sum
noxy_libs/

# Binários e artefatos
bin/
dist/

# Temporários dos testes
tests/tmp/
__pycache__/

# Sistema / editores
.DS_Store
.vscode/
.idea/
```

- [ ] **Passo 2: o harness de testes**

`tests/run.nx`, no formato dos outros projetos Noxy do autor. Cada tarefa acrescenta uma `func test_x()` antes de `report()` e a chamada `test_x()` logo acima de `report()`.

```noxy
// tests/run.nx — suite do editor. Roda sem navegador:
//     noxy tests/run.nx      (a partir da raiz do projeto)
use sys

let fails = 0
let total = 0

func check(name: string, cond: bool) -> void
    total = total + 1
    if cond then
        print(f"  ok   {name}")
    else
        print(f"FAIL   {name}")
        fails = fails + 1
    end
end

func report() -> void
    print("")
    print(f"{total - fails}/{total} passaram")
    if fails > 0 then
        sys.exit(1)
    end
end

func test_document() -> void
    print("document")
    let d: doc.Document = doc.from_text("x.nx", "ab\r\ncd\n")
    check("from_text normaliza CRLF e mantem a linha final vazia", length(d.lines) == 3 && d.lines[0] == "ab" && d.lines[1] == "cd" && d.lines[2] == "")
    check("to_text devolve LF", doc.to_text(d) == "ab\ncd\n")
    let e: doc.Document = doc.from_text("", "")
    check("documento vazio tem uma linha", length(e.lines) == 1 && e.lines[0] == "")

    let p: doc.Pos = doc.insert(ref d, doc.Pos(0, 1), "X")
    check("insert na linha", d.lines[0] == "aXb" && p.line == 0 && p.col == 2 && d.dirty)
    p = doc.insert(ref d, doc.Pos(0, 2), "1\n2\n3")
    check("insert multilinha divide a linha", d.lines[0] == "aX1" && d.lines[1] == "2" && d.lines[2] == "3b" && length(d.lines) == 5)
    check("insert multilinha devolve o fim do texto", p.line == 2 && p.col == 1)
    let u: doc.Document = doc.from_text("", "héllo")
    doc.insert(ref u, doc.Pos(0, 2), "ç")
    check("insert conta code points", u.lines[0] == "héçllo")

    doc.delete_range(ref d, doc.Pos(0, 2), doc.Pos(2, 1))
    check("delete_range atravessando linhas junta as pontas", d.lines[0] == "aXb" && length(d.lines) == 3)
    doc.delete_range(ref d, doc.Pos(0, 0), doc.Pos(0, 1))
    check("delete_range na linha", d.lines[0] == "Xb")
    doc.delete_range(ref d, doc.Pos(1, 0), doc.Pos(1, 0))
    check("delete_range vazio nao muda nada", d.lines[1] == "cd")

    check("text_range na linha", doc.text_range(d, doc.Pos(1, 0), doc.Pos(1, 1)) == "c")
    check("text_range multilinha", doc.text_range(d, doc.Pos(0, 1), doc.Pos(2, 0)) == "b\ncd\n")

    let c: doc.Pos = doc.clamp(d, doc.Pos(9, 9))
    check("clamp traz para dentro", c.line == 2 && c.col == 0)
    let r: doc.Range = doc.ordered(doc.Pos(2, 0), doc.Pos(0, 1))
    check("ordered poe a menor primeiro", r.start.line == 0 && r.stop.line == 2)
end

report()
```

- [ ] **Passo 3: rodar**

Run: `noxy tests/run.nx`
Esperado: uma linha em branco e `0/0 passaram`, código de saída 0.

- [ ] **Passo 4: o registro de achados**

`docs/ACHADOS.md` já nasce com os cinco achados que a prototipagem produziu:

````markdown
# Achados sobre a linguagem

O produto principal de um projeto de experimentação: o que o Noxy não deu
conta, o que incomodou e o que sugiro. Para cada item: o que aconteceu, onde
no código, como contornei, sugestão. Entradas novas vão no fim.

## 1. Não há como interromper um processo filho

**Onde:** `src/runner.nx`. **O que:** `sys.exec_output` bloqueia até o
programa terminar e não devolve handle; um programa que não termina (servidor,
jogo) fica rodando até o editor sair. **Contorno:** F5 durante uma execução
responde "já está rodando"; o editor continua utilizável porque a execução é
uma `spawn_task`. **Sugestão:** `sys.spawn_process(cmd) -> Process` com
`kill`, `wait` e leitura incremental da saída.

## 2. `time_now()` não tem tipo de retorno estático

**Onde:** todo `let t: int = time_now()`. **O que:** `let t = time_now()` é
erro de compilação ("cannot infer type"), embora o valor seja sempre `int`.
**Contorno:** anotar. **Sugestão:** dar retorno estático a `time_now`, como
`length` e `to_str` já têm.

## 3. A stdlib não tem ordenação

**Onde:** `session.sort_nodes`. **O que:** não há `sort` para arrays; a
árvore precisa de nomes ordenados. **Contorno:** ordenação por inserção em
Noxy (listas por diretório são pequenas). **Sugestão:** `sort(ref xs)` e
`sort_by(ref xs, func)` no core ou num módulo `arrays`.

## 4. `use strings select *` sombreia o `contains` de arrays

**Onde:** `src/lexer.nx`, `src/session.nx`. **O que:** `strings.contains(s,
sub)` e o builtin `contains(xs, v)` têm o mesmo nome; com `select *` o
builtin some e `contains(KEYWORDS, word)` vira erro de tipo. **Contorno:**
importar por nome (`use strings select substring, codes`). **Sugestão:** um
aviso do compilador quando um `select *` sombreia um builtin.

## 5. `serve` da stdlib imprime no stdout do programa

**Onde:** `src/server.nx`. **O que:** `http_server.serve` imprime `Server
listening on ...` em stdout, misturado à saída do editor, sem opção de
silenciar. **Contorno:** nenhum. **Sugestão:** mover para stderr ou tornar
opcional.
````

- [ ] **Passo 5: commit**

```bash
git add noxy.mod .gitignore tests/run.nx docs/ACHADOS.md
git commit -m "chore: esqueleto do Noxy Editor — noxy.mod, harness de testes e registro de achados"
```


### Tarefa 2: Document — linhas e posições

**Files:**
- Create: `src/document.nx`
- Modify: `tests/run.nx`

**Interfaces:**
- Consumes: `check` de `tests/run.nx`.
- Produces: `Pos(line, col)`, `Range(start, stop)`, `Document(path, lines, dirty)`; `from_text(path, text) -> Document`, `to_text(d) -> string`, `line_count(d)`, `line_len(d, i)`, `before(a, b)`, `same(a, b)`, `ordered(a, b) -> Range`, `clamp(d, p) -> Pos`, `insert(ref d, p, text) -> Pos`, `delete_range(ref d, a, b)`, `text_range(d, a, b) -> string`.

- [ ] **Passo 1: o teste que falha**

Em `tests/run.nx`, acrescente `use src.document as doc` logo abaixo de `use sys`, esta função antes de `report()`, e a chamada `test_document()` na linha acima de `report()`:

```noxy
func test_document() -> void
    print("document")
    let d: doc.Document = doc.from_text("x.nx", "ab\r\ncd\n")
    check("from_text normaliza CRLF e mantem a linha final vazia", length(d.lines) == 3 && d.lines[0] == "ab" && d.lines[1] == "cd" && d.lines[2] == "")
    check("to_text devolve LF", doc.to_text(d) == "ab\ncd\n")
    let e: doc.Document = doc.from_text("", "")
    check("documento vazio tem uma linha", length(e.lines) == 1 && e.lines[0] == "")

    let p: doc.Pos = doc.insert(ref d, doc.Pos(0, 1), "X")
    check("insert na linha", d.lines[0] == "aXb" && p.line == 0 && p.col == 2 && d.dirty)
    p = doc.insert(ref d, doc.Pos(0, 2), "1\n2\n3")
    check("insert multilinha divide a linha", d.lines[0] == "aX1" && d.lines[1] == "2" && d.lines[2] == "3b" && length(d.lines) == 5)
    check("insert multilinha devolve o fim do texto", p.line == 2 && p.col == 1)
    let u: doc.Document = doc.from_text("", "héllo")
    doc.insert(ref u, doc.Pos(0, 2), "ç")
    check("insert conta code points", u.lines[0] == "héçllo")

    doc.delete_range(ref d, doc.Pos(0, 2), doc.Pos(2, 1))
    check("delete_range atravessando linhas junta as pontas", d.lines[0] == "aXb" && length(d.lines) == 3)
    doc.delete_range(ref d, doc.Pos(0, 0), doc.Pos(0, 1))
    check("delete_range na linha", d.lines[0] == "Xb")
    doc.delete_range(ref d, doc.Pos(1, 0), doc.Pos(1, 0))
    check("delete_range vazio nao muda nada", d.lines[1] == "cd")

    check("text_range na linha", doc.text_range(d, doc.Pos(1, 0), doc.Pos(1, 1)) == "c")
    check("text_range multilinha", doc.text_range(d, doc.Pos(0, 1), doc.Pos(2, 0)) == "b\ncd\n")

    let c: doc.Pos = doc.clamp(d, doc.Pos(9, 9))
    check("clamp traz para dentro", c.line == 2 && c.col == 0)
    let r: doc.Range = doc.ordered(doc.Pos(2, 0), doc.Pos(0, 1))
    check("ordered poe a menor primeiro", r.start.line == 0 && r.stop.line == 2)
end
```

- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: erro de compilação dizendo que o módulo `src.document` não pôde ser carregado (`could not be loaded`).

- [ ] **Passo 3: implementar**

```noxy
// src/document.nx — o documento: linhas de texto e posicoes em code points.
// Nao conhece cursor, tela nem arquivo. Toda operacao que muda texto marca
// dirty. Posicoes usam a mesma unidade de substring e codes.
use strings select substring, split, join_count, replace

struct Pos
    line: int       // 0-based
    col: int        // em code points
end

struct Range
    start: Pos      // inclusive
    stop: Pos       // exclusivo; nunca antes de start
end

struct Document
    path: string    // absoluto; "" para um buffer sem arquivo
    lines: string[] // nunca vazio: um documento vazio tem uma linha ""
    dirty: bool
end

func from_text(path: string, text: string) -> Document
    let clean: string = replace(replace(text, "\r\n", "\n"), "\r", "\n")
    let parts: string[] = split(clean, "\n").parts
    if length(parts) == 0 then
        parts = [""]
    end
    return Document(path, parts, false)
end

func to_text(d: Document) -> string
    return join_count(d.lines, "\n", length(d.lines))
end

func line_count(d: Document) -> int
    return length(d.lines)
end

func line_len(d: Document, i: int) -> int
    return length(d.lines[i])
end

func before(a: Pos, b: Pos) -> bool
    return a.line < b.line || (a.line == b.line && a.col < b.col)
end

func same(a: Pos, b: Pos) -> bool
    return a.line == b.line && a.col == b.col
end

// ordered devolve as duas posicoes em ordem, para tratar uma selecao feita
// em qualquer direcao.
func ordered(a: Pos, b: Pos) -> Range
    if before(b, a) then
        return Range(b, a)
    end
    return Range(a, b)
end

func clamp(d: Document, p: Pos) -> Pos
    let line: int = p.line
    if line < 0 then
        line = 0
    end
    if line >= length(d.lines) then
        line = length(d.lines) - 1
    end
    let col: int = p.col
    if col < 0 then
        col = 0
    end
    if col > length(d.lines[line]) then
        col = length(d.lines[line])
    end
    return Pos(line, col)
end

// insert poe text em p; "\n" divide linhas. Devolve a posicao logo depois
// do texto inserido.
func insert(d: ref Document, p: Pos, text: string) -> Pos
    let pieces: string[] = split(text, "\n").parts
    let n: int = length(pieces)
    let line: string = d.lines[p.line]
    let head: string = substring(line, 0, p.col)
    let tail: string = substring(line, p.col, length(line))
    d.dirty = true
    if n == 1 then
        d.lines[p.line] = head + text + tail
        return Pos(p.line, p.col + length(text))
    end
    let out: string[] = slice(d.lines, 0, p.line)
    append(ref out, head + pieces[0])
    for i in range(1, n - 1) do
        append(ref out, pieces[i])
    end
    append(ref out, pieces[n - 1] + tail)
    for i in range(p.line + 1, length(d.lines)) do
        append(ref out, d.lines[i])
    end
    d.lines = out
    return Pos(p.line + n - 1, length(pieces[n - 1]))
end

// delete_range remove [a, b); atravessando linhas, junta as pontas.
func delete_range(d: ref Document, a: Pos, b: Pos) -> void
    if same(a, b) then
        return
    end
    let first: string = d.lines[a.line]
    let last: string = d.lines[b.line]
    let joined: string = substring(first, 0, a.col) + substring(last, b.col, length(last))
    d.dirty = true
    if a.line == b.line then
        d.lines[a.line] = joined
        return
    end
    let out: string[] = slice(d.lines, 0, a.line)
    append(ref out, joined)
    for i in range(b.line + 1, length(d.lines)) do
        append(ref out, d.lines[i])
    end
    d.lines = out
end

func text_range(d: Document, a: Pos, b: Pos) -> string
    if a.line == b.line then
        return substring(d.lines[a.line], a.col, b.col)
    end
    let out: string = substring(d.lines[a.line], a.col, length(d.lines[a.line])) + "\n"
    for i in range(a.line + 1, b.line) do
        out = out + d.lines[i] + "\n"
    end
    return out + substring(d.lines[b.line], 0, b.col)
end
```

- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx`
Esperado: `14/14 passaram`.

- [ ] **Passo 5: commit**

```bash
git add src/document.nx tests/run.nx
git commit -m "feat(document): linhas e posicoes em code points, inserir, apagar e trechos"
```


### Tarefa 3: Lexer — tokenizador de Noxy

**Files:**
- Create: `src/lexer.nx`
- Modify: `tests/run.nx`

**Interfaces:**
- Consumes: nada do projeto (só `strings`).
- Produces: `Token(kind, text)`; `tokenize(line) -> Token[]` com kinds `keyword type ident call number string comment operator punct space`; `join_tokens(ts) -> string`. Invariante: `join_tokens(tokenize(l)) == l`.

- [ ] **Passo 1: o teste que falha**

Acrescente `use src.lexer as lexer` e `use io` abaixo dos `use` existentes em `tests/run.nx`, estas duas funções antes de `report()`, e `test_lexer()` acima de `report()`:

```noxy
func kinds(line: string) -> string
    let out: string = ""
    for t in lexer.tokenize(line) do
        if t.kind != "space" then
            out = out + t.kind + " "
        end
    end
    return out
end

func test_lexer() -> void
    print("lexer")
    check("keyword type ident operator number", kinds("let x: int = 10") == "keyword ident punct type operator number ")
    check("call vs ident", kinds("print(x)") == "call punct ident punct ")
    check("struct e type", kinds("Pos(1, 2)") == "type punct number punct number punct ")
    check("comentario ate o fim", kinds("x // a \"b\"") == "ident comment ")
    check("string com escape", kinds("\"a\\\"b\" + 'c'") == "string operator string ")
    check("string aberta vai ate o fim", kinds("\"abc") == "string ")
    check("f-string com aspas dentro de chaves", kinds("f\"n = {fmt(\"%d\", n)}\" + 1") == "string operator number ")
    check("bytes literal", kinds("b\"hi\"") == "string ")
    check("float e hex", kinds("3.14 0xFF 7") == "number number number ")
    check("operadores de dois caracteres", kinds("a -> b == c && d") == "ident operator ident operator ident operator ident ")
    check("identificador unicode", kinds("ação = 1") == "ident operator number ")
    check("caractere solto vira punct", kinds("@") == "punct ")
    check("tab e espaco", lexer.tokenize("\tx")[0].kind == "space")

    // a invariante vale para todo modulo do projeto, os que existem agora e
    // os que vierem
    let broken = 0
    for name in io.list_dir("src").data do
        let f: io.File = io.open("src/" + name, "r")
        let r: io.IOLinesResult = io.read_lines(f)
        io.close(f)
        for line in r.data do
            if lexer.join_tokens(lexer.tokenize(line)) != line then
                broken = broken + 1
            end
        end
    end
    check("invariante: tokens concatenados devolvem a linha, em todo src/", broken == 0)
end
```

- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: erro de compilação: módulo `src.lexer` não pôde ser carregado.

- [ ] **Passo 3: implementar**

Sem `use strings select *`: o módulo usa o builtin `contains` de arrays.

```noxy
// src/lexer.nx — tokenizador de Noxy, uma linha por vez, sem estado entre
// linhas (comentario e so //, strings nao atravessam linha). Invariante: a
// concatenacao dos textos dos tokens devolve a linha original — e o que
// mantem as colunas do cliente corretas.
use strings select substring, codes

struct Token
    kind: string    // keyword type ident call number string comment operator punct space
    text: string
end

let KEYWORDS: string[] = ["let", "func", "struct", "if", "elif", "then", "else", "end", "while", "do", "return", "break", "continue", "for", "in", "defer", "when", "case", "default", "try", "ref", "use", "select", "as", "true", "false", "null", "zeros"]
let TYPES: string[] = ["int", "float", "string", "bool", "void", "bytes", "any", "map", "chan"]

func is_digit(c: int) -> bool
    return c >= 48 && c <= 57
end

func is_hex(c: int) -> bool
    return is_digit(c) || (c >= 97 && c <= 102) || (c >= 65 && c <= 70)
end

func is_upper(c: int) -> bool
    return c >= 65 && c <= 90
end

func is_ident_start(c: int) -> bool
    return (c >= 97 && c <= 122) || is_upper(c) || c == 95 || c > 127
end

func is_ident_char(c: int) -> bool
    return is_ident_start(c) || is_digit(c)
end

func is_operator_char(c: int) -> bool
    // + - * / % = < > ! & | ^ ?
    return c == 43 || c == 45 || c == 42 || c == 47 || c == 37 || c == 61 || c == 60 || c == 62 || c == 33 || c == 38 || c == 124 || c == 94 || c == 63
end

// scan_string: i na aspa de abertura; devolve o indice logo depois da aspa
// de fechamento, ou o fim da linha se nao fechar. Numa f-string a aspa so
// fecha fora de chaves, como no lexer do compilador.
func scan_string(cs: int[], i: int, fstr: bool) -> int
    let n: int = length(cs)
    let q: int = cs[i]
    let depth: int = 0
    i = i + 1
    while i < n do
        let c: int = cs[i]
        if c == 92 then
            i = i + 2
        elif fstr && c == 123 then
            depth = depth + 1
            i = i + 1
        elif fstr && c == 125 && depth > 0 then
            depth = depth - 1
            i = i + 1
        elif c == q && depth == 0 then
            return i + 1
        else
            i = i + 1
        end
    end
    return n
end

func scan_number(cs: int[], i: int) -> int
    let n: int = length(cs)
    if cs[i] == 48 && i + 1 < n && (cs[i + 1] == 120 || cs[i + 1] == 88) then
        i = i + 2
        while i < n && is_hex(cs[i]) do
            i = i + 1
        end
        return i
    end
    while i < n && is_digit(cs[i]) do
        i = i + 1
    end
    if i + 1 < n && cs[i] == 46 && is_digit(cs[i + 1]) then
        i = i + 1
        while i < n && is_digit(cs[i]) do
            i = i + 1
        end
    end
    return i
end

func scan_operator(cs: int[], i: int) -> int
    let n: int = length(cs)
    if i + 1 < n then
        let a: int = cs[i]
        let b: int = cs[i + 1]
        // == != <= >= && || -> << >>
        if (b == 61 && (a == 61 || a == 33 || a == 60 || a == 62)) || (a == 38 && b == 38) || (a == 124 && b == 124) || (a == 45 && b == 62) || (a == 60 && b == 60) || (a == 62 && b == 62) then
            return i + 2
        end
    end
    return i + 1
end

// classify decide keyword, type, call ou ident para a palavra que termina
// em i (exclusivo). Nome iniciado em maiuscula e type (struct).
func classify(word: string, cs: int[], i: int) -> string
    if contains(KEYWORDS, word) then
        return "keyword"
    end
    if contains(TYPES, word) || is_upper(cs[i - length(word)]) then
        return "type"
    end
    let j: int = i
    while j < length(cs) && (cs[j] == 32 || cs[j] == 9) do
        j = j + 1
    end
    if j < length(cs) && cs[j] == 40 then
        return "call"
    end
    return "ident"
end

func tokenize(line: string) -> Token[]
    let cs: int[] = codes(line)
    let n: int = length(cs)
    let out: Token[] = []
    let i: int = 0
    while i < n do
        let c: int = cs[i]
        let start: int = i
        if c == 47 && i + 1 < n && cs[i + 1] == 47 then
            append(ref out, Token("comment", substring(line, i, n)))
            i = n
        elif c == 32 || c == 9 then
            while i < n && (cs[i] == 32 || cs[i] == 9) do
                i = i + 1
            end
            append(ref out, Token("space", substring(line, start, i)))
        elif c == 34 || c == 39 then
            i = scan_string(cs, i, false)
            append(ref out, Token("string", substring(line, start, i)))
        elif (c == 102 || c == 98) && i + 1 < n && (cs[i + 1] == 34 || cs[i + 1] == 39) then
            i = scan_string(cs, i + 1, c == 102)
            append(ref out, Token("string", substring(line, start, i)))
        elif is_digit(c) then
            i = scan_number(cs, i)
            append(ref out, Token("number", substring(line, start, i)))
        elif is_ident_start(c) then
            while i < n && is_ident_char(cs[i]) do
                i = i + 1
            end
            let word: string = substring(line, start, i)
            append(ref out, Token(classify(word, cs, i), word))
        elif is_operator_char(c) then
            i = scan_operator(cs, i)
            append(ref out, Token("operator", substring(line, start, i)))
        else
            append(ref out, Token("punct", substring(line, i, i + 1)))
            i = i + 1
        end
    end
    return out
end

// join_tokens reconstroi a linha; os testes conferem a invariante com ele.
func join_tokens(ts: Token[]) -> string
    let out: string = ""
    for t in ts do
        out = out + t.text
    end
    return out
end
```

- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx`
Esperado: `28/28 passaram` (14 do document, 14 do lexer, incluindo a invariante sobre todo arquivo de `src/`).

- [ ] **Passo 5: commit**

```bash
git add src/lexer.nx tests/run.nx
git commit -m "feat(lexer): tokenizador de Noxy linha a linha com invariante de reconstrucao"
```


### Tarefa 4: History — undo e redo por snapshot

**Files:**
- Create: `src/history.nx`
- Modify: `tests/run.nx`

**Interfaces:**
- Consumes: `doc.Pos`.
- Produces: `Snapshot(lines, cursor)`, `History(undo, redo, last_kind, last_time)`; `new_history()`, `record(ref h, snap, kind, now)`, `undo(ref h, current) -> Snapshot?`, `redo(ref h, current) -> Snapshot?`. Kinds: `"typing"`, `"delete"`, `"other"`.

- [ ] **Passo 1: o teste que falha**

Acrescente `use src.history as history` aos `use`, a função antes de `report()` e `test_history()` acima de `report()`:

```noxy
func test_history() -> void
    print("history")
    let h: history.History = history.new_history()
    let s1: history.Snapshot = history.Snapshot(["a"], doc.Pos(0, 1))
    let s2: history.Snapshot = history.Snapshot(["ab"], doc.Pos(0, 2))
    let s3: history.Snapshot = history.Snapshot(["abc"], doc.Pos(0, 3))
    history.record(ref h, s1, "typing", 1000)
    history.record(ref h, s2, "typing", 1500)
    check("digitacao consecutiva agrupa", length(h.undo) == 1)
    history.record(ref h, s3, "typing", 3000)
    check("depois de 1 s abre outro grupo", length(h.undo) == 2)
    history.record(ref h, s3, "delete", 3100)
    check("kind diferente abre outro grupo", length(h.undo) == 3)

    let back: history.Snapshot? = history.undo(ref h, history.Snapshot(["abcd"], doc.Pos(0, 4)))
    check("undo devolve o topo", back != null && length(h.undo) == 2 && length(h.redo) == 1)
    if back != null then
        check("undo devolve o snapshot certo", back.lines[0] == "abc")
    end
    let fwd: history.Snapshot? = history.redo(ref h, s3)
    check("redo devolve o que foi desfeito", fwd != null && length(h.redo) == 0 && length(h.undo) == 3)
    history.undo(ref h, s3)
    history.record(ref h, s1, "other", 5000)
    check("edicao nova limpa o redo", length(h.redo) == 0)
    let empty: history.History = history.new_history()
    check("undo vazio devolve null", history.undo(ref empty, s1) == null)

    let big: history.History = history.new_history()
    for i in range(250) do
        history.record(ref big, s1, "other", i)
    end
    check("limite de 200 entradas", length(big.undo) == 200)
end
```

- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: erro de compilação: módulo `src.history` não pôde ser carregado.

- [ ] **Passo 3: implementar**

```noxy
// src/history.nx — undo e redo por snapshot. Cada snapshot e uma copia por
// valor das linhas; copy-on-write faz isso custar uma copia rasa do array.
use src.document as doc

let MAX = 200
let GROUP_MS = 1000

struct Snapshot
    lines: string[]
    cursor: doc.Pos
end

struct History
    undo: Snapshot[]
    redo: Snapshot[]
    last_kind: string   // "typing", "delete" ou "other"
    last_time: int      // ms do ultimo record
end

func new_history() -> History
    return History([], [], "", 0)
end

// record guarda o estado ANTES de uma edicao. Digitacao ou apagamento
// consecutivos dentro de GROUP_MS nao empilham de novo: o snapshot anterior
// ja guarda o estado antes do burst. Toda edicao nova limpa o redo.
func record(h: ref History, snap: Snapshot, kind: string, now: int) -> void
    let grouped: bool = (kind == "typing" || kind == "delete") && kind == h.last_kind && now - h.last_time < GROUP_MS
    h.last_kind = kind
    h.last_time = now
    h.redo = []
    if grouped && length(h.undo) > 0 then
        return
    end
    append(ref h.undo, snap)
    if length(h.undo) > MAX then
        h.undo = slice(h.undo, 1, length(h.undo))
    end
end

// undo devolve o snapshot a restaurar e guarda current no redo; null se
// nao ha o que desfazer.
func undo(h: ref History, current: Snapshot) -> Snapshot?
    if length(h.undo) == 0 then
        return null
    end
    append(ref h.redo, current)
    h.last_kind = ""
    return pop(ref h.undo)
end

func redo(h: ref History, current: Snapshot) -> Snapshot?
    if length(h.redo) == 0 then
        return null
    end
    append(ref h.undo, current)
    h.last_kind = ""
    return pop(ref h.redo)
end
```

- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx`
Esperado: `37/37 passaram`.

- [ ] **Passo 5: commit**

```bash
git add src/history.nx tests/run.nx
git commit -m "feat(history): undo e redo por snapshot com agrupamento de digitacao"
```


### Tarefa 5: Editing, parte 1 — cursor, seleção, movimento e scroll

**Files:**
- Create: `src/editing.nx`
- Modify: `tests/run.nx`

**Interfaces:**
- Consumes: `doc.*`, `history.*`.
- Produces: `Editor(doc, cursor, anchor, top, goal_col, history)`; `new_editor(d)`, `has_sel(ed)`, `sel_range(ed) -> Range`, `snapshot(ed)`, `first_non_space(line)`, `ensure_visible(ref ed, rows)`, `scroll(ref ed, delta, rows)`, `place(ref ed, p, shift, rows)`, `move_left/right/up/down/home/end/doc_start/doc_end/word_left/word_right(ref ed, shift, rows)`, `page_up/page_down(ref ed, shift, rows)`, `select_all(ref ed)`, `select_word_at(ref ed, p, rows)`, `select_line(ref ed, n, rows)`, `click(ref ed, p, shift, rows)`, `drag(ref ed, p, rows)`. A Tarefa 6 acrescenta o resto ao mesmo arquivo.

- [ ] **Passo 1: o teste que falha**

Acrescente `use src.editing as editing` aos `use`, estas três funções antes de `report()` e `test_editing_moves()` acima de `report()`:

```noxy
func ed_of(text: string) -> editing.Editor
    return editing.new_editor(doc.from_text("t.nx", text))
end

func at(ed: editing.Editor, line: int, col: int) -> bool
    return ed.cursor.line == line && ed.cursor.col == col
end

func test_editing_moves() -> void
    print("editing: movimentos e selecao")
    let ed: editing.Editor = ed_of("abc\n    def\nghi")
    editing.move_right(ref ed, false, 10)
    editing.move_right(ref ed, false, 10)
    editing.move_right(ref ed, false, 10)
    editing.move_right(ref ed, false, 10)
    check("right no fim da linha vai para a proxima", at(ed, 1, 0))
    editing.move_left(ref ed, false, 10)
    check("left no inicio volta ao fim da anterior", at(ed, 0, 3))
    editing.move_down(ref ed, false, 10)
    editing.move_down(ref ed, false, 10)
    check("down mantem a coluna desejada", at(ed, 2, 3))
    editing.move_up(ref ed, false, 10)
    check("up volta com a meta", at(ed, 1, 3))
    editing.move_home(ref ed, false, 10)
    check("home vai ao primeiro nao-espaco", at(ed, 1, 4))
    editing.move_home(ref ed, false, 10)
    check("home de novo vai a coluna 0", at(ed, 1, 0))
    editing.move_end(ref ed, false, 10)
    check("end", at(ed, 1, 7))
    editing.move_doc_start(ref ed, false, 10)
    check("ctrl+home", at(ed, 0, 0))
    editing.move_doc_end(ref ed, false, 10)
    check("ctrl+end", at(ed, 2, 3))

    let w: editing.Editor = ed_of("let  x_1 = foo(bar)")
    editing.move_word_right(ref w, false, 10)
    check("ctrl+right salta a palavra", at(w, 0, 3))
    editing.move_word_right(ref w, false, 10)
    check("ctrl+right pula espacos e a proxima palavra", at(w, 0, 8))
    editing.move_word_right(ref w, false, 10)
    check("ctrl+right trata pontuacao como bloco", at(w, 0, 10))
    editing.move_word_left(ref w, false, 10)
    editing.move_word_left(ref w, false, 10)
    check("ctrl+left volta ao inicio da palavra", at(w, 0, 5))

    let s: editing.Editor = ed_of("abc\ndef")
    editing.move_right(ref s, true, 10)
    editing.move_right(ref s, true, 10)
    check("shift+right seleciona", editing.has_sel(s) && editing.copy(s) == "ab")
    editing.move_left(ref s, false, 10)
    check("left sem shift colapsa no inicio da selecao", !editing.has_sel(s) && at(s, 0, 0))
    editing.select_all(ref s)
    check("selecionar tudo", editing.copy(s) == "abc\ndef")
    editing.select_word_at(ref s, doc.Pos(1, 1), 10)
    check("duplo clique seleciona a palavra", editing.copy(s) == "def")
    editing.select_line(ref s, 0, 10)
    check("clique no gutter seleciona a linha com a quebra", editing.copy(s) == "abc\n")
    editing.click(ref s, doc.Pos(0, 1), false, 10)
    editing.drag(ref s, doc.Pos(1, 1), 10)
    check("arrastar seleciona do clique ate o mouse", editing.copy(s) == "bc\nd")
    check("copy sem selecao pega a linha inteira", editing.copy(ed_of("xy\nz")) == "xy\n")

    let v: editing.Editor = ed_of("0\n1\n2\n3\n4\n5\n6\n7\n8\n9")
    editing.move_doc_end(ref v, false, 3)
    check("ensure_visible desce a janela", v.top == 7)
    editing.move_doc_start(ref v, false, 3)
    check("ensure_visible sobe a janela", v.top == 0)
    editing.scroll(ref v, 5, 3)
    check("scroll move so a janela", v.top == 5 && at(v, 0, 0))
    editing.scroll(ref v, 100, 3)
    check("scroll nao passa do fim", v.top == 7)
    editing.page_down(ref v, false, 3)
    check("pagedown anda rows-1", at(v, 2, 0))
    editing.click(ref v, doc.Pos(99, 99), false, 3)
    check("clique alem do fim vai para o fim da ultima linha", at(v, 9, 1) && v.top == 7)
end
```

- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: erro de compilação: módulo `src.editing` não pôde ser carregado.

- [ ] **Passo 3: implementar a primeira metade**

`src/editing.nx` termina, por enquanto, em `drag`. As funções são declaradas antes de quem as chama; mantenha a ordem.

```noxy
// src/editing.nx — o editor de uma aba: cursor, ancora da selecao, scroll e
// as operacoes de edicao sobre um Document, com History. Toda operacao que
// muda o texto grava um snapshot antes; toda operacao que move o cursor
// chama ensure_visible para ele nao sair da tela. rows e o numero de linhas
// visiveis, informado pelo cliente a cada evento. As funcoes sao declaradas
// antes de quem as chama.
use strings select substring, codes, starts_with
use src.document as doc
use src.history as history

let TAB = "    "

struct Editor
    doc: doc.Document
    cursor: doc.Pos
    anchor: doc.Pos     // outra ponta da selecao; igual ao cursor sem selecao
    top: int            // primeira linha visivel
    goal_col: int       // coluna desejada ao subir e descer; -1 sem meta
    history: history.History
end

func new_editor(d: doc.Document) -> Editor
    return Editor(d, doc.Pos(0, 0), doc.Pos(0, 0), 0, -1, history.new_history())
end

func has_sel(ed: Editor) -> bool
    return !doc.same(ed.cursor, ed.anchor)
end

func sel_range(ed: Editor) -> doc.Range
    return doc.ordered(ed.cursor, ed.anchor)
end

func snapshot(ed: Editor) -> history.Snapshot
    return history.Snapshot(ed.doc.lines, ed.cursor)
end

func max0(v: int) -> int
    if v < 0 then
        return 0
    end
    return v
end

func first_non_space(line: string) -> int
    let cs: int[] = codes(line)
    let i: int = 0
    while i < length(cs) && (cs[i] == 32 || cs[i] == 9) do
        i = i + 1
    end
    return i
end

func is_word(c: int) -> bool
    return (c >= 48 && c <= 57) || (c >= 65 && c <= 90) || (c >= 97 && c <= 122) || c == 95 || c > 127
end

// char_class: 0 espaco, 1 palavra, 2 pontuacao — para saltar por palavra.
func char_class(c: int) -> int
    if c == 32 || c == 9 then
        return 0
    end
    if is_word(c) then
        return 1
    end
    return 2
end

// word_right: a proxima fronteira de palavra a direita de col; -1 no fim.
func word_right(line: string, col: int) -> int
    let cs: int[] = codes(line)
    let n: int = length(cs)
    if col >= n then
        return -1
    end
    let i: int = col
    while i < n && char_class(cs[i]) == 0 do
        i = i + 1
    end
    if i < n then
        let k: int = char_class(cs[i])
        while i < n && char_class(cs[i]) == k do
            i = i + 1
        end
    end
    return i
end

func word_left(line: string, col: int) -> int
    let cs: int[] = codes(line)
    if col <= 0 then
        return -1
    end
    let i: int = col
    while i > 0 && char_class(cs[i - 1]) == 0 do
        i = i - 1
    end
    if i > 0 then
        let k: int = char_class(cs[i - 1])
        while i > 0 && char_class(cs[i - 1]) == k do
            i = i - 1
        end
    end
    return i
end

func ensure_visible(ed: ref Editor, rows: int) -> void
    let r: int = rows
    if r < 1 then
        r = 1
    end
    if ed.cursor.line < ed.top then
        ed.top = ed.cursor.line
    elif ed.cursor.line >= ed.top + r then
        ed.top = ed.cursor.line - r + 1
    end
    let max_top: int = max0(length(ed.doc.lines) - r)
    if ed.top > max_top then
        ed.top = max_top
    end
    if ed.top < 0 then
        ed.top = 0
    end
end

// scroll move so a janela, nunca o cursor.
func scroll(ed: ref Editor, delta: int, rows: int) -> void
    let max_top: int = max0(length(ed.doc.lines) - rows)
    let t: int = ed.top + delta
    if t < 0 then
        t = 0
    end
    if t > max_top then
        t = max_top
    end
    ed.top = t
end

// place poe o cursor em p (clampado); sem shift a ancora acompanha.
func place(ed: ref Editor, p: doc.Pos, shift: bool, rows: int) -> void
    ed.cursor = doc.clamp(ed.doc, p)
    if !shift then
        ed.anchor = ed.cursor
    end
    ensure_visible(ed, rows)
end

func move_left(ed: ref Editor, shift: bool, rows: int) -> void
    ed.goal_col = -1
    if !shift && has_sel(*ed) then
        place(ed, sel_range(*ed).start, false, rows)
        return
    end
    let p: doc.Pos = ed.cursor
    if p.col > 0 then
        place(ed, doc.Pos(p.line, p.col - 1), shift, rows)
    elif p.line > 0 then
        place(ed, doc.Pos(p.line - 1, doc.line_len(ed.doc, p.line - 1)), shift, rows)
    end
end

func move_right(ed: ref Editor, shift: bool, rows: int) -> void
    ed.goal_col = -1
    if !shift && has_sel(*ed) then
        place(ed, sel_range(*ed).stop, false, rows)
        return
    end
    let p: doc.Pos = ed.cursor
    if p.col < doc.line_len(ed.doc, p.line) then
        place(ed, doc.Pos(p.line, p.col + 1), shift, rows)
    elif p.line + 1 < length(ed.doc.lines) then
        place(ed, doc.Pos(p.line + 1, 0), shift, rows)
    end
end

// move_vertical anda delta linhas mantendo a coluna desejada (goal_col).
func move_vertical(ed: ref Editor, delta: int, shift: bool, rows: int) -> void
    if ed.goal_col < 0 then
        ed.goal_col = ed.cursor.col
    end
    let goal: int = ed.goal_col
    let line: int = ed.cursor.line + delta
    if line < 0 then
        line = 0
    end
    let last: int = length(ed.doc.lines) - 1
    if line > last then
        line = last
    end
    place(ed, doc.Pos(line, goal), shift, rows)
    ed.goal_col = goal
end

func move_up(ed: ref Editor, shift: bool, rows: int) -> void
    move_vertical(ed, -1, shift, rows)
end

func move_down(ed: ref Editor, shift: bool, rows: int) -> void
    move_vertical(ed, 1, shift, rows)
end

func page_up(ed: ref Editor, shift: bool, rows: int) -> void
    move_vertical(ed, -(rows - 1), shift, rows)
end

func page_down(ed: ref Editor, shift: bool, rows: int) -> void
    move_vertical(ed, rows - 1, shift, rows)
end

// move_home alterna entre o primeiro nao-espaco e a coluna 0.
func move_home(ed: ref Editor, shift: bool, rows: int) -> void
    ed.goal_col = -1
    let fns: int = first_non_space(ed.doc.lines[ed.cursor.line])
    let col: int = fns
    if ed.cursor.col == fns then
        col = 0
    end
    place(ed, doc.Pos(ed.cursor.line, col), shift, rows)
end

func move_end(ed: ref Editor, shift: bool, rows: int) -> void
    ed.goal_col = -1
    place(ed, doc.Pos(ed.cursor.line, doc.line_len(ed.doc, ed.cursor.line)), shift, rows)
end

func move_doc_start(ed: ref Editor, shift: bool, rows: int) -> void
    ed.goal_col = -1
    place(ed, doc.Pos(0, 0), shift, rows)
end

func move_doc_end(ed: ref Editor, shift: bool, rows: int) -> void
    ed.goal_col = -1
    let last: int = length(ed.doc.lines) - 1
    place(ed, doc.Pos(last, doc.line_len(ed.doc, last)), shift, rows)
end

func move_word_right(ed: ref Editor, shift: bool, rows: int) -> void
    ed.goal_col = -1
    let p: doc.Pos = ed.cursor
    let c: int = word_right(ed.doc.lines[p.line], p.col)
    if c >= 0 then
        place(ed, doc.Pos(p.line, c), shift, rows)
    elif p.line + 1 < length(ed.doc.lines) then
        place(ed, doc.Pos(p.line + 1, 0), shift, rows)
    end
end

func move_word_left(ed: ref Editor, shift: bool, rows: int) -> void
    ed.goal_col = -1
    let p: doc.Pos = ed.cursor
    let c: int = word_left(ed.doc.lines[p.line], p.col)
    if c >= 0 then
        place(ed, doc.Pos(p.line, c), shift, rows)
    elif p.line > 0 then
        place(ed, doc.Pos(p.line - 1, doc.line_len(ed.doc, p.line - 1)), shift, rows)
    end
end

func select_all(ed: ref Editor) -> void
    ed.goal_col = -1
    let last: int = length(ed.doc.lines) - 1
    ed.anchor = doc.Pos(0, 0)
    ed.cursor = doc.Pos(last, doc.line_len(ed.doc, last))
end

// select_word_at seleciona a palavra sob p (duplo clique); sem palavra,
// um caractere.
func select_word_at(ed: ref Editor, p: doc.Pos, rows: int) -> void
    let q: doc.Pos = doc.clamp(ed.doc, p)
    let cs: int[] = codes(ed.doc.lines[q.line])
    let a: int = q.col
    let b: int = q.col
    while a > 0 && is_word(cs[a - 1]) do
        a = a - 1
    end
    while b < length(cs) && is_word(cs[b]) do
        b = b + 1
    end
    if a == b && b < length(cs) then
        b = b + 1
    end
    ed.goal_col = -1
    ed.anchor = doc.Pos(q.line, a)
    ed.cursor = doc.Pos(q.line, b)
    ensure_visible(ed, rows)
end

// select_line seleciona a linha n inteira, com a quebra (clique no gutter).
func select_line(ed: ref Editor, n: int, rows: int) -> void
    let last: int = length(ed.doc.lines) - 1
    let line: int = n
    if line < 0 then
        line = 0
    end
    if line > last then
        line = last
    end
    ed.goal_col = -1
    ed.anchor = doc.Pos(line, 0)
    if line < last then
        ed.cursor = doc.Pos(line + 1, 0)
    else
        ed.cursor = doc.Pos(line, doc.line_len(ed.doc, line))
    end
    ensure_visible(ed, rows)
end

func click(ed: ref Editor, p: doc.Pos, shift: bool, rows: int) -> void
    ed.goal_col = -1
    place(ed, p, shift, rows)
end

// drag move so o cursor; a ancora fica onde o clique comecou.
func drag(ed: ref Editor, p: doc.Pos, rows: int) -> void
    ed.goal_col = -1
    ed.cursor = doc.clamp(ed.doc, p)
    ensure_visible(ed, rows)
end
```

- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx`
Esperado: `63/63 passaram`.

- [ ] **Passo 5: commit**

```bash
git add src/editing.nx tests/run.nx
git commit -m "feat(editing): cursor, selecao, movimento por caractere, palavra e pagina, scroll"
```


### Tarefa 6: Editing, parte 2 — texto, undo e clipboard

**Files:**
- Modify: `src/editing.nx` (acrescentar ao fim)
- Modify: `tests/run.nx`

**Interfaces:**
- Consumes: tudo da Tarefa 5.
- Produces: `insert_text(ref ed, text, rows, now)`, `paste(ref ed, text, rows, now)`, `newline(ref ed, rows, now)`, `backspace(ref ed, rows, now)`, `delete_forward(ref ed, rows, now)`, `tab(ref ed, shift, rows, now)`, `toggle_comment(ref ed, rows, now)`, `copy(ed) -> string`, `cut(ref ed, rows, now) -> string`, `undo(ref ed, rows)`, `redo(ref ed, rows)`. `now` é `time_now()` em ms; os testes passam constantes.

- [ ] **Passo 1: o teste que falha**

Função antes de `report()`, chamada `test_editing_text()` logo depois de `test_editing_moves()`:

```noxy
func test_editing_text() -> void
    print("editing: texto, undo e clipboard")
    let t: editing.Editor = ed_of("")
    editing.insert_text(ref t, "a", 10, 1000)
    editing.insert_text(ref t, "b", 10, 1100)
    check("digitar", t.doc.lines[0] == "ab" && at(t, 0, 2) && t.doc.dirty)
    editing.newline(ref t, 10, 1200)
    editing.insert_text(ref t, "c", 10, 1300)
    check("enter", length(t.doc.lines) == 2 && t.doc.lines[1] == "c")
    editing.undo(ref t, 10)
    check("undo desfaz a ultima digitacao", t.doc.lines[1] == "" && at(t, 1, 0))
    editing.undo(ref t, 10)
    check("undo desfaz o enter", length(t.doc.lines) == 1 && t.doc.lines[0] == "ab")
    editing.undo(ref t, 10)
    check("undo desfaz o burst de digitacao inteiro", t.doc.lines[0] == "")
    editing.redo(ref t, 10)
    check("redo refaz o burst", t.doc.lines[0] == "ab" && at(t, 0, 2))
    editing.redo(ref t, 10)
    editing.redo(ref t, 10)
    check("redo ate o fim", length(t.doc.lines) == 2 && t.doc.lines[1] == "c")

    let n: editing.Editor = ed_of("    if x then")
    editing.move_end(ref n, false, 10)
    editing.newline(ref n, 10, 1)
    check("enter copia a indentacao", n.doc.lines[1] == "    " && at(n, 1, 4))
    let n2: editing.Editor = ed_of("    x")
    editing.click(ref n2, doc.Pos(0, 2), false, 10)
    editing.newline(ref n2, 10, 1)
    check("enter dentro da indentacao copia so ate o cursor", n2.doc.lines[1] == "    x" && at(n2, 1, 2))

    let b: editing.Editor = ed_of("ab\ncd")
    editing.click(ref b, doc.Pos(1, 0), false, 10)
    editing.backspace(ref b, 10, 1)
    check("backspace no inicio junta com a anterior", b.doc.lines[0] == "abcd" && at(b, 0, 2))
    editing.backspace(ref b, 10, 2)
    check("backspace apaga um caractere", b.doc.lines[0] == "acd" && at(b, 0, 1))
    editing.delete_forward(ref b, 10, 3)
    check("delete apaga a frente", b.doc.lines[0] == "ad")
    editing.move_end(ref b, false, 10)
    editing.delete_forward(ref b, 10, 4)
    check("delete no fim da ultima linha nao faz nada", b.doc.lines[0] == "ad")
    let b2: editing.Editor = ed_of("ab\ncd")
    editing.move_end(ref b2, false, 10)
    editing.delete_forward(ref b2, 10, 1)
    check("delete no fim junta com a proxima", b2.doc.lines[0] == "abcd" && length(b2.doc.lines) == 1)
    editing.select_all(ref b2)
    editing.backspace(ref b2, 10, 2)
    check("backspace com selecao apaga a selecao", b2.doc.lines[0] == "" && length(b2.doc.lines) == 1)

    let tb: editing.Editor = ed_of("a\nb\nc")
    editing.tab(ref tb, false, 10, 1)
    check("tab insere quatro espacos", tb.doc.lines[0] == "    a" && at(tb, 0, 4))
    editing.click(ref tb, doc.Pos(1, 0), false, 10)
    editing.drag(ref tb, doc.Pos(2, 0), 10)
    editing.tab(ref tb, false, 10, 2)
    check("tab com selecao multilinha indenta as linhas tocadas, nao a que termina na coluna 0", tb.doc.lines[1] == "    b" && tb.doc.lines[2] == "c")
    check("tab em bloco mantem a selecao", editing.has_sel(tb) && tb.anchor.col == 4 && at(tb, 2, 0))
    editing.tab(ref tb, true, 10, 3)
    check("shift+tab desindenta", tb.doc.lines[1] == "b" && tb.anchor.col == 0)
    editing.click(ref tb, doc.Pos(0, 5), false, 10)
    editing.tab(ref tb, true, 10, 4)
    check("shift+tab sem selecao desindenta a linha do cursor", tb.doc.lines[0] == "a" && at(tb, 0, 1))

    let c: editing.Editor = ed_of("  x\n\n    y")
    editing.select_all(ref c)
    editing.toggle_comment(ref c, 10, 1)
    check("ctrl+/ comenta na menor indentacao e pula linhas vazias", c.doc.lines[0] == "  // x" && c.doc.lines[1] == "" && c.doc.lines[2] == "  //   y")
    editing.toggle_comment(ref c, 10, 2)
    check("ctrl+/ de novo descomenta", c.doc.lines[0] == "  x" && c.doc.lines[2] == "    y")

    let k: editing.Editor = ed_of("ab\ncd\nef")
    editing.click(ref k, doc.Pos(1, 1), false, 10)
    let cut1: string = editing.cut(ref k, 10, 1)
    check("cut sem selecao tira a linha inteira", cut1 == "cd\n" && length(k.doc.lines) == 2 && k.doc.lines[1] == "ef" && at(k, 1, 0))
    editing.paste(ref k, "X\nY", 10, 2)
    check("paste multilinha", k.doc.lines[1] == "X" && k.doc.lines[2] == "Yef" && at(k, 2, 1))
    editing.click(ref k, doc.Pos(0, 0), false, 10)
    editing.drag(ref k, doc.Pos(0, 1), 10)
    let cut2: string = editing.cut(ref k, 10, 3)
    check("cut com selecao", cut2 == "a" && k.doc.lines[0] == "b")
    let last: editing.Editor = ed_of("so")
    editing.cut(ref last, 10, 1)
    check("cut da unica linha deixa uma linha vazia", length(last.doc.lines) == 1 && last.doc.lines[0] == "")

end
```

- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: erro de compilação em `tests/run.nx`: `'editing' has no member 'insert_text'` (ou o primeiro membro ausente que o compilador encontrar).

- [ ] **Passo 3: implementar a segunda metade**

Acrescente ao **fim** de `src/editing.nx`:

```noxy
// delete_selection e interna: nao grava snapshot.
func delete_selection(ed: ref Editor) -> void
    if has_sel(*ed) then
        let r: doc.Range = sel_range(*ed)
        doc.delete_range(ref ed.doc, r.start, r.stop)
        ed.cursor = r.start
        ed.anchor = r.start
    end
end

func insert_with_kind(ed: ref Editor, text: string, kind: string, rows: int, now: int) -> void
    history.record(ref ed.history, snapshot(*ed), kind, now)
    delete_selection(ed)
    let p: doc.Pos = doc.insert(ref ed.doc, ed.cursor, text)
    ed.cursor = p
    ed.anchor = p
    ed.goal_col = -1
    ensure_visible(ed, rows)
end

// insert_text e a digitacao: um caractere agrupa no undo como "typing".
func insert_text(ed: ref Editor, text: string, rows: int, now: int) -> void
    let kind: string = "other"
    if length(text) == 1 && text != "\n" then
        kind = "typing"
    end
    insert_with_kind(ed, text, kind, rows, now)
end

func paste(ed: ref Editor, text: string, rows: int, now: int) -> void
    insert_with_kind(ed, text, "other", rows, now)
end

// newline copia a indentacao da linha atual; com o cursor dentro da
// indentacao, copia so ate o cursor para nao duplicar.
func newline(ed: ref Editor, rows: int, now: int) -> void
    history.record(ref ed.history, snapshot(*ed), "other", now)
    delete_selection(ed)
    let line: string = ed.doc.lines[ed.cursor.line]
    let fns: int = first_non_space(line)
    if fns > ed.cursor.col then
        fns = ed.cursor.col
    end
    let p: doc.Pos = doc.insert(ref ed.doc, ed.cursor, "\n" + substring(line, 0, fns))
    ed.cursor = p
    ed.anchor = p
    ed.goal_col = -1
    ensure_visible(ed, rows)
end

func backspace(ed: ref Editor, rows: int, now: int) -> void
    if has_sel(*ed) then
        history.record(ref ed.history, snapshot(*ed), "other", now)
        delete_selection(ed)
    elif ed.cursor.col > 0 then
        history.record(ref ed.history, snapshot(*ed), "delete", now)
        let p: doc.Pos = doc.Pos(ed.cursor.line, ed.cursor.col - 1)
        doc.delete_range(ref ed.doc, p, ed.cursor)
        ed.cursor = p
        ed.anchor = p
    elif ed.cursor.line > 0 then
        history.record(ref ed.history, snapshot(*ed), "other", now)
        let p: doc.Pos = doc.Pos(ed.cursor.line - 1, doc.line_len(ed.doc, ed.cursor.line - 1))
        doc.delete_range(ref ed.doc, p, ed.cursor)
        ed.cursor = p
        ed.anchor = p
    end
    ed.goal_col = -1
    ensure_visible(ed, rows)
end

func delete_forward(ed: ref Editor, rows: int, now: int) -> void
    if has_sel(*ed) then
        history.record(ref ed.history, snapshot(*ed), "other", now)
        delete_selection(ed)
    elif ed.cursor.col < doc.line_len(ed.doc, ed.cursor.line) then
        history.record(ref ed.history, snapshot(*ed), "delete", now)
        doc.delete_range(ref ed.doc, ed.cursor, doc.Pos(ed.cursor.line, ed.cursor.col + 1))
    elif ed.cursor.line + 1 < length(ed.doc.lines) then
        history.record(ref ed.history, snapshot(*ed), "other", now)
        doc.delete_range(ref ed.doc, ed.cursor, doc.Pos(ed.cursor.line + 1, 0))
    end
    ed.goal_col = -1
    ensure_visible(ed, rows)
end

// touched_lines: [primeira, ultima] linha que a selecao toca. Uma selecao
// que termina na coluna 0 de uma linha nao toca essa linha (VS Code).
func touched_lines(ed: Editor) -> int[]
    let r: doc.Range = sel_range(ed)
    let last: int = r.stop.line
    if last > r.start.line && r.stop.col == 0 then
        last = last - 1
    end
    return [r.start.line, last]
end

// shift_col move cursor e ancora que estao na linha i em delta colunas.
func shift_col(ed: ref Editor, i: int, delta: int) -> void
    if ed.cursor.line == i then
        ed.cursor.col = max0(ed.cursor.col + delta)
    end
    if ed.anchor.line == i then
        ed.anchor.col = max0(ed.anchor.col + delta)
    end
end

func indent_lines(ed: ref Editor, first: int, last: int, shift: bool) -> void
    for i in range(first, last + 1) do
        let line: string = ed.doc.lines[i]
        if shift then
            let cs: int[] = codes(line)
            let n: int = 0
            while n < 4 && n < length(cs) && cs[n] == 32 do
                n = n + 1
            end
            ed.doc.lines[i] = substring(line, n, length(line))
            shift_col(ed, i, -n)
        else
            ed.doc.lines[i] = TAB + line
            shift_col(ed, i, 4)
        end
    end
    ed.doc.dirty = true
end

// tab: sem selecao multilinha insere quatro espacos; com ela indenta o
// bloco. Shift+Tab desindenta as linhas tocadas.
func tab(ed: ref Editor, shift: bool, rows: int, now: int) -> void
    let r: doc.Range = sel_range(*ed)
    let multi: bool = has_sel(*ed) && r.start.line != r.stop.line
    history.record(ref ed.history, snapshot(*ed), "other", now)
    if !shift && !multi then
        delete_selection(ed)
        let p: doc.Pos = doc.insert(ref ed.doc, ed.cursor, TAB)
        ed.cursor = p
        ed.anchor = p
    else
        let tl: int[] = touched_lines(*ed)
        indent_lines(ed, tl[0], tl[1], shift)
    end
    ed.goal_col = -1
    ensure_visible(ed, rows)
end

// toggle_comment: se toda linha nao vazia tocada comeca com //, remove
// "// " (ou "//"); senao insere "// " na menor indentacao.
func toggle_comment(ed: ref Editor, rows: int, now: int) -> void
    let tl: int[] = touched_lines(*ed)
    let all_commented: bool = true
    let min_indent: int = -1
    let any_text: bool = false
    for i in range(tl[0], tl[1] + 1) do
        let line: string = ed.doc.lines[i]
        let fns: int = first_non_space(line)
        if fns < length(line) then
            any_text = true
            if !starts_with(substring(line, fns, length(line)), "//") then
                all_commented = false
            end
            if min_indent < 0 || fns < min_indent then
                min_indent = fns
            end
        end
    end
    if !any_text then
        return
    end
    history.record(ref ed.history, snapshot(*ed), "other", now)
    for i in range(tl[0], tl[1] + 1) do
        let line: string = ed.doc.lines[i]
        let fns: int = first_non_space(line)
        if fns < length(line) then
            if all_commented then
                let rest: string = substring(line, fns + 2, length(line))
                let removed: int = 2
                if starts_with(rest, " ") then
                    rest = substring(rest, 1, length(rest))
                    removed = 3
                end
                ed.doc.lines[i] = substring(line, 0, fns) + rest
                shift_col(ed, i, -removed)
            else
                ed.doc.lines[i] = substring(line, 0, min_indent) + "// " + substring(line, min_indent, length(line))
                shift_col(ed, i, 3)
            end
        end
    end
    ed.doc.dirty = true
    ed.cursor = doc.clamp(ed.doc, ed.cursor)
    ed.anchor = doc.clamp(ed.doc, ed.anchor)
    ensure_visible(ed, rows)
end

// copy sem selecao devolve a linha inteira com a quebra (VS Code).
func copy(ed: Editor) -> string
    if has_sel(ed) then
        let r: doc.Range = sel_range(ed)
        return doc.text_range(ed.doc, r.start, r.stop)
    end
    return ed.doc.lines[ed.cursor.line] + "\n"
end

func cut(ed: ref Editor, rows: int, now: int) -> string
    let text: string = copy(*ed)
    history.record(ref ed.history, snapshot(*ed), "other", now)
    if has_sel(*ed) then
        delete_selection(ed)
    else
        let line: int = ed.cursor.line
        let count: int = length(ed.doc.lines)
        if line + 1 < count then
            doc.delete_range(ref ed.doc, doc.Pos(line, 0), doc.Pos(line + 1, 0))
        elif line > 0 then
            doc.delete_range(ref ed.doc, doc.Pos(line - 1, doc.line_len(ed.doc, line - 1)), doc.Pos(line, doc.line_len(ed.doc, line)))
        else
            doc.delete_range(ref ed.doc, doc.Pos(0, 0), doc.Pos(0, doc.line_len(ed.doc, 0)))
        end
        ed.cursor = doc.clamp(ed.doc, doc.Pos(line, 0))
        ed.anchor = ed.cursor
    end
    ed.goal_col = -1
    ensure_visible(ed, rows)
    return text
end

func restore(ed: ref Editor, s: history.Snapshot, rows: int) -> void
    ed.doc.lines = s.lines
    ed.doc.dirty = true
    ed.cursor = doc.clamp(ed.doc, s.cursor)
    ed.anchor = ed.cursor
    ed.goal_col = -1
    ensure_visible(ed, rows)
end

func undo(ed: ref Editor, rows: int) -> void
    let s: history.Snapshot? = history.undo(ref ed.history, snapshot(*ed))
    if s != null then
        restore(ed, s, rows)
    end
end

func redo(ed: ref Editor, rows: int) -> void
    let s: history.Snapshot? = history.redo(ref ed.history, snapshot(*ed))
    if s != null then
        restore(ed, s, rows)
    end
end
```

- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx`
Esperado: `89/89 passaram`.

- [ ] **Passo 5: commit**

```bash
git add src/editing.nx tests/run.nx
git commit -m "feat(editing): digitar, enter com indentacao, apagar, tab, comentar, clipboard, undo e redo"
```


### Tarefa 7: Runner — rodar um arquivo numa task

**Files:**
- Create: `src/runner.nx`
- Modify: `tests/run.nx`

**Interfaces:**
- Consumes: só `sys` e `strings`.
- Produces: `RunState(running, task, text, version, cmd)`; `new_run()`, `command(root, rel) -> string`, `start(ref r, root, rel) -> string` ("" ou recusa), `poll(ref r)`. Também os helpers de teste `write_file`, `read_file`, `tmp_root()` (cria `tests/tmp/run` com `b.nx`, `a.txt`, `.hidden`, `sub/c.nx`, `hello.nx`) usados pelas Tarefas 8 a 10.

- [ ] **Passo 1: o teste que falha**

Acrescente `use src.runner as runner` e `use strings` aos `use` (a suíte usa `strings.contains` qualificado, para não sombrear o `contains` de arrays), estas quatro funções antes de `report()` e `test_runner()` acima de `report()`:

```noxy
func write_file(path: string, text: string) -> void
    let f: io.File = io.open(path, "w")
    io.write(f, text)
    io.close(f)
end

func read_file(path: string) -> string
    let f: io.File = io.open(path, "r")
    let r: io.IOResult = io.read(f)
    io.close(f)
    return r.data
end

func tmp_root() -> string
    let root: string = sys.getcwd() + "/tests/tmp/run"
    io.mkdir(root + "/sub")
    io.remove(root + "/bin.nx")    // sobra do teste de UTF-8 da rodada anterior
    write_file(root + "/b.nx", "let b = 1\n")
    write_file(root + "/a.txt", "texto\n")
    write_file(root + "/.hidden", "")
    write_file(root + "/sub/c.nx", "print(\"c\")\n")
    write_file(root + "/hello.nx", "use sys\nprint(\"oi\")\nsys.exit(3)\n")
    return root
end

func test_runner() -> void
    print("runner")
    let root: string = tmp_root()
    let r: runner.RunState = runner.new_run()
    check("comando com cd, aspas e /dev/null", runner.command("/x y", "a'b.nx") == "cd '/x y' && noxy 'a'\\''b.nx' < /dev/null 2>&1")
    check("start", runner.start(ref r, root, "hello.nx") == "" && r.running && r.version == 1)
    check("start durante execucao recusa", runner.start(ref r, root, "hello.nx") == "ja esta rodando")
    let waited: int = 0
    while r.running && waited < 100 do
        sys.sleep(50)
        runner.poll(ref r)
        waited = waited + 1
    end
    check("poll recolhe a saida e o codigo", !r.running && r.text == "$ noxy hello.nx\noi\n[saiu com 3]" && r.version == 2)
    let bad: runner.RunState = runner.new_run()
    runner.start(ref bad, root, "nao.nx")
    waited = 0
    while bad.running && waited < 100 do
        sys.sleep(50)
        runner.poll(ref bad)
        waited = waited + 1
    end
    check("arquivo inexistente mostra o erro do noxy", !bad.running && strings.contains(bad.text, "Error reading file") && strings.contains(bad.text, "[saiu com 1]"))
end
```

- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: erro de compilação: módulo `src.runner` não pôde ser carregado.

- [ ] **Passo 3: implementar**

```noxy
// src/runner.nx — roda um arquivo .nx numa task e recolhe a saida quando
// termina. Nao conhece a sessao: recebe a raiz e o caminho relativo. O
// programa roda com a raiz como cwd (noxy.mod e caminhos relativos
// funcionam como no terminal) e com a entrada em /dev/null, para input()
// devolver "" em vez de travar. Nao ha como interromper um programa que
// nao termina (docs/ACHADOS.md).
use sys
use strings select replace, ends_with

struct RunState
    running: bool
    task: any          // handle de spawn_task; null parado
    text: string       // o conteudo do painel de saida
    version: int       // muda a cada alteracao de text ou running
    cmd: string
end

func new_run() -> RunState
    return RunState(false, null, "", 0, "")
end

func shell_quote(s: string) -> string
    return "'" + replace(s, "'", "'\\''") + "'"
end

func command(root: string, rel: string) -> string
    if sys.os() == "windows" then
        return "cd /d \"" + root + "\" && noxy \"" + rel + "\" < NUL 2>&1"
    end
    return "cd " + shell_quote(root) + " && noxy " + shell_quote(rel) + " < /dev/null 2>&1"
end

// exec_cmd e a funcao da task: bloqueia ate o programa terminar.
func exec_cmd(cmd: string) -> sys.SysResult
    return sys.exec_output(cmd)
end

// start dispara a execucao; devolve "" ou a mensagem de recusa.
func start(r: ref RunState, root: string, rel: string) -> string
    if r.running then
        return "ja esta rodando"
    end
    r.cmd = command(root, rel)
    r.text = "$ noxy " + rel + "\n"
    r.running = true
    r.version = r.version + 1
    r.task = spawn_task(exec_cmd, r.cmd)
    return ""
end

// poll recolhe o resultado se a task terminou; chamado a cada evento.
func poll(r: ref RunState) -> void
    if !r.running then
        return
    end
    let env: any = task_await(r.task, 0)
    if env["status"] == "timeout" then
        return
    end
    if env["status"] == "ok" then
        let res: sys.SysResult = env["value"]
        r.text = r.text + res.output
        if length(res.output) > 0 && !ends_with(res.output, "\n") then
            r.text = r.text + "\n"
        end
        if res.output == "" && res.error != "" then
            r.text = r.text + res.error + "\n"
        end
        r.text = r.text + "[saiu com " + to_str(res.exit_code) + "]"
    else
        let err: any = env["error"]
        r.text = r.text + "falha ao executar: " + to_str(err["message"])
    end
    r.running = false
    r.task = null
    r.version = r.version + 1
end
```

- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx`
Esperado: `94/94 passaram`. O teste roda `noxy` de verdade sobre `tests/tmp/run/hello.nx`, então leva um ou dois segundos a mais.

- [ ] **Passo 5: commit**

```bash
git add src/runner.nx tests/run.nx
git commit -m "feat(runner): roda o arquivo numa task com cd na raiz e recolhe saida e codigo"
```


### Tarefa 8: Session — abas, árvore, arquivos e modal

**Files:**
- Create: `src/session.nx`
- Modify: `tests/run.nx`

**Interfaces:**
- Consumes: `doc.*`, `editing.new_editor`, `runner.RunState`/`new_run`.
- Produces: `Tab(editor)`, `Node(path, name, is_dir, depth, expanded)`, `Button(label, id)`, `Modal(text, buttons, pending)`, `Session(root, tabs, active, tree, tree_version, rows, run, message, modal, clipboard, quitting, bye, last_event)`; `no_modal()`, `new_session(root)`, `basename`, `dirname`, `relative(root, path)`, `sort_nodes`, `list_children(path, depth)`, `load(ref s) -> bool`, `find_node`, `toggle_dir(ref s, path)`, `find_tab`, `open_file(ref s, path)`, `save_tab(ref s, i) -> bool`, `save(ref s)`, `save_all(ref s) -> bool`, `has_dirty(s)`, `remove_tab`, `close_tab(ref s, i)`, `request_quit(ref s)`, `answer_modal(ref s, id)`.

- [ ] **Passo 1: o teste que falha**

Acrescente `use src.session as session` aos `use`, a função antes de `report()` e `test_session()` acima de `report()` (antes de `test_runner()` ou depois, tanto faz):

```noxy
func test_session() -> void
    print("session")
    let root: string = tmp_root()
    let s: session.Session = session.new_session(root)
    let missing: session.Session = session.new_session(root + "/nao")
    check("load de raiz inexistente falha", !session.load(ref missing))
    check("load", session.load(ref s) && s.tree_version == 2)
    let names: string = ""
    for n in s.tree do
        names = names + n.name + " "
    end
    check("arvore: pastas antes, ordenada, sem ocultos", names == "sub a.txt b.nx hello.nx ")
    session.toggle_dir(ref s, root + "/sub")
    check("expandir lista os filhos abaixo", length(s.tree) == 5 && s.tree[1].name == "c.nx" && s.tree[1].depth == 1 && s.tree[0].expanded && s.tree_version == 3)
    session.toggle_dir(ref s, root + "/sub")
    check("recolher remove os descendentes", length(s.tree) == 4 && !s.tree[0].expanded)
    session.toggle_dir(ref s, root + "/b.nx")
    check("toggle em arquivo nao faz nada", length(s.tree) == 4 && s.tree_version == 4)

    session.open_file(ref s, root + "/b.nx")
    check("abrir cria a aba e ativa", length(s.tabs) == 1 && s.active == 0 && s.tabs[0].editor.doc.lines[0] == "let b = 1")
    session.open_file(ref s, root + "/sub/c.nx")
    session.open_file(ref s, root + "/b.nx")
    check("abrir de novo so ativa", length(s.tabs) == 2 && s.active == 0)
    session.open_file(ref s, root + "/nao.nx")
    check("abrir inexistente vira mensagem", length(s.tabs) == 2 && s.message != "")

    editing.insert_text(ref s.tabs[0].editor, "x", 10, 1)
    check("editar suja a aba", s.tabs[0].editor.doc.dirty && session.has_dirty(s))
    session.save(ref s)
    check("salvar grava e limpa dirty", read_file(root + "/b.nx") == "xlet b = 1\n" && !s.tabs[0].editor.doc.dirty && s.message == "salvo b.nx")

    editing.insert_text(ref s.tabs[0].editor, "y", 10, 2)
    session.close_tab(ref s, 0)
    check("fechar aba suja abre modal", s.modal.text != "" && s.modal.pending == "close_tab:0" && length(s.tabs) == 2)
    session.answer_modal(ref s, "cancel")
    check("cancelar fecha o modal e mantem a aba", s.modal.text == "" && length(s.tabs) == 2)
    session.close_tab(ref s, 0)
    session.answer_modal(ref s, "discard")
    check("nao salvar fecha a aba sem gravar", length(s.tabs) == 1 && read_file(root + "/b.nx") == "xlet b = 1\n" && s.active == 0)
    session.close_tab(ref s, 0)
    check("fechar aba limpa remove direto", length(s.tabs) == 0 && s.active == -1)

    session.open_file(ref s, root + "/sub/c.nx")
    editing.insert_text(ref s.tabs[0].editor, "z", 10, 3)
    session.request_quit(ref s)
    check("sair com aba suja abre modal", s.modal.pending == "quit" && !s.quitting)
    session.answer_modal(ref s, "save")
    check("salvar tudo e sair", s.quitting && read_file(root + "/sub/c.nx") == "zprint(\"c\")\n")
    let bf: io.File = io.open(root + "/bin.nx", "w")
    io.write_bytes(bf, hex_decode("fffe00"))
    io.close(bf)
    let before: int = length(s.tabs)
    session.open_file(ref s, root + "/bin.nx")
    check("arquivo que nao e UTF-8 vira mensagem, sem aba", length(s.tabs) == before && strings.contains(s.message, "nao consegui ler"))
    session.open_file(ref s, root + "/b.nx")
    s.tabs[s.active].editor.doc.path = root + "/nao_existe/b.nx"
    editing.insert_text(ref s.tabs[s.active].editor, "q", 10, 9)
    session.save(ref s)
    check("salvar num caminho que nao existe vira mensagem e a aba continua suja", strings.contains(s.message, "nao consegui gravar") && s.tabs[s.active].editor.doc.dirty)
    check("relative e basename", session.relative(root, root + "/sub/c.nx") == "sub/c.nx" && session.basename("/a/b.nx") == "b.nx" && session.dirname("/a/b.nx") == "/a" && session.dirname("b.nx") == ".")
end
```

- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: erro de compilação: módulo `src.session` não pôde ser carregado.

- [ ] **Passo 3: implementar**

Repare no `use errors select Result, Failure`: `io.write_result` devolve `Result<int>`, e nomear esse tipo exige os dois structs importados.

```noxy
// src/session.nx — a sessao: raiz aberta, abas, arvore de arquivos, modal,
// execucao e as operacoes de arquivo. Nao conhece HTTP nem o quadro. Toda
// falha de arquivo vira message; nada aqui levanta erro.
use strings select substring, split, join_count, starts_with
use io
use errors select Result, Failure
use src.document as doc
use src.editing as editing
use src.runner as runner

struct Tab
    editor: editing.Editor
end

struct Node
    path: string        // absoluto
    name: string
    is_dir: bool
    depth: int
    expanded: bool
end

struct Button
    label: string
    id: string          // "save", "discard" ou "cancel"
end

struct Modal
    text: string        // "" quando nao ha modal
    buttons: Button[]
    pending: string     // o que fazer depois: "close_tab:3" ou "quit"
end

struct Session
    root: string        // absoluto, sem barra final
    tabs: Tab[]
    active: int         // -1 sem aba
    tree: Node[]        // lista plana das entradas visiveis
    tree_version: int   // muda a cada alteracao da arvore
    rows: int           // ultimo valor informado pelo cliente
    run: runner.RunState
    message: string     // status transitorio
    modal: Modal
    clipboard: string   // preenchido por copy/cut, consumido pelo quadro
    quitting: bool
    bye: bool           // a pagina avisou que esta fechando (pagehide)
    last_event: int     // ms do ultimo evento que nao foi quit_if_idle
end

func no_modal() -> Modal
    return Modal("", [], "")
end

func new_session(root: string) -> Session
    return Session(root, [], -1, [], 1, 30, runner.new_run(), "", no_modal(), "", false, false, 0)
end

func basename(path: string) -> string
    let parts: string[] = split(path, "/").parts
    return parts[length(parts) - 1]
end

func dirname(path: string) -> string
    let parts: string[] = split(path, "/").parts
    if length(parts) <= 1 then
        return "."
    end
    if length(parts) == 2 && parts[0] == "" then
        return "/"
    end
    return join_count(parts, "/", length(parts) - 1)
end

func relative(root: string, path: string) -> string
    if starts_with(path, root + "/") then
        return substring(path, length(root) + 1, length(path))
    end
    return path
end

// sort_nodes ordena por nome (insercao: listas por diretorio sao pequenas;
// a stdlib nao tem sort — docs/ACHADOS.md).
func sort_nodes(nodes: Node[]) -> Node[]
    let out: Node[] = nodes
    for i in range(1, length(out)) do
        let j: int = i
        while j > 0 && out[j - 1].name > out[j].name do
            let t: Node = out[j - 1]
            out[j - 1] = out[j]
            out[j] = t
            j = j - 1
        end
    end
    return out
end

// list_children lista um diretorio: pastas antes de arquivos, ordenados,
// sem entradas iniciadas por ponto. Vazio se nao der para ler.
func list_children(path: string, depth: int) -> Node[]
    let r: io.IOLinesResult = io.list_dir(path)
    if !r.ok then
        return []
    end
    let dirs: Node[] = []
    let files: Node[] = []
    for name in r.data do
        if !starts_with(name, ".") then
            let full: string = path + "/" + name
            if io.stat(full).is_dir then
                append(ref dirs, Node(full, name, true, depth, false))
            else
                append(ref files, Node(full, name, false, depth, false))
            end
        end
    end
    let out: Node[] = sort_nodes(dirs)
    for f in sort_nodes(files) do
        append(ref out, f)
    end
    return out
end

func load(s: ref Session) -> bool
    let st: io.FileInfo = io.stat(s.root)
    if !st.exists || !st.is_dir then
        return false
    end
    s.tree = list_children(s.root, 0)
    s.tree_version = s.tree_version + 1
    return true
end

func find_node(s: Session, path: string) -> int
    for i in range(length(s.tree)) do
        if s.tree[i].path == path then
            return i
        end
    end
    return -1
end

// toggle_dir expande (listando os filhos na hora) ou recolhe (removendo
// todos os descendentes) a pasta em path.
func toggle_dir(s: ref Session, path: string) -> void
    let i: int = find_node(*s, path)
    if i < 0 || !s.tree[i].is_dir then
        return
    end
    let node: Node = s.tree[i]
    let out: Node[] = slice(s.tree, 0, i)
    if node.expanded then
        node.expanded = false
        append(ref out, node)
        let j: int = i + 1
        while j < length(s.tree) && s.tree[j].depth > node.depth do
            j = j + 1
        end
        for k in range(j, length(s.tree)) do
            append(ref out, s.tree[k])
        end
    else
        node.expanded = true
        append(ref out, node)
        for c in list_children(node.path, node.depth + 1) do
            append(ref out, c)
        end
        for k in range(i + 1, length(s.tree)) do
            append(ref out, s.tree[k])
        end
    end
    s.tree = out
    s.tree_version = s.tree_version + 1
end

func find_tab(s: Session, path: string) -> int
    for i in range(length(s.tabs)) do
        if s.tabs[i].editor.doc.path == path then
            return i
        end
    end
    return -1
end

func open_file(s: ref Session, path: string) -> void
    let i: int = find_tab(*s, path)
    if i >= 0 then
        s.active = i
        return
    end
    let f: io.File = io.open(path, "r")
    if !f.open then
        s.message = "nao consegui abrir " + relative(s.root, path)
        return
    end
    let r: io.IOResult = io.read(f)
    io.close(f)
    if !r.ok then
        s.message = "nao consegui ler " + relative(s.root, path) + ": " + r.error
        return
    end
    append(ref s.tabs, Tab(editing.new_editor(doc.from_text(path, r.data))))
    s.active = length(s.tabs) - 1
end

func save_tab(s: ref Session, i: int) -> bool
    let path: string = s.tabs[i].editor.doc.path
    let f: io.File = io.open(path, "w")
    if !f.open then
        s.message = "nao consegui gravar " + relative(s.root, path)
        return false
    end
    let r: Result<int> = io.write_result(f, doc.to_text(s.tabs[i].editor.doc))
    io.close(f)
    if !r.ok then
        s.message = "nao consegui gravar " + relative(s.root, path) + ": " + r.failure.message
        return false
    end
    s.tabs[i].editor.doc.dirty = false
    return true
end

func save(s: ref Session) -> void
    if s.active < 0 then
        return
    end
    if save_tab(s, s.active) then
        s.message = "salvo " + relative(s.root, s.tabs[s.active].editor.doc.path)
    end
end

func save_all(s: ref Session) -> bool
    for i in range(length(s.tabs)) do
        if s.tabs[i].editor.doc.dirty && !save_tab(s, i) then
            return false
        end
    end
    return true
end

func has_dirty(s: Session) -> bool
    for t in s.tabs do
        if t.editor.doc.dirty then
            return true
        end
    end
    return false
end

// remove_tab tira a aba i e ativa a vizinha.
func remove_tab(s: ref Session, i: int) -> void
    pop(ref s.tabs, i)
    if length(s.tabs) == 0 then
        s.active = -1
    elif s.active >= length(s.tabs) then
        s.active = length(s.tabs) - 1
    elif s.active > i then
        s.active = s.active - 1
    end
end

func close_tab(s: ref Session, i: int) -> void
    if i < 0 || i >= length(s.tabs) then
        return
    end
    if s.tabs[i].editor.doc.dirty then
        let name: string = basename(s.tabs[i].editor.doc.path)
        s.modal = Modal("Fechar " + name + " sem salvar?", [Button("Salvar", "save"), Button("Nao salvar", "discard"), Button("Cancelar", "cancel")], "close_tab:" + to_str(i))
        return
    end
    remove_tab(s, i)
end

func request_quit(s: ref Session) -> void
    if has_dirty(*s) then
        s.modal = Modal("Ha abas com alteracoes nao salvas. Sair?", [Button("Salvar tudo", "save"), Button("Sair sem salvar", "discard"), Button("Cancelar", "cancel")], "quit")
        return
    end
    s.quitting = true
end

// answer_modal executa o pendente conforme o botao; "cancel" so fecha.
func answer_modal(s: ref Session, id: string) -> void
    let pending: string = s.modal.pending
    s.modal = no_modal()
    if id == "cancel" then
        return
    end
    if pending == "quit" then
        if id == "save" && !save_all(s) then
            return
        end
        s.quitting = true
    elif starts_with(pending, "close_tab:") then
        let i: int = to_int(substring(pending, 10, length(pending)))
        if i < 0 || i >= length(s.tabs) then
            return
        end
        if id == "save" && !save_tab(s, i) then
            return
        end
        remove_tab(s, i)
    end
end
```

- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx`
Esperado: `114/114 passaram`.

- [ ] **Passo 5: commit**

```bash
git add src/session.nx tests/run.nx
git commit -m "feat(session): raiz, arvore lazy, abas, abrir, salvar, fechar e modal"
```


### Tarefa 9: Frame — o quadro para o navegador

**Files:**
- Create: `src/frame.nx`
- Modify: `tests/run.nx`

**Interfaces:**
- Consumes: `lexer.tokenize`, `editing.has_sel/sel_range`, `session.*`.
- Produces: `title_of(ref s) -> string` e `build(ref s, client_tree_version) -> string` (JSON). Structs de saída `SpanOut(k, t, s)`, `LineOut(n, spans)`, `CursorOut`, `ViewOut(top, total, cursor, has_sel, lines)`, `TabOut`, `StatusOut(left, right, message)`, `OutputOut(version, running, text)`, `Frame`.

- [ ] **Passo 1: o teste que falha**

Acrescente `use src.frame as frame` aos `use`, a função antes de `report()` e `test_frame()` acima de `report()`:

```noxy
func test_frame() -> void
    print("frame")
    let root: string = tmp_root()
    let s: session.Session = session.new_session(root)
    session.load(ref s)
    s.rows = 2
    let empty: string = frame.build(ref s, 0)
    check("sem aba: tabs vazio e arvore presente", strings.contains(empty, "\"tabs\":[]") && strings.contains(empty, "\"name\":\"b.nx\"") && strings.contains(empty, "\"title\":\"Noxy Editor\""))
    let same: string = frame.build(ref s, s.tree_version)
    check("arvore omitida quando a versao bate", strings.contains(same, "\"tree\":[]"))

    session.open_file(ref s, root + "/b.nx")
    editing.move_end(ref s.tabs[0].editor, false, 2)
    editing.insert_text(ref s.tabs[0].editor, "\n", 2, 1)
    editing.insert_text(ref s.tabs[0].editor, "x", 2, 2)
    editing.click(ref s.tabs[0].editor, doc.Pos(0, 1), false, 2)
    editing.drag(ref s.tabs[0].editor, doc.Pos(1, 1), 2)
    s.clipboard = "cp"
    let f: string = frame.build(ref s, s.tree_version)
    check("spans cortados na fronteira da selecao", strings.contains(f, "{\"k\":\"keyword\",\"s\":false,\"t\":\"l\"}") && strings.contains(f, "{\"k\":\"keyword\",\"s\":true,\"t\":\"et\"}") && strings.contains(f, "{\"k\":\"ident\",\"s\":true,\"t\":\"x\"}"))
    check("cursor, has_sel e total", strings.contains(f, "\"cursor\":{\"col\":1,\"line\":1}") && strings.contains(f, "\"has_sel\":true") && strings.contains(f, "\"total\":3"))
    check("aba suja e titulo", strings.contains(f, "\"dirty\":true") && strings.contains(f, "b.nx ● — Noxy Editor"))
    check("status", strings.contains(f, "\"left\":\"b.nx ●\"") && strings.contains(f, "Ln 2, Col 2"))
    check("clipboard vai e e consumido", strings.contains(f, "\"clipboard\":\"cp\"") && s.clipboard == "")
    s.rows = 1
    editing.ensure_visible(ref s.tabs[0].editor, 1)
    let one: string = frame.build(ref s, s.tree_version)
    check("so as linhas visiveis", strings.contains(one, "\"n\":1") && !strings.contains(one, "\"n\":0") && !strings.contains(one, "\"n\":2"))
    check("title_of", frame.title_of(ref s) == "b.nx ● — Noxy Editor")

    let big: string[] = []
    for i in range(5000) do
        append(ref big, "let v" + to_str(i) + ": int = " + to_str(i) + " // linha")
    end
    let bs: session.Session = session.new_session(root)
    append(ref bs.tabs, session.Tab(editing.new_editor(doc.Document(root + "/big.nx", big, false))))
    bs.active = 0
    bs.rows = 50
    editing.move_doc_end(ref bs.tabs[0].editor, false, 50)
    let t0: int = time_now()
    let bf: string = frame.build(ref bs, 1)
    let dt: int = time_now() - t0
    check("arquivo de 5000 linhas: quadro so com as visiveis, em menos de 200 ms", strings.contains(bf, "\"total\":5000") && !strings.contains(bf, "\"n\":100,") && dt < 200)
end
```

- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: erro de compilação: módulo `src.frame` não pôde ser carregado.

- [ ] **Passo 3: implementar**

`json_dumps` serializa structs com os campos em ordem alfabética; os testes dependem disso (`{"k":..,"s":..,"t":..}`).

```noxy
// src/frame.nx — monta o quadro que o navegador pinta. So as linhas
// visiveis sao tokenizadas; spans sao cortados na fronteira da selecao e
// marcados com s, para o cliente nao fazer aritmetica de colunas. A arvore
// so vai quando a versao do cliente e outra. O clipboard e consumido.
use strings select substring
use src.document as doc
use src.lexer as lexer
use src.editing as editing
use src.session as session

struct SpanOut
    k: string       // kind do token
    t: string       // texto exato
    s: bool         // dentro da selecao
end

struct LineOut
    n: int          // indice 0-based; o gutter mostra n + 1
    spans: SpanOut[]
end

struct CursorOut
    line: int
    col: int
end

struct ViewOut
    top: int
    total: int
    cursor: CursorOut
    has_sel: bool
    lines: LineOut[]
end

struct TabOut
    name: string
    path: string
    dirty: bool
    active: bool
end

struct StatusOut
    left: string
    right: string
    message: string
end

struct OutputOut
    version: int
    running: bool
    text: string
end

struct Frame
    title: string
    root: string
    tabs: TabOut[]
    tree_version: int
    tree: session.Node[]
    view: ViewOut
    status: StatusOut
    output: OutputOut
    clipboard: string
    modal: session.Modal
end

// cut_span corta um token que comeca na coluna col em ate tres pedacos na
// fronteira [a, b) da selecao dentro da linha.
func cut_span(kind: string, text: string, col: int, a: int, b: int) -> SpanOut[]
    let n: int = length(text)
    let lo: int = a - col
    let hi: int = b - col
    if lo < 0 then
        lo = 0
    end
    if hi > n then
        hi = n
    end
    if hi <= lo then
        return [SpanOut(kind, text, false)]
    end
    let out: SpanOut[] = []
    if lo > 0 then
        append(ref out, SpanOut(kind, substring(text, 0, lo), false))
    end
    append(ref out, SpanOut(kind, substring(text, lo, hi), true))
    if hi < n then
        append(ref out, SpanOut(kind, substring(text, hi, n), false))
    end
    return out
end

func build_line(ed: editing.Editor, n: int) -> LineOut
    let line: string = ed.doc.lines[n]
    let a: int = 0
    let b: int = 0
    if editing.has_sel(ed) then
        let r: doc.Range = editing.sel_range(ed)
        if n >= r.start.line && n <= r.stop.line then
            if n == r.start.line then
                a = r.start.col
            end
            b = length(line)
            if n == r.stop.line then
                b = r.stop.col
            end
        end
    end
    let spans: SpanOut[] = []
    let col: int = 0
    for t in lexer.tokenize(line) do
        for sp in cut_span(t.kind, t.text, col, a, b) do
            append(ref spans, sp)
        end
        col = col + length(t.text)
    end
    return LineOut(n, spans)
end

func build_view(ed: editing.Editor, rows: int) -> ViewOut
    let total: int = length(ed.doc.lines)
    let stop: int = ed.top + rows
    if stop > total then
        stop = total
    end
    let lines: LineOut[] = []
    for n in range(ed.top, stop) do
        append(ref lines, build_line(ed, n))
    end
    return ViewOut(ed.top, total, CursorOut(ed.cursor.line, ed.cursor.col), editing.has_sel(ed), lines)
end

func empty_view() -> ViewOut
    return ViewOut(0, 0, CursorOut(0, 0), false, [])
end

// title_of e o titulo da janela: nome da aba ativa, marcador de alteracao
// e o nome do editor. editor.nx compara com o anterior para set_title.
func title_of(s: ref session.Session) -> string
    if s.active < 0 then
        return "Noxy Editor"
    end
    let d: doc.Document = s.tabs[s.active].editor.doc
    let mark: string = ""
    if d.dirty then
        mark = " ●"
    end
    return session.basename(d.path) + mark + " — Noxy Editor"
end

func build(s: ref session.Session, client_tree_version: int) -> string
    let tabs: TabOut[] = []
    for i in range(length(s.tabs)) do
        let d: doc.Document = s.tabs[i].editor.doc
        append(ref tabs, TabOut(session.basename(d.path), d.path, d.dirty, i == s.active))
    end
    let tree: session.Node[] = []
    if client_tree_version != s.tree_version then
        tree = s.tree
    end
    let view: ViewOut = empty_view()
    let title: string = title_of(s)
    let left: string = ""
    let right: string = ""
    if s.active >= 0 then
        let ed: editing.Editor = s.tabs[s.active].editor
        view = build_view(ed, s.rows)
        let mark: string = ""
        if ed.doc.dirty then
            mark = " ●"
        end
        left = session.relative(s.root, ed.doc.path) + mark
        right = "Ln " + to_str(ed.cursor.line + 1) + ", Col " + to_str(ed.cursor.col + 1) + "   Espaços: 4   UTF-8"
    end
    let f: Frame = Frame(title, session.basename(s.root), tabs, s.tree_version, tree, view, StatusOut(left, right, s.message), OutputOut(s.run.version, s.run.running, s.run.text), s.clipboard, s.modal)
    s.clipboard = ""
    return json_dumps(f)
end
```

- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx`
Esperado: `124/124 passaram`.

- [ ] **Passo 5: commit**

```bash
git add src/frame.nx tests/run.nx
git commit -m "feat(frame): quadro JSON com linhas visiveis tokenizadas e spans cortados na selecao"
```


### Tarefa 10: Events — do JSON ao efeito, dentro de call_result

**Files:**
- Create: `src/events.nx`
- Modify: `tests/run.nx`

**Interfaces:**
- Consumes: tudo de `editing`, `session`, `runner`, `frame`.
- Produces: `Event` (schema fixo), `empty_event()`, `dispatch(ref s, body, now) -> string` ("" para JSON inválido), `apply(s, e, now) -> Session` (por valor), `handle_key`, `run_active`. Eventos: `init key text paste copy cut click drag dblclick scroll tab_select tab_close tree_toggle tree_open run poll modal quit bye quit_if_idle`.

- [ ] **Passo 1: o teste que falha**

Acrescente `use src.events as events` aos `use`, a função antes de `report()` e `test_events()` acima de `report()`:

```noxy
func test_events() -> void
    print("events")
    let root: string = tmp_root()
    let s: session.Session = session.new_session(root)
    session.load(ref s)
    check("json invalido devolve vazio", events.dispatch(ref s, "{nope", 1) == "")
    check("campo com tipo errado devolve vazio", events.dispatch(ref s, "{\"kind\":\"click\",\"line\":\"x\"}", 1) == "")
    let f0: string = events.dispatch(ref s, "{\"kind\":\"init\",\"rows\":20,\"tree_version\":0}", 1)
    check("init guarda rows e devolve a arvore", s.rows == 20 && strings.contains(f0, "\"name\":\"sub\""))
    events.dispatch(ref s, "{\"kind\":\"tree_open\",\"path\":\"" + root + "/b.nx\",\"rows\":20,\"tree_version\":2}", 2)
    check("tree_open abre a aba", s.active == 0)
    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"end\",\"rows\":20,\"tree_version\":2}", 3)
    events.dispatch(ref s, "{\"kind\":\"text\",\"text\":\"é\",\"rows\":20,\"tree_version\":2}", 4)
    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"enter\",\"rows\":20,\"tree_version\":2}", 5)
    let d: doc.Document = s.tabs[0].editor.doc
    check("end, texto e enter", d.lines[0] == "let b = 1é" && length(d.lines) == 3)
    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"z\",\"ctrl\":true,\"rows\":20,\"tree_version\":2}", 6)
    check("ctrl+z", length(s.tabs[0].editor.doc.lines) == 2)
    events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"a\",\"ctrl\":true,\"rows\":20,\"tree_version\":2}", 7)
    let fc: string = events.dispatch(ref s, "{\"kind\":\"copy\",\"rows\":20,\"tree_version\":2}", 8)
    check("ctrl+a e copy devolvem o clipboard", strings.contains(fc, "\"clipboard\":\"let b = 1é\\n\""))
    events.dispatch(ref s, "{\"kind\":\"click\",\"line\":0,\"col\":-1,\"rows\":20,\"tree_version\":2}", 9)
    check("click no gutter seleciona a linha", editing.copy(s.tabs[0].editor) == "let b = 1é\n")
    let fu: string = events.dispatch(ref s, "{\"kind\":\"zzz\",\"rows\":20,\"tree_version\":2}", 10)
    check("kind desconhecido vira mensagem", strings.contains(fu, "evento desconhecido: zzz"))
    events.dispatch(ref s, "{\"kind\":\"tab_select\",\"index\":7,\"rows\":20,\"tree_version\":2}", 11)
    check("tab_select fora do intervalo e ignorado", s.active == 0)
    events.dispatch(ref s, "{\"kind\":\"tab_close\",\"index\":0,\"rows\":20,\"tree_version\":2}", 12)
    check("tab_close de aba suja abre modal", s.modal.text != "")
    events.dispatch(ref s, "{\"kind\":\"modal\",\"key\":\"discard\",\"rows\":20,\"tree_version\":2}", 13)
    check("resposta do modal fecha a aba", length(s.tabs) == 0 && s.modal.text == "")
    let fr: string = events.dispatch(ref s, "{\"kind\":\"run\",\"rows\":20,\"tree_version\":2}", 14)
    check("run sem aba avisa", strings.contains(fr, "nenhum arquivo aberto"))
    events.dispatch(ref s, "{\"kind\":\"tree_open\",\"path\":\"" + root + "/a.txt\",\"rows\":20,\"tree_version\":2}", 15)
    let ft: string = events.dispatch(ref s, "{\"kind\":\"key\",\"key\":\"f5\",\"rows\":20,\"tree_version\":2}", 16)
    check("f5 em .txt recusa", strings.contains(ft, "so arquivos .nx"))
    events.dispatch(ref s, "{\"kind\":\"tree_open\",\"path\":\"" + root + "/hello.nx\",\"rows\":20,\"tree_version\":2}", 17)
    let f5: string = events.dispatch(ref s, "{\"kind\":\"run\",\"rows\":20,\"tree_version\":2}", 18)
    check("run dispara e o quadro mostra running", s.run.running && strings.contains(f5, "\"running\":true"))
    let waited: int = 0
    let last: string = ""
    while s.run.running && waited < 100 do
        sys.sleep(50)
        last = events.dispatch(ref s, "{\"kind\":\"poll\",\"rows\":20,\"tree_version\":2}", 19)
        waited = waited + 1
    end
    check("poll recolhe a saida no quadro", strings.contains(last, "[saiu com 3]"))
    events.dispatch(ref s, "{\"kind\":\"quit\",\"rows\":20,\"tree_version\":2}", 20)
    check("quit marca quitting", s.quitting)
end
```

- [ ] **Passo 2: ver falhar**

Run: `noxy tests/run.nx`
Esperado: erro de compilação: módulo `src.events` não pôde ser carregado.

- [ ] **Passo 3: implementar**

`call_result` exige `use errors select *` no módulo. `apply` recebe e devolve a sessão **por valor**: se levantar erro, `dispatch` descarta o resultado e a sessão fica como estava.

```noxy
// src/events.nx — do JSON do evento ao efeito na sessao. dispatch e o unico
// ponto de entrada do dono do estado: decodifica num Event de schema fixo,
// aplica dentro de call_result (um bug vira "erro interno" e a sessao fica
// como estava, porque apply recebe e devolve a sessao por valor), consulta
// a execucao e devolve o quadro.
use strings select ends_with
use errors select *
use src.document as doc
use src.editing as editing
use src.session as session
use src.runner as runner
use src.frame as frame

let IDLE_QUIT_MS = 2500     // bye sem evento novo por este tempo encerra o editor

struct Event
    kind: string
    key: string         // KeyboardEvent.key em minusculas; id do botao no modal
    ctrl: bool
    shift: bool
    alt: bool
    text: string
    line: int
    col: int            // -1 no click = clique no gutter
    delta: int
    path: string
    index: int
    rows: int
    tree_version: int   // a versao da arvore que o cliente tem
end

func empty_event() -> Event
    return Event("", "", false, false, false, "", 0, 0, 0, "", 0, 0, 0)
end

// trivial: eventos que nao apagam a mensagem de status.
func trivial(kind: string) -> bool
    return kind == "poll" || kind == "scroll" || kind == "drag" || kind == "quit_if_idle" || kind == "bye"
end

// run_active salva a aba ativa se preciso e dispara a execucao.
func run_active(s: ref session.Session) -> void
    if s.active < 0 then
        s.message = "nenhum arquivo aberto"
        return
    end
    let path: string = s.tabs[s.active].editor.doc.path
    if !ends_with(path, ".nx") then
        s.message = "so arquivos .nx"
        return
    end
    if s.tabs[s.active].editor.doc.dirty then
        session.save(s)
        if s.tabs[s.active].editor.doc.dirty then
            return
        end
    end
    let msg: string = runner.start(ref s.run, s.root, session.relative(s.root, path))
    if msg != "" then
        s.message = msg
    end
end

func handle_key(s: ref session.Session, e: Event, now: int) -> void
    if e.ctrl && e.key == "q" then
        session.request_quit(s)
        return
    end
    if e.key == "f5" then
        run_active(s)
        return
    end
    if e.key == "escape" && s.modal.text != "" then
        session.answer_modal(s, "cancel")
        return
    end
    if s.active < 0 then
        return
    end
    let rows: int = s.rows
    let ed: ref editing.Editor = ref s.tabs[s.active].editor
    if e.ctrl then
        if e.key == "s" then
            session.save(s)
        elif e.key == "z" && e.shift then
            editing.redo(ed, rows)
        elif e.key == "z" then
            editing.undo(ed, rows)
        elif e.key == "y" then
            editing.redo(ed, rows)
        elif e.key == "a" then
            editing.select_all(ed)
        elif e.key == "w" then
            session.close_tab(s, s.active)
        elif e.key == "/" then
            editing.toggle_comment(ed, rows, now)
        elif e.key == "arrowleft" then
            editing.move_word_left(ed, e.shift, rows)
        elif e.key == "arrowright" then
            editing.move_word_right(ed, e.shift, rows)
        elif e.key == "home" then
            editing.move_doc_start(ed, e.shift, rows)
        elif e.key == "end" then
            editing.move_doc_end(ed, e.shift, rows)
        end
        return
    end
    if e.key == "arrowleft" then
        editing.move_left(ed, e.shift, rows)
    elif e.key == "arrowright" then
        editing.move_right(ed, e.shift, rows)
    elif e.key == "arrowup" then
        editing.move_up(ed, e.shift, rows)
    elif e.key == "arrowdown" then
        editing.move_down(ed, e.shift, rows)
    elif e.key == "home" then
        editing.move_home(ed, e.shift, rows)
    elif e.key == "end" then
        editing.move_end(ed, e.shift, rows)
    elif e.key == "pageup" then
        editing.page_up(ed, e.shift, rows)
    elif e.key == "pagedown" then
        editing.page_down(ed, e.shift, rows)
    elif e.key == "enter" then
        editing.newline(ed, rows, now)
    elif e.key == "backspace" then
        editing.backspace(ed, rows, now)
    elif e.key == "delete" then
        editing.delete_forward(ed, rows, now)
    elif e.key == "tab" then
        editing.tab(ed, e.shift, rows, now)
    elif e.key == "escape" then
        ed.anchor = ed.cursor
    end
end

// apply recebe e devolve a sessao por valor: se levantar erro, dispatch
// descarta o resultado e a sessao continua como estava.
func apply(s: session.Session, e: Event, now: int) -> session.Session
    if e.rows > 0 && e.rows != s.rows then
        s.rows = e.rows
        if s.active >= 0 then
            editing.ensure_visible(ref s.tabs[s.active].editor, s.rows)
        end
    end
    if !trivial(e.kind) then
        s.message = ""
    end
    if e.kind != "quit_if_idle" then
        s.last_event = now
    end
    if e.kind == "key" then
        handle_key(ref s, e, now)
    elif e.kind == "text" then
        if s.active >= 0 then
            editing.insert_text(ref s.tabs[s.active].editor, e.text, s.rows, now)
        end
    elif e.kind == "paste" then
        if s.active >= 0 then
            editing.paste(ref s.tabs[s.active].editor, e.text, s.rows, now)
        end
    elif e.kind == "copy" then
        if s.active >= 0 then
            s.clipboard = editing.copy(s.tabs[s.active].editor)
        end
    elif e.kind == "cut" then
        if s.active >= 0 then
            s.clipboard = editing.cut(ref s.tabs[s.active].editor, s.rows, now)
        end
    elif e.kind == "click" then
        if s.active >= 0 then
            if e.col < 0 then
                editing.select_line(ref s.tabs[s.active].editor, e.line, s.rows)
            else
                editing.click(ref s.tabs[s.active].editor, doc.Pos(e.line, e.col), e.shift, s.rows)
            end
        end
    elif e.kind == "drag" then
        if s.active >= 0 then
            editing.drag(ref s.tabs[s.active].editor, doc.Pos(e.line, e.col), s.rows)
        end
    elif e.kind == "dblclick" then
        if s.active >= 0 then
            editing.select_word_at(ref s.tabs[s.active].editor, doc.Pos(e.line, e.col), s.rows)
        end
    elif e.kind == "scroll" then
        if s.active >= 0 then
            editing.scroll(ref s.tabs[s.active].editor, e.delta, s.rows)
        end
    elif e.kind == "tab_select" then
        if e.index >= 0 && e.index < length(s.tabs) then
            s.active = e.index
        end
    elif e.kind == "tab_close" then
        session.close_tab(ref s, e.index)
    elif e.kind == "tree_toggle" then
        session.toggle_dir(ref s, e.path)
    elif e.kind == "tree_open" then
        session.open_file(ref s, e.path)
    elif e.kind == "run" then
        run_active(ref s)
    elif e.kind == "modal" then
        session.answer_modal(ref s, e.key)
    elif e.kind == "quit" then
        s.quitting = true
    elif e.kind == "bye" then
        s.bye = true
    elif e.kind == "quit_if_idle" then
        if now - s.last_event >= IDLE_QUIT_MS then
            s.quitting = true
        end
    elif e.kind != "init" && e.kind != "poll" then
        s.message = "evento desconhecido: " + e.kind
    end
    return s
end

// dispatch devolve o quadro, ou "" quando body nao e um evento valido.
func dispatch(s: ref session.Session, body: string, now: int) -> string
    let e: Event = empty_event()
    if !json_loads(body, ref e) then
        return ""
    end
    let r = call_result(apply, *s, e, now)
    if r.ok then
        *s = r.value
    else
        eprint("erro interno no evento " + e.kind + ": " + r.failure.message)
        s.message = "erro interno: " + r.failure.message
    end
    runner.poll(ref s.run)
    return frame.build(s, e.tree_version)
end
```

- [ ] **Passo 4: ver passar**

Run: `noxy tests/run.nx`
Esperado: `141/141 passaram`.

- [ ] **Passo 5: commit**

```bash
git add src/events.nx tests/run.nx
git commit -m "feat(events): despacho de eventos com sessao por valor em call_result e atalhos"
```


### Tarefa 11: Server — rotas, token e ponte com o dono

**Files:**
- Create: `src/server.nx`
- Create: `web/index.html` (mínimo, substituído na Tarefa 12)
- Create: `tests/protocol.nx`

**Interfaces:**
- Consumes: `session`, `events`.
- Produces: `Request(body, reply)`, globais `inbox: chan any`, `token`, `web_dir`, `server`; `start(web, tok) -> int` (porta ou 0), `stop()`, `handler(req)`.

- [ ] **Passo 1: um `web/index.html` mínimo**

Só para o teste de `GET /` ter o que conferir; a Tarefa 12 escreve o de verdade.

```html
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Noxy Editor</title>
<link rel="stylesheet" href="/editor.css">
</head>
<body>
<script src="/editor.js"></script>
</body>
</html>
```

E `web/editor.css` e `web/editor.js` vazios por enquanto: `printf '' > web/editor.css; printf '' > web/editor.js`.

- [ ] **Passo 2: o teste que falha**

```noxy
// tests/protocol.nx — o pipeline inteiro menos o navegador: sobe o
// servidor na porta 0 com o loop dono numa routine e faz POSTs reais.
//     noxy tests/protocol.nx      (a partir da raiz do projeto)
use sys
use io
use strings
use http_client
use src.session as session
use src.events as events
use src.server as server

let fails = 0
let total = 0

func check(name: string, cond: bool) -> void
    total = total + 1
    if cond then
        print(f"  ok   {name}")
    else
        print(f"FAIL   {name}")
        fails = fails + 1
    end
end

func write_file(path: string, text: string) -> void
    let f: io.File = io.open(path, "w")
    io.write(f, text)
    io.close(f)
end

let root: string = sys.getcwd() + "/tests/tmp/protocol"
io.mkdir(root)
write_file(root + "/p.nx", "let p = 1\n")

let s: session.Session = session.new_session(root)
session.load(ref s)

func owner() -> void
    while !s.quitting do
        let r: any = chan_recv(server.inbox)
        let req: server.Request = r
        let now: int = time_now()
        chan_send(req.reply, events.dispatch(ref s, req.body, now))
    end
end

func post(base: string, tok: string, body: string) -> http_client.ClientResponse
    let c: http_client.HttpClient = http_client.new_client()
    let hs: string[64]
    hs[0] = "X-Noxy-Token: " + tok
    hs[1] = "Content-Type: application/json"
    return http_client.request(ref c, "POST", base + "/event", hs, 2, to_bytes(body))
end

let port: int = server.start(sys.getcwd() + "/web", "segredo")
check("bind numa porta efemera", port > 0)
spawn(owner)
let base: string = "http://127.0.0.1:" + to_str(port)

let page: http_client.ClientResponse = http_client.get(base + "/?t=segredo")
check("GET / serve a pagina", page.status_code == 200 && strings.contains(to_str(page.body), "<title>Noxy Editor</title>"))
let css: http_client.ClientResponse = http_client.get(base + "/editor.css")
check("GET /editor.css", css.status_code == 200)
let nope: http_client.ClientResponse = http_client.get(base + "/outro")
check("GET desconhecido e 404", nope.status_code == 404)

let no_token: http_client.ClientResponse = http_client.post(base + "/event", to_bytes("{\"kind\":\"init\"}"))
check("POST sem token e 403", no_token.status_code == 403)
let bad: http_client.ClientResponse = post(base, "segredo", "{nope")
check("POST com JSON invalido e 400", bad.status_code == 400)

let init: http_client.ClientResponse = post(base, "segredo", "{\"kind\":\"init\",\"rows\":10,\"tree_version\":0}")
let body: string = to_str(init.body)
check("init devolve o quadro com a arvore", init.status_code == 200 && strings.contains(body, "\"name\":\"p.nx\"") && strings.contains(body, "\"tabs\":[]"))
post(base, "segredo", "{\"kind\":\"tree_open\",\"path\":\"" + root + "/p.nx\",\"rows\":10,\"tree_version\":2}")
post(base, "segredo", "{\"kind\":\"key\",\"key\":\"end\",\"rows\":10,\"tree_version\":2}")
let typed: http_client.ClientResponse = post(base, "segredo", "{\"kind\":\"text\",\"text\":\"0\",\"rows\":10,\"tree_version\":2}")
let tbody: string = to_str(typed.body)
check("abrir, end e digitar refletem no quadro", strings.contains(tbody, "\"t\":\"10\"") && strings.contains(tbody, "\"dirty\":true") && strings.contains(tbody, "\"tree\":[]"))
let beacon: http_client.ClientResponse = http_client.post(base + "/event?t=segredo", to_bytes("{\"kind\":\"quit\",\"rows\":10,\"tree_version\":2}"))
check("quit com token na query (sendBeacon) e aceito", beacon.status_code == 200)
let waited: int = 0
while !s.quitting && waited < 50 do
    sys.sleep(20)
    waited = waited + 1
end
check("quit encerra o loop dono", s.quitting)
server.stop()

print("")
print(f"{total - fails}/{total} passaram")
if fails > 0 then
    sys.exit(1)
end
```

- [ ] **Passo 3: ver falhar**

Run: `noxy tests/protocol.nx`
Esperado: erro de compilação: módulo `src.server` não pôde ser carregado.

- [ ] **Passo 4: implementar**

```noxy
// src/server.nx — as rotas HTTP e a ponte com o dono do estado. A stdlib
// roda cada conexao numa routine propria; o handler de /event so empacota
// o corpo com um canal de resposta, manda no inbox e espera o quadro. O
// token gerado na partida vai na URL da pagina e volta no cabecalho
// X-Noxy-Token (ou em ?t=, para o sendBeacon do quit).
use http_server select *
use http_parser select *
use strings select is_valid_utf8

struct Request
    body: string
    reply: chan any
end

let inbox: chan any = make_chan(64)
let token: string = ""
let web_dir: string = ""
let server: HttpServer = new_server("127.0.0.1", 0)

func static_path(path: string) -> string
    if path == "/" then
        return web_dir + "/index.html"
    end
    if path == "/editor.css" || path == "/editor.js" then
        return web_dir + path
    end
    return ""
end

func token_ok(req: HttpRequest) -> bool
    if get_header(req.headers, req.header_count, "X-Noxy-Token") == token then
        return true
    end
    return req.query == "t=" + token
end

func handler(req: HttpRequest) -> HttpResponse
    if req.method == "GET" then
        let file: string = static_path(req.path)
        if file != "" then
            return serve_static(file)
        end
        return response_404()
    end
    if req.method == "POST" && req.path == "/event" then
        if !token_ok(req) then
            return response_error(403, "token invalido")
        end
        if !is_valid_utf8(req.body) then
            return response_error(400, "corpo nao e UTF-8")
        end
        let reply: chan any = make_chan(1)
        chan_send(inbox, Request(to_str(req.body), reply))
        let out: string = chan_recv(reply)
        if out == "" then
            return response_error(400, "evento invalido")
        end
        return response_json(out)
    end
    return response_404()
end

func serve_forever() -> void
    serve(ref server, handler)
end

// start faz o bind numa porta efemera e serve numa routine; devolve a
// porta, ou 0 se nao conseguiu.
func start(web: string, tok: string) -> int
    web_dir = web
    token = tok
    if !bind_server(ref server) then
        return 0
    end
    spawn(serve_forever)
    return server.port
end

func stop() -> void
    stop_server(ref server)
end
```

- [ ] **Passo 5: ver passar**

Run: `noxy tests/protocol.nx`
Esperado: `10/10 passaram` (mais a linha `Server listening on 127.0.0.1:<porta>` que a stdlib imprime). `noxy tests/run.nx` continua em `141/141`.

- [ ] **Passo 6: commit**

```bash
git add src/server.nx web/ tests/protocol.nx
git commit -m "feat(server): rotas estaticas, POST /event com token e ponte por canal com o dono"
```


### Tarefa 12: Cliente web, lançador (fallback) e entrada

**Files:**
- Create: `web/index.html`, `web/editor.css`, `web/editor.js`
- Create: `src/launch.nx` (versão fallback)
- Create: `editor.nx`
- Create: `tests/cdp.py`, `tests/web_smoke.py`

**Interfaces:**
- Consumes: `server.start/stop/inbox/token/Request`, `events.dispatch`, `session.*`.
- Produces: `launch.open_window(url) -> string`, `launch.close_window()`, `launch.mode`; `editor.nx` executável; `NOXY_EDITOR_NO_WINDOW=1`.

- [ ] **Passo 1: o teste que falha — o smoke headless**

`tests/cdp.py` é um cliente mínimo do Chrome DevTools Protocol, só biblioteca padrão:

```python
# cdp.py — cliente minimo do Chrome DevTools Protocol (websocket em socket cru)
import base64, json, os, socket, struct, sys, time, urllib.request, subprocess

class WS:
    def __init__(self, url):
        assert url.startswith("ws://")
        hostport, path = url[5:].split("/", 1)
        host, port = hostport.split(":")
        self.s = socket.create_connection((host, int(port)))
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.s.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        assert b" 101 " in buf.split(b"\r\n")[0], buf
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.next_id = 0
    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out
    def send(self, text):
        data = text.encode()
        head = bytes([0x81])
        n = len(data)
        if n < 126: head += bytes([0x80 | n])
        elif n < 65536: head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else: head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.s.sendall(head + mask + masked)
    def recv(self):
        while True:
            b0, b1 = self._read(2)
            op = b0 & 0x0f
            n = b1 & 0x7f
            if n == 126: n = struct.unpack(">H", self._read(2))[0]
            elif n == 127: n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if op == 1: return payload.decode()
            if op == 9: self.s.sendall(bytes([0x8a, 0x80]) + os.urandom(4))  # pong
            if op == 8: raise EOFError
    def call(self, method, params=None):
        self.next_id += 1
        mid = self.next_id
        self.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.recv())
            if msg.get("id") == mid:
                if "error" in msg: raise RuntimeError(msg["error"])
                return msg.get("result", {})

def start_chrome(port):
    p = subprocess.Popen(["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
                          f"--remote-debugging-port={port}", "--window-size=1200,800", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version").read()
            return p
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("chrome nao subiu")

def page_ws(port):
    targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json").read())
    page = [t for t in targets if t["type"] == "page"][0]
    return page["webSocketDebuggerUrl"]
```

`tests/web_smoke.py` sobe o editor sem janela numa pasta de demo, abre a página num Chrome headless e exercita o cliente de verdade:

```python
# tests/web_smoke.py — o cliente web de verdade: sobe o editor sem janela,
# abre a pagina num Chrome headless pelo DevTools Protocol (tests/cdp.py) e
# exercita teclado, mouse, clipboard, F5 e modal. Precisa de google-chrome.
#     python3 tests/web_smoke.py      (a partir da raiz do projeto)
import base64, json, sys, time, re
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import WS, start_chrome, page_ws

import subprocess
# estado limpo: uma pasta de demo nova em tests/tmp/web e o editor sem janela
demo = os.path.join("tests", "tmp", "web")
os.makedirs(os.path.join(demo, "src"), exist_ok=True)
open(os.path.join(demo, "exemplo.nx"), "w").write('use sys\n// um exemplo para o editor\nfunc soma(a: int, b: int) -> int\n    return a + b\nend\nlet nome: string = "Noxy"\nprint(f"ola {nome}: {soma(2, 3)}")\nfor i in range(3) do\n    print(i)\nend\n')
open(os.path.join(demo, "notas.txt"), "w").write("texto simples\n")
open(os.path.join(demo, "src", "util.nx"), "w").write("let x = 1\n")
env = dict(os.environ, NOXY_EDITOR_NO_WINDOW="1")
log = os.path.join("tests", "tmp", "web_editor.log")
editor = subprocess.Popen(["noxy", "editor.nx", demo], env=env, stdout=subprocess.DEVNULL, stderr=open(log, "w"))
url = None
for _ in range(50):
    m = re.search(r"http://127\.0\.0\.1:\d+/\?t=[a-z0-9-]+", open(log).read())
    if m: url = m.group(0); break
    time.sleep(0.1)
chrome = start_chrome(9333)
ws = WS(page_ws(9333))
ws.call("Page.enable"); ws.call("Runtime.enable")
fails = 0
def ev(expr):
    r = ws.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
    if "exceptionDetails" in r: raise RuntimeError(r["exceptionDetails"])
    return r["result"].get("value")
def check(name, cond):
    global fails
    print(("  ok   " if cond else "FAIL   ") + name)
    if not cond: fails += 1
def settle(ms=350): time.sleep(ms / 1000)
def key(k, text=None, mods=0, code=None):
    p = {"type": "keyDown", "key": k, "modifiers": mods, "windowsVirtualKeyCode": 0}
    if text: p["text"] = text
    ws.call("Input.dispatchKeyEvent", p)
    p["type"] = "keyUp"; p.pop("text", None)
    ws.call("Input.dispatchKeyEvent", p)
    settle()
def insert(text):
    ws.call("Input.insertText", {"text": text}); settle()
def mouse(kind, x, y, button="left", clicks=1, mods=0):
    ws.call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": button, "clickCount": clicks, "modifiers": mods})

ws.call("Page.navigate", {"url": url}); settle(1500)
check("arvore renderizada", ev("document.querySelectorAll('#tree .node').length") == 3)
check("nome da raiz", ev("document.getElementById('root-name').textContent") == "web")
check("titulo inicial", ev("document.title") == "Noxy Editor")
# abrir exemplo.nx pela arvore
ev("document.querySelectorAll('#tree .node.file')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
check("abrir arquivo cria aba e linhas", ev("document.querySelectorAll('.tab').length") == 1 and ev("document.querySelectorAll('#text .line').length") == 11)
check("highlighting: keyword e string", ev("!!document.querySelector('.k-keyword') && !!document.querySelector('.k-string')"))
check("cursor visivel na linha 1", ev("!document.getElementById('cursor').classList.contains('hidden') && document.querySelector('.line.cur').dataset.n") == "0")
check("textarea focado", ev("document.activeElement.id") == "input")
# End + digitar com acento
key("End")
insert("ção")
check("digitar acentos no fim da linha 1", ev("document.querySelector('.line[data-n=\"0\"]').textContent") == "use sysção")
check("status mostra a aba suja", "●" in ev("document.getElementById('status-left').textContent"))
check("titulo com a bolinha", ev("document.title").startswith("exemplo.nx ●"))
# Enter + Ctrl+Z
key("Enter")
check("enter cria linha", ev("document.querySelectorAll('#text .line').length") == 12)
key("z", mods=2)
check("ctrl+z desfaz o enter", ev("document.querySelectorAll('#text .line').length") == 11)
key("z", mods=2)
check("ctrl+z desfaz a digitacao", ev("document.querySelector('.line[data-n=\"0\"]').textContent") == "use sys")
# clique numa posicao do texto: linha 3 (func soma...), depois de 'func '
rect = ev("(() => { const r = document.querySelector('.line[data-n=\"2\"] .k-call').getBoundingClientRect(); return [r.left, r.top, r.height]; })()")
mouse("mousePressed", rect[0] + 1, rect[1] + rect[2] / 2); mouse("mouseReleased", rect[0] + 1, rect[1] + rect[2] / 2); settle()
check("clique posiciona o cursor", "Ln 3, Col 6" in ev("document.getElementById('status-right').textContent"))
# shift+End seleciona ate o fim
key("End", mods=8)
check("shift+end seleciona", ev("document.querySelectorAll('.line[data-n=\"2\"] .sel').length") > 0)
# Ctrl+C copia -> clipboard interno; depois Ctrl+V cola via evento paste sintetico
key("c", mods=2)
ev("(() => { const dt = new DataTransfer(); dt.setData('text', 'X'); document.getElementById('input').dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true})); })()"); settle()
check("paste substitui a selecao", ev("document.querySelector('.line[data-n=\"2\"]').textContent") == "func X")
# arrastar: da coluna 0 da linha 4 ate a linha 5
r4 = ev("(() => { const r = document.querySelector('.line[data-n=\"3\"]').getBoundingClientRect(); return [r.left, r.top, r.height]; })()")
mouse("mousePressed", r4[0] + 2, r4[1] + 5); mouse("mouseMoved", r4[0] + 40, r4[1] + r4[2] + 5); settle(); mouse("mouseReleased", r4[0] + 40, r4[1] + r4[2] + 5); settle()
check("arrastar seleciona duas linhas", ev("document.querySelectorAll('.line[data-n=\"3\"] .sel').length") > 0 and ev("document.querySelectorAll('.line[data-n=\"4\"] .sel').length") > 0)
# duplo clique seleciona palavra
key("Escape")
r6 = ev("(() => { const r = document.querySelector('.line[data-n=\"5\"] .k-type').getBoundingClientRect(); return [r.left, r.top, r.height]; })()")
mouse("mousePressed", r6[0] + 3, r6[1] + 5, clicks=1); mouse("mouseReleased", r6[0] + 3, r6[1] + 5, clicks=1)
mouse("mousePressed", r6[0] + 3, r6[1] + 5, clicks=2); mouse("mouseReleased", r6[0] + 3, r6[1] + 5, clicks=2); settle()
check("duplo clique seleciona a palavra", ev("Array.from(document.querySelectorAll('.line[data-n=\"5\"] .sel')).map(e => e.textContent).join('')") == "string")
# roda do mouse: o arquivo tem 10 linhas e a janela mais que isso, entao top fica 0; testa que nao quebra
ws.call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": r6[0], "y": r6[1], "deltaX": 0, "deltaY": 100}); settle()
check("roda nao quebra com arquivo curto", ev("document.querySelectorAll('#text .line').length") == 11)
# F5 roda o arquivo (salva antes) e o painel aparece
key("F5"); settle(1500)
check("F5 mostra o painel de saida", not ev("document.getElementById('output').classList.contains('hidden')"))
out = ev("document.getElementById('output-text').textContent")
check("saida do programa aparece", "$ noxy exemplo.nx" in out and "[saiu com" in out)
print("SAIDA:", out.replace("\n", " | ")[:200])
# digitar de novo para sujar, entao fechar pelo x: modal
key("End"); insert("!")
ev("document.querySelector('.tab .close').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
check("fechar aba suja abre modal", not ev("document.getElementById('modal').classList.contains('hidden')"))
ev("document.querySelectorAll('#modal-buttons button')[2].click()"); settle()
check("cancelar fecha o modal", ev("document.getElementById('modal').classList.contains('hidden')"))
# screenshot
shot = ws.call("Page.captureScreenshot", {"format": "png"})["data"]
open(os.path.join("tests", "tmp", "web_screenshot.png"), "wb").write(base64.b64decode(shot))
chrome.terminate()
editor.terminate()
print(f"\n{'FALHOU' if fails else 'OK'}: {fails} falhas")
sys.exit(1 if fails else 0)
```

- [ ] **Passo 2: ver falhar**

Run: `python3 tests/web_smoke.py`
Esperado: traceback ao esperar a URL (o `editor.nx` ainda não existe, `url` fica `None`), ou `Error reading file` no log.

- [ ] **Passo 3: `src/launch.nx`, versão fallback**

```noxy
// src/launch.nx — abre a janela do editor. Nesta fase so o fallback: um
// navegador em modo app (janela sem barra de endereco) ou o navegador
// padrao. A extensao noxy_webview entra na frente disso na Tarefa 16.
use sys
use strings select replace

let BROWSERS: string[] = ["google-chrome", "chromium", "chromium-browser", "brave-browser", "microsoft-edge"]
let mode: string = ""       // "app", "browser" ou ""

func has_command(name: string) -> bool
    return sys.exec("command -v " + name + " >/dev/null 2>&1").exit_code == 0
end

func shell_quote(s: string) -> string
    return "'" + replace(s, "'", "'\\''") + "'"
end

// open_browser devolve "app" (janela sem barra), "browser" ou "".
func open_browser(url: string) -> string
    let q: string = shell_quote(url)
    for b in BROWSERS do
        if has_command(b) then
            sys.exec(b + " --app=" + q + " >/dev/null 2>&1 &")
            return "app"
        end
    end
    if sys.os() == "darwin" then
        sys.exec("open " + q)
        return "browser"
    end
    if has_command("xdg-open") then
        sys.exec("xdg-open " + q + " >/dev/null 2>&1 &")
        return "browser"
    end
    return ""
end

// open_window devolve como a janela foi aberta ("app", "browser") ou "".
func open_window(url: string) -> string
    mode = open_browser(url)
    return mode
end

// close_window fecha a janela se ela e nossa; no fallback nao ha o que fechar.
func close_window() -> void
end
```

- [ ] **Passo 4: `editor.nx`**

```noxy
// editor.nx — Noxy Editor. Um editor de codigo para arquivos Noxy, escrito
// em Noxy: o navegador so pinta e encaminha entrada.
//     noxy editor.nx [pasta | arquivo]      (sem argumento: o diretorio atual)
// A routine principal e a dona do estado: recebe os eventos que o servidor
// (src/server, em routines da stdlib) poe no canal, aplica na sessao e
// responde o quadro. A janela e a extensao noxy_webview, com fallback para
// o navegador em modo app (src/launch).
use sys
use io
use uuid
use strings select starts_with, substring, ends_with
use src.session as session
use src.events as events
use src.server as server
use src.launch as launch

func absolute(path: string) -> string
    if starts_with(path, "/") then
        return path
    end
    if path == "." then
        return sys.getcwd()
    end
    if starts_with(path, "./") then
        return sys.getcwd() + "/" + substring(path, 2, length(path))
    end
    return sys.getcwd() + "/" + path
end

func strip_slash(path: string) -> string
    if length(path) > 1 && ends_with(path, "/") then
        return substring(path, 0, length(path) - 1)
    end
    return path
end

let args: string[] = sys.argv()
let editor_dir: string = session.dirname(absolute(args[1]))
let target: string = sys.getcwd()
if length(args) > 2 then
    target = strip_slash(absolute(args[2]))
end
let first_file: string = ""
let st: io.FileInfo = io.stat(target)
if !st.exists then
    eprint("nao encontrei " + target)
    sys.exit(1)
end
if !st.is_dir then
    first_file = target
    target = session.dirname(target)
end

let s: session.Session = session.new_session(target)
if !session.load(ref s) then
    eprint("nao consegui ler a pasta " + target)
    sys.exit(1)
end
if first_file != "" then
    session.open_file(ref s, first_file)
end

let port: int = server.start(editor_dir + "/web", uuid.uuid4())
if port == 0 then
    eprint("nao consegui abrir uma porta em 127.0.0.1")
    sys.exit(1)
end
let url: string = "http://127.0.0.1:" + to_str(port) + "/?t=" + server.token
let mode: string = "none"
if !sys.getenv("NOXY_EDITOR_NO_WINDOW").ok then
    mode = launch.open_window(url)
end
if mode == "" then
    eprint("nao consegui abrir uma janela; abra " + url + " num navegador")
else
    eprint("Noxy Editor em " + url + " (" + mode + ")")
end

// delayed_quit: a pagina avisou que esta fechando; se em 3 s nao chegar
// evento novo (um reload manda init de novo), o editor encerra.
func delayed_quit() -> void
    sys.sleep(3000)
    let reply: chan any = make_chan(1)
    chan_send(server.inbox, server.Request("{\"kind\":\"quit_if_idle\"}", reply))
    chan_recv(reply)
end

while !s.quitting do
    let r: any = chan_recv(server.inbox)
    let req: server.Request = r
    let now: int = time_now()
    let out: string = events.dispatch(ref s, req.body, now)
    chan_send(req.reply, out)
    if s.bye then
        s.bye = false
        spawn(delayed_quit)
    end
end
server.stop()
launch.close_window()
sys.exit(0)
```

- [ ] **Passo 5: a página**

`web/index.html`:

```html
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Noxy Editor</title>
<link rel="stylesheet" href="/editor.css">
</head>
<body>
<div id="app">
  <aside id="sidebar">
    <div id="root-name"></div>
    <div id="tree"></div>
  </aside>
  <main id="main">
    <div id="tabbar">
      <div id="tabs"></div>
      <button id="run-btn" title="Executar (F5)">▶ Executar</button>
    </div>
    <div id="editor">
      <div id="gutter"></div>
      <div id="text"></div>
      <div id="cursor" class="hidden"></div>
      <div id="welcome">Abra um arquivo na árvore à esquerda.</div>
    </div>
    <div id="output" class="hidden">
      <div id="output-head"><span>Saída</span><button id="output-close" title="Fechar">×</button></div>
      <pre id="output-text"></pre>
    </div>
    <div id="status">
      <span id="status-left"></span>
      <span id="status-msg"></span>
      <span id="status-right"></span>
    </div>
  </main>
</div>
<div id="modal" class="hidden">
  <div id="modal-box">
    <div id="modal-text"></div>
    <div id="modal-buttons"></div>
  </div>
</div>
<textarea id="input" autocomplete="off" autocapitalize="off" spellcheck="false"></textarea>
<script src="/editor.js"></script>
</body>
</html>
```

`web/editor.css`:

```css
/* editor.css — tema escuro fixo (paleta Catppuccin Mocha). Cada kind de
   token e uma classe .k-<kind>; .sel marca o trecho selecionado. */
:root {
  --bg: #1e1e2e;
  --bg-side: #181825;
  --bg-bar: #181825;
  --bg-status: #11111b;
  --bg-hover: #313244;
  --fg: #cdd6f4;
  --fg-dim: #6c7086;
  --border: #313244;
  --cur-line: #262637;
  --sel: #45475a;
  --accent: #89b4fa;
  --cursor: #f5e0dc;
  --danger: #f38ba8;
  --k-keyword: #cba6f7;
  --k-type: #f9e2af;
  --k-ident: #cdd6f4;
  --k-call: #89b4fa;
  --k-number: #fab387;
  --k-string: #a6e3a1;
  --k-comment: #6c7086;
  --k-operator: #94e2d5;
  --k-punct: #9399b2;
  --k-space: #cdd6f4;
  --font-mono: ui-monospace, "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", monospace;
  --font-ui: system-ui, -apple-system, "Segoe UI", sans-serif;
  --line-h: 22px;
}

* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; background: var(--bg); color: var(--fg); font: 13px var(--font-ui); overflow: hidden; }
.hidden { display: none !important; }
button { font: inherit; color: inherit; background: none; border: none; cursor: pointer; }

#app { display: grid; grid-template-columns: 260px 1fr; height: 100vh; }

/* barra lateral */
#sidebar { background: var(--bg-side); border-right: 1px solid var(--border); overflow: auto; user-select: none; }
#root-name { padding: 10px 14px 6px; font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--fg-dim); }
.node { display: flex; align-items: center; height: 24px; padding-right: 8px; white-space: nowrap; cursor: pointer; }
.node:hover { background: var(--bg-hover); }
.node .chev { width: 16px; text-align: center; color: var(--fg-dim); font-size: 10px; }
.node.dir .name { color: var(--fg); }
.node.file .name { color: var(--fg); opacity: .9; }

/* area principal */
#main { display: grid; grid-template-rows: 36px minmax(0, 1fr) auto 24px; min-width: 0; }
#tabbar { display: flex; align-items: stretch; background: var(--bg-bar); border-bottom: 1px solid var(--border); }
#tabs { display: flex; flex: 1; min-width: 0; overflow-x: auto; }
.tab { display: flex; align-items: center; gap: 8px; padding: 0 10px 0 14px; border-right: 1px solid var(--border); color: var(--fg-dim); cursor: pointer; white-space: nowrap; }
.tab.active { background: var(--bg); color: var(--fg); box-shadow: inset 0 2px 0 var(--accent); }
.tab .close { width: 18px; height: 18px; line-height: 18px; text-align: center; border-radius: 4px; color: var(--fg-dim); }
.tab .close:hover { background: var(--bg-hover); color: var(--fg); }
#run-btn { padding: 0 14px; color: var(--k-string); }
#run-btn:hover { background: var(--bg-hover); }

#editor { position: relative; display: flex; overflow-x: auto; overflow-y: hidden; font: 14px var(--font-mono); }
#gutter { position: sticky; left: 0; z-index: 2; flex: none; width: 56px; padding-right: 12px; text-align: right; color: var(--fg-dim); background: var(--bg); user-select: none; }
#text { position: relative; flex: 1; min-width: max-content; }
.line, .gline { height: var(--line-h); line-height: var(--line-h); white-space: pre; tab-size: 4; }
.line { padding-left: 4px; }
.line.cur, .gline.cur { background: var(--cur-line); }
.gline.cur { color: var(--fg); }
#cursor { position: absolute; width: 2px; height: var(--line-h); background: var(--cursor); pointer-events: none; z-index: 3; animation: blink 1s steps(2, start) infinite; }
@keyframes blink { 50% { opacity: 0; } }
.sel { background: var(--sel); }
#welcome { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--fg-dim); font: 14px var(--font-ui); }

.k-keyword { color: var(--k-keyword); }
.k-type { color: var(--k-type); }
.k-ident { color: var(--k-ident); }
.k-call { color: var(--k-call); }
.k-number { color: var(--k-number); }
.k-string { color: var(--k-string); }
.k-comment { color: var(--k-comment); font-style: italic; }
.k-operator { color: var(--k-operator); }
.k-punct { color: var(--k-punct); }

/* painel de saida */
#output { border-top: 1px solid var(--border); background: var(--bg-side); max-height: 40vh; display: flex; flex-direction: column; }
#output-head { display: flex; justify-content: space-between; align-items: center; padding: 4px 12px; font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--fg-dim); }
#output-close { color: var(--fg-dim); font-size: 16px; line-height: 1; }
#output-text { margin: 0; padding: 4px 14px 10px; overflow: auto; font: 13px var(--font-mono); white-space: pre-wrap; }

/* barra de status */
#status { display: flex; align-items: center; gap: 16px; padding: 0 14px; background: var(--bg-status); border-top: 1px solid var(--border); font-size: 12px; color: var(--fg-dim); }
#status-msg { flex: 1; color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#status.dead #status-msg { color: var(--danger); }

/* modal */
#modal { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(0, 0, 0, .5); z-index: 10; }
#modal-box { background: var(--bg-side); border: 1px solid var(--border); border-radius: 8px; padding: 20px 24px; min-width: 320px; }
#modal-text { margin-bottom: 16px; }
#modal-buttons { display: flex; gap: 8px; justify-content: flex-end; }
#modal-buttons button { padding: 6px 14px; border-radius: 6px; background: var(--bg-hover); }
#modal-buttons button:first-child { background: var(--accent); color: var(--bg); }

/* a entrada invisivel que recebe o teclado */
#input { position: fixed; left: 0; top: 0; width: 1px; height: 1px; opacity: 0; border: none; padding: 0; resize: none; pointer-events: none; }
```

`web/editor.js`:

```javascript
// editor.js — o cliente burro: pinta o quadro que o Noxy manda e encaminha
// teclado e mouse como eventos. Nao guarda o texto. Uma requisicao em voo
// por vez; scroll acumula, drag e poll pendentes sao substituidos.
(() => {
  "use strict";
  const token = new URLSearchParams(location.search).get("t") || "";
  const $ = (id) => document.getElementById(id);
  const els = {
    rootName: $("root-name"), tree: $("tree"), tabs: $("tabs"), runBtn: $("run-btn"),
    editor: $("editor"), gutter: $("gutter"), text: $("text"), cursor: $("cursor"), welcome: $("welcome"),
    output: $("output"), outputText: $("output-text"), outputClose: $("output-close"),
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
      if (f.output.version > 0) {
        els.output.classList.remove("hidden");
        els.outputText.textContent = f.output.text + (f.output.running ? "\n…" : "");
        els.outputText.scrollTop = els.outputText.scrollHeight;
      }
    }
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
    els.text.replaceChildren(...lines);
    els.gutter.replaceChildren(...nums);
    placeCursor(v);
  }

  // placeCursor usa um Range no texto da linha: fica exato com tabs,
  // caracteres largos e qualquer fonte.
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
  const CTRL = { s: 1, z: 1, y: 1, a: 1, w: 1, "/": 1, q: 1, arrowleft: 1, arrowright: 1, home: 1, end: 1 };

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

  // ---- botoes, redimensionar, poll durante execucao, fechamento
  els.runBtn.addEventListener("mousedown", (e) => { e.preventDefault(); send({ kind: "run" }); });
  els.outputClose.addEventListener("mousedown", (e) => { e.preventDefault(); els.output.classList.add("hidden"); });
  new ResizeObserver(() => {
    const r = rowsNow();
    if (r !== rows) { rows = r; send({ kind: "poll" }); }
  }).observe(els.editor);
  setInterval(() => { if (frame && frame.output.running) send({ kind: "poll" }); }, 250);
  window.addEventListener("pagehide", () => {
    navigator.sendBeacon("/event?t=" + encodeURIComponent(token), JSON.stringify({ kind: "bye", rows, tree_version: treeVersion }));
  });

  rows = rowsNow();
  send({ kind: "init" });
})();
```

- [ ] **Passo 6: ver passar**

Run: `python3 tests/web_smoke.py`
Esperado: 23 linhas `ok`, uma linha `SAIDA: $ noxy exemplo.nx | [3:7] SyntaxError: ...` (o teste colou "X" sobre a assinatura da função antes do F5, e o erro do `noxy` no painel prova que salvou e rodou) e `OK: 0 falhas`. O screenshot fica em `tests/tmp/web_screenshot.png`: sidebar com `DEMO`, aba `exemplo.nx ●`, código colorido, painel `SAÍDA` e barra de status `Ln 6, Col 27`.

Run: `noxy tests/run.nx && noxy tests/protocol.nx`
Esperado: `141/141` e `10/10`.

- [ ] **Passo 7: rodar de verdade**

Run: `noxy editor.nx /home/estevao/Documentos/noxy_projects/zombie_apocalypse`
Esperado: uma janela do Chrome em modo app (sem barra de endereço) com a árvore do projeto; o terminal mostra `Noxy Editor em http://127.0.0.1:<porta>/?t=... (app)`. Abrir `zombie_apocalypse.nx`, digitar, Ctrl+Z, Ctrl+S, F5. Fechar a janela: o `noxy` encerra em até 3 s.

- [ ] **Passo 8: commit**

```bash
git add editor.nx src/launch.nx web/ tests/cdp.py tests/web_smoke.py
git commit -m "feat(web): cliente burro em HTML/CSS/JS, lancador em modo app e entrada do editor"
```


### Tarefa 13: Documentação do editor

**Files:**
- Create: `README.md`
- Create: `tests/MANUAL.md`

**Interfaces:**
- Consumes: nada.
- Produces: documentação do que existe até aqui; a Tarefa 16 não muda o README além do que já está escrito sobre a extensão.

- [ ] **Passo 1: README**

````markdown
# Noxy Editor

Um editor de código para arquivos Noxy, escrito em
[Noxy](https://github.com/estevaofon/noxy). Buffer, cursor, seleção, undo,
lexer, abas, árvore de arquivos e execução vivem no Noxy; o navegador só pinta
o que o Noxy manda e encaminha teclado e mouse. É um projeto de experimentação
da linguagem: o que ela não deu conta está em [docs/ACHADOS.md](docs/ACHADOS.md).

## Rodar

    noxy editor.nx [pasta | arquivo]

Sem argumento abre o diretório atual. Um arquivo abre a pasta dele com o
arquivo numa aba. A janela é a extensão
[noxy_webview](https://github.com/estevaofon/noxy_webview); se ela não
estiver disponível, o editor abre num navegador em modo app (Chrome, Chromium,
Brave ou Edge) ou no navegador padrão. Com `NOXY_EDITOR_NO_WINDOW=1` o editor
só imprime a URL, para desenvolver o cliente ou rodar o smoke.

## Atalhos

| Tecla | Ação |
|---|---|
| Setas, Home, End, PageUp, PageDown | mover; com Shift, selecionar |
| Ctrl+Setas | por palavra |
| Ctrl+Home, Ctrl+End | início e fim do documento |
| Ctrl+A | selecionar tudo |
| Ctrl+C, Ctrl+X, Ctrl+V | clipboard (linha inteira sem seleção) |
| Ctrl+Z, Ctrl+Y ou Ctrl+Shift+Z | desfazer, refazer |
| Ctrl+S | salvar |
| Ctrl+W | fechar a aba |
| Ctrl+/ | comentar ou descomentar |
| Tab, Shift+Tab | indentar, desindentar (quatro espaços) |
| Enter | nova linha com a indentação da atual |
| Escape | fechar o modal; senão colapsar a seleção |
| F5 | salvar e rodar o arquivo ativo (`noxy arquivo.nx`), saída no painel |
| Ctrl+Q | sair (pergunta se há abas com alterações) |

Mouse: clique posiciona, arraste seleciona, duplo clique seleciona a palavra,
clique no gutter seleciona a linha, roda rola. Fechar a janela pelo X encerra
sem perguntar: alterações não salvas se perdem (use Ctrl+Q).

## Como está organizado

A routine principal de `editor.nx` é a dona de todo o estado. O servidor HTTP
da stdlib (`src/server`) roda cada requisição numa routine própria e só
empacota o evento com um canal de resposta; o dono aplica e responde o quadro.

| Módulo | Responsabilidade |
|---|---|
| `src/document` | linhas de texto e posições em code points; inserir, apagar, trechos |
| `src/lexer` | tokenizador de Noxy, uma linha por vez |
| `src/history` | undo e redo por snapshot (copy-on-write faz a cópia ser rasa) |
| `src/editing` | cursor, seleção, scroll e as operações de edição de uma aba |
| `src/session` | raiz, abas, árvore, modal, abrir, salvar, fechar |
| `src/runner` | roda o arquivo numa task e recolhe a saída |
| `src/frame` | o quadro JSON com as linhas visíveis tokenizadas |
| `src/events` | do JSON do evento ao efeito na sessão, dentro de `call_result` |
| `src/server` | rotas, token e a ponte com o dono do estado |
| `src/launch` | janela pela extensão, fallback navegador |
| `web/` | o cliente: `index.html`, `editor.css`, `editor.js` |

Design e plano em `docs/superpowers/`.

## Testes

    noxy tests/run.nx            # o núcleo inteiro, sem navegador
    noxy tests/protocol.nx       # servidor + cliente HTTP in-process
    python3 tests/web_smoke.py   # o cliente web num Chrome headless (precisa de google-chrome)

`tests/MANUAL.md` lista o que só se confere à mão.

## Limitações da v1

Sem busca, paleta de comandos, temas, git, terminal ou minimap. Um programa
que não termina não pode ser interrompido. Fechar pelo X perde alterações não
salvas. Arquivos com `\r\n` são salvos com `\n`. Testado no Linux.
````

- [ ] **Passo 2: MANUAL**

````markdown
# Testes manuais

O que nem `tests/run.nx`, `tests/protocol.nx` nem `tests/web_smoke.py`
provam. Conferir a cada release, com a extensão instalada:

- [ ] `noxy editor.nx .` abre uma janela nativa com o título "Noxy Editor" e a árvore da pasta.
- [ ] Abrir um `.nx` muda o título da janela para `nome.nx — Noxy Editor`; editar acrescenta `●`.
- [ ] Acentos pelo teclado real: `´` + `e` dá `é`; `~` + `a` dá `ã`; `ç` direto. Com IME (se houver), a composição chega inteira.
- [ ] Ctrl+C no editor e Ctrl+V em outro programa colam o texto; Ctrl+V no editor cola o que veio de fora.
- [ ] Redimensionar a janela mantém o cursor visível e o número de linhas acompanha.
- [ ] Linha mais larga que a janela rola horizontalmente e o cursor acompanha.
- [ ] Ctrl+Q com aba suja abre o modal; "Salvar tudo" grava e fecha a janela; o processo `noxy` termina (`pgrep noxy` vazio).
- [ ] Fechar pelo X encerra o processo sem órfãos (`pgrep -f noxy-plugin-webview` vazio).
- [ ] Sem a extensão (`mv bin bin.off` no package), o editor avisa no terminal e abre no navegador em modo app; fechar a janela do navegador encerra o `noxy` em até 3 s.
- [ ] `NOXY_WEBVIEW_DEBUG=1 noxy editor.nx .` abre com o inspetor do WebKit disponível.
````

- [ ] **Passo 3: commit**

```bash
git add README.md tests/MANUAL.md
git commit -m "docs: README do editor e checklist manual"
```


### Tarefa 14: noxy_webview — repositório e a máquina de estados da janela

**Files:**
- Create: `/home/estevao/Documentos/noxy_projects/noxy_webview/go.mod`
- Create: `window/window.go`
- Create: `window/window_test.go`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nada.
- Produces: pacote `window`: `Native` (interface), `OpenRequest`, `State` com `New()`, `Open(ctx, req)`, `OpenRequests()`, `Serve(req, create)`, `Wait(ctx)`, `Close()`, `SetTitle(title)`; erros `ErrAlreadyOpen`, `ErrClosed`, `ErrNotOpen`.

Tudo nesta tarefa roda em `/home/estevao/Documentos/noxy_projects/noxy_webview`.

- [ ] **Passo 1: repositório e módulo**

```bash
mkdir -p /home/estevao/Documentos/noxy_projects/noxy_webview/window && cd /home/estevao/Documentos/noxy_projects/noxy_webview && git init -q -b main
```

`go.mod` (os `require` entram na Tarefa 15 com `go mod tidy`):

```
module github.com/estevaofon/noxy_webview

go 1.25.0
```

`.gitignore`:

```
bin/
dist/
```

- [ ] **Passo 2: o teste que falha**

```go
package window

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"
)

// fake e uma janela sem tela: Run bloqueia ate Terminate; Dispatch executa
// na hora, como se ja estivesse na thread principal.
type fake struct {
	mu     sync.Mutex
	titles []string
	size   [2]int
	url    string
	quit   chan struct{}
	once   sync.Once
	killed bool
}

func newFake() *fake { return &fake{quit: make(chan struct{})} }

func (f *fake) SetTitle(t string)  { f.mu.Lock(); f.titles = append(f.titles, t); f.mu.Unlock() }
func (f *fake) SetSize(w, h int)   { f.size = [2]int{w, h} }
func (f *fake) Navigate(u string)  { f.url = u }
func (f *fake) Run()               { <-f.quit }
func (f *fake) Terminate()         { f.once.Do(func() { close(f.quit) }) }
func (f *fake) Dispatch(fn func()) { fn() }
func (f *fake) Destroy()           { f.killed = true }

// start sobe a thread principal falsa: espera o pedido e serve.
func start(t *testing.T, s *State, f *fake) {
	t.Helper()
	go func() {
		req := <-s.OpenRequests()
		s.Serve(req, func() Native { return f })
	}()
}

func TestBeforeOpenEverythingFails(t *testing.T) {
	s := New()
	if err := s.Wait(context.Background()); !errors.Is(err, ErrNotOpen) {
		t.Fatalf("Wait antes de Open: %v", err)
	}
	if err := s.Close(); !errors.Is(err, ErrNotOpen) {
		t.Fatalf("Close antes de Open: %v", err)
	}
	if err := s.SetTitle("x"); !errors.Is(err, ErrNotOpen) {
		t.Fatalf("SetTitle antes de Open: %v", err)
	}
}

func TestOpenConfiguresAndWaitReturnsOnClose(t *testing.T) {
	s, f := New(), newFake()
	start(t, s, f)
	req := OpenRequest{Title: "Noxy Editor", Width: 1200, Height: 800, URL: "http://127.0.0.1:1/?t=x"}
	if err := s.Open(context.Background(), req); err != nil {
		t.Fatalf("Open: %v", err)
	}
	if f.titles[0] != "Noxy Editor" || f.size != [2]int{1200, 800} || f.url != req.URL {
		t.Fatalf("janela configurada errado: %+v %v %q", f.titles, f.size, f.url)
	}
	if err := s.Open(context.Background(), req); !errors.Is(err, ErrAlreadyOpen) {
		t.Fatalf("segundo Open: %v", err)
	}
	if err := s.SetTitle("main.nx — Noxy Editor"); err != nil || f.titles[len(f.titles)-1] != "main.nx — Noxy Editor" {
		t.Fatalf("SetTitle: %v %v", err, f.titles)
	}
	waited := make(chan error, 1)
	go func() { waited <- s.Wait(context.Background()) }()
	select {
	case err := <-waited:
		t.Fatalf("Wait voltou antes de fechar: %v", err)
	case <-time.After(50 * time.Millisecond):
	}
	if err := s.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}
	select {
	case err := <-waited:
		if err != nil {
			t.Fatalf("Wait depois de Close: %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("Wait nao destravou com Close")
	}
	f.mu.Lock()
	killed := f.killed
	f.mu.Unlock()
	if !killed {
		t.Fatal("Destroy nao foi chamado antes de Wait voltar")
	}
	if err := s.Close(); err != nil {
		t.Fatalf("Close depois de fechada deve ser no-op: %v", err)
	}
	if err := s.SetTitle("x"); !errors.Is(err, ErrClosed) {
		t.Fatalf("SetTitle depois de fechada: %v", err)
	}
	if err := s.Open(context.Background(), req); !errors.Is(err, ErrClosed) {
		t.Fatalf("Open depois de fechada: %v", err)
	}
	if err := s.Wait(context.Background()); err != nil {
		t.Fatalf("Wait depois de fechada volta na hora: %v", err)
	}
}

func TestWaitHonoursContext(t *testing.T) {
	s, f := New(), newFake()
	start(t, s, f)
	if err := s.Open(context.Background(), OpenRequest{Title: "t", Width: 1, Height: 1, URL: "u"}); err != nil {
		t.Fatalf("Open: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	if err := s.Wait(ctx); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("Wait com contexto expirado: %v", err)
	}
	f.Terminate()
}

func TestOpenHonoursContextWhenMainNeverServes(t *testing.T) {
	s := New()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	if err := s.Open(ctx, OpenRequest{Title: "t", Width: 1, Height: 1, URL: "u"}); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("Open sem thread principal: %v", err)
	}
}
```

- [ ] **Passo 3: ver falhar**

Run: `go test ./window/`
Esperado: erros de compilação `undefined: New`, `undefined: Native`, ...

- [ ] **Passo 4: implementar**

```go
// Package window guarda o estado da janela unica do processo sem tocar na
// biblioteca webview: main.go injeta a implementacao nativa e os testes
// injetam uma falsa. Regras: uma janela por processo; open repetido ou
// depois de fechada e erro; wait, close e set_title antes de open sao erro;
// close depois de fechada e no-op.
package window

import (
	"context"
	"errors"
	"sync"
)

// Native e o que a janela nativa precisa oferecer; main.go adapta
// webview.WebView a esta interface.
type Native interface {
	SetTitle(title string)
	SetSize(w, h int)
	Navigate(url string)
	Run()
	Terminate()
	Dispatch(f func())
	Destroy()
}

// OpenRequest e o pedido que a thread principal espera para criar a janela.
type OpenRequest struct {
	Title         string
	Width, Height int
	URL           string
}

var (
	ErrAlreadyOpen = errors.New("window already open")
	ErrClosed      = errors.New("window was closed")
	ErrNotOpen     = errors.New("window is not open: call webview.open first")
)

// State e a maquina de estados: aberta, pronta (native criado) e fechada.
type State struct {
	mu      sync.Mutex
	opened  bool
	closed  bool
	native  Native
	openReq chan OpenRequest // consumido pela thread principal
	ready   chan struct{}    // fechado quando native existe, antes de Run
	done    chan struct{}    // fechado quando Run volta
}

func New() *State {
	return &State{openReq: make(chan OpenRequest, 1), ready: make(chan struct{}), done: make(chan struct{})}
}

// Open e o handler de webview_open: entrega o pedido a thread principal e
// espera a janela existir, ou o contexto acabar.
func (s *State) Open(ctx context.Context, req OpenRequest) error {
	s.mu.Lock()
	if s.closed {
		s.mu.Unlock()
		return ErrClosed
	}
	if s.opened {
		s.mu.Unlock()
		return ErrAlreadyOpen
	}
	s.opened = true
	s.mu.Unlock()
	s.openReq <- req
	select {
	case <-s.ready:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// OpenRequests e lido pela thread principal: o unico pedido de abertura.
func (s *State) OpenRequests() <-chan OpenRequest { return s.openReq }

// Serve roda na thread principal: cria a janela com create, marca pronta,
// roda o loop ate a janela fechar, destroi a janela e so entao libera Wait.
// Bloqueia ate o fim.
func (s *State) Serve(req OpenRequest, create func() Native) {
	n := create()
	n.SetTitle(req.Title)
	n.SetSize(req.Width, req.Height)
	n.Navigate(req.URL)
	s.mu.Lock()
	s.native = n
	s.mu.Unlock()
	close(s.ready)
	n.Run()
	s.mu.Lock()
	s.closed = true // a partir daqui Close e no-op e SetTitle e erro
	s.mu.Unlock()
	n.Destroy()
	close(s.done) // quem acorda em Wait ja ve a janela destruida
}

// Wait e o handler de webview_wait: bloqueia ate a janela fechar.
func (s *State) Wait(ctx context.Context) error {
	s.mu.Lock()
	opened := s.opened
	s.mu.Unlock()
	if !opened {
		return ErrNotOpen
	}
	select {
	case <-s.done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// live espera a janela existir e devolve o native, ou nil se ja fechou.
func (s *State) live() (Native, error) {
	s.mu.Lock()
	opened := s.opened
	s.mu.Unlock()
	if !opened {
		return nil, ErrNotOpen
	}
	<-s.ready
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil, nil
	}
	return s.native, nil
}

// Close e o handler de webview_close: pede o fim do loop; no-op se ja fechou.
// Terminate e seguro de qualquer thread, mas Dispatch mantem tudo na UI.
func (s *State) Close() error {
	n, err := s.live()
	if err != nil || n == nil {
		return err
	}
	n.Dispatch(n.Terminate)
	return nil
}

// SetTitle e o handler de webview_set_title; erro depois de fechada.
func (s *State) SetTitle(title string) error {
	n, err := s.live()
	if err != nil {
		return err
	}
	if n == nil {
		return ErrClosed
	}
	n.Dispatch(func() { n.SetTitle(title) })
	return nil
}
```

- [ ] **Passo 5: ver passar**

Run: `gofmt -l . && go vet ./window/ && go test ./window/ -count=1 -race`
Esperado: `gofmt` sem saída, `ok github.com/estevaofon/noxy_webview/window`.

- [ ] **Passo 6: commit**

```bash
git add go.mod .gitignore window/
git commit -m "feat(window): maquina de estados da janela unica, sem dependencia da biblioteca webview"
```


### Tarefa 15: noxy_webview — o processo, o manifesto, o wrapper e o build

**Files:**
- Create: `main.go`, `noxy_ext.toml`, `noxy_webview.nx`, `noxy.mod`, `examples/smoke.nx`, `release/build.sh`, `.github/workflows/release.yml`, `README.md`
- Modify: `go.mod` (via `go mod tidy`)

**Interfaces:**
- Consumes: `window.*`.
- Produces: extensão `webview` com `webview_open(title, width, height, url)`, `webview_wait()`, `webview_close()`, `webview_set_title(title)`; wrapper `noxy_webview.nx` com `open`, `wait`, `close`, `set_title`; binário em `bin/noxy-plugin-webview-linux-amd64`; o package linkado em `Noxy-Editor/noxy_libs/github_com/estevaofon/noxy_webview`.

- [ ] **Passo 1: `main.go`**

```go
// noxy_webview — uma janela nativa para uma pagina local, empacotada como
// extensao por processo do Noxy (kind = "process" em noxy_ext.toml).
//
// O SDK (noxyplugin) serve stdin/stdout numa goroutine; a thread principal
// espera webview_open e entao roda o loop da janela, que exige a main
// (webview_go trava a thread principal no init). Uma janela por processo.
package main

import (
	"context"
	"fmt"
	"os"

	"github.com/estevaofon/noxy/sdk/noxyplugin"
	webview "github.com/webview/webview_go"

	"github.com/estevaofon/noxy_webview/window"
)

// native adapta webview.WebView a window.Native: SetSize sem hint.
type native struct{ webview.WebView }

func (n native) SetSize(w, h int) { n.WebView.SetSize(w, h, webview.HintNone) }

func main() {
	st := window.New()
	p := noxyplugin.New()
	p.Handle("webview_open", noxyplugin.Func4(func(ctx context.Context, title string, width, height int64, url string) (any, error) {
		if width <= 0 || height <= 0 {
			return nil, fmt.Errorf("width and height must be positive, got %dx%d", width, height)
		}
		if url == "" {
			return nil, fmt.Errorf("url must not be empty")
		}
		return nil, st.Open(ctx, window.OpenRequest{Title: title, Width: int(width), Height: int(height), URL: url})
	}))
	p.Handle("webview_wait", noxyplugin.Func0(func(ctx context.Context) (any, error) { return nil, st.Wait(ctx) }))
	p.Handle("webview_close", noxyplugin.Func0(func(ctx context.Context) (any, error) { return nil, st.Close() }))
	p.Handle("webview_set_title", noxyplugin.Func1(func(ctx context.Context, title string) (any, error) { return nil, st.SetTitle(title) }))
	go p.Main() // sai do processo (os.Exit) quando o host fecha o stdin

	req := <-st.OpenRequests()
	debug := os.Getenv("NOXY_WEBVIEW_DEBUG") == "1" // inspetor do WebKit
	st.Serve(req, func() window.Native { return native{webview.New(debug)} })
	select {} // a janela fechou; o processo vive ate o host fechar o stdin
}
```

- [ ] **Passo 2: manifesto, wrapper e `noxy.mod`**

`noxy_ext.toml`:

```toml
name = "webview"
abi = 1
kind = "process"
min_noxy = "0.25.0"
concurrency = "concurrent"      # wait bloqueia; close e set_title precisam passar
capabilities = ["display"]

[binaries]                      # release assets; noxy --get baixa o do seu OS/arch
linux-amd64   = "noxy-plugin-webview-linux-amd64"
windows-amd64 = "noxy-plugin-webview-windows-amd64.exe"
darwin-amd64  = "noxy-plugin-webview-darwin-amd64"
darwin-arm64  = "noxy-plugin-webview-darwin-arm64"

[[export]]
name = "webview_open"           # (title, width, height, url): abre a unica janela
params = ["string", "int", "int", "string"]
returns = "void"
stateful = true

[[export]]
name = "webview_wait"           # bloqueia ate a janela fechar (X ou close)
params = []
returns = "void"
timeout_ms = 0

[[export]]
name = "webview_close"          # pede o fechamento; no-op depois de fechada
params = []
returns = "void"

[[export]]
name = "webview_set_title"      # (title): muda o titulo da janela aberta
params = ["string"]
returns = "void"
```

`noxy_webview.nx`:

```noxy
// noxy_webview.nx — wrapper tipado da extensao `webview`: uma janela nativa
// (WebKitGTK no Linux, WebView2 no Windows, WKWebView no macOS) apontando
// para uma URL. Os nativos webview_open, webview_wait, webview_close e
// webview_set_title sao registrados pela VM a partir de noxy_ext.toml; o
// binario em bin/ comeca na primeira chamada. Uma janela por processo.
// Toda falha e um erro de runtime `extension 'webview' failed: <motivo>`,
// capturavel com call_result.

// open abre a janela com o titulo e o tamanho dados, carregando url.
// Erros: janela ja aberta, janela ja fechada, tamanho nao positivo.
func open(title: string, width: int, height: int, url: string) -> void
    webview_open(title, width, height, url)
end

// wait bloqueia ate a janela fechar, pelo X ou por close.
func wait() -> void
    webview_wait()
end

// close pede o fechamento; idempotente depois de fechada.
func close() -> void
    webview_close()
end

// set_title muda o titulo da janela aberta.
func set_title(title: string) -> void
    webview_set_title(title)
end
```

`noxy.mod`:

```
module noxy_webview

noxy v0.25.0
```

- [ ] **Passo 3: smoke, build e workflow**

`examples/smoke.nx`:

```noxy
// examples/smoke.nx — abre uma pagina data: por meio segundo, fecha sozinho
// e imprime ok. Roda a partir de um projeto que tenha a extensao em
// noxy_libs (ou deste checkout linkado la):
//     noxy examples/smoke.nx
use sys
use github_com.estevaofon.noxy_webview.noxy_webview as webview

webview.open("noxy_webview smoke", 480, 320, "data:text/html,<h1 style='font-family:sans-serif'>ok</h1>")
sys.sleep(500)
webview.set_title("fechando")
webview.close()
webview.wait()
print("ok")
```

`release/build.sh`:

```sh
#!/usr/bin/env sh
# Builds this platform's plugin binary into dist/ and its sha256 line. A
# biblioteca webview e cgo em todo OS, entao cada OS compila o seu: o
# workflow roda isto num runner por plataforma e junta os checksums.
#
# No Linux, webview_go ainda pede webkit2gtk-4.0 no pkg-config (PR
# webview_go#62 troca para 4.1, ainda aberto) e as distros atuais so tem a
# 4.1. O shim abaixo cria um diretorio temporario onde os nomes 4.0 apontam
# para os arquivos .pc da 4.1, e o poe no PKG_CONFIG_PATH so para este build.
set -eu
NAME="${1:?usage: build.sh <extension-name> [GOARCH]}"
ARCH="${2:-$(go env GOARCH)}"
OS="$(go env GOOS)"
ext=""; [ "$OS" = windows ] && ext=".exe"
if [ "$OS" = linux ] && ! pkg-config --exists webkit2gtk-4.0 && pkg-config --exists webkit2gtk-4.1; then
  shim="$(mktemp -d)"
  for lib in webkit2gtk javascriptcoregtk; do
    ln -s "$(pkg-config --variable=pcfiledir "$lib-4.1")/$lib-4.1.pc" "$shim/$lib-4.0.pc"
  done
  export PKG_CONFIG_PATH="$shim${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
fi
mkdir -p dist
CGO_ENABLED=1 GOARCH="$ARCH" go build -trimpath -ldflags=-s -o "dist/noxy-plugin-$NAME-$OS-$ARCH$ext" .
(cd dist && sha256sum -- "noxy-plugin-$NAME-$OS-$ARCH$ext" > "checksums-$OS-$ARCH.txt")
echo "dist/noxy-plugin-$NAME-$OS-$ARCH$ext"
```

`.github/workflows/release.yml`:

```yaml
# Release da extensao noxy_webview. A biblioteca webview e cgo em todo OS,
# entao cada plataforma compila nativamente; o ultimo job junta os
# checksums em checksums.txt e publica tudo como assets do release da tag,
# com os nomes listados em [binaries] de noxy_ext.toml.

name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: windows-latest
            arch: amd64
          - os: ubuntu-latest
            arch: amd64
          - os: macos-latest
            arch: arm64
          - os: macos-latest
            arch: amd64
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version-file: go.mod
      - if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y libgtk-3-dev libwebkit2gtk-4.1-dev
      - run: sh release/build.sh webview ${{ matrix.arch }}
        shell: bash
      - uses: actions/upload-artifact@v4
        with:
          name: dist-${{ matrix.os }}-${{ matrix.arch }}
          path: dist/*

  release:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          path: dist
          merge-multiple: true
      - run: cd dist && cat checksums-*.txt > checksums.txt && rm checksums-*.txt && ls -l
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/*
```

- [ ] **Passo 4: dependências Go**

Run: `go mod tidy`
Esperado: `go.mod` ganha `require github.com/estevaofon/noxy/sdk/noxyplugin v0.1.0` e `require github.com/webview/webview_go v0.0.0-20240831120633-6173450d4dd6`; `go.sum` criado. (`go mod tidy` não precisa dos headers do WebKit.)

- [ ] **Passo 5: os headers do WebKit (ação do usuário)**

Peça ao usuário para rodar, no terminal dele (`! sudo apt install ...` no Claude Code):

```bash
sudo apt install -y libgtk-3-dev libwebkit2gtk-4.1-dev
```

Confira: `pkg-config --modversion webkit2gtk-4.1 gtk+-3.0` imprime duas versões.

- [ ] **Passo 6: compilar**

Run: `sh release/build.sh webview && mkdir -p bin && cp dist/noxy-plugin-webview-linux-amd64 bin/ && ls -la bin/`
Esperado: `dist/noxy-plugin-webview-linux-amd64` impresso e o binário em `bin/` (dezenas de MB). Se o build falhar com erros de API do WebKit dentro de `webview.h`, a alternativa é `go mod edit -replace github.com/webview/webview_go=github.com/lvlrt/webview_go@patch-1 && go mod tidy` (o fork do PR #62) e rodar o build de novo.

Run: `./bin/noxy-plugin-webview-linux-amd64`
Esperado: `this program is a Noxy extension; install it with 'noxy --get'` e código 2 (o SDK recusa rodar num terminal).

- [ ] **Passo 7: linkar no editor e rodar o smoke**

```bash
mkdir -p /home/estevao/Documentos/noxy_projects/Noxy-Editor/noxy_libs/github_com/estevaofon
ln -sfn /home/estevao/Documentos/noxy_projects/noxy_webview /home/estevao/Documentos/noxy_projects/Noxy-Editor/noxy_libs/github_com/estevaofon/noxy_webview
cd /home/estevao/Documentos/noxy_projects/Noxy-Editor && noxy noxy_libs/github_com/estevaofon/noxy_webview/examples/smoke.nx
```

Esperado: um aviso único de confiança da VM (sem entrada em `noxy.sum`), uma janela pequena com `ok` por meio segundo, título mudando para `fechando`, e `ok` no terminal. `pgrep -f noxy-plugin-webview` vazio depois.

- [ ] **Passo 8: README e commit**

````markdown
# noxy_webview

Uma janela nativa para uma página local, como extensão por processo do
[Noxy](https://github.com/estevaofon/noxy): WebKitGTK no Linux, WebView2 no
Windows, WKWebView no macOS, via [webview_go](https://github.com/webview/webview_go).
Feita para o [Noxy Editor](https://github.com/estevaofon/Noxy-Editor), serve
para qualquer programa Noxy que sirva uma página em `127.0.0.1` e queira uma
janela sem barra de endereço.

## Instalação

    noxy --get github.com/estevaofon/noxy_webview

`noxy --get` baixa o binário da sua plataforma para `bin/` e grava os hashes
em `noxy.sum`. Requer Noxy 0.25.0 ou mais novo. Em runtime, o Linux precisa
de `libwebkit2gtk-4.1` (presente em desktops GNOME); o Windows, do runtime
WebView2 (incluído no Windows 11).

## API

```noxy
use github_com.estevaofon.noxy_webview.noxy_webview as webview

webview.open("Minha página", 1200, 800, "http://127.0.0.1:8080/")
webview.set_title("Minha página — carregada")
webview.wait()          // bloqueia até a janela fechar
```

| Função | Efeito |
|---|---|
| `open(title, width, height, url)` | Abre a única janela do processo. Erro se já aberta, já fechada ou tamanho não positivo |
| `wait()` | Bloqueia até a janela fechar, pelo X ou por `close` |
| `close()` | Pede o fechamento; no-op depois de fechada |
| `set_title(title)` | Muda o título; erro depois de fechada |

Toda falha é um erro de runtime `extension 'webview' failed: <motivo>`,
capturável com `call_result`. `NOXY_WEBVIEW_DEBUG=1` no ambiente do `noxy`
abre a janela com o inspetor do WebKit.

## Ciclo de vida

O SDK (`noxyplugin`) serve stdin/stdout numa goroutine; a thread principal
espera `open` e roda o loop da janela, que exige a main. Quando o loop volta,
a janela é destruída e todo `wait` pendente retorna. O processo vive até o
host fechar o stdin. A máquina de estados fica no pacote `window/`, sem
dependência da biblioteca webview, para `go test ./window/` rodar em qualquer
máquina.

## Compilar localmente

Linux:

    sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev
    sh release/build.sh webview
    mkdir -p bin && cp dist/noxy-plugin-webview-linux-amd64 bin/

O `webview_go` publicado ainda pede `webkit2gtk-4.0` no `pkg-config`, que as
distros atuais não têm (PR webview_go#62, aberto). `release/build.sh` contorna
com um diretório temporário onde `webkit2gtk-4.0.pc` e
`javascriptcoregtk-4.0.pc` apontam para os arquivos 4.1, posto no
`PKG_CONFIG_PATH` só durante o build.

Para usar um checkout num projeto sem release, linke o diretório em
`<projeto>/noxy_libs/github_com/estevaofon/noxy_webview`; sem entrada em
`noxy.sum` a VM avisa uma vez e roda. Então `noxy examples/smoke.nx` (a partir
do projeto) abre uma janela por meio segundo e imprime `ok`.

## Release

Push de uma tag `vX.Y.Z`. O workflow compila em um runner por plataforma
(cgo em todas), junta os checksums em `checksums.txt` e publica os assets com
os nomes de `[binaries]` em `noxy_ext.toml`.
````

```bash
cd /home/estevao/Documentos/noxy_projects/noxy_webview
git add main.go noxy_ext.toml noxy_webview.nx noxy.mod go.mod go.sum examples/ release/ .github/ README.md
git commit -m "feat: extensao por processo com open, wait, close e set_title sobre webview_go"
```


### Tarefa 16: Integrar a janela nativa no editor

**Files:**
- Modify: `src/launch.nx` (substituir pela versão com a extensão)
- Modify: `editor.nx` (routine que espera a janela e o título)

**Interfaces:**
- Consumes: wrapper `noxy_webview` (Tarefa 15), `frame.title_of`.
- Produces: `launch.open_window` tenta a extensão antes do navegador; `launch.wait_window()`, `launch.set_title(title)`, `launch.close_window()`; `editor.nx` encerra quando a janela fecha e atualiza o título.

Roda em `/home/estevao/Documentos/noxy_projects/Noxy-Editor`, com o link da Tarefa 15 no lugar.

- [ ] **Passo 1: `src/launch.nx` final**

```noxy
// src/launch.nx — abre a janela do editor. Primeiro a extensao noxy_webview
// (janela nativa); se ela falhar — sem binario, sem WebKitGTK, processo
// morto — um navegador em modo app (janela sem barra de endereco), e por
// ultimo o navegador padrao. mode guarda o que deu certo.
use sys
use strings select replace
use errors select *
use github_com.estevaofon.noxy_webview.noxy_webview as webview

let BROWSERS: string[] = ["google-chrome", "chromium", "chromium-browser", "brave-browser", "microsoft-edge"]
let mode: string = ""       // "webview", "app", "browser" ou ""

func has_command(name: string) -> bool
    return sys.exec("command -v " + name + " >/dev/null 2>&1").exit_code == 0
end

func shell_quote(s: string) -> string
    return "'" + replace(s, "'", "'\\''") + "'"
end

// open_browser devolve "app" (janela sem barra), "browser" ou "".
func open_browser(url: string) -> string
    let q: string = shell_quote(url)
    for b in BROWSERS do
        if has_command(b) then
            sys.exec(b + " --app=" + q + " >/dev/null 2>&1 &")
            return "app"
        end
    end
    if sys.os() == "darwin" then
        sys.exec("open " + q)
        return "browser"
    end
    if has_command("xdg-open") then
        sys.exec("xdg-open " + q + " >/dev/null 2>&1 &")
        return "browser"
    end
    return ""
end

// open_window tenta a extensao e cai para o navegador; devolve o modo.
func open_window(url: string) -> string
    let r = call_result(webview.open, "Noxy Editor", 1200, 800, url)
    if r.ok then
        mode = "webview"
        return mode
    end
    eprint("janela pela extensao indisponivel: " + r.failure.message + "; abrindo no navegador")
    mode = open_browser(url)
    return mode
end

// wait_window bloqueia ate a janela da extensao fechar; nos outros modos
// volta na hora.
func wait_window() -> void
    if mode == "webview" then
        let r = call_result(webview.wait)
        if !r.ok then
            eprint("janela: " + r.failure.message)
        end
    end
end

func set_title(title: string) -> void
    if mode == "webview" then
        call_result(webview.set_title, title)
    end
end

func close_window() -> void
    if mode == "webview" then
        call_result(webview.close)
    end
end
```

- [ ] **Passo 2: `editor.nx` final**

As diferenças para a Tarefa 12: `use src.frame as frame`, a routine `window_watch` que manda `quit` quando `wait_window` volta, e o título comparado a cada evento.

```noxy
// editor.nx — Noxy Editor. Um editor de codigo para arquivos Noxy, escrito
// em Noxy: o navegador so pinta e encaminha entrada.
//     noxy editor.nx [pasta | arquivo]      (sem argumento: o diretorio atual)
// A routine principal e a dona do estado: recebe os eventos que o servidor
// (src/server, em routines da stdlib) poe no canal, aplica na sessao e
// responde o quadro. A janela e a extensao noxy_webview, com fallback para
// o navegador em modo app (src/launch).
use sys
use io
use uuid
use strings select starts_with, substring, ends_with
use src.session as session
use src.events as events
use src.server as server
use src.launch as launch
use src.frame as frame

func absolute(path: string) -> string
    if starts_with(path, "/") then
        return path
    end
    if path == "." then
        return sys.getcwd()
    end
    if starts_with(path, "./") then
        return sys.getcwd() + "/" + substring(path, 2, length(path))
    end
    return sys.getcwd() + "/" + path
end

func strip_slash(path: string) -> string
    if length(path) > 1 && ends_with(path, "/") then
        return substring(path, 0, length(path) - 1)
    end
    return path
end

let args: string[] = sys.argv()
let editor_dir: string = session.dirname(absolute(args[1]))
let target: string = sys.getcwd()
if length(args) > 2 then
    target = strip_slash(absolute(args[2]))
end
let first_file: string = ""
let st: io.FileInfo = io.stat(target)
if !st.exists then
    eprint("nao encontrei " + target)
    sys.exit(1)
end
if !st.is_dir then
    first_file = target
    target = session.dirname(target)
end

let s: session.Session = session.new_session(target)
if !session.load(ref s) then
    eprint("nao consegui ler a pasta " + target)
    sys.exit(1)
end
if first_file != "" then
    session.open_file(ref s, first_file)
end

let port: int = server.start(editor_dir + "/web", uuid.uuid4())
if port == 0 then
    eprint("nao consegui abrir uma porta em 127.0.0.1")
    sys.exit(1)
end
let url: string = "http://127.0.0.1:" + to_str(port) + "/?t=" + server.token
let mode: string = "none"
if !sys.getenv("NOXY_EDITOR_NO_WINDOW").ok then
    mode = launch.open_window(url)
end
if mode == "" then
    eprint("nao consegui abrir uma janela; abra " + url + " num navegador")
else
    eprint("Noxy Editor em " + url + " (" + mode + ")")
end

// window_watch: a janela da extensao fechou (X ou close); encerra o editor.
func window_watch() -> void
    launch.wait_window()
    let reply: chan any = make_chan(1)
    chan_send(server.inbox, server.Request("{\"kind\":\"quit\"}", reply))
    chan_recv(reply)
end

if mode == "webview" then
    spawn(window_watch)
end

// delayed_quit: a pagina avisou que esta fechando; se em 3 s nao chegar
// evento novo (um reload manda init de novo), o editor encerra.
func delayed_quit() -> void
    sys.sleep(3000)
    let reply: chan any = make_chan(1)
    chan_send(server.inbox, server.Request("{\"kind\":\"quit_if_idle\"}", reply))
    chan_recv(reply)
end

let last_title: string = ""
while !s.quitting do
    let r: any = chan_recv(server.inbox)
    let req: server.Request = r
    let now: int = time_now()
    let out: string = events.dispatch(ref s, req.body, now)
    chan_send(req.reply, out)
    if s.bye then
        s.bye = false
        spawn(delayed_quit)
    end
    let title: string = frame.title_of(ref s)
    if title != last_title then
        last_title = title
        launch.set_title(title)
    end
end
server.stop()
launch.close_window()
sys.exit(0)
```

- [ ] **Passo 3: as suítes continuam passando**

Run: `noxy tests/run.nx && noxy tests/protocol.nx && python3 tests/web_smoke.py`
Esperado: `141/141`, `10/10`, `OK: 0 falhas` (o smoke usa `NOXY_EDITOR_NO_WINDOW=1`, então nunca toca a extensão).

- [ ] **Passo 4: a janela de verdade**

Run: `noxy editor.nx /home/estevao/Documentos/noxy_projects/zombie_apocalypse`
Esperado: janela nativa `Noxy Editor` com a árvore; o terminal diz `(webview)`. Abrir `zombie_apocalypse.nx` muda o título da janela para `zombie_apocalypse.nx — Noxy Editor`; digitar acrescenta `●`; Ctrl+Z; Ctrl+S; F5 mostra a saída (o jogo abre a janela dele; feche-a). Fechar pelo X: o terminal volta ao prompt e `pgrep -f "noxy editor.nx"` e `pgrep -f noxy-plugin-webview` ficam vazios.

Run: `mv noxy_libs/github_com/estevaofon/noxy_webview/bin noxy_libs/github_com/estevaofon/noxy_webview/bin.off && noxy editor.nx . ; mv noxy_libs/github_com/estevaofon/noxy_webview/bin.off noxy_libs/github_com/estevaofon/noxy_webview/bin`
Esperado: `janela pela extensao indisponivel: extension 'webview' trapped: ...; abrindo no navegador` e a janela do Chrome em modo app; fechar a janela encerra o editor em até 3 s.

- [ ] **Passo 5: `tests/MANUAL.md` conferido**

Passe pela lista de `tests/MANUAL.md` e marque cada item; o que falhar volta para a tarefa dona antes do commit.

- [ ] **Passo 6: commit**

```bash
git add src/launch.nx editor.nx
git commit -m "feat(launch): janela nativa pela extensao noxy_webview com fallback para o navegador"
```

