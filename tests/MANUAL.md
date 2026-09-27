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
- [ ] Com a extensão recusando a janela (troque a largura `1200` por `0` no `webview.open` de `src/launch.nx`), o editor avisa `janela pela extensao indisponivel` no terminal e abre no navegador em modo app; fechar a janela do navegador encerra o `noxy` em uns 3 s. Desfaça a troca depois. Trocar ou tirar o binário da extensão não serve: o `use` confere o binário contra o `noxy.sum` e o editor nem abre (achado 7 de `docs/ACHADOS.md`).
- [ ] `NOXY_WEBVIEW_DEBUG=1 noxy editor.nx .` abre com o inspetor do WebKit disponível.
- [ ] Terminal (Ctrl+`): `vim` abre, Escape troca de modo, `:q` sai; `top` desenha e atualiza; Ctrl+C interrompe um `sleep 100`.
- [ ] Redimensionar o painel com `top` aberto: o `top` redesenha no tamanho novo.
- [ ] Fechar a janela pelo X com `sleep 1000` no terminal e um programa rodando pelo F5: `pgrep -f "sleep 1000"` vazio e `pgrep -af noxy` sem o arquivo do F5.
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
- [ ] Ctrl+` abre um `cmd.exe` na pasta aberta, com o prompt e acentos certos (`dir` numa pasta com `café.nx`); `cls` limpa; Ctrl+C interrompe um `ping -t 127.0.0.1`; `exit` fecha e a aba avisa que o shell terminou.
- [ ] Redimensionar o painel com o terminal aberto: `mode con` mostra o tamanho novo.
- [ ] Fechar a janela pelo X com um `ping -t 127.0.0.1` no terminal: nenhum `ping.exe` nem `cmd.exe` órfão no Gerenciador de Tarefas.
- [ ] Editar sem salvar, fechar pelo X, abrir a mesma pasta: a aba volta suja (a cópia fica em `%LOCALAPPDATA%\noxy-editor\recovery\`).
- [ ] Trocar o tema e reabrir: continua (`%APPDATA%\noxy-editor\settings.json`).
- [ ] Numa pasta com espaço e acento no caminho dentro de um repositório: a branch aparece na status e um arquivo salvo fica âmbar.
- [ ] Fechar pelo X encerra o `noxy.exe` e o `noxy-plugin-webview-windows-amd64.exe`.
- [ ] Com o WebView2 quebrado (`set WEBVIEW2_BROWSER_EXECUTABLE_FOLDER=C:\nao\existe` no prompt antes de abrir o editor), depois de uns 30 s o editor avisa `janela pela extensao indisponivel` e abre no Chrome ou Edge em modo app; fechar essa janela encerra o `noxy.exe` em uns 3 s; sem Chrome nem Edge, abre no navegador padrão. Feche o prompt depois. Renomear o binário da extensão não serve: o editor nem abre (achado 7 de `docs/ACHADOS.md`).
