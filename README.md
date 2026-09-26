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
[noxy_webview](https://github.com/estevaofon/noxy_webview), que precisa estar
instalada (veja "Extensão de janela"); se ela não conseguir abrir a janela
nesta máquina, o editor abre num navegador em modo app (Chrome, Chromium,
Brave ou Edge) ou no navegador padrão. Com `NOXY_EDITOR_NO_WINDOW=1` o editor
só imprime a URL, para desenvolver o cliente ou rodar o smoke.

## Extensão de janela

A janela nativa é o package `noxy_webview`, que o editor importa em
`src/launch.nx`. Sem o binário dele em `noxy_libs/.../noxy_webview/bin/` a VM
recusa o `use` na compilação e o editor não abre (é o achado 7 em
`docs/ACHADOS.md`). Dois caminhos:

- **Publicado** (quando houver release no GitHub): `require
  github.com/estevaofon/noxy_webview vX.Y.Z` no `noxy.mod` e `noxy --sync`,
  que baixa o binário da sua plataforma e grava os hashes em `noxy.sum`.
- **Desenvolvimento** (hoje): clone a extensão ao lado deste repositório,
  compile e linke o checkout em `noxy_libs`. A VM avisa uma vez que não há
  entrada em `noxy.sum` e roda.

  ```bash
  git clone https://github.com/estevaofon/noxy_webview ../noxy_webview
  sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev        # Linux
  (cd ../noxy_webview && sh release/build.sh webview && mkdir -p bin && cp dist/noxy-plugin-webview-linux-amd64 bin/)
  mkdir -p noxy_libs/github_com/estevaofon
  ln -sfn "$(pwd)/../noxy_webview" noxy_libs/github_com/estevaofon/noxy_webview
  ```

Se a extensão estiver instalada mas não conseguir abrir a janela nesta máquina
(sem `libwebkit2gtk-4.1`, por exemplo), o editor abre num navegador em modo
app. Nesse modo a URL com o token não vai na linha de comando: o editor grava
uma página de redirecionamento num diretório temporário só seu e passa o
caminho dela ao navegador.

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
| Ctrl+J | mostrar ou ocultar o painel de saída (arraste a barra "Saída" ou o divisor acima dela para redimensionar) |
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
    GDK_BACKEND=x11 python3 tests/webkit_smoke.py   # layout e arraste do painel no WebKitGTK real (PyGObject; abre uma janela)

`tests/MANUAL.md` lista o que só se confere à mão.

## Limitações da v1

Sem busca, paleta de comandos, temas, git, terminal ou minimap. Um programa
que não termina não pode ser interrompido. Fechar pelo X perde alterações não
salvas. Arquivos com `\r\n` são salvos com `\n`. Testado no Linux.
