# Noxy Editor

Um editor de código para arquivos Noxy, escrito em
[Noxy](https://github.com/estevaofon/noxy): abas, árvore de arquivos, busca
no arquivo e na pasta, F5 com a saída ao vivo, terminal integrado, git na
árvore, minimap e temas. Buffer, cursor, seleção, undo, lexer e execução
vivem no Noxy; a janela só pinta o que o Noxy manda e encaminha teclado e
mouse.

<img width="1721" height="1186" alt="image" src="https://github.com/user-attachments/assets/312933a5-0ad3-4e65-a5b6-af41114f5b54" />

## Requisitos

- [Noxy](https://github.com/estevaofon/noxy) v0.26.0, instalado com Go 1.25
  ou mais novo.
- Git, para clonar (e para o editor mostrar a branch e o status dos
  arquivos).

## Instalar

    go install github.com/estevaofon/noxy/cmd/noxy@v0.26.0
    git clone https://github.com/estevaofon/Noxy-Editor
    cd Noxy-Editor
    noxy --sync

O `go install` põe o `noxy` em `$(go env GOPATH)/bin`, que precisa estar no
PATH. O `noxy --sync` baixa as extensões de janela
([noxy_webview](https://github.com/estevaofon/noxy_webview)) e de terminal
([noxy_pty](https://github.com/estevaofon/noxy_pty)) da sua plataforma para
`noxy_libs/` e confere os hashes gravados no `noxy.sum`. Sem esse passo o
editor não abre.

## Rodar com o Noxy

    noxy editor.nx [pasta | arquivo]

Sem argumento abre o diretório atual; um arquivo abre a pasta dele com o
arquivo numa aba. No Windows: `noxy editor.nx C:\projeto` (por dentro o
editor usa `/` em todas as plataformas).

## Rodar como executável

    noxy build editor.nx -o dist/noxy-editor
    dist/noxy-editor [pasta | arquivo]

O `noxy build` gera um executável único, que roda sem `noxy` nem
`noxy_libs` na máquina: ele leva o `web/` (linha `include web` do
`noxy.mod`), as extensões da plataforma e o fonte do editor. Gere na
plataforma onde ele vai rodar: Linux ou Windows (lá sai
`dist\noxy-editor.exe`); no macOS é experimental. O F5 roda os arquivos com
o próprio executável; o terminal integrado não ganha um `noxy` no PATH,
porque o app não instala nada. Detalhes em `docs/BUILD.md` do Noxy.

## Usar

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
dele (fora das abas) ou o divisor acima para redimensionar. A árvore de
arquivos também: arraste a borda direita dela (de 160 px a 60% da janela).
A altura do painel e a largura da árvore ficam guardadas no navegador.

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

O terminal abre o `sh` no Linux e no macOS e o `cmd.exe` do `COMSPEC` no
Windows (mude o `COMSPEC` para usar outro shell).

## Desenvolvimento

### Como está organizado

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

### Extensões

A janela é o package [noxy_webview](https://github.com/estevaofon/noxy_webview)
(WebKitGTK no Linux, WebView2 no Windows, WKWebView no macOS), importado em
`src/launch.nx`; o terminal é o [noxy_pty](https://github.com/estevaofon/noxy_pty),
em Go puro (pty no Linux e no macOS, ConPTY no Windows), importado em
`src/term.nx`. Os dois vêm do `noxy.mod` e são instalados pelo `noxy --sync`.

Quando a janela não abre, o editor usa o navegador em modo app sem pôr a URL
com o token na linha de comando: grava uma página de redirecionamento num
diretório temporário só seu e passa o caminho dela ao navegador. Com
`NOXY_EDITOR_NO_WINDOW=1` o editor só imprime a URL, para desenvolver o
cliente ou rodar os testes do navegador.

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

### Testes

    noxy tests/run.nx            # o núcleo inteiro, sem navegador
    noxy tests/protocol.nx       # servidor + cliente HTTP in-process
    python3 tests/web_smoke.py   # o cliente web num Chrome headless (precisa de google-chrome)
    GDK_BACKEND=x11 python3 tests/webkit_smoke.py   # layout, arraste do painel e da árvore e terminal no WebKitGTK real (PyGObject; abre uma janela)

A CI (`.github/workflows/ci.yml`) roda as duas suítes Noxy no Ubuntu e no
Windows, com um shell de verdade no terminal (`sh` e `cmd.exe`). Os testes
usam cache e configuração próprios em `tests/tmp`, nunca os seus.

`tests/MANUAL.md` lista o que só se confere à mão.
