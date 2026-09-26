# Noxy Editor — Design

Data: 2026-09-25
Projetos: `Noxy-Editor` (o editor, em Noxy) e `noxy_webview` (a extensão de
janela, em Go)
Plataforma: Noxy v0.25.1; SDK `github.com/estevaofon/noxy/sdk/noxyplugin`
v0.1.0; `github.com/webview/webview_go`
Referência: [Kof-Editor](https://github.com/KofLang/Kof-Editor)

## 1. O que é

Um editor de código para arquivos Noxy, escrito em Noxy, feito para exercitar
a linguagem em um programa de verdade e para uso diário. Abre uma pasta, mostra
a árvore de arquivos, edita em abas com highlighting de Noxy, salva, e roda o
arquivo aberto mostrando a saída num painel.

A interface é uma página web renderizada numa janela nativa. Diferente do
Kof-Editor, onde a edição acontece num `textarea` em JavaScript e o núcleo em
Kof só tokeniza, aqui **o Noxy é dono do modelo inteiro**: buffer, cursor,
seleção, undo, lexer, abas, árvore e execução. O navegador só pinta o que o
Noxy manda e encaminha teclado e mouse. O JavaScript não guarda o texto.

O que a v1 entrega:

- abrir uma pasta pela linha de comando; árvore de arquivos na lateral;
- abas; abrir, editar, salvar e fechar arquivos;
- cursor, seleção com teclado e mouse, clipboard, undo e redo;
- highlighting de Noxy, números de linha, scroll, linha atual destacada;
- barra de status; tema escuro fixo;
- rodar o arquivo ativo (F5) com a saída num painel;
- janela nativa pela extensão `noxy_webview`, com fallback para o navegador
  em modo app.

O que a v1 não entrega está na seção 15.

## 2. Fatos verificados da plataforma

Sondados com o binário `noxy` v0.25.1 antes de escrever este documento. O
desenho depende deles.

| Fato | Consequência |
|---|---|
| `use src.x` resolve pelo diretório do script, não pelo cwd | `noxy /caminho/Noxy-Editor/editor.nx .` funciona de qualquer pasta |
| `json_loads(texto, ref struct)` preenche campos presentes, deixa ausentes no zero, ignora extras e devolve `false` em tipo errado | Um único struct `Event` com schema fixo serve para todos os eventos |
| Um struct com campo `chan any` pode ser enviado por outro canal | O handler HTTP manda `Request { body, reply }` e espera no `reply` |
| 200 snapshots de um documento de 5000 linhas custam menos de 1 ms | Undo por snapshot é viável: copy-on-write faz a cópia ser rasa |
| `codes(linha)` mais um loop sobre 50 linhas, 60 vezes, custa menos de 1 ms | Tokenizar só as linhas visíveis a cada evento é barato |
| `spawn_task` + `sys.exec_output` + `task_await(t, 0)` | Rodar o arquivo sem travar o editor, consultando a cada evento |
| `io.list_dir` devolve nomes; `io.stat(...).is_dir` distingue pastas | Árvore lazy, um nível por expansão |
| O servidor HTTP da stdlib roda cada conexão numa routine (`spawn`), uma requisição por conexão, sem streaming | Estado precisa de dono único; o cliente faz polling quando há execução |
| 200 POSTs a um servidor in-process passam em menos de 1 s | Uma requisição por tecla é aceitável em localhost |
| `time_now()` não tem tipo de retorno estático | `let t: int = time_now()`; entra no registro de achados |
| Comentários são só `//`; strings e f-strings não atravessam linha | O lexer não guarda estado entre linhas |

## 3. Arquitetura

```
┌──────────────────────────── janela nativa (noxy_webview) ───────────────────────────┐
│  web/index.html + editor.css + editor.js                                            │
│  pinta o quadro · captura teclado e mouse · uma requisição em voo por vez           │
└───────────────┬────────────────────────────────────────────────────▲────────────────┘
                │ POST /event  {kind, key, text, line, col, ...}      │ quadro JSON
┌───────────────▼────────────────────────────────────────────────────┴────────────────┐
│  servidor HTTP da stdlib (127.0.0.1:porta efêmera)                                  │
│  handler por conexão, em routine: Request{body, reply} ──► inbox ──► espera reply   │
└───────────────┬─────────────────────────────────────────────────────────────────────┘
                │ chan
┌───────────────▼─────────────────────────────────────────────────────────────────────┐
│  routine principal = dona do estado                                                 │
│  Session { tabs[Editor{Document, cursor, History}], tree, run, ... }                │
│  events.dispatch ──► editing / session / runner ──► frame.build ──► reply           │
└─────────────────────────────────────────────────────────────────────────────────────┘
        ▲ webview.wait() numa routine manda `quit` no inbox quando a janela fecha
```

Três regras que o desenho inteiro obedece:

1. **Todo estado mutável vive na routine principal.** Handlers HTTP e a
   routine que espera a janela só mandam mensagens no `inbox`. Não há global
   escrito por duas routines.
2. **O cliente é burro.** Ele não sabe o que é um cursor: recebe linhas com
   spans, uma posição, e desenha. Toda regra de edição está em Noxy e é
   testável sem navegador.
3. **Erro é dado.** Arquivo que não abre, JSON inválido, bug numa operação:
   tudo vira mensagem no status ou resposta HTTP de erro. O editor não cai por
   causa de um evento.

## 4. Repositórios e layout

Dois repositórios git em `noxy_projects/`.

```
Noxy-Editor/
├── editor.nx             # entrada: argv, sessão, servidor, janela, loop dono
├── src/
│   ├── lexer.nx          # tokenizador de Noxy, uma linha por vez
│   ├── document.nx       # Document: linhas, inserir, apagar, trechos
│   ├── editing.nx        # Editor: cursor, seleção, movimento, operações
│   ├── history.nx        # undo e redo por snapshot
│   ├── session.nx        # abas, abrir, salvar, fechar, árvore, modal
│   ├── frame.nx          # monta o quadro para o navegador
│   ├── events.nx         # JSON → Event → despacho
│   ├── runner.nx         # roda o arquivo ativo numa task
│   ├── server.nx         # rotas HTTP, token, ponte com o inbox
│   └── launch.nx         # janela pela extensão, fallback navegador
├── web/
│   ├── index.html
│   ├── editor.css
│   └── editor.js
├── tests/
│   ├── run.nx            # suíte sem navegador
│   ├── protocol.nx       # servidor + cliente HTTP in-process
│   └── MANUAL.md         # o que só o navegador prova
├── docs/
│   ├── ACHADOS.md        # registro de achados sobre a linguagem
│   └── superpowers/{specs,plans}/
├── noxy.mod              # module noxy_editor / noxy v0.25.1
├── noxy.sum
├── .gitignore            # noxy_libs/, bin/
└── README.md

noxy_webview/
├── noxy_ext.toml
├── noxy_webview.nx       # wrapper tipado
├── noxy.mod              # module noxy_webview / noxy v0.25.1
├── go.mod                # github.com/estevaofon/noxy_webview
├── main.go               # SDK numa goroutine; janela na thread principal
├── window.go             # estado da janela
├── window_test.go        # sem janela, com uma janela falsa
├── examples/smoke.nx
├── release/build.sh
├── .github/workflows/release.yml
└── README.md
```

Durante o desenvolvimento a extensão é compilada localmente
(`go build -o bin/noxy-plugin-webview-linux-amd64 .`) e o diretório do
checkout é linkado em
`Noxy-Editor/noxy_libs/github_com/estevaofon/noxy_webview`. Sem entrada em
`noxy.sum` a VM avisa uma vez (confiança na primeira execução) e roda. A
linha `require github.com/estevaofon/noxy_webview vX.Y.Z` no `noxy.mod` do
editor só entra quando o package for publicado no GitHub com release.

Identificadores em inglês, comentários e documentação em português, como nos
outros projetos Noxy do autor.

## 5. Execução e ciclo de vida

```
noxy editor.nx [pasta | arquivo]
```

Sem argumento abre o diretório atual. Um arquivo abre a pasta dele com o
arquivo numa aba. `editor.nx`:

1. Resolve a raiz e o diretório do próprio editor (de `sys.argv()[0]`, para
   achar `web/` de qualquer cwd).
2. `session.load(root)`: lista o primeiro nível da árvore.
3. Gera um token (`uuid`), cria o servidor em `127.0.0.1` porta 0,
   `bind_server`, lê `server.port`, `spawn(serve)`.
4. `launch.open(url)`: tenta `webview.open("Noxy Editor", 1200, 800, url)`
   dentro de `call_result`; se falhar, fallback (seção 11).
5. Se a janela abriu pela extensão, `spawn(wait_window)`: a routine chama
   `webview.wait()` e, ao voltar, manda `quit` no `inbox`.
6. Loop dono: `while true do` recebe do `inbox`, despacha, responde. Sai no
   `quit`.
7. `stop_server`, `webview.close()` se ainda aberta, `sys.exit(0)`.

Falha ao abrir a porta ou ao ler a raiz: mensagem no stderr e `sys.exit(1)`.

Com a variável de ambiente `NOXY_EDITOR_NO_WINDOW=1` o passo 4 é pulado e o
editor só imprime a URL no stderr: é assim que o smoke de navegador
(`tests/web_smoke.py`) e o desenvolvimento do cliente rodam.

## 6. O modelo em Noxy

### 6.1 Document (`src/document.nx`)

```noxy
struct Pos
    line: int      // 0-based
    col: int       // em code points, o mesmo que substring e codes usam
end

struct Document
    path: string   // absoluto; "" para um buffer sem arquivo
    lines: string[]
    dirty: bool
end
```

- `from_text(path, text) -> Document`: divide em `\n`, normaliza `\r\n`.
  Texto vazio dá uma linha vazia; `lines` nunca é vazio.
- `to_text(d) -> string`: junta com `\n`.
- `insert(ref d, p, text)`: `text` pode conter `\n`; divide a linha em `p`,
  insere as linhas intermediárias. Devolve a `Pos` depois do texto inserido.
- `delete_range(ref d, a, b)`: remove de `a` (inclusive) a `b` (exclusivo),
  com `a <= b`; atravessando linhas, junta as pontas.
- `text_range(d, a, b) -> string`.
- `clamp(d, p) -> Pos`: traz uma posição para dentro do documento.
- `line_len(d, i) -> int`.

Não conhece cursor, tela nem arquivo. Toda operação marca `dirty`.

### 6.2 Editing (`src/editing.nx`)

```noxy
struct Editor
    doc: Document
    cursor: Pos
    anchor: Pos       // outra ponta da seleção; == cursor quando não há
    top: int          // primeira linha visível
    goal_col: int     // coluna desejada ao subir e descer; -1 sem meta
    history: History
end
```

Operações (todas `ref Editor`, todas chamam `ensure_visible(rows)` no fim,
exceto `scroll`):

| Operação | Regra |
|---|---|
| `move_left/right/up/down(shift)` | Com `shift`, a âncora fica; sem, a âncora acompanha e uma seleção existente colapsa para a ponta correspondente antes de mover |
| `move_word_left/right(shift)` | Palavra é sequência de letras, dígitos e `_`; salta espaço e pontuação como blocos |
| `move_home(shift)` | Alterna entre o primeiro não-espaço e a coluna 0 |
| `move_end(shift)`, `move_doc_start/end(shift)` | |
| `page_up/down(rows, shift)` | Move `rows - 1` linhas e `top` junto |
| `select_all` | |
| `select_word_at(p)` | Duplo clique |
| `select_line(n)` | Clique no gutter: âncora no início da linha, cursor no início da seguinte |
| `click(p, shift)`, `drag(p)` | `drag` move só o cursor, mantendo a âncora |
| `insert_text(text)` | Substitui a seleção, se houver |
| `newline` | Insere `\n` mais o espaço inicial da linha atual |
| `backspace` | Com seleção, apaga a seleção; no início da linha, junta com a anterior |
| `delete` | Simétrico |
| `tab(shift)` | Sem seleção: quatro espaços (Shift: remove até quatro espaços iniciais da linha). Com seleção multilinha: indenta ou desindenta todas as linhas tocadas, mantendo a seleção |
| `toggle_comment` | Nas linhas tocadas pela seleção ou do cursor: se todas as não vazias começam com `//` (após espaço), remove `// `; senão insere `// ` na menor indentação |
| `copy() -> string`, `cut() -> string`, `paste(text)` | Sem seleção, `copy` e `cut` agem na linha inteira, como no VS Code |
| `undo`, `redo` | Restauram linhas e cursor do snapshot |
| `scroll(delta, rows)` | Move `top` dentro de `[0, max(0, total - rows)]`; não toca o cursor |
| `ensure_visible(rows)` | Ajusta `top` para o cursor ficar na tela |

Cada operação que muda o texto chama `history.record(...)` antes de mudar.

### 6.3 History (`src/history.nx`)

```noxy
struct Snapshot
    lines: string[]
    cursor: Pos
end

struct History
    undo: Snapshot[]
    redo: Snapshot[]
    last_kind: string   // "typing", "delete", "other"
    last_time: int      // ms
end
```

- `record(ref h, snap, kind)`: se `kind` é `"typing"` ou `"delete"`, igual a
  `last_kind`, e passou menos de 1000 ms, não empilha (o snapshot anterior já
  guarda o estado antes do burst). Senão empilha, limita a 200 entradas
  descartando a mais antiga. Sempre limpa `redo`.
- `undo(ref h, current) -> Snapshot?`: move `current` para `redo`, devolve o
  topo de `undo`; `null` quando vazio.
- `redo` simétrico.

Um snapshot é uma cópia por valor de `lines`; copy-on-write faz isso custar
uma cópia rasa do array.

### 6.4 Lexer (`src/lexer.nx`)

```noxy
struct Token
    kind: string
    text: string
end

func tokenize(line: string) -> Token[]
```

Sem estado entre linhas. Trabalha sobre `codes(line)` e monta `text` com
`substring`. Kinds e regras, na ordem em que são tentadas:

| kind | regra |
|---|---|
| `comment` | de `//` até o fim da linha |
| `string` | `"..."`, `'...'`, com prefixo `f` ou `b` opcional; `\` escapa o próximo caractere; sem fechamento, vai até o fim da linha. A interpolação de f-string não é colorida à parte na v1 |
| `number` | dígitos, com `.` seguido de dígito e `0x` hexadecimal |
| `keyword` | `let func struct if elif then else end while do return break continue for in defer when case default try ref use select as true false null zeros` |
| `type` | `int float string bool void bytes any map chan` e identificador iniciado em maiúscula (nome de struct) |
| `call` | identificador seguido, após espaços, de `(` |
| `ident` | `[A-Za-z_][A-Za-z0-9_]*` e letras não ASCII |
| `operator` | `+ - * / % = == != < > <= >= && \|\| ! & \| ^ << >> -> ?` |
| `punct` | `( ) [ ] { } , : .` |
| `space` | espaços e tabs |

Os kinds contextuais (`map`, `int`, ...) são sempre `type`; a v1 aceita a
imprecisão. Qualquer caractere que não case vira `punct` de um caractere, para
a soma dos textos dos tokens ser sempre a linha original: o cliente desenha
exatamente `text`, então essa invariante é o que mantém colunas corretas.

### 6.5 Session (`src/session.nx`)

```noxy
struct Tab
    editor: Editor
end

struct Node
    path: string
    name: string
    is_dir: bool
    depth: int
    expanded: bool
end

struct Button
    label: string
    id: string
end

struct Modal
    text: string      // "" quando não há modal
    buttons: Button[]
    pending: string   // o que fazer depois: "close_tab:3", "quit"
end

struct Session
    root: string
    tabs: Tab[]
    active: int          // -1 sem aba
    tree: Node[]         // lista plana das entradas visíveis
    tree_version: int    // começa em 1; incrementa a cada mudança na árvore
    rows: int            // último valor recebido do cliente
    run: RunState
    message: string      // status transitório; limpo no próximo evento não trivial
    modal: Modal
    clipboard: string    // preenchido por copy/cut, consumido pelo quadro
end
```

- `load(root)`: `tree` recebe o primeiro nível. Entradas iniciadas por `.`
  ficam ocultas; diretórios antes de arquivos, ambos ordenados por nome.
- `toggle_dir(ref s, path)`: expandir lista os filhos na hora e insere logo
  abaixo com `depth + 1`; recolher remove todos os descendentes.
  `tree_version` incrementa.
- `open_file(ref s, path)`: já aberto ativa a aba. Senão `io.open` + `read`;
  `ok = false` vira `message`. Cria `Tab` com `Editor` novo.
- `save(ref s)`: grava `to_text` com `io.open(path, "w")` e `write_result`;
  falha vira `message`; sucesso limpa `dirty` e diz "salvo".
- `close_tab(ref s, i)`: suja abre `modal` "Fechar sem salvar?" com botões
  `save` / `discard` / `cancel` e `pending = "close_tab:i"`. Limpa ativa a
  aba vizinha.
- `request_quit(ref s)`: com abas sujas abre modal `save_all` / `discard` /
  `cancel`, `pending = "quit"`; sem, encerra.
- `answer_modal(ref s, id)`: executa `pending` conforme o botão.
- `message` é sobrescrito por qualquer operação que queira falar e limpo no
  início de todo evento que não seja `poll`, `scroll` ou `drag`.

### 6.6 Frame (`src/frame.nx`)

`build(ref s, client_tree_version) -> string` monta structs e chama
`json_dumps`. Só as linhas `[top, top + rows)` são tokenizadas. Spans são
cortados na fronteira da seleção e recebem `s = true` no trecho selecionado,
para o cliente não precisar de aritmética de colunas. `tree` vai vazia quando
`client_tree_version == s.tree_version`. `clipboard` é zerado depois de
incluído. Formato na seção 7.3.

### 6.7 Events (`src/events.nx`)

```noxy
struct Event
    kind: string
    key: string
    ctrl: bool
    shift: bool
    alt: bool
    text: string
    line: int
    col: int
    delta: int
    path: string
    index: int
    rows: int
    tree_version: int
end
```

`dispatch(ref s, body) -> string`: `json_loads` num `Event` zerado (falha
devolve `""`, e o servidor responde 400), guarda `rows` (se mudou, chama
`ensure_visible` na aba ativa), limpa `message` se o evento não é trivial, despacha por `kind` num `if`/`elif`, consulta o runner
(seção 10), e devolve `frame.build`. A chamada ao despacho propriamente dito
passa por `call_result`: um erro de runtime vira `message = "erro interno:
..."` e a stack vai para o stderr com `eprint`.

Teclas (`kind = "key"`), com `key` no vocabulário do `KeyboardEvent.key` em
minúsculas: `arrowleft`, `arrowright`, `arrowup`, `arrowdown`, `home`, `end`,
`pageup`, `pagedown`, `enter`, `backspace`, `delete`, `tab`, `escape`, `f5`, e
qualquer caractere (`a`, `/`, ...) quando `ctrl` ou `alt` está apertado. A tabela de atalhos está na seção 9.

### 6.8 Runner (`src/runner.nx`), Server (`src/server.nx`), Launch (`src/launch.nx`)

Descritos nas seções 10, 7 e 11.

## 7. Protocolo

### 7.1 Rotas

| Rota | Resposta |
|---|---|
| `GET /` | `web/index.html` |
| `GET /editor.css`, `GET /editor.js` | os arquivos de `web/` |
| `POST /event` | quadro JSON; 403 se o token falta ou não confere; 400 se o corpo não é JSON válido |
| qualquer outra | 404 |

O token gerado na partida vai na URL da página (`/?t=<token>`); o JS o lê de
`location.search` e o manda no cabeçalho `X-Noxy-Token` de todo `/event`. O
servidor só escuta em `127.0.0.1`; o token impede que outro processo local
mande eventos.

O handler de `/event` cria `Request { body: string, reply: chan any }`,
manda no `inbox` (buffer 64) e bloqueia em `chan_recv(reply)`. O que volta é
a string do quadro ou `""` para 400.

### 7.2 Eventos

| kind | campos | efeito |
|---|---|---|
| `init` | rows | primeiro quadro, com a árvore |
| `key` | key, ctrl, shift, alt | tecla não textual ou combinação |
| `text` | text | caracteres digitados, inclusive acentos compostos |
| `paste` | text | colar |
| `copy`, `cut` | | quadro volta com `clipboard` |
| `click`, `drag`, `dblclick` | line, col, shift | cursor e seleção |
| `scroll` | delta (linhas, sinal indica direção) | move `top` |
| `tab_select`, `tab_close` | index | |
| `tree_toggle`, `tree_open` | path | expandir ou recolher pasta; abrir arquivo |
| `run` | | salva e roda o arquivo ativo |
| `poll` | | só devolve o quadro |
| `modal` | key = id do botão | resposta a um modal |
| `quit` | | janela fechada (mandado pela routine que espera a extensão) |
| `bye` | | página descarregando (`pagehide`); o editor sai se nada chegar em 3 s |
| `quit_if_idle` | | mandado pelo próprio editor 3 s após `bye`: encerra se nenhum evento chegou depois do `bye` |

Todo evento carrega `rows` e `tree_version` (a versão que o cliente tem).
Um reload da página manda `bye` e logo depois `init`, então o
`quit_if_idle` que chega 3 s depois encontra um evento recente e não encerra;
fechar a janela do navegador manda só `bye`, e o editor encerra.
Evento de kind desconhecido devolve o quadro com `message = "evento
desconhecido: <kind>"`.

### 7.3 Quadro

```json
{
  "title": "main.nx ● Noxy Editor",
  "root": "zombie_apocalypse",
  "tabs": [{"name": "main.nx", "path": "/abs/main.nx", "dirty": true, "active": true}],
  "tree_version": 3,
  "tree": [{"path": "/abs/src", "name": "src", "is_dir": true, "depth": 0, "expanded": true},
           {"path": "/abs/src/vec.nx", "name": "vec.nx", "is_dir": false, "depth": 1, "expanded": false}],
  "view": {
    "top": 0, "total": 120, "cursor": {"line": 2, "col": 5}, "has_sel": true,
    "lines": [
      {"n": 0, "spans": [{"k": "keyword", "t": "let", "s": false}, {"k": "space", "t": " ", "s": false},
                         {"k": "ident", "t": "x", "s": true}]}
    ]
  },
  "status": {"left": "src/main.nx ●", "right": "Ln 3, Col 6   Espaços: 4   UTF-8", "message": "salvo"},
  "output": {"version": 2, "running": false, "text": "$ noxy main.nx\nhello\n[saiu com 0]"},
  "clipboard": "",
  "modal": {"text": "", "buttons": [], "pending": ""}
}
```

`n` é 0-based; o gutter mostra `n + 1`. `tree` vazia significa "você já tem
a versão `tree_version`". Sem abas, `tabs` é vazio e o cliente mostra a tela
inicial em vez do editor. `modal.text` vazio é "sem modal".

## 8. Cliente web

### 8.1 Layout e visual

```
┌──────────┬──────────────────────────────────────────────┐
│ ZOMBIE_… │ main.nx ●  │ vec.nx  │           ▶ Executar   │
│ ▸ data   ├──────────────────────────────────────────────┤
│ ▾ src    │  1 │ use sys                                 │
│   vec.nx │  2 │                                         │
│   ...    │  3 │ let x: int = 10          ◄ linha atual  │
│          │    │                                         │
│          ├──────────────────────────────── Saída ─── × ─┤
│          │ $ noxy main.nx                               │
│          │ hello                                        │
│          │ [saiu com 0]                                 │
├──────────┴──────────────────────────────────────────────┤
│ src/main.nx ●  salvo            Ln 3, Col 6  Espaços: 4 │
└─────────────────────────────────────────────────────────┘
```

- Sidebar de 260 px, cabeçalho com o nome da raiz, árvore com indentação por
  `depth` e chevron nos diretórios.
- Barra de abas com `×` em cada aba e o botão Executar à direita.
- Área do editor: gutter com números, linhas em `white-space: pre`, overflow
  horizontal nativo do navegador para linhas longas; overflow vertical
  desligado, porque o scroll é do Noxy.
- Painel de saída recolhido até o primeiro `run`; `×` recolhe.
- Barra de status: esquerda com caminho relativo e `●` se suja, e a mensagem
  transitória; direita com posição, indentação e codificação.
- Fonte: `ui-monospace, "JetBrains Mono", "Fira Code", "DejaVu Sans Mono",
  monospace`, 14 px, linha de 22 px. Nenhum arquivo de fonte no repositório.
- Tema escuro fixo em variáveis CSS em `:root`; uma classe por kind de token
  (`.k-keyword`, `.k-string`, ...), `.sel` para o trecho selecionado, `.cur`
  na linha atual.

### 8.2 Renderização

Cada quadro re-renderiza: as abas, a árvore (só se veio no quadro), as
linhas visíveis (um `div.line[data-n]` por linha, `span` por token), a
status, o painel de saída (se `version` mudou) e o modal. `document.title`
recebe `title`.

O cursor é um `div.cursor` absoluto. A posição vem de um `Range` no nó de
texto da linha na coluna `cursor.col`, via `getBoundingClientRect()`. Isso
fica exato com tabs, caracteres largos e qualquer fonte. A animação de piscar
é reiniciada a cada quadro para o cursor ficar sólido enquanto se digita.

`rows` é `floor(altura da área do editor / 22)`, recalculado por
`ResizeObserver`; quando muda, o cliente manda um `poll`, e o despacho, ao
ver um `rows` diferente do guardado, chama `ensure_visible` na aba ativa.

### 8.3 Entrada

Um `textarea` invisível fica sempre focado; clicar em qualquer lugar do
editor devolve o foco a ele.

- `keydown`: teclas não textuais (setas, Home, End, PageUp, PageDown, Enter,
  Backspace, Delete, Tab, Escape, F5) e qualquer combinação com Ctrl ou Alt
  viram `key` com `preventDefault`. Teclas textuais sem modificador não são
  tratadas aqui.
- `input` (com `inputType` de inserção) e `compositionend`: o texto inserido
  no `textarea` vira `text`, e o `textarea` é esvaziado. É isso que faz dead
  keys e IME funcionarem.
- `paste`: `clipboardData.getData("text")` vira `paste`; `preventDefault`.
- Ctrl+C e Ctrl+X: mandam `copy` ou `cut`; o `clipboard` do quadro vai para
  `navigator.clipboard.writeText` e para uma variável interna. Ctrl+V: o
  evento `paste` do DOM entrega o texto; se vier vazio e a variável interna
  tiver algo, usa a variável.
- Mouse nas linhas: `mousedown` → `caretPositionFromPoint` → `n` do `div` e
  `offset` dentro do texto da linha → `click` (com `shift`); `mousemove` com
  botão apertado → `drag` no ritmo de `requestAnimationFrame`; `dblclick` →
  `dblclick`. Clique no gutter manda `click` com `col = -1`, que o Noxy trata como
  `select_line`.
- `wheel`: acumula `deltaY` e manda `scroll` com `round(deltaY / 22)`,
  mínimo 1 na direção do sinal, coalescido por quadro de animação.
- Abas: clique seleciona, `×` ou botão do meio fecha. Árvore: clique em
  pasta alterna, em arquivo abre. Botão Executar: `run`.
- Modal: sobreposição com o texto e os botões; clique manda `modal` com o
  `id`; Escape manda o `id` `cancel`.

### 8.4 Fila de requisições

Uma requisição em voo por vez. Enquanto há uma em voo, novos eventos entram
numa fila; um `scroll` ou `drag` pendente é substituído pelo mais novo do
mesmo kind, o resto mantém ordem. Ao chegar a resposta, renderiza e dispara o
próximo. Um `fetch` que falha ou responde fora de 200 mostra "conexão
perdida" na status e para a fila; a página precisa ser recarregada.

Enquanto `output.running`, um `setInterval` de 250 ms enfileira `poll`.

Em `pagehide` a página manda `bye` por `navigator.sendBeacon` para
`/event?t=<token>` (o beacon não leva cabeçalhos, por isso o servidor aceita o
token também na query).

## 9. Atalhos

Todos resolvidos em Noxy a partir de eventos `key`; o cliente só impede o
comportamento padrão do navegador.

| Tecla | Ação |
|---|---|
| Setas, Home, End, PageUp, PageDown | mover; com Shift, selecionar |
| Ctrl+Setas | por palavra |
| Ctrl+Home, Ctrl+End | início e fim do documento |
| Ctrl+A | selecionar tudo |
| Ctrl+C, Ctrl+X, Ctrl+V | clipboard (linha inteira sem seleção) |
| Ctrl+Z, Ctrl+Y ou Ctrl+Shift+Z | undo, redo |
| Ctrl+S | salvar |
| Ctrl+W | fechar aba |
| Ctrl+/ | alternar comentário |
| Tab, Shift+Tab | indentar, desindentar |
| Enter | nova linha com a indentação da atual |
| Escape | fechar modal; senão colapsar a seleção |
| F5 | rodar o arquivo ativo |
| Ctrl+Q | sair (com modal se houver abas sujas) |

## 10. Rodar arquivo

```noxy
struct RunState
    running: bool
    task: any          // handle de spawn_task; null quando parado
    text: string
    version: int
    cmd: string
end
```

`run(ref s)`:

1. Sem aba ativa ou arquivo que não termina em `.nx`: `message = "só
   arquivos .nx"`.
2. Se já `running`: `message = "já está rodando"`.
3. Se a aba está suja, `save`. Falha ao salvar aborta.
4. Monta o comando, no Linux e macOS:
   `cd '<raiz>' && noxy '<caminho relativo>' < /dev/null 2>&1`, com `'`
   escapado como `'\''`. No Windows (fora do escopo de teste da v1, só a
   string): `cd /d "<raiz>" && noxy "<relativo>" < NUL 2>&1`. Escolhido por
   `sys.os()`.
5. `text = "$ noxy <relativo>\n"`, `running = true`, `version++`,
   `task = spawn_task(exec, cmd)`, onde `exec` chama `sys.exec_output`.

`poll_run(ref s)`, chamado pelo despacho a cada evento: se `running`,
`task_await(task, 0)`; em `"ok"`, anexa `output` e `[saiu com <exit_code>]`
(`ok = false` por saída não UTF-8 anexa a mensagem de erro), `running =
false`, `version++`; em `"error"`, anexa a mensagem e encerra igual.

O `cd` para a raiz aberta faz `noxy.mod` e os caminhos relativos do programa
funcionarem como no terminal. `/dev/null` na entrada faz `input()` devolver
`""` em vez de travar. Não há como interromper um programa que não termina;
o editor continua utilizável, e F5 responde "já está rodando". Limitação
registrada em `docs/ACHADOS.md`.

## 11. Extensão `noxy_webview`

### 11.1 Manifesto

```toml
name = "webview"
abi = 1
kind = "process"
min_noxy = "0.25.0"
concurrency = "concurrent"      # wait bloqueia; close e set_title precisam passar
capabilities = ["display"]

[binaries]
linux-amd64   = "noxy-plugin-webview-linux-amd64"
windows-amd64 = "noxy-plugin-webview-windows-amd64.exe"
darwin-amd64  = "noxy-plugin-webview-darwin-amd64"
darwin-arm64  = "noxy-plugin-webview-darwin-arm64"

[[export]]
name = "webview_open"           # (title, width, height, url): abre a janela
params = ["string", "int", "int", "string"]
returns = "void"
stateful = true

[[export]]
name = "webview_wait"           # bloqueia até a janela fechar
params = []
returns = "void"
timeout_ms = 0

[[export]]
name = "webview_close"
params = []
returns = "void"

[[export]]
name = "webview_set_title"
params = ["string"]
returns = "void"
```

### 11.2 Wrapper

```noxy
// noxy_webview.nx
func open(title: string, width: int, height: int, url: string) -> void
func wait() -> void
func close() -> void
func set_title(title: string) -> void
```

Cada função chama o nativo correspondente. Erros chegam como
`extension 'webview' failed: <mensagem>`, capturáveis com `call_result`.

### 11.3 Ciclo de vida do processo

`main.go` registra os quatro handlers, roda `p.Main()` numa goroutine e
bloqueia a goroutine principal esperando o pedido de `open`. Ao chegar:
`webview.New(debug)`, `SetTitle`, `SetSize(w, h, HintNone)`, `Navigate(url)`,
`Run()`. `Run()` precisa da thread principal; é por isso que o SDK vai para a
goroutine, o mesmo arranjo da engine com o Ebiten. Quando `Run()` volta (X da
janela ou `Terminate`), o processo marca fechado, libera todo `wait`
pendente e fica em `select {}` até o host fechar o stdin.

`window.go` guarda o estado atrás de um mutex: `opened`, `closed`, o canal do
pedido de abertura e um canal fechado ao encerrar, no qual `wait` seleciona
junto com `ctx.Done()`. Regras:

- `open` com a janela aberta ou já fechada: erro `window already open` /
  `window was closed`. Uma janela por processo.
- `wait` antes de `open`: erro. Depois: bloqueia até fechar ou o contexto
  ser cancelado (CANCEL do host ou EOF).
- `close` e `set_title` antes de `open`: erro. Depois de fechado, `close` é
  no-op e `set_title` é erro. Ambos passam por `Dispatch`, que executa na
  thread principal, como a biblioteca exige.
- `NOXY_WEBVIEW_DEBUG=1` no ambiente do `noxy` passa `debug = true`, que
  habilita o inspetor do WebKit.

### 11.4 Build e release

Linux: `apt install libgtk-3-dev libwebkit2gtk-4.1-dev`, então
`sh release/build.sh webview` no diretório da extensão e copiar o binário de
`dist/` para `bin/`. O `webview_go` publicado ainda pede `webkit2gtk-4.0` no
`pkg-config`, que as distros atuais não têm (PR webview_go#62, aberto, troca só
essa linha para 4.1); `release/build.sh` contorna criando um diretório
temporário onde `webkit2gtk-4.0.pc` e `javascriptcoregtk-4.0.pc` apontam para
os arquivos 4.1 e pondo-o no `PKG_CONFIG_PATH` só durante o build. Em runtime
basta o `libwebkit2gtk-4.1` comum, presente em desktops GNOME. O workflow de release copia o da engine: um runner por OS (a
biblioteca é cgo em todos), `release/build.sh webview <arch>`, merge dos
`checksums-*.txt` em `checksums.txt`, assets no release da tag. Windows e
macOS só passam pelo workflow; a v1 é testada no Linux.

A máquina de estados fica no pacote `window/`, sem importar a biblioteca
webview, para `go test ./window/` rodar em qualquer máquina, sem headers;
`main.go` injeta a janela real. `window_test.go` exercita com uma janela falsa
(`Run`, `Terminate`, `SetTitle`, `Navigate`, `Dispatch`, `Destroy`): abrir uma
vez, `wait` destrava no fechamento e já vê a janela destruída, erros antes de
`open`, `close` idempotente, contextos cancelados.
`examples/smoke.nx` abre uma URL `data:text/html,ok`, dorme 500 ms,
`close()`, `wait()` volta, imprime `ok`.

### 11.5 Fallback (`src/launch.nx`)

Se `call_result(webview.open, ...)` falha (o processo da extensão não sobe,
por exemplo sem `libwebkit2gtk-4.1` na máquina, ou morre), o editor escreve
no stderr `janela pela extensão indisponível: <motivo>; abrindo no navegador`
e tenta,
na ordem, `google-chrome`, `chromium`, `chromium-browser`, `brave-browser`,
`microsoft-edge`, cada um com `--app=<url>` em segundo plano
(`sys.exec("<bin> --app='<url>' >/dev/null 2>&1 &")`, testando a existência
com `command -v`). Sem nenhum, `xdg-open` (Linux) ou `open` (macOS). Nesse
modo o loop dono encerra 3 s depois do `bye` que a página manda em
`pagehide`, se nenhum evento novo chegar, ou em Ctrl+C.

## 12. Erros

| Situação | Comportamento |
|---|---|
| Raiz inexistente ou ilegível | stderr e `exit(1)` |
| Porta não abre | stderr e `exit(1)` |
| Arquivo não abre, não salva | `message` no status |
| Token ausente ou errado | 403 |
| Evento com JSON inválido | 400 |
| Kind desconhecido | `message` |
| Erro de runtime no despacho | `call_result`: `message = "erro interno: ..."`, stack no stderr |
| Extensão morre no meio | `wait` volta com erro; o editor avisa no stderr e encerra |
| Package `noxy_webview` sem o binário da plataforma | A VM recusa o `use` na compilação (`binary ... not found — run 'noxy --sync'`): o editor não abre. O fallback só cobre falhas em tempo de execução; instalar o package é pré-requisito (achado 7) |
| Programa executado não termina | o editor continua; sem interrupção na v1 |
| Fechar a janela pelo X com abas sujas | alterações perdidas; Ctrl+Q é o caminho com modal. Limitação da v1 |

O compilador fala primeiro: nada é `any` fora das fronteiras que a
plataforma impõe (`task_await`, `chan any`, `json_parse` não é usado).

## 13. Testes

**`tests/run.nx`** (sem navegador; `check(nome, cond)` e `exit(1)` se algo
falha, como no Zombie Apocalypse):

- Document: inserção e remoção dentro da linha, atravessando linhas, com
  `\n` no texto, com caracteres multibyte; `from_text` com `\r\n`; `clamp`.
- Editing: cada movimento com e sem Shift; Backspace no início da linha e
  Delete no fim; Enter copiando indentação; Tab e Shift+Tab sem e com
  seleção multilinha; `toggle_comment` nos dois sentidos; palavra;
  `copy`/`cut` sem seleção pegam a linha; `ensure_visible` e `scroll`.
- History: burst de digitação vira um undo; redo limpo por edição nova;
  limite de 200.
- Lexer: um caso por kind; string aberta; f-string com aspas dentro de
  `{}`; `b"..."`; `call` versus `ident`; comentário após código; invariante
  "concatenar os tokens devolve a linha" sobre um arquivo real de
  `noxy_examples`.
- Session: em diretório temporário, `load` oculta pontos e ordena; abrir,
  editar, salvar e reler; abrir duas vezes ativa; fechar suja abre modal e
  `discard` fecha; `save_all` no `quit`.
- Frame: spans cortados na seleção; `tree` vazia quando a versão bate;
  `tabs` vazio sem aba; `clipboard` zerado após um quadro.
- Events: sequência de JSONs (`init`, `text`, `key enter`, `key ctrl+z`)
  produz o documento esperado; JSON inválido devolve `""`; kind desconhecido
  vira `message`.
- Runner: roda um `.nx` temporário que imprime e sai com 3; o painel
  termina com `[saiu com 3]`; `.txt` recusa.

**`tests/protocol.nx`**: sobe o servidor na porta 0 com o loop dono numa
routine, faz POSTs reais com `http_client.post` (`init`, `text`, `key`),
confere status 200, o token errado dando 403, e o quadro com as linhas
esperadas. Encerra com `quit`.

**`tests/web_smoke.py`**: sobe o editor com `NOXY_EDITOR_NO_WINDOW=1`, abre a
página num Chrome headless pelo DevTools Protocol (cliente mínimo em
`tests/cdp.py`, só biblioteca padrão do Python) e exercita o JS de verdade:
árvore, abrir arquivo, digitar com acento, Enter, Ctrl+Z, clique, Shift+End,
colar, arrastar, duplo clique, roda, F5 com saída, modal ao fechar aba suja,
e tira um screenshot. Precisa de `google-chrome` no PATH.

**Extensão**: `go test ./...` e `noxy examples/smoke.nx`.

**`tests/MANUAL.md`**: o que nem o smoke headless prova, conferido à mão a
cada release: acentos por dead key e IME no teclado real, clipboard do sistema
nos dois sentidos, redimensionar a janela, a janela pela extensão (título,
fechar pelo X encerra o processo), fallback sem extensão.

## 14. Documentação e registro de achados

- `README.md` do editor, em português, no formato do Zombie Apocalypse:
  como rodar, atalhos, como está organizado, testes, limitações.
- `README.md` da extensão: instalação, API, ciclo de vida, build local,
  release.
- `docs/ACHADOS.md`: para cada achado sobre a linguagem, o que faltou ou
  incomodou, onde no código, como foi contornado, sugestão. Entradas
  iniciais:
  1. Não há como interromper ou matar um processo iniciado por
     `sys.exec_output`.
  2. `time_now()` não tem tipo de retorno estático e exige anotação em `let`.
  3. A stdlib não tem ordenação (`sort`); a árvore usa inserção em Noxy.
  4. `use strings select *` sombreia o builtin `contains` de arrays com o
     `contains` de strings: módulos que usam os dois importam por nome.
  5. `serve` da stdlib imprime `Server listening on ...` no stdout do
     programa, sem opção de silenciar.
- Spec e plano em `docs/superpowers/` do editor, cobrindo os dois
  repositórios.
- Commits `tipo(escopo): descrição` em português.

## 15. Fora do escopo da v1

Busca e substituição; Quick Open; paleta de comandos; troca de tema; git;
terminal integrado; minimap; interromper o programa em execução; recuperação
de alterações não salvas; edição otimista no cliente; fontes embutidas;
seleção múltipla; autocomplete e diagnósticos; colorir a interpolação de
f-strings; Windows testado; mais de uma janela; publicação da extensão no
GitHub (o passo de publicar é do autor, depois da v1 rodar).

## 16. Critérios de sucesso

- `noxy editor.nx <pasta>` abre uma janela nativa com a árvore da pasta.
- Abrir, editar com acentos, selecionar com mouse e teclado, copiar e colar,
  desfazer, salvar e fechar um arquivo `.nx` funciona e o arquivo salvo é
  byte a byte o esperado.
- F5 num exemplo de `noxy_examples` mostra a saída dele no painel.
- `noxy tests/run.nx` e `noxy tests/protocol.nx` passam sem janela;
  `go test ./...` passa na extensão; `smoke.nx` imprime `ok`.
- Fechar a janela encerra o processo `noxy` sem órfãos.
- Com a extensão instalada mas incapaz de abrir a janela (processo que não
  sobe), o editor abre no navegador em modo app.
- `docs/ACHADOS.md` tem os achados encontrados durante a implementação.
