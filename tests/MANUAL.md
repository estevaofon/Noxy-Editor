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
