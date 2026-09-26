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
env = dict(os.environ, NOXY_EDITOR_NO_WINDOW="1")
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
key("j", mods=2)
check("ctrl+j esconde o painel", ev("document.getElementById('output').classList.contains('hidden')"))
key("j", mods=2)
check("ctrl+j de novo mostra o painel", not ev("document.getElementById('output').classList.contains('hidden')"))
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
chrome.terminate()
editor.terminate()
print(f"\n{'FALHOU' if fails else 'OK'}: {fails} falhas")
sys.exit(1 if fails else 0)
