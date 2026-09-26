# tests/web_smoke.py — o cliente web de verdade: sobe o editor sem janela,
# abre a pagina num Chrome headless pelo DevTools Protocol (tests/cdp.py) e
# exercita teclado, mouse, clipboard, F5 e modal. Precisa de google-chrome.
#     python3 tests/web_smoke.py      (a partir da raiz do projeto)
import base64, json, sys, time, re
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import WS, start_chrome, page_ws

import subprocess
# estado limpo: uma pasta de demo nova em tests/tmp/web e o editor sem janela
demo = os.path.join("tests", "tmp", "web")
os.makedirs(os.path.join(demo, "src"), exist_ok=True)
open(os.path.join(demo, "exemplo.nx"), "w").write('use sys\n// um exemplo para o editor\nfunc soma(a: int, b: int) -> int\n    return a + b\nend\nlet nome: string = "Noxy"\nprint(f"ola {nome}: {soma(2, 3)}")\nfor i in range(3) do\n    print(i)\nend\n')
open(os.path.join(demo, "notas.txt"), "w").write("texto simples\n")
open(os.path.join(demo, "src", "util.nx"), "w").write("let x = 1\n")
cfg = os.path.join(os.getcwd(), "tests", "tmp", "web_config")
env = dict(os.environ, NOXY_EDITOR_NO_WINDOW="1", NOXY_EDITOR_CONFIG_DIR=cfg, NOXY_EDITOR_CACHE_DIR=os.path.join(os.getcwd(), "tests", "tmp", "web_cache"))
import shutil as _sh; _sh.rmtree(env["NOXY_EDITOR_CACHE_DIR"], ignore_errors=True)
if os.path.exists(os.path.join(cfg, "settings.json")): os.remove(os.path.join(cfg, "settings.json"))
log = os.path.join("tests", "tmp", "web_editor.log")
editor = subprocess.Popen(["noxy", "editor.nx", demo], env=env, stdout=subprocess.DEVNULL, stderr=open(log, "w"))
url = None
for _ in range(50):
    m = re.search(r"http://127\.0\.0\.1:\d+/\?t=[a-z0-9-]+", open(log).read())
    if m: url = m.group(0); break
    time.sleep(0.1)
chrome = start_chrome(9333)
ws = WS(page_ws(9333))
ws.call("Page.enable"); ws.call("Runtime.enable")
fails = 0
def ev(expr):
    r = ws.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
    if "exceptionDetails" in r: raise RuntimeError(r["exceptionDetails"])
    return r["result"].get("value")
def check(name, cond):
    global fails
    print(("  ok   " if cond else "FAIL   ") + name)
    if not cond: fails += 1
def settle(ms=350): time.sleep(ms / 1000)
def key(k, text=None, mods=0, code=None):
    p = {"type": "keyDown", "key": k, "modifiers": mods, "windowsVirtualKeyCode": 0}
    if text: p["text"] = text
    ws.call("Input.dispatchKeyEvent", p)
    p["type"] = "keyUp"; p.pop("text", None)
    ws.call("Input.dispatchKeyEvent", p)
    settle()
def insert(text):
    ws.call("Input.insertText", {"text": text}); settle()
# cursor_diff: distancia entre a barra do cursor e o caret real na coluna
# que a barra de status mostra, calculado por um Range independente do
# cliente; zero quando o cursor esta desenhado no lugar certo.
def cursor_diff():
    return ev("""(() => {
      const lineEl = document.querySelector('.line.cur');
      const st = document.getElementById('status-right').textContent.match(/Ln (\\d+), Col (\\d+)/);
      const col = parseInt(st[2], 10) - 1;
      let remaining = col, x = null, last = null, node;
      const walker = document.createTreeWalker(lineEl, NodeFilter.SHOW_TEXT);
      while ((node = walker.nextNode())) {
        const len = Array.from(node.data).length;
        if (remaining <= len) {
          let i = 0, n = 0;
          while (n < remaining) { i += node.data.codePointAt(i) > 0xffff ? 2 : 1; n++; }
          const r = document.createRange(); r.setStart(node, i); r.collapse(true);
          x = r.getBoundingClientRect().left; break;
        }
        remaining -= len; last = node;
      }
      if (x === null) {
        if (!last) return document.getElementById('cursor').getBoundingClientRect().left - (lineEl.getBoundingClientRect().left + 4);
        const r = document.createRange(); r.setStart(last, last.data.length); r.collapse(true);
        x = r.getBoundingClientRect().left;
      }
      return document.getElementById('cursor').getBoundingClientRect().left - x;
    })()""")
def cursor_in_view():
    return ev("""(() => { const c = document.getElementById('cursor').getBoundingClientRect(); const b = document.getElementById('editor').getBoundingClientRect(); return c.left >= b.left + 56 && c.right <= b.right; })()""")

def mouse(kind, x, y, button="left", clicks=1, mods=0):
    ws.call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": button, "clickCount": clicks, "modifiers": mods})

ws.call("Page.navigate", {"url": url}); settle(1500)
check("arvore renderizada", ev("document.querySelectorAll('#tree .node').length") == 3)
check("nome da raiz", ev("document.getElementById('root-name').textContent") == "web")
check("titulo inicial", ev("document.title") == "Noxy Editor")
check("tema escuro aplicado no html", ev("document.documentElement.classList.contains('theme-dark')"))
# abrir exemplo.nx pela arvore
ev("document.querySelectorAll('#tree .node.file')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
check("abrir arquivo cria aba e linhas", ev("document.querySelectorAll('.tab').length") == 1 and ev("document.querySelectorAll('#text .line').length") == 11)
check("highlighting: keyword e string", ev("!!document.querySelector('.k-keyword') && !!document.querySelector('.k-string')"))
check("cursor visivel na linha 1", ev("!document.getElementById('cursor').classList.contains('hidden') && document.querySelector('.line.cur').dataset.n") == "0")
check("textarea focado", ev("document.activeElement.id") == "input")
# End + digitar com acento
key("End")
insert("ção")
check("digitar acentos no fim da linha 1", ev("document.querySelector('.line[data-n=\"0\"]').textContent") == "use sysção")
check("status mostra a aba suja", "●" in ev("document.getElementById('status-left').textContent"))
check("titulo com a bolinha", ev("document.title").startswith("exemplo.nx ●"))
# Enter + Ctrl+Z
key("Enter")
check("enter cria linha", ev("document.querySelectorAll('#text .line').length") == 12)
key("z", mods=2)
check("ctrl+z desfaz o enter", ev("document.querySelectorAll('#text .line').length") == 11)
key("z", mods=2)
check("ctrl+z desfaz a digitacao", ev("document.querySelector('.line[data-n=\"0\"]').textContent") == "use sys")
# clique numa posicao do texto: linha 3 (func soma...), depois de 'func '
rect = ev("(() => { const r = document.querySelector('.line[data-n=\"2\"] .k-call').getBoundingClientRect(); return [r.left, r.top, r.height]; })()")
mouse("mousePressed", rect[0] + 1, rect[1] + rect[2] / 2); mouse("mouseReleased", rect[0] + 1, rect[1] + rect[2] / 2); settle()
check("clique posiciona o cursor", "Ln 3, Col 6" in ev("document.getElementById('status-right').textContent"))
d = cursor_diff()
check("cursor desenhado na coluna do status (diferenca %.1f px)" % d, abs(d) < 1.5)
# shift+End seleciona ate o fim
key("End", mods=8)
check("shift+end seleciona", ev("document.querySelectorAll('.line[data-n=\"2\"] .sel').length") > 0)
# Ctrl+C copia -> clipboard interno; depois Ctrl+V cola via evento paste sintetico
key("c", mods=2)
ev("(() => { const dt = new DataTransfer(); dt.setData('text', 'X'); document.getElementById('input').dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true})); })()"); settle()
check("paste substitui a selecao", ev("document.querySelector('.line[data-n=\"2\"]').textContent") == "func X")
# arrastar: da coluna 0 da linha 4 ate a linha 5
r4 = ev("(() => { const r = document.querySelector('.line[data-n=\"3\"]').getBoundingClientRect(); return [r.left, r.top, r.height]; })()")
mouse("mousePressed", r4[0] + 2, r4[1] + 5); mouse("mouseMoved", r4[0] + 40, r4[1] + r4[2] + 5); settle(); mouse("mouseReleased", r4[0] + 40, r4[1] + r4[2] + 5); settle()
check("arrastar seleciona duas linhas", ev("document.querySelectorAll('.line[data-n=\"3\"] .sel').length") > 0 and ev("document.querySelectorAll('.line[data-n=\"4\"] .sel').length") > 0)
# duplo clique seleciona palavra
key("Escape")
r6 = ev("(() => { const r = document.querySelector('.line[data-n=\"5\"] .k-type').getBoundingClientRect(); return [r.left, r.top, r.height]; })()")
mouse("mousePressed", r6[0] + 3, r6[1] + 5, clicks=1); mouse("mouseReleased", r6[0] + 3, r6[1] + 5, clicks=1)
mouse("mousePressed", r6[0] + 3, r6[1] + 5, clicks=2); mouse("mouseReleased", r6[0] + 3, r6[1] + 5, clicks=2); settle()
check("duplo clique seleciona a palavra", ev("Array.from(document.querySelectorAll('.line[data-n=\"5\"] .sel')).map(e => e.textContent).join('')") == "string")
# roda do mouse: o arquivo tem 10 linhas e a janela mais que isso, entao top fica 0; testa que nao quebra
ws.call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": r6[0], "y": r6[1], "deltaX": 0, "deltaY": 100}); settle()
check("roda nao quebra com arquivo curto", ev("document.querySelectorAll('#text .line').length") == 11)
# F5 roda o arquivo (salva antes) e o painel aparece
key("F5"); settle(1500)
check("F5 mostra o painel de saida", not ev("document.getElementById('output').classList.contains('hidden')"))
out = ev("document.getElementById('output-text').textContent")
check("saida do programa aparece", "$ noxy exemplo.nx" in out and "[saiu com" in out)
# parar pelo botao: um programa sem fim com saida ao vivo
open(os.path.join(demo, "sem_fim.nx"), "w").write('use sys\nlet i = 0\nwhile true do\n    print(f"volta {i}")\n    i = i + 1\n    sys.sleep(100)\nend\n')
key("p", mods=2); ws.call("Input.insertText", {"text": "sem_fim"}); settle(); key("Enter")
key("F5"); settle(1200)
check("saida ao vivo enquanto roda", "volta 2" in ev("document.getElementById('output-text').textContent") and not ev("document.getElementById('run-stop').classList.contains('hidden')"))
ev("document.getElementById('run-stop').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle(1500)
check("parar encerra e esconde o botao", "[interrompido]" in ev("document.getElementById('output-text').textContent") and ev("document.getElementById('run-stop').classList.contains('hidden')"))
ev("document.querySelector('.tab.active .close').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
print("SAIDA:", out.replace("\n", " | ")[:200])
# painel de saida: altura inicial de 35% da area, divisor arrastavel, Ctrl+J alterna
def output_h(): return ev("document.getElementById('output').getBoundingClientRect().height")
main_h = ev("document.getElementById('main').clientHeight")
h0 = output_h()
check("painel de saida abre com 35%% da area (%.0f de %.0f px)" % (h0, main_h), abs(h0 - 0.35 * main_h) < 3)
grip = ev("(() => { const g = document.getElementById('output-resize'); if (!g) return null; const r = g.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
check("divisor do painel existe", grip is not None)
if grip:
    mouse("mousePressed", grip[0], grip[1]); mouse("mouseMoved", grip[0], grip[1] - 120); settle(); mouse("mouseReleased", grip[0], grip[1] - 120); settle()
    h1 = output_h()
    check("arrastar o divisor para cima aumenta o painel (%.0f -> %.0f px)" % (h0, h1), abs((h1 - h0) - 120) < 3)
    check("altura lembrada no localStorage", ev("localStorage.getItem('noxy-editor.output-h')") is not None)
head = ev("(() => { const r = document.getElementById('output-head').getBoundingClientRect(); return [r.left + 60, r.top + r.height / 2]; })()")
h2 = output_h()
mouse("mousePressed", head[0], head[1]); mouse("mouseMoved", head[0], head[1] + 80); settle(); mouse("mouseReleased", head[0], head[1] + 80); settle()
h3 = output_h()
check("arrastar pela barra SAIDA tambem redimensiona (%.0f -> %.0f px)" % (h2, h3), abs((h3 - h2) + 80) < 3)
check("aba Saida ativa apos F5", ev("document.querySelector('#panel-tabs .ptab.active').dataset.tab") == "output")
ev("document.querySelector('#panel-tabs .ptab[data-tab=\"search\"]').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
check("clicar na aba Busca troca a aba", ev("document.querySelector('#panel-tabs .ptab.active').dataset.tab") == "search" and not ev("document.getElementById('search-view').classList.contains('hidden')"))
key("f", mods=10)
check("ctrl+shift+f foca o campo de busca na pasta", ev("document.activeElement.id") == "search-input")
ws.call("Input.insertText", {"text": "let x"}); key("Enter"); settle(1200)
check("resultados agrupados por arquivo", ev("document.querySelectorAll('#search-results .sfile').length") >= 1 and "util.nx" in ev("document.getElementById('search-results').textContent"))
ev("document.querySelector('#search-results .shit').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
check("clicar num resultado abre o arquivo com a ocorrencia", ev("document.querySelector('.tab.active .name').textContent").startswith("util.nx") and ev("document.querySelectorAll('#text .sel').length") >= 1)
check("abrir um resultado devolve o foco ao editor", ev("document.activeElement.id") == "input")
ev("document.querySelectorAll('.tab')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
key("Escape")
# paleta: ctrl+shift+p, filtrar, escolher um tema
key("p", mods=10)
check("ctrl+shift+p abre a paleta com foco no campo", not ev("document.getElementById('list').classList.contains('hidden')") and ev("document.activeElement.id") == "list-input")
ws.call("Input.insertText", {"text": "nord"}); settle()
check("filtrar mostra so o tema", ev("document.querySelectorAll('#list-items .litem').length") == 1 and "Nord" in ev("document.querySelector('#list-items .litem').textContent"))
key("Enter")
check("escolher aplica o tema e fecha", ev("document.documentElement.classList.contains('theme-nord')") and ev("document.getElementById('list').classList.contains('hidden')") and ev("document.activeElement.id") == "input")
check("tema gravado no settings.json", open(os.path.join(cfg, "settings.json")).read() == '{"theme":"nord"}')
key("p", mods=10); key("Escape")
check("escape fecha a paleta", ev("document.getElementById('list').classList.contains('hidden')"))
# quick open: ctrl+p, filtrar, abrir
key("p", mods=2)
check("ctrl+p abre o quick open", not ev("document.getElementById('list').classList.contains('hidden')") and ev("document.getElementById('list-input').placeholder") == "Nome do arquivo")
ws.call("Input.insertText", {"text": "util"}); settle()
check("filtro acha src/util.nx", ev("document.querySelector('#list-items .litem .label') && document.querySelector('#list-items .litem .label').textContent") == "src/util.nx")
key("Enter")
tabs_now = ev("Array.from(document.querySelectorAll('.tab .name')).map(e => e.textContent).join(',')")
check("enter abre o arquivo numa aba (abas: %s; status: %s)" % (tabs_now, ev("document.getElementById('status-msg').textContent")), tabs_now == "exemplo.nx,util.nx")
ev("document.querySelectorAll('.tab')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
# busca no arquivo: ctrl+f, contador, enter, marcas, ctrl+h substituir todas, escape
key("f", mods=2)
check("ctrl+f abre a barra com foco no campo", not ev("document.getElementById('findbar').classList.contains('hidden')") and ev("document.activeElement.id") == "find-input")
ws.call("Input.insertText", {"text": "print"}); settle()
check("contador de ocorrencias", ev("document.getElementById('find-count').textContent") == "1 de 2" and ev("document.querySelectorAll('#text .c').length") >= 1 and ev("document.querySelectorAll('#text .f').length") >= 1)
key("Enter")
check("enter vai para a proxima", ev("document.getElementById('find-count').textContent") == "2 de 2")
key("h", mods=2)
check("ctrl+h mostra a linha de substituir", not ev("document.getElementById('find-replace-row').classList.contains('hidden')") and ev("document.activeElement.id") == "find-replace")
ws.call("Input.insertText", {"text": "puts"}); settle()
ev("document.getElementById('find-all').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
check("substituir todas troca no texto e zera o contador", ev("document.getElementById('find-count').textContent") == "sem resultados" and ev("document.querySelector('.line[data-n=\"6\"]').textContent").startswith("puts("))
key("Escape")
check("escape fecha a barra e devolve o foco", ev("document.getElementById('findbar').classList.contains('hidden')") and ev("document.activeElement.id") == "input" and ev("document.querySelectorAll('#text .f').length") == 0)
key("z", mods=2)
check("ctrl+z desfaz a substituicao inteira", ev("document.querySelector('.line[data-n=\"6\"]').textContent").startswith("print("))
key("j", mods=2)
check("ctrl+j esconde o painel", ev("document.getElementById('output').classList.contains('hidden')"))
key("j", mods=2)
check("ctrl+j de novo mostra o painel", not ev("document.getElementById('output').classList.contains('hidden')"))
check("reabrir o painel nao tira o foco do editor", ev("document.activeElement.id") == "input")
# digitar de novo para sujar, entao fechar pelo x: modal
key("End"); insert("!")
ev("document.querySelector('.tab .close').dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
check("fechar aba suja abre modal", not ev("document.getElementById('modal').classList.contains('hidden')"))
ev("document.querySelectorAll('#modal-buttons button')[2].click()"); settle()
check("cancelar fecha o modal", ev("document.getElementById('modal').classList.contains('hidden')"))
# linha longa: a vista rola para acompanhar o cursor
key("End"); insert("x" * 300)
check("linha longa: a vista rola horizontalmente", ev("document.getElementById('editor').scrollLeft") > 0 and cursor_in_view())
key("Home")
check("home volta a vista ao inicio", ev("document.getElementById('editor').scrollLeft") == 0 and cursor_in_view())
key("z", mods=2)
# screenshot
shot = ws.call("Page.captureScreenshot", {"format": "png"})["data"]
open(os.path.join("tests", "tmp", "web_screenshot.png"), "wb").write(base64.b64decode(shot))
# fallback: a pagina de redirecionamento (token fora da linha de comando)
# leva ao editor; a pagina anterior manda bye no pagehide e o init novo
# cancela o encerramento
helper = os.path.join("tests", "tmp", "web_redir.nx")   # fora da pasta de demo, que a arvore lista
open(helper, "w").write("use src.browser as browser\nuse sys\nprint(browser.write_redirect(sys.argv()[2]))\n")
page = subprocess.run(["noxy", helper, url], capture_output=True, text=True).stdout.strip()
check("write_redirect devolve um caminho", page.startswith("/"))
ws.call("Page.navigate", {"url": "file://" + page}); settle(2000)
check("pagina de redirecionamento leva ao editor", ev("location.href").startswith(url.split("?")[0]) and ev("document.querySelectorAll('#tree .node').length") == 3)
time.sleep(3.5)
check("editor continua vivo 3 s depois do reload", editor.poll() is None and ev("document.querySelectorAll('#tree .node').length") == 3)
# recuperacao: editar sem salvar, esperar a copia (poll 1,5 s depois da
# ultima edicao), matar o editor e abrir outro: a aba volta suja
ev("document.querySelectorAll('#tree .node.file')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}))"); settle()
key("Home", mods=2); insert("// nao salvo\n")
settle(2500)
cache = env["NOXY_EDITOR_CACHE_DIR"]
check("copia de recuperacao gravada sem outro evento", len(os.listdir(os.path.join(cache, "recovery"))) >= 1)
for fn in os.listdir(os.path.join(cache, "recovery")):
editor.kill(); editor.wait()
editor = subprocess.Popen(["noxy", "editor.nx", demo], env=env, stdout=subprocess.DEVNULL, stderr=open(log, "w"))
url = None
for _ in range(50):
    m = re.search(r"http://127\.0\.0\.1:\d+/\?t=[a-z0-9-]+", open(log).read())
    if m: url = m.group(0); break
    time.sleep(0.1)
ws.call("Page.navigate", {"url": url}); settle(1500)
check("depois de fechar sem salvar, a aba volta suja com o texto", "●" in ev("document.querySelector('.tab.active .name').textContent") and ev("document.querySelector('.line[data-n=\"0\"]').textContent") == "// nao salvo")
check("mensagem de arquivos recuperados", "recuperado" in ev("document.getElementById('status-msg').textContent"))
key("s", mods=2)
check("salvar apaga a copia", len(os.listdir(os.path.join(cache, "recovery"))) == 0)
chrome.terminate()
editor.terminate()
print(f"\n{'FALHOU' if fails else 'OK'}: {fails} falhas")
sys.exit(1 if fails else 0)
