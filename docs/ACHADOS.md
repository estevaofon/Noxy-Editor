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

## 6. Importar um módulo ausente pode derrubar o compilador com panic

**Onde:** `tests/protocol.nx` antes de `src/server.nx` existir (Task 11 do
plano). **O que:** com `use src.server as server` apontando para um módulo que
não existe, e o programa usando `server.Request` num struct e `server.inbox`
numa routine, o `noxy` respondeu `Recovered from panic: runtime error:
invalid memory address or nil pointer dereference` com stack de
`internal/compiler/compiler.go` (linhas 2521, 2427, 453, 2414, 1796, 3839),
em vez do `module not found: src.server` que os outros casos dão.
**Contorno:** nenhum; criar o módulo. **Sugestão:** o compilador tratar a
falha de carga do módulo antes de resolver membros qualificados
(`server.Request` como tipo de campo parece ser o gatilho, diferente de
`server.x` numa expressão).

## 7. A VM exige o binário da extensão na importação

**Onde:** `src/launch.nx` (`use github_com.estevaofon.noxy_webview.noxy_webview`).
**O que:** `docs/EXTENSIONS.md` diz que o processo de uma extensão começa na
primeira chamada, mas o `use` já falha na compilação quando o binário da
plataforma não está em `bin/` (`extension "webview": binary ... not found —
run 'noxy --sync'`). Não há como um programa degradar graciosamente quando o
package está presente sem o binário: o fallback para o navegador só alcança
falhas em tempo de execução (processo que não sobe ou morre). **Contorno:**
documentar o package como pré-requisito. **Sugestão:** adiar a verificação do
binário para a primeira chamada, como a documentação descreve, ou oferecer um
`use ... optional` cujas chamadas falhem em runtime.

## 8. `time_now()` devolve segundos, não milissegundos

**Onde:** `editor.nx` (o relógio do dono do estado) e tudo o que media
tempo com ele. **O que:** o README do Noxy descreve `time_now()` como
"timestamp in ms", mas o valor é em segundos (`1790399009` contra
`1790399009754` de `date +%s%3N`). O editor tratava o valor como ms: o
agrupamento de digitação do undo, de 1 s, virava 1000 s (tudo digitado em
16 minutos desfazia de uma vez), e o teste de desempenho do quadro comparava
segundos com 200. **Contorno:** `events.now()` usa `time.now_ms()`, com teste
que dorme 120 ms e confere a diferença. **Sugestão:** corrigir a descrição no
README, ou fazer `time_now()` devolver ms como documentado e deixar
`time.now()` para segundos.

## 9. `sys.exec_output` apara espaços nas pontas da saída

**Onde:** `src/gitinfo.nx`. **O que:** `SysResult.output` volta sem os
espaços e quebras do começo e do fim (`"  dois espacos\n fim  \n"` vira
`"dois espacos\n fim"`). Para saída com formato posicional isso corrompe
dados: a primeira linha do `git status --porcelain` (` M a.nx`) perdia o
espaço e o caminho perdia a primeira letra. **Contorno:** uma linha `#` antes
do comando (`echo '#'; git status ...`), ignorada no parse. **Sugestão:**
devolver a saída intacta; quem quiser aparar usa `strings.trim`.
