# Achados sobre a linguagem

O produto principal de um projeto de experimentação: o que o Noxy não deu
conta, o que incomodou e o que sugiro. Para cada item: o que aconteceu, onde
no código, como contornei, sugestão. Entradas novas vão no fim.

Os achados 1 a 6 e 8 a 12 foram resolvidos na v0.26.0 do Noxy (veja o
CHANGELOG dele) e saíram daqui; o editor já usa as respostas: o módulo
`process` no runner, `sort`/`sort_by`, `sys.cache_dir`/`config_dir`/
`temp_dir`, a saída intacta do `exec_output` e as aspas que chegam ao `cmd`.
Os números não mudam, porque o CHANGELOG do Noxy os cita; a próxima entrada
é a 13.

## 7. A VM exige o binário da extensão na importação

**Onde:** `src/launch.nx` (`use github_com.noxylang.noxy_webview.noxy_webview`).
**O que:** `docs/EXTENSIONS.md` diz que o processo de uma extensão começa na
primeira chamada, mas o `use` já falha na compilação quando o binário da
plataforma não está em `bin/` (`extension "webview": binary ... not found —
run 'noxy --sync'`). Não há como um programa degradar graciosamente quando o
package está presente sem o binário: o fallback para o navegador só alcança
falhas em tempo de execução (processo que não sobe ou morre). **Contorno:**
documentar o package como pré-requisito. **Sugestão:** adiar a verificação do
binário para a primeira chamada, como a documentação descreve, ou oferecer um
`use ... optional` cujas chamadas falhem em runtime.
**Resposta (v0.26.0):** o Noxy corrigiu o `docs/EXTENSIONS.md` (o binário
é lido e tem o hash conferido no `use`; só o start do processo espera a
primeira chamada) e manteve a verificação como decisão: a integridade é
conferida antes de o programa rodar qualquer coisa. No executável do
`noxy build` o binário vai embutido, então o caso só aparece rodando pelo
fonte.
