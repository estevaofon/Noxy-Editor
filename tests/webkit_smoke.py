# tests/webkit_smoke.py — o layout e o arraste do painel de saida no motor
# da janela de verdade (WebKitGTK, o mesmo da extensao), com eventos de mouse
# entregues pelo GTK. Precisa de PyGObject com WebKit2 4.1 e roda sob X11 ou
# XWayland; abre uma janela por alguns segundos.
#     GDK_BACKEND=x11 python3 tests/webkit_smoke.py      (a partir da raiz)
import gi, os, re, sys, time, subprocess, json, shutil
gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0"); gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, Gdk, WebKit2, GLib

demo = os.path.join("tests", "tmp", "webkit"); os.makedirs(demo, exist_ok=True)
open(os.path.join(demo, "longo.nx"), "w").write("".join(f"let v{i}: int = {i}   // " + "x" * 200 + "\n" for i in range(120)) + "print(\"fim\")\n")
log = os.path.join("tests", "tmp", "webkit_editor.log")
editor = subprocess.Popen(["noxy", "editor.nx", demo], env=dict(os.environ, NOXY_EDITOR_NO_WINDOW="1", SHELL="/bin/sh", NOXY_EDITOR_CONFIG_DIR=os.path.join(os.getcwd(), "tests", "tmp", "webkit_config"), NOXY_EDITOR_CACHE_DIR=os.path.join(os.getcwd(), "tests", "tmp", "webkit_cache")), stdout=subprocess.DEVNULL, stderr=open(log, "w"))
url = None
for _ in range(50):
    m = re.search(r"http://127\.0\.0\.1:\d+/\?t=[a-z0-9-]+", open(log).read())
    if m: url = m.group(0); break
    time.sleep(0.1)

fails = 0
def check(name, cond):
    global fails
    print(("  ok   " if cond else "FAIL   ") + name)
    if not cond: fails += 1

W, H = 1200, 800
win = Gtk.Window(title="webkit_smoke"); win.set_default_size(W, H); win.set_resizable(False)
wv = WebKit2.WebView(); win.add(wv); win.show_all()
def js(expr, cb):
    def done(w, res):
        try: v = w.run_javascript_finish(res).get_js_value().to_string()
        except Exception as e: v = "ERR " + str(e)
        cb(v)
    wv.run_javascript(expr, None, done)
def later(ms, f): GLib.timeout_add(ms, lambda: (f(), False)[1])
def gwin(): return wv.get_window()

# eventos sinteticos entregues pelo GTK ao widget: o WebKit os converte em
# eventos de mouse e faz o hit-test no processo web, como com o mouse real
_keep = []
def _dev(): return Gdk.Display.get_default().get_default_seat().get_pointer()
def _fill(ev, kind, x, y):
    w = gwin(); ok, ox, oy = w.get_origin(); e = getattr(ev, kind)
    e.window = w; e.send_event = True; e.time = int(GLib.get_monotonic_time() / 1000)
    e.x = float(x); e.y = float(y); e.x_root = float(ox + x); e.y_root = float(oy + y)
    e.device = _dev(); ev.set_device(_dev()); ev.set_source_device(_dev()); _keep.append(ev)
def move(x, y, held):
    ev = Gdk.Event.new(Gdk.EventType.MOTION_NOTIFY); _fill(ev, "motion", x, y)
    ev.motion.state = Gdk.ModifierType.BUTTON1_MASK if held else Gdk.ModifierType(0); Gtk.main_do_event(ev)
def button(down, x, y):
    ev = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS if down else Gdk.EventType.BUTTON_RELEASE); _fill(ev, "button", x, y)
    ev.button.button = 1; ev.button.state = Gdk.ModifierType(0) if down else Gdk.ModifierType.BUTTON1_MASK; Gtk.main_do_event(ev)
def click(x, y, done):
    move(x, y, False); later(60, lambda: button(True, x, y)); later(120, lambda: button(False, x, y)); later(200, done)
def drag(x, y, dy, done, dx=0):
    move(x, y, False); later(60, lambda: button(True, x, y))
    for i, f in enumerate([0.2, 0.4, 0.6, 0.8, 1.0]):
        later(120 + i * 50, (lambda ff: (lambda: move(x + dx * ff, y + dy * ff, True)))(f))
    later(420, lambda: button(False, x + dx, y + dy)); later(800, done)

LAYOUT = "JSON.stringify({inner: innerHeight, editorH: document.getElementById('editor').getBoundingClientRect().height, rows: document.querySelectorAll('#text .line').length, outH: document.getElementById('output').getBoundingClientRect().height, outBottom: document.getElementById('output').getBoundingClientRect().bottom, statusBottom: document.getElementById('status').getBoundingClientRect().bottom, statusH: document.getElementById('status').getBoundingClientRect().height, hidden: document.getElementById('output').classList.contains('hidden'), sw: document.getElementById('editor').scrollWidth, cw: document.getElementById('editor').clientWidth})"
def center(sel): return f"(() => {{ const r = document.querySelector('{sel}').getBoundingClientRect(); return JSON.stringify([r.left + Math.min(60, r.width / 2), r.top + r.height / 2]); }})()"
st = {}
# a barra de status inteira colada no rodape, com ou sem o painel
def status_ok(l): return l["statusH"] == 24 and abs(l["statusBottom"] - l["inner"]) < 0.5
def fits(l): return status_ok(l) and l["outBottom"] <= l["inner"] + 0.5 and abs(l["editorH"] - (l["inner"] - 36 - l["outH"] - 24)) < 1.5

def s_open():
    js("document.querySelectorAll('#tree .node.file')[0].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0})); 'ok'", lambda _: later(600, s_before))
def s_before():
    def got(v):
        l = json.loads(v); st["before"] = l
        check("arquivo largo aberto, com rolagem horizontal", l["rows"] > 20 and l["sw"] > l["cw"])
        check("status inteira no rodape com o painel fechado (fundo %d, altura %d, janela %d)" % (l["statusBottom"], l["statusH"], l["inner"]), l["hidden"] and status_ok(l))
        js(SIDE, lambda v: (st.__setitem__("side", json.loads(v)), js(center("#sidebar-resize"), lambda c: drag(*json.loads(c), 0, s_after_side, dx=120))))
    js(LAYOUT, got)
# a barra lateral pelo divisor da borda direita, com o mouse entregue pelo GTK
SIDE = "JSON.stringify({w: document.getElementById('sidebar').getBoundingClientRect().width, main: document.getElementById('main').getBoundingClientRect().left})"
def s_after_side():
    def got(v):
        s = json.loads(v)
        check("arrastar o divisor da barra lateral alarga 120 px (%d -> %d) e o editor acompanha" % (st["side"]["w"], s["w"]), abs((s["w"] - st["side"]["w"]) - 120) < 2 and abs(s["main"] - s["w"]) < 1)
        js(center("#run-btn"), lambda c: click(*json.loads(c), lambda: later(3500, s_after_run)))
    js(SIDE, got)
def s_after_run():
    def got(v):
        l = json.loads(v); st["run"] = l
        check("F5 abre o painel", not l["hidden"] and l["outH"] > 100)
        check("painel e status cabem na janela e o editor encolheu (editor %d, painel %d, janela %d)" % (l["editorH"], l["outH"], l["inner"]), fits(l))
        check("linhas visiveis diminuiram (%d -> %d)" % (st["before"]["rows"], l["rows"]), l["rows"] < st["before"]["rows"])
        js("(() => { const r = document.getElementById('output-head').getBoundingClientRect(); return JSON.stringify([r.left + r.width * 0.6, r.top + r.height / 2]); })()", lambda c: drag(*json.loads(c), -150, s_after_head))
    js(LAYOUT, got)
def s_after_head():
    def got(v):
        l = json.loads(v); st["head"] = l
        check("arrastar pela parte vazia da barra do painel cresce 150 px (%d -> %d)" % (st["run"]["outH"], l["outH"]), abs((l["outH"] - st["run"]["outH"]) - 150) < 2)
        check("layout continua cabendo apos o arraste", fits(l) and l["rows"] < st["run"]["rows"])
        js(center("#output-resize"), lambda c: drag(*json.loads(c), 60, s_after_grip))
    js(LAYOUT, got)
def s_after_grip():
    def got(v):
        l = json.loads(v)
        check("arrastar pelo divisor para baixo encolhe 60 px (%d -> %d)" % (st["head"]["outH"], l["outH"]), abs((st["head"]["outH"] - l["outH"]) - 60) < 2)
        check("layout continua cabendo", fits(l))
        js(center('#panel-tabs .ptab[data-tab="terminal"]'), lambda c: click(*json.loads(c), lambda: later(2000, s_term)))
    js(LAYOUT, got)

TERM = "JSON.stringify({x: !!document.querySelector('#term-view .xterm'), bottom: (document.querySelector('#term-view .xterm') || document.body).getBoundingClientRect().bottom, inner: innerHeight, rows: document.querySelectorAll('#term-view .xterm-rows > div').length, text: (document.querySelector('#term-view .xterm-rows') || {textContent: ''}).textContent})"
def s_term():
    def got(v):
        t = json.loads(v); st["term"] = t
        check("aba Terminal: xterm dentro da janela (fundo %d, janela %d)" % (t["bottom"], t["inner"]), t["x"] and t["bottom"] <= t["inner"] + 0.5 and t["rows"] >= 5)
        js("fetch('/event?t=' + new URLSearchParams(location.search).get('t'), {method: 'POST', body: JSON.stringify({kind: 'poll', rows: 5, tree_version: 0})}).then(r => r.json()).then(f => fetch('/term/write', {method: 'POST', headers: {'X-Noxy-Token': new URLSearchParams(location.search).get('t')}, body: JSON.stringify({id: f.term.id, data: btoa('echo webkit_$((3*3))\\n')})})); 'ok'", lambda _: later(1500, s_term_out))
    js(TERM, got)
def s_term_out():
    def got(v):
        t = json.loads(v)
        check("o shell responde no xterm do WebKitGTK", "webkit_9" in t["text"])
        js(center("#output-resize"), lambda c: drag(*json.loads(c), -120, s_term_resized))
    js(TERM, got)
def s_term_resized():
    def got(v):
        t = json.loads(v)
        check("painel maior: o xterm ganha linhas (%d -> %d) e continua dentro da janela" % (st["term"]["rows"], t["rows"]), t["rows"] > st["term"]["rows"] and t["bottom"] <= t["inner"] + 0.5)
        finish()
    js(TERM, got)
def finish():
    editor.terminate(); Gtk.main_quit()
def on_load(w, ev):
    if ev == WebKit2.LoadEvent.FINISHED: later(1200, s_open)
wv.connect("load-changed", on_load); wv.load_uri(url)
GLib.timeout_add(45000, lambda: (print("FAIL   timeout"), finish(), False)[2])
Gtk.main()
print(f"\n{'FALHOU' if fails else 'OK'}: {fails} falhas")
sys.exit(1 if fails else 0)
