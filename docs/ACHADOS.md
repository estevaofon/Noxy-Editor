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
