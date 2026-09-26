# Achados sobre a linguagem

O produto principal de um projeto de experimentação: o que o Noxy não deu
conta, o que incomodou e o que sugiro. Para cada item: o que aconteceu, onde
no código, como contornei, sugestão. Entradas novas vão no fim.

## 1. Não há como interromper um processo filho

**Onde:** `src/runner.nx`. **O que:** `sys.exec_output` bloqueia até o
programa terminar e não devolve handle; um programa que não termina (servidor,
jogo) fica rodando até o editor sair, e a saída só aparece no fim.
**Contorno (v1.1):** o shell faz o trabalho: `setsid sh -c '...' & echo $!`
dá o PID do líder de um grupo de processos próprio, a saída vai para um
arquivo lido aos pedaços a cada evento (`io.read_bytes` num handle aberto
devolve só o que chegou), um arquivo `code` marca o fim, e Parar é
`kill -TERM -PGID` (no `sh` do Ubuntu, o dash, sem `--`). **Sugestão:**
`sys.spawn_process(cmd) -> Process` com `kill`, `wait` e leitura não
bloqueante da saída.

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

## 10. No Windows, `sys.exec` não consegue entregar aspas duplas ao `cmd`

**Onde:** `src/platform.nx` (`arg`), `src/runner.nx`, `src/gitinfo.nx`,
`src/browser.nx`. **O que:** no Windows `sys.exec` e `sys.exec_output` rodam
`exec.Command("cmd", "/C", comando)`, e o Go monta a linha de comando
escapando cada `"` do argumento como `\"` (`syscall.EscapeArg`); o `cmd`
tira só as aspas externas e repassa os `\"` ao programa, que os lê como
aspas literais. `echo "a b"` imprime `\"a b\"`, e `git -C "D:\pasta com
espaço" status` chega ao git como `-C`, `"D:\pasta`, `com`, `espaço"`. Sem
aspas, nenhum caminho com espaço passa. **Contorno:** o valor vai, já entre
aspas, numa variável de ambiente (`sys.setenv`, que o filho herda) e o
comando recebe `%NOME%`, que o `cmd` expande antes de tratar aspas
(`platform.arg`); o runner monta a linha inteira do programa numa variável
e o PowerShell a repassa a um `cmd` oculto (`Start-Process -PassThru`, que
também é o único jeito de obter o PID). **Sugestão:** no Windows, `sys.exec`
usar `SysProcAttr.CmdLine` com `cmd /S /C "<comando>"` intacto, ou um
`sys.exec_args(argv)` sem shell.

## 11. Não há como saber os diretórios do usuário nem o temporário

**Onde:** `src/platform.nx`. **O que:** a stdlib não tem equivalente a
`os.UserCacheDir`, `os.UserConfigDir` e `os.TempDir`. `HOME` não existe no
Windows (é `USERPROFILE`), e cache e configuração ficam em `LOCALAPPDATA` e
`APPDATA`, não em `~/.cache` e `~/.config`; o temporário é `TEMP`, não
`/tmp`, e `mktemp` não existe. **Contorno:** montar em Noxy a partir das
variáveis de ambiente de cada plataforma, com `uuid.uuid4()` no lugar do
`mktemp -d`. **Sugestão:** `sys.cache_dir()`, `sys.config_dir()` e
`sys.temp_dir()` sobre as funções do Go.

## 12. `sys.exec_output` recusa a saída do console do Windows

**Onde:** `runner.group_alive` e `runner.kill_group`. **O que:** `tasklist`
e `taskkill` escrevem as mensagens na codepage do console (cp850 num
Windows em português), que não é UTF-8; `exec_output` devolve `ok=false`,
`output=""` e um erro de UTF-8 mesmo com `exit_code=0`, e não há como ler
os bytes. **Contorno:** `tasklist /FO CSV`, que só tem ASCII quando há
tarefa, e tratar `ok=false` como "sem processo"; `taskkill` por `sys.exec`
com `>nul 2>nul`. **Sugestão:** um `output_bytes` no `SysResult`, ou
decodificar pela codepage do console.
