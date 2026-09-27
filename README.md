# Noxy Editor

Um editor de código para arquivos Noxy, escrito em
[Noxy](https://github.com/estevaofon/noxy). Buffer, cursor, seleção, undo,
lexer, abas, árvore de arquivos e execução vivem no Noxy; o navegador só pinta
o que o Noxy manda e encaminha teclado e mouse. É um projeto de experimentação
da linguagem: o que ela não deu conta está em [docs/ACHADOS.md](docs/ACHADOS.md).

<img width="1721" height="1186" alt="image" src="https://github.com/user-attachments/assets/312933a5-0ad3-4e65-a5b6-af41114f5b54" />

## Rodar

    noxy editor.nx [pasta | arquivo]

Sem argumento abre o diretório atual. Um arquivo abre a pasta dele com o
arquivo numa aba. Roda no Linux, no macOS e no Windows (`noxy editor.nx
C:\projeto`; por dentro o editor usa `/` em todas as plataformas). A janela é a extensão
[noxy_webview](https://github.com/estevaofon/noxy_webview), instalada com
`noxy --sync` (veja "Extensão de janela"); se ela não conseguir abrir a
janela nesta máquina, o editor abre num navegador em modo app (Chrome,
Chromium, Brave ou Edge) ou no navegador padrão. Com `NOXY_EDITOR_NO_WINDOW=1` o editor
só imprime a URL, para desenvolver o cliente ou rodar o smoke.

## Distribuir

    noxy build editor.nx -o dist/noxy-editor

gera um executável único (Linux e Windows; macOS experimental) que roda sem
`noxy` nem `noxy_libs` na máquina: `dist/noxy-editor pasta`. Ele leva o
`web/` (linha `include web` do `noxy.mod`), os plugins `noxy_webview` e
`noxy_pty` desta plataforma e o fonte do editor — legível com `unzip`. O F5
roda os arquivos com o próprio executável (`sys.executable()` +
`NOXY_INTERPRETER=1` no processo filho); o terminal integrado **não** ganha
um `noxy` no PATH, porque o app não instala nada. Detalhes em
`docs/BUILD.md` do noxy.

## Extensão de janela

A janela nativa é o package [`noxy_webview`](https://github.com/estevaofon/noxy_webview),
que o editor importa em `src/launch.nx`. O `noxy.mod` já o exige
(`require github.com/estevaofon/noxy_webview v0.1.0`), então num clone novo
basta:

    noxy --sync

Isso baixa o binário da sua plataforma (Linux, Windows, macOS Intel e Apple
Silicon) para `noxy_libs/.../noxy_webview/bin/` e confere os hashes gravados
em `noxy.sum`. Sem esse binário a VM recusa o `use` na compilação e o editor
não abre (achado 7 em `docs/ACHADOS.md`). Em runtime, o Linux precisa de
`libwebkit2gtk-4.1`, presente em desktops GNOME.

Se a extensão estiver instalada mas não conseguir abrir a janela nesta máquina
(sem `libwebkit2gtk-4.1`, por exemplo), o editor abre num navegador em modo
app. Nesse modo a URL com o token não vai na linha de comando: o editor grava
uma página de redirecionamento num diretório temporário só seu e passa o
caminho dela ao navegador.

Para mexer na extensão em vez de usar o release, clone-a ao lado deste
repositório, compile e linke o checkout no lugar do package instalado:

```bash
git clone https://github.com/estevaofon/noxy_webview ../noxy_webview
sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev        # Linux
(cd ../noxy_webview && sh release/build.sh webview && mkdir -p bin && cp dist/noxy-plugin-webview-linux-amd64 bin/)
rm -rf noxy_libs/github_com/estevaofon/noxy_webview
ln -sfn "$(pwd)/../noxy_webview" noxy_libs/github_com/estevaofon/noxy_webview
```

A VM avisa uma vez que o checkout não bate com o `noxy.sum` e roda.

## Extensão de terminal

O terminal (Ctrl+`) é o package [`noxy_pty`](https://github.com/estevaofon/noxy_pty),
importado em `src/term.nx` e instalado pelo mesmo `noxy --sync`. É Go puro,
sem dependências de sistema: pty no Linux e no macOS, pseudoconsole
(ConPTY) no Windows, onde abre o `cmd.exe` do `COMSPEC` e precisa do Windows
10 1809 ou mais novo.

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
| F5 | salvar e rodar o arquivo ativo, com a saída ao vivo no painel |
| Ctrl+F5 | parar o programa (também o botão Parar do painel) |
| Ctrl+F, Ctrl+H | buscar, substituir no arquivo (F3 e Shift+F3 navegam) |
| Ctrl+Shift+F | buscar na pasta |
| Ctrl+P | abrir arquivo pelo nome |
| Ctrl+Shift+P | paleta de comandos (inclui os temas) |
| Ctrl+J | mostrar ou ocultar o painel inferior |
| Ctrl+` | terminal; com o terminal focado, volta ao editor |
| Escape | fecha lista, barra de busca ou modal; senão colapsa a seleção (no terminal, vai para o shell) |
| Ctrl+Q | sair (pergunta se há abas com alterações) |

Mouse: clique posiciona, arraste seleciona, duplo clique seleciona a palavra,
clique no gutter seleciona a linha, roda rola, clique ou arraste no minimap
rola. O painel inferior tem as abas Saída, Busca e Terminal; arraste a barra
dele (fora das abas) ou o divisor acima para redimensionar.

**Alterações não salvas não se perdem.** Cada aba suja tem uma cópia em
`~/.cache/noxy-editor/recovery/` (`%LOCALAPPDATA%\noxy-editor\recovery\` no
Windows, `~/Library/Caches/noxy-editor/recovery/` no macOS), gravada no
máximo uma vez por segundo e 1,5 s depois da última tecla. Fechar pelo X,
uma queda do editor ou da máquina: na próxima vez que a pasta for aberta,
as abas voltam sujas, com o texto. Salvar ou fechar sem salvar apaga a cópia.

**Temas**: Escuro, Claro, Dracula, Nord e Monokai, pela paleta ("Tema: ...").
A escolha fica em `~/.config/noxy-editor/settings.json`
(`%APPDATA%\noxy-editor\settings.json` no Windows,
`~/Library/Application Support/noxy-editor/settings.json` no macOS).

**Git**: se a pasta está num repositório, a branch aparece na barra de
status e os arquivos modificados (âmbar), novos (verde) e apagados (riscados)
ficam marcados na árvore e nas abas; atualiza ao salvar, ao fim de uma
execução e pelo comando "Git: atualizar".

Arquivos com `\r\n` continuam com `\r\n` ao salvar; a barra de status
mostra LF ou CRLF.

## Como está organizado

A routine principal de `editor.nx` é a dona de todo o estado. O servidor HTTP
da stdlib (`src/server`) roda cada requisição numa routine própria e só
empacota o evento com um canal de resposta; o dono aplica e responde o quadro.

| Módulo | Responsabilidade |
|---|---|
| `src/document` | linhas de texto, posições em code points, a quebra de linha do arquivo |
| `src/lexer` | tokenizador de Noxy, uma linha por vez |
| `src/history` | undo e redo por snapshot (copy-on-write faz a cópia ser rasa) |
| `src/editing` | cursor, seleção, scroll e as operações de edição de uma aba |
| `src/find` | busca e substituição no arquivo |
| `src/search` | busca na pasta, numa task |
| `src/index` | índice de arquivos e o filtro difuso do Ctrl+P |
| `src/commands` | os comandos da paleta |
| `src/settings` | `settings.json` |
| `src/recovery` | cópias de recuperação das abas sujas |
| `src/gitinfo` | branch e status do git, numa task |
| `src/minimap` | o formato do arquivo para o minimap |
| `src/term` | o terminal sobre a extensão `noxy_pty` |
| `src/session` | raiz, abas, árvore, painel, lista, modal, abrir, salvar, fechar |
| `src/runner` | roda o arquivo em segundo plano, saída ao vivo, Parar |
| `src/platform` | o que muda por plataforma: caminhos, diretórios do usuário, temporários, argumentos para o shell do `sys.exec` |
| `src/frame` | o quadro JSON com as linhas visíveis tokenizadas |
| `src/events` | do JSON do evento ao efeito na sessão, dentro de `call_result` |
| `src/server` | rotas, token, a ponte com o dono do estado e as rotas `/term` |
| `src/launch`, `src/browser` | janela pela extensão, fallback navegador |
| `web/` | o cliente: `index.html`, `editor.css`, `editor.js`; `web/vendor/` tem o xterm.js |

Design e plano em `docs/superpowers/`.

## Testes

    noxy tests/run.nx            # o núcleo inteiro, sem navegador
    noxy tests/protocol.nx       # servidor + cliente HTTP in-process
    python3 tests/web_smoke.py   # o cliente web num Chrome headless (precisa de google-chrome)
    GDK_BACKEND=x11 python3 tests/webkit_smoke.py   # layout, arraste do painel e terminal no WebKitGTK real (PyGObject; abre uma janela)

A CI (`.github/workflows/ci.yml`) roda as duas suítes Noxy no Ubuntu e no
Windows, com um shell de verdade no terminal (`sh` e `cmd.exe`). Os testes
usam cache e configuração próprios em `tests/tmp`, nunca os seus.

`tests/MANUAL.md` lista o que só se confere à mão.

## Limitações

Busca sem regex; um terminal por vez; git só para ver (commit, pull e push
pelo terminal); o programa executado recebe `/dev/null` (`nul` no Windows)
como entrada (para programas interativos, use o terminal).

No Windows: Parar termina a árvore de processos na hora (o job do
programa), sem os 2 s de TERM do Linux; um `%` no nome da raiz ou do
arquivo pode quebrar o F5 e o git (o `cmd` expande `%VAR%` mesmo entre
aspas); e o terminal é o `cmd.exe` (mude o `COMSPEC` para outro shell). O
Linux e o macOS usam `sh`; o Windows usa `cmd`, sem depender de Git Bash ou
WSL.
