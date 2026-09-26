# Noxy Editor v1.1 — Design

Data: 2026-09-26
Branch: `feat/v1.1` (uma branch para os seis sub-projetos, validada antes do
merge em `main`)
Base: [v1](2026-09-25-noxy-editor-design.md) — tudo o que não está aqui
continua como lá. Plataforma: Noxy v0.25.1, `noxy_webview` v0.1.0, e a nova
extensão `noxy_pty`.

## 1. O que é

A v1 entregou o núcleo: editar, salvar, rodar. A v1.1 remove as limitações
listadas no README da v1, menos "testado só no Linux", que fica: os testes
continuam no Linux e o Windows é validado depois, à mão.

O que entra, agrupado como será construído:

1. **Base compartilhada**: painel inferior com abas (Saída, Busca, Terminal),
   `settings.json`, recuperação de alterações não salvas, `\r\n` preservado,
   execução com saída ao vivo e botão Parar, CI no Ubuntu.
2. **Busca**: no arquivo (Ctrl+F, Ctrl+H) e na pasta (Ctrl+Shift+F).
3. **Navegação**: Quick Open (Ctrl+P) e paleta de comandos (Ctrl+Shift+P).
4. **Temas**: Escuro, Claro, Dracula, Nord e Monokai, pela paleta.
5. **Git**: branch na barra de status; arquivos alterados marcados na árvore
   e nas abas.
6. **Minimap**.
7. **Terminal** de verdade: extensão `noxy_pty` e xterm.js.

Fora do escopo: seção 18.

## 2. Fatos verificados da plataforma

Sondados nesta máquina antes de escrever.

| Fato | Consequência |
|---|---|
| `crypto.sha256(bytes) -> string` (hex) na stdlib | Nome do arquivo de recuperação é o sha256 do caminho |
| `setsid sh -c '...' & echo $!` dá um grupo de processos próprio e `kill -TERM -- -PGID` derruba o grupo | Parar mata o programa e o que ele abriu (a janela de um jogo, por exemplo) |
| `io.read` num handle aberto devolve só o que foi acrescentado desde a última leitura | Saída ao vivo lendo o arquivo de saída a cada `poll`, sem reabrir |
| `XDG_CACHE_HOME` costuma não existir; `HOME` sim | Caminhos `~/.cache/noxy-editor/` e `~/.config/noxy-editor/`, com `XDG_*` quando definidos |
| O servidor HTTP da stdlib é requisição e resposta; handlers rodam em routines | O terminal usa long-poll de até 1 s numa rota própria, fora do dono do estado |
| `spawn_task` + `task_await(t, 0)` (v1) | Busca na pasta, índice de arquivos e `git status` rodam em tasks e são recolhidos a cada evento |
| xterm.js 6.0.0 e `@xterm/addon-fit` 0.11.0, MIT; `creack/pty` v1.1.24 | Versões fixadas em `web/vendor/` e no `go.mod` da extensão |
| Sem binário da extensão a VM recusa o `use` (achado 7) | `noxy_pty` publica binário Windows que responde "indisponível" em vez de faltar |

## 3. Arquitetura

Nada muda no desenho da v1: o dono do estado continua sendo a routine
principal, o cliente continua burro, o quadro continua sendo a única coisa
que o cliente pinta. O que se acrescenta:

```
                        ┌─ POST /event ───────► inbox ──► dono do estado (Session) ──► quadro
navegador (xterm.js) ───┼─ POST /term/read ───► pty_read (bloqueia até 1 s)  ─┐ fora do dono:
                        └─ POST /term/write ──► pty_write                    ─┘ o terminal não é estado do editor
tasks (spawn_task): busca na pasta · índice de arquivos · git status · execução (saída num arquivo)
arquivos: ~/.config/noxy-editor/settings.json · ~/.cache/noxy-editor/recovery/<sha256>.json
```

Módulos novos em `src/` e os que mudam:

| Módulo | Responsabilidade |
|---|---|
| `find.nx` (novo) | ocorrências de uma consulta num `Document`, navegação, substituir |
| `search.nx` (novo) | busca na pasta numa task; resultados |
| `index.nx` (novo) | índice de caminhos da raiz; filtro difuso com pontuação |
| `commands.nx` (novo) | registro de comandos da paleta: id, rótulo, atalho |
| `settings.nx` (novo) | `settings.json`: ler e gravar |
| `recovery.nx` (novo) | cópias de recuperação: gravar, listar, apagar |
| `gitinfo.nx` (novo) | branch e status do git numa task |
| `minimap.nx` (novo) | o formato do documento: comprimento e cor por linha |
| `term.nx` (novo) | o terminal: abrir, fechar, redimensionar; `pty_read`/`pty_write` para o servidor |
| `document.nx` | ganha `eol` |
| `runner.nx` | reescrito: saída num arquivo, PID, Parar |
| `session.nx` | ganha painel, busca, lista, git, settings, índice, recuperação, terminal |
| `frame.nx`, `events.nx`, `server.nx`, `editor.nx` | novos campos, eventos, rotas e partida |

## 4. Base compartilhada

### 4.1 Painel inferior com abas

`Session.panel = Panel { open: bool, tab: string }` com `tab` em `"output"`,
`"search"`, `"terminal"`. O quadro leva `panel`; o cliente desenha a faixa de
abas no lugar do título fixo "Saída", mantendo o divisor, a altura lembrada
e o `×`. Ctrl+J alterna `open`; Ctrl+Shift+F abre em `search`; Ctrl+` abre
em `terminal`; rodar abre em `output`. Clicar numa aba manda `panel_tab`.

### 4.2 Configurações

`~/.config/noxy-editor/settings.json` (`$XDG_CONFIG_HOME` quando definido):

```json
{"theme": "dark"}
```

`settings.load() -> Settings` na partida (arquivo ausente ou inválido dá o
padrão, com aviso no stderr se inválido); `settings.save(s)` quando um comando
muda algo, criando o diretório. `Settings` vai no quadro como `settings`.

### 4.3 Recuperação de alterações não salvas

Diretório `~/.cache/noxy-editor/recovery/` (`$XDG_CACHE_HOME` quando
definido). Para cada aba suja, um arquivo `<sha256 do caminho>.json`:

```json
{"path": "/abs/x.nx", "text": "...", "eol": "\n", "saved_at": 1727300000000}
```

- `Editor` ganha `edits: int` (incrementa em toda mudança de texto, inclusive
  undo) e `recovered_edits: int` (o `edits` da última cópia gravada).
- No fim de todo evento não trivial, o dono percorre as abas: suja com
  `edits != recovered_edits` e última gravação há mais de 1000 ms grava a
  cópia. No `bye`, grava todas sem esperar.
- O cliente, 1500 ms depois da última edição sem outro evento, manda um
  `poll`, para a gravação pendente acontecer com o usuário parado.
- `save` bem-sucedido apaga a cópia da aba. Fechar aba com "Não salvar"
  também apaga.
- Na partida, `recovery.list()` lê todas as cópias; cada uma cujo `text`
  difere do conteúdo atual do arquivo em disco (ou cujo arquivo sumiu)
  reabre como aba suja com o texto da cópia; as iguais ao disco são apagadas.
  A mensagem "N arquivos recuperados" aparece na status. A cópia só é
  apagada quando o usuário salva ou descarta.

Isso cobre fechar pelo X, queda do editor e da máquina, sem gancho na
biblioteca webview.

### 4.4 `\r\n` preservado

`Document.eol: string` é `"\r\n"` se o texto lido contém `\r\n`, senão
`"\n"`. `from_text` divide como antes; `to_text` junta com `eol`. A barra de
status mostra `LF` ou `CRLF` no lugar do `UTF-8` fixo (a codificação continua
UTF-8, o que já é garantido pela linguagem).

### 4.5 Execução com saída ao vivo e Parar

`runner.start(ref r, root, rel)` cria um diretório temporário (`mktemp -d`)
com `out`, `pid` e `code`, e dispara numa task:

```sh
setsid sh -c '(cd <raiz> && exec noxy <relativo>) > <dir>/out 2>&1 < /dev/null; echo $? > <dir>/code' &
echo $! > <dir>/pid
```

(`sys.exec` da linha inteira; `$!` é o PID do `setsid`, que é o líder do
grupo.) A task fica em `sys.exec_output("while [ ! -f code ]; do sleep 0.1; done")`
só para o dono saber que terminou.

- `runner.poll(ref r)`: lê do handle aberto de `out` o que foi acrescentado e
  anexa a `text`; quando `code` existe, anexa `[saiu com N]`, fecha, apaga o
  diretório e marca parado. `version` muda a cada anexo.
- `runner.stop(ref r)`: `kill -TERM -- -<pid>`; 2 s depois, se `code` ainda
  não existe, `kill -KILL`. O painel mostra `[interrompido]`.
- O painel Saída ganha o botão **Parar** (visível enquanto roda); Ctrl+F5
  faz o mesmo. F5 durante uma execução continua respondendo "já está
  rodando".
- O cliente faz `poll` a cada 250 ms enquanto `running`, como na v1.

### 4.6 CI

`.github/workflows/ci.yml`, no Ubuntu, em push e pull request: `go install
github.com/estevaofon/noxy/cmd/noxy@v0.25.1`, `noxy --sync --locked`,
`noxy tests/run.nx`, `noxy tests/protocol.nx`. Os smokes de navegador ficam
fora da CI.

## 5. Busca no arquivo

```noxy
struct Find
    open: bool
    replace: bool        // a linha de substituir está visível
    query: string
    case_sensitive: bool
    matches: doc.Pos[]   // início de cada ocorrência, em ordem
    current: int         // índice em matches; -1 sem ocorrência
end
```

- `find.matches(d, query, case_sensitive) -> Pos[]`: busca literal por linha
  (sem regex nesta versão); ocorrências não se sobrepõem.
- Toda mudança de texto na aba ativa e toda alteração de `query` recalculam
  `matches`; `current` vira a primeira ocorrência a partir do cursor.
- `find_next`/`find_prev` movem `current`, põem o cursor no fim da
  ocorrência e a âncora no início (fica selecionada), e rolam até ela.
- `replace_one`: se a seleção é a ocorrência atual, substitui e vai para a
  próxima; senão só vai para a atual. `replace_all`: substitui todas de trás
  para a frente numa única entrada de undo (`history.record` uma vez).
- O quadro leva `find` e os spans ganham `f` (dentro de uma ocorrência) e
  `c` (dentro da ocorrência atual), cortados nas fronteiras como `s`.
- Cliente: barra no topo do editor com campo, botão `Aa`, contador
  `3 de 12` (ou `sem resultados`), setas, `×`, e a segunda linha com o campo
  de substituir e os botões `Substituir` e `Todas` quando `replace`. O campo
  manda `find` a cada tecla; Enter `find_next`, Shift+Enter `find_prev`,
  Escape `find_close` (devolve o foco ao editor). Ctrl+F com seleção de uma
  linha só abre com ela como consulta.

## 6. Busca na pasta

```noxy
struct SearchHit
    path: string
    rel: string
    line: int      // 0-based
    col: int
    text: string   // a linha inteira, cortada em 200 caracteres
end

struct Search
    query: string
    case_sensitive: bool
    running: bool
    task: any
    hits: SearchHit[]
    truncated: bool   // parou nos 500
    version: int
end
```

`search.start` dispara uma task que percorre a raiz (pulando `.git`,
`noxy_libs`, `node_modules`, entradas ocultas, arquivos acima de 2 MB e
arquivos que não são UTF-8) e coleta até 500 ocorrências; `poll` recolhe. O
painel mostra o campo, "buscando…", os resultados agrupados por arquivo com
`rel`, e `linha: trecho`; clicar manda `search_open` (path, line, col), que
abre o arquivo e seleciona a ocorrência. Uma consulta nova cancela a
exibição da anterior (a task antiga termina sozinha e é ignorada pela
versão).

## 7. Quick Open

`index.build(root) -> string[]` percorre a raiz numa task com as mesmas
exclusões da busca e devolve os caminhos relativos; roda na partida e pelo
comando "Reindexar arquivos". `index.filter(paths, query, limit) -> Match[]`:
subsequência com pontuação — cada caractere casado soma 1, +3 se no início
do nome, +2 se no início de um segmento (`/`, `_`, `-`, `.`), +1 se
consecutivo; sem consulta, os 50 primeiros em ordem alfabética.

## 8. Paleta de comandos

`commands.nx` lista `Command { id, label, hint }`:

| id | rótulo | atalho |
|---|---|---|
| `save` | Salvar | Ctrl+S |
| `save_all` | Salvar tudo | |
| `close_tab` | Fechar aba | Ctrl+W |
| `run` | Rodar arquivo | F5 |
| `stop` | Parar execução | Ctrl+F5 |
| `find` | Buscar no arquivo | Ctrl+F |
| `replace` | Substituir no arquivo | Ctrl+H |
| `search` | Buscar na pasta | Ctrl+Shift+F |
| `quick_open` | Abrir arquivo | Ctrl+P |
| `panel` | Mostrar ou ocultar o painel | Ctrl+J |
| `terminal` | Terminal | Ctrl+` |
| `theme:dark` … `theme:monokai` | Tema: Escuro, Claro, Dracula, Nord, Monokai | |
| `git_refresh` | Git: atualizar | |
| `reindex` | Reindexar arquivos | |
| `quit` | Sair | Ctrl+Q |

A lista sobre o editor é um componente só, `List { kind: "" \| "palette" \|
"files", query, items: Item[], selected }` na sessão; `list_filter` (texto)
refaz `items`, setas mudam `selected`, `list_pick` executa (`command` para a
paleta, `tree_open` para arquivos), Escape fecha. Todo atalho de teclado
passa a chamar o mesmo `run_command(ref s, id)` que a paleta usa, então os
dois nunca divergem.

## 9. Temas

Cinco conjuntos de variáveis CSS em `editor.css`, selecionados pela classe
`theme-<id>` em `html`: `dark` (o atual, Catppuccin Mocha), `light`
(Catppuccin Latte), `dracula`, `nord`, `monokai`. O comando `theme:<id>`
grava em `settings.json`; o quadro leva `settings.theme`; o cliente só aplica
a classe. Nenhum tema no `localStorage`.

## 10. Git na interface

```noxy
struct GitInfo
    available: bool          // git no PATH e a raiz dentro de um repositório
    branch: string
    status: map[string, string]   // caminho relativo -> "M", "A", "D", "?", "R"…
    dirs: map[string, bool]       // pastas com alteração dentro
    version: int
    task: any
end
```

`gitinfo.refresh` dispara uma task com `git -C <raiz> rev-parse --abbrev-ref HEAD`
e `git -C <raiz> status --porcelain --untracked-files=all`; `poll` recolhe.
Disparado na partida, depois de cada `save`, ao fim de uma execução e pelo
comando "Git: atualizar". `Node` e `TabOut` ganham `git: string`; a status
mostra a branch à direita. Cores: modificado em âmbar, novo ou não rastreado
em verde, apagado riscado; pasta com alteração ganha um ponto. Sem git ou
fora de um repositório, nada aparece e nenhuma mensagem é mostrada.

## 11. Minimap

`minimap.shape(d) -> int[]`: para cada linha, dois inteiros, o comprimento
(máximo 120) e o índice do kind do primeiro token não espaço (0 = vazio).
O quadro leva `minimap { version, lines }` só quando o cliente manda
`want_minimap = true`, o que ele faz quando `minimap_version` do quadro
anterior difere da que tem, no máximo a cada 300 ms. `version` é `edits` da
aba mais um contador de troca de aba. O cliente desenha num canvas de 90 px
à direita do editor, 2 px por linha, cor por kind com opacidade, e a janela
visível como um retângulo translúcido; clicar ou arrastar manda
`minimap_goto` (line) que ajusta `top`.

## 12. Terminal

### 12.1 Extensão `noxy_pty`

Repositório `github.com/estevaofon/noxy_pty`, mesmo molde da
`noxy_webview`: `main.go` com os handlers, `ptys/` com o estado sem
dependência de sistema (testável), `noxy_ext.toml`, `noxy_pty.nx`,
`release/build.sh`, workflow, README.

```toml
name = "pty"
abi = 1
kind = "process"
min_noxy = "0.25.0"
concurrency = "concurrent"   # read bloqueia; write e resize precisam passar
capabilities = ["process"]

[[export]] name = "pty_open"   params = ["string", "string", "int", "int"] returns = "int"    stateful = true   # (cmd, cwd, cols, rows) -> id
[[export]] name = "pty_read"   params = ["int", "int"]                     returns = "string" timeout_ms = 0    # (id, timeout_ms) -> base64; "" no timeout
[[export]] name = "pty_write"  params = ["int", "string"]                  returns = "void"                     # (id, base64)
[[export]] name = "pty_resize" params = ["int", "int", "int"]              returns = "void"                     # (id, cols, rows)
[[export]] name = "pty_close"  params = ["int"]                            returns = "void"                     # mata e fecha
```

- `pty_open`: `creack/pty` com `cmd` (o editor manda `$SHELL` ou `/bin/sh`),
  `cwd`, `TERM=xterm-256color`, tamanho inicial. Vários ids por processo.
- `pty_read`: bloqueia até haver dados ou `timeout_ms`; devolve base64; `""`
  no timeout; erro `pty <id> exited` quando o processo terminou e não há mais
  dados. O binário grava base64 para não depender de como `bytes` viaja no
  JSON do quadro.
- `pty_close`: `SIGHUP` e fecha; idempotente.
- Windows: os handlers existem e `pty_open` devolve `terminal indisponivel no
  Windows nesta versao`; o binário é publicado para o `use` compilar.
- Testes Go: o pacote `ptys` com um leitor falso (abrir, ler com timeout,
  fim de processo, fechar idempotente), com `-race`; e um teste de
  integração com `/bin/sh -c 'echo ok'` real, só no Linux.

### 12.2 Servidor e sessão

`term.nx` guarda `Term { open: bool, id: int, exited: bool, cols, rows }` na
sessão. Eventos pelo dono: `term_open` (abre com `cols`/`rows` do cliente e
`cwd = raiz`), `term_close`, `term_resize` (cols, rows). Dados fora do dono:

| Rota | Efeito |
|---|---|
| `POST /term/read` | corpo `{"id": n}`; `pty_read(id, 1000)`; devolve `{"data": "<base64>"}`; `{"exited": true}` quando o processo terminou |
| `POST /term/write` | corpo `{"id": n, "data": "<base64>"}`; `pty_write` |

Ambas exigem o token. O id do terminal vai no quadro (`term.id`), e um id
que não é o atual é 404, o que encerra o long-poll de uma aba antiga. Quando
`/term/read` devolve `exited`, o cliente manda `term_close` pelo `/event`
para o quadro refletir.

### 12.3 Cliente

`web/vendor/xterm.js`, `xterm.css` e `addon-fit.js` (6.0.0 e 0.11.0, MIT,
com `LICENSE` ao lado), servidos por `GET /vendor/<arquivo>` (lista fixa). A
aba Terminal hospeda um `Terminal` do xterm com o tema atual; `fit` calcula
`cols`/`rows` e manda `term_resize` quando o painel muda de tamanho. Enquanto
`term.open`, um long-poll contínuo em `/term/read` escreve no xterm;
`onData` do xterm manda `/term/write`. O foco: abrir a aba foca o xterm;
Escape (com o xterm focado) e clique no editor devolvem o foco ao editor;
Ctrl+` foca de volta. Quando termina, o xterm mostra `[terminal encerrado —
Enter para abrir outro]`. Um terminal por vez.

## 13. Eventos e quadro (o que muda)

Campos novos em `Event`: `cols: int`, `want_minimap: bool`,
`minimap_version: int`, `git_version: int`, `case: bool`.

| kind | campos | efeito |
|---|---|---|
| `panel_tab` | key | muda a aba do painel |
| `panel_toggle` | | abre ou fecha o painel |
| `stop` | | interrompe a execução |
| `find_open` | key = "replace" para Ctrl+H | abre a barra |
| `find` | text, case | consulta nova |
| `find_next`, `find_prev`, `find_close` | | |
| `replace_one`, `replace_all` | text = substituto | |
| `search` | text, case | busca na pasta |
| `search_open` | path, line, col | abre resultado |
| `quick_open`, `palette` | | abre a lista |
| `list_filter` | text | |
| `list_move` | delta | seleção na lista |
| `list_pick` | index (-1 = o selecionado) | |
| `list_close` | | |
| `command` | key = id | executa um comando da paleta |
| `minimap_goto` | line | |
| `term_open`, `term_close` | cols, rows | |
| `term_resize` | cols, rows | |

Campos novos no quadro: `panel`, `find`, `search`, `list`, `settings`,
`git` (só quando `git_version` difere), `minimap` (só quando pedido),
`term`, `run.stoppable`, `status.eol`; `tabs[].git`, `tree[].git`; spans com
`f` e `c`.

## 14. Atalhos (tabela completa da v1.1)

| Tecla | Ação |
|---|---|
| Setas, Home, End, PageUp, PageDown, Ctrl+Setas, Ctrl+Home/End | como na v1 |
| Ctrl+A, Ctrl+C, Ctrl+X, Ctrl+V, Ctrl+Z, Ctrl+Y, Ctrl+Shift+Z | como na v1 |
| Ctrl+S, Ctrl+W, Ctrl+/, Tab, Shift+Tab, Enter, Ctrl+Q | como na v1 |
| F5 | rodar; Ctrl+F5 parar |
| Ctrl+F, Ctrl+H | buscar, substituir no arquivo |
| Ctrl+Shift+F | buscar na pasta |
| Ctrl+P | abrir arquivo (Quick Open) |
| Ctrl+Shift+P | paleta de comandos |
| Ctrl+J | painel inferior |
| Ctrl+` | terminal |
| Escape | fecha lista, barra de busca ou modal; senão colapsa a seleção; no terminal, devolve o foco ao editor |

## 15. Erros

| Situação | Comportamento |
|---|---|
| `settings.json` inválido | aviso no stderr, padrão em memória, regravado na próxima mudança |
| Cópia de recuperação ilegível | ignorada com aviso no stderr, não apagada |
| Não consegue gravar cópia de recuperação | mensagem na status uma vez, editor segue |
| `git` ausente ou raiz fora de repositório | `git.available = false`, nada na interface |
| Busca na pasta encontra arquivo ilegível | pula em silêncio |
| `pty_open` falha (Windows, sem shell) | aba Terminal mostra a mensagem da extensão |
| `/term/read` com id antigo | 404, o cliente para aquele long-poll |
| Parar sem execução | mensagem "nada rodando" |

Tudo o que já valia na v1 (`call_result` no despacho, sessão intacta em erro
interno) continua.

## 16. Testes

- `tests/run.nx` ganha: `document` (eol), `find` (ocorrências, navegação,
  substituir uma e todas com um undo), `index` (filtro difuso e pontuação),
  `commands` (todo atalho tem comando), `settings` (ler, gravar, inválido),
  `recovery` (gravar, listar, apagar, reabrir na partida com diferença e sem),
  `search` (task sobre `tests/tmp`, exclusões, limite), `gitinfo` (parse do
  porcelain com fixtures; `available = false` fora de repositório), `minimap`
  (shape), `runner` (saída ao vivo em pedaços, código de saída, Parar mata um
  `sleep`), `session`/`events`/`frame` (painel, lista, spans `f`/`c`, campos
  novos só quando pedidos).
- `tests/protocol.nx` ganha as rotas `/term/read` e `/term/write` com a
  extensão instalada: abre, escreve `echo ok\n`, lê `ok`, fecha.
- `tests/web_smoke.py` ganha: barra de busca (Ctrl+F, contador, Enter,
  substituir), busca na pasta com clique em resultado, Quick Open, paleta com
  troca de tema (classe em `html` e `settings.json`), Parar numa execução
  longa, abas do painel, minimap presente e clique nele, terminal (abre, `echo
  ok`, lê `ok` no xterm, fecha).
- `tests/webkit_smoke.py` ganha o painel com abas e o terminal aberto e
  redimensionado.
- Extensão: `go test ./... -race`; `examples/smoke.nx` abre `sh -c 'echo ok'`
  e lê `ok`.
- CI no Ubuntu roda as suítes Noxy.

## 17. Documentação e achados

README com a tabela de atalhos nova, o painel, os temas, o git, o terminal e
a instalação das duas extensões; `tests/MANUAL.md` com terminal interativo
(vim, `top`), Ctrl+C dentro do shell, recuperação depois de fechar pelo X, e
temas. `docs/ACHADOS.md` recebe o que aparecer; já previstos: a ausência de
`kill` e de leitura não bloqueante de processo (contornados com `setsid` e
arquivos), e o transporte de `bytes` no JSON.

## 18. Fora do escopo

Regex na busca; múltiplos terminais; diff por linha e commit pela interface;
recuperação com merge quando o arquivo mudou em disco (a cópia vence e o
usuário decide); atalhos configuráveis; Windows e macOS testados (o binário
Windows da `noxy_pty` só recusa abrir); busca na pasta com substituição.

## 19. Critérios de sucesso

- Fechar pelo X com abas sujas e abrir de novo reabre as abas com o texto,
  marcadas como sujas.
- Um arquivo `\r\n` salvo continua `\r\n` (byte a byte, fora as edições).
- Rodar um programa que imprime em loop mostra a saída ao vivo e Parar o
  encerra, com `[interrompido]` no painel e sem processo órfão.
- Ctrl+F, Ctrl+H, Ctrl+Shift+F, Ctrl+P e Ctrl+Shift+P fazem o que a tabela
  diz, no Chrome headless e na janela WebKitGTK.
- Trocar o tema pela paleta persiste entre execuções.
- Num repositório git, a branch aparece na status e um arquivo editado e
  salvo fica âmbar na árvore.
- O minimap acompanha o arquivo e clicar nele rola.
- Ctrl+` abre um shell interativo onde `vim` e `top` funcionam; fechar o
  editor encerra o shell.
- `noxy tests/run.nx`, `tests/protocol.nx`, os dois smokes e `go test` das
  extensões passam; a CI passa no Ubuntu.
