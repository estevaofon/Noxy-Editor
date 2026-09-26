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
- [ ] Com a extensão incapaz de abrir (troque `bin/noxy-plugin-webview-linux-amd64` no package por um script `#!/bin/sh` que faz `exit 127`, guardando o binário real), o editor avisa `janela pela extensao indisponivel` no terminal e abre no navegador em modo app; fechar a janela do navegador encerra o `noxy` em até 3 s. Restaure o binário depois.
- [ ] `NOXY_WEBVIEW_DEBUG=1 noxy editor.nx .` abre com o inspetor do WebKit disponível.
- [ ] Terminal (Ctrl+`): `vim` abre, Escape troca de modo, `:q` sai; `top` desenha e atualiza; Ctrl+C interrompe um `sleep 100`.
- [ ] Redimensionar o painel com `top` aberto: o `top` redesenha no tamanho novo.
- [ ] Fechar a janela pelo X com `sleep 1000` no terminal e um programa rodando pelo F5: `pgrep -f "sleep 1000"` e `pgrep -f "exec noxy"` vazios.
- [ ] Editar sem salvar, fechar pelo X, abrir a mesma pasta: a aba volta suja, com o texto.
- [ ] Trocar o tema pela paleta, fechar e abrir: o tema continua.
- [ ] Num repositório, salvar um arquivo: ele fica âmbar na árvore e na aba; a branch aparece na status.
- [ ] F5 num programa que imprime em loop: a saída aparece ao vivo; Parar encerra com `[interrompido]`.

## Windows

Com o `noxy` no PATH de um prompt (cmd ou PowerShell), sem Git Bash nem WSL:

- [ ] `noxy editor.nx C:\pasta com espaço` abre a janela nativa (WebView2) com a árvore; o log diz `(webview)`.
- [ ] `noxy editor.nx arquivo.nx` abre a pasta do arquivo com ele numa aba e o título `arquivo.nx — Noxy Editor`.
- [ ] F5 num `.nx` que imprime aos poucos: a saída aparece ao vivo no painel e termina com `[saiu com N]`; nenhuma janela de console pisca.
- [ ] F5 num programa sem fim e Parar: `[interrompido]` no painel e nenhum `noxy.exe` sobrando no Gerenciador de Tarefas além do editor.
- [ ] Ctrl+` mostra `terminal: terminal indisponivel no Windows nesta versao` na barra de status; o editor continua.
- [ ] Editar sem salvar, fechar pelo X, abrir a mesma pasta: a aba volta suja (a cópia fica em `%LOCALAPPDATA%\noxy-editor\recovery\`).
- [ ] Trocar o tema e reabrir: continua (`%APPDATA%\noxy-editor\settings.json`).
- [ ] Numa pasta com espaço e acento no caminho dentro de um repositório: a branch aparece na status e um arquivo salvo fica âmbar.
- [ ] Fechar pelo X encerra o `noxy.exe` e o `noxy-plugin-webview-windows-amd64.exe`.
- [ ] Com o binário da extensão renomeado (guarde o original), o editor avisa `janela pela extensao indisponivel` e abre no Chrome ou Edge em modo app; sem eles, no navegador padrão.
