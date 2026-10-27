"""Telas: resolution, refresh rate, orientation and arrangement (xrandr), and
Luz noturna (featheros-gamma, on a schedule run by sessiond).

Changes are tried first and kept only when confirmed (15 s, like GNOME);
kept settings go to ~/.config/featheros/displays, which featheros-session
applies at login."""
import os
import re

from gi.repository import GLib, Gtk

import ui
import util

DISPLAYS = os.path.join(util.CONFIG_DIR, "displays")
ROTATIONS = [("normal", "Paisagem"), ("right", "Retrato à direita"),
             ("left", "Retrato à esquerda"), ("inverted", "Paisagem invertida")]
POSITIONS = [("right-of", "À direita"), ("left-of", "À esquerda"), ("above", "Acima"),
             ("below", "Abaixo"), ("same-as", "Espelhar (mesma imagem)")]
RATIOS = [(16 / 9, "16:9"), (16 / 10, "16:10"), (4 / 3, "4:3"), (5 / 4, "5:4"),
          (3 / 2, "3:2"), (21 / 9, "21:9")]
NIGHT_APPLY = 'featheros-gamma "$(featheros_night_temp)"'


def query():
    """Monitors as xrandr reports them, connected ones first."""
    outs, cur = [], None
    for line in util.output("xrandr", "--query").splitlines():
        if line.startswith("Screen") or not line.strip():
            continue
        if not line[0].isspace():
            head = line.split("(")[0].split()
            cur = {"name": head[0], "connected": head[1] == "connected",
                   "primary": "primary" in head, "pos": None, "rotation": "normal",
                   "mode": None, "rate": None, "modes": {}, "preferred": None}
            m = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)(?:\s+(left|right|inverted))?",
                          line.split("(")[0])
            if m:
                cur["pos"] = (int(m.group(3)), int(m.group(4)))
                cur["rotation"] = m.group(5) or "normal"
            outs.append(cur)
        elif cur is not None:
            # "   1280x800      60.00*+  50.00  ": each rate is "%6.2f" then
            # '*' (current) or ' ', then '+' (preferred) or ' '.
            name, _, rest = line.strip().partition(" ")
            for rate, current, preferred in re.findall(r"(\d+\.\d+)([* ])([+ ])",
                                                       " " + rest + "  "):
                cur["modes"].setdefault(name, [])
                if rate not in cur["modes"][name]:
                    cur["modes"][name].append(rate)
                if current == "*":
                    cur["mode"], cur["rate"] = name, rate
                if preferred == "+":
                    cur["preferred"] = name
    outs.sort(key=lambda o: (not o["connected"], not o["primary"]))
    return [o for o in outs if o["connected"]]


def mode_label(mode):
    m = re.match(r"(\d+)x(\d+)", mode)
    if not m:
        return mode
    w, h = int(m.group(1)), int(m.group(2))
    ratio = next((t for r, t in RATIOS if abs(w / h - r) < 0.02), None)
    return f"{w} × {h}" + (f" ({ratio})" if ratio else "")


def pixels(mode):
    m = re.match(r"(\d+)x(\d+)", mode)
    return int(m.group(1)) * int(m.group(2)) if m else 0


def current_args(outs):
    """xrandr arguments that recreate the current layout exactly."""
    args = []
    for o in outs:
        args += ["--output", o["name"]]
        if o["mode"]:
            args += ["--mode", o["mode"], "--rate", o["rate"], "--rotate", o["rotation"],
                     "--pos", "%dx%d" % o["pos"]]
            if o["primary"]:
                args.append("--primary")
        else:
            args.append("--off")
    return args


class Panel(ui.Panel):
    title = "Telas"

    def build(self):
        page = ui.Page()
        self.arrange = page.group()
        self.monitor = self.arrange.append(ui.ComboRow("Monitor", [], on_change=self._select))
        self.enabled = self.arrange.append(ui.SwitchRow(
            "Usar este monitor", on_toggle=lambda on: self._change(enabled=on)))
        self.position = self.arrange.append(ui.ComboRow(
            "Posição", POSITIONS, on_change=lambda v: self._change(position=v),
            subtitle="Em relação ao monitor principal"))
        self.modes = page.group()
        self.rotation = self.modes.append(ui.ComboRow(
            "Orientação", ROTATIONS, on_change=lambda v: self._change(rotation=v)))
        self.resolution = self.modes.append(ui.ComboRow(
            "Resolução", [], on_change=self._resolution))
        self.rate = self.modes.append(ui.ComboRow(
            "Taxa de atualização", [], on_change=lambda v: self._change(rate=v)))

        self.bar = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=12)
        for b in (ui.button("Cancelar", on_click=self.load),
                  ui.button("Aplicar", None, self.apply, "suggested-action")):
            b.show()
            self.bar.pack_start(b, False, False, 0)
        self.bar.set_no_show_all(True)  # shown when something changes
        page.append(self.bar)

        night = page.group()
        self.night_row = night.append(ui.Row("Luz noturna", icon_name="night-light-symbolic",
                                             on_activate=self.show_night, arrow=True))
        self.load()
        return page

    # --- monitors ------------------------------------------------------------------
    def load(self):
        self.outs = query()
        self.want = {o["name"]: {"enabled": bool(o["mode"]), "mode": o["mode"],
                                 "rate": o["rate"], "rotation": o["rotation"],
                                 "position": "right-of"} for o in self.outs}
        self.selected = self.outs[0]["name"] if self.outs else None
        self.monitor.set_options([(o["name"], self._monitor_name(o)) for o in self.outs],
                                 self.selected)
        self.arrange.set_visible(len(self.outs) > 1)
        self.modes.set_visible(bool(self.outs))
        self.bar.hide()
        self._fill()
        self._night_subtitle()

    @staticmethod
    def _monitor_name(o):
        kind = "Tela do notebook" if o["name"].startswith(("LVDS", "eDP")) else o["name"]
        return kind + (" (principal)" if o["primary"] else "")

    def _select(self, name):
        self.selected = name
        self._fill()

    def _fill(self):
        if not self.selected:
            return
        o = next(o for o in self.outs if o["name"] == self.selected)
        w = self.want[self.selected]
        main = self.selected == self.outs[0]["name"]
        self.enabled.set_visible(not main)
        self.position.set_visible(not main)
        self.enabled.set_active(w["enabled"])
        self.position.set_active(w["position"])
        modes = sorted(o["modes"], key=pixels, reverse=True)
        mode = w["mode"] or o["preferred"] or (modes[0] if modes else None)
        self.resolution.set_options([(m, mode_label(m)) for m in modes], mode)
        self.rotation.set_active(w["rotation"])
        self._rates(mode, w["rate"])
        for row in (self.rotation, self.resolution, self.rate, self.position):
            row.set_sensitive(w["enabled"])

    def _rates(self, mode, rate):
        rates = self.outs and next(o for o in self.outs
                                   if o["name"] == self.selected)["modes"].get(mode, [])
        rate = rate if rate in rates else (rates[0] if rates else None)
        self.rate.set_options([(r, f"{float(r):.2f} Hz".replace(".", ",")) for r in rates],
                              rate)
        return rate

    def _resolution(self, mode):
        self._change(mode=mode, rate=self._rates(mode, self.want[self.selected]["rate"]))

    def _change(self, **changes):
        w = self.want[self.selected]
        w.update(changes)
        if "enabled" in changes:
            o = next(o for o in self.outs if o["name"] == self.selected)
            w["mode"] = w["mode"] or o["preferred"] or next(iter(o["modes"]), None)
            w["rate"] = w["rate"] or (o["modes"].get(w["mode"]) or [None])[0]
            self._fill()
        self.bar.show()

    def apply(self):
        before = current_args(self.outs)
        main = self.outs[0]["name"]
        args = []
        for o in self.outs:
            w = self.want[o["name"]]
            args += ["--output", o["name"]]
            if not w["enabled"] or not w["mode"]:
                args.append("--off")
                continue
            args += ["--mode", w["mode"], "--rotate", w["rotation"]]
            if w["rate"]:
                args += ["--rate", w["rate"]]
            if o["name"] == main:
                args += ["--primary", "--pos", "0x0"]
            else:
                args += ["--" + w["position"], main]
        self.bar.hide()

        def done(ok, out):
            self._redraw()
            if not ok:
                ui.message(self.win, "Não foi possível aplicar", out)
                util.run(["xrandr", *before], lambda *_: (self._redraw(), self.load()))
                return
            self._ask_keep(before)
        util.run(["xrandr", *args], done)

    def _redraw(self):
        # A new screen size needs the wallpaper again; gamma may be reset.
        util.shell(f"featheros_wallpaper; {NIGHT_APPLY}")

    def _ask_keep(self, before):
        d = Gtk.MessageDialog(transient_for=self.win, modal=True,
                              message_type=Gtk.MessageType.QUESTION,
                              text="Manter estas configurações de tela?")
        d.add_button("Reverter", Gtk.ResponseType.CANCEL)
        ui.style(d.add_button("Manter", Gtk.ResponseType.OK), "suggested-action")
        left = [15]

        def text():
            d.format_secondary_text(f"As configurações anteriores voltam em {left[0]} s.")

        def tick():
            left[0] -= 1
            if left[0] <= 0:
                d.response(Gtk.ResponseType.CANCEL)
                return False
            text()
            return True
        text()
        timer = [GLib.timeout_add_seconds(1, tick)]

        def response(dialog, r):
            if left[0] > 0:
                GLib.source_remove(timer[0])
            left[0] = 0
            dialog.destroy()
            if r == Gtk.ResponseType.OK:
                self.save()
                self.load()
            else:
                util.run(["xrandr", *before], lambda *_: (self._redraw(), self.load()))
        d.connect("response", response)
        d.show()

    def save(self):
        lines = []
        for o in query():
            if o["mode"]:
                extra = " --primary" if o["primary"] else ""
                lines.append(f"{o['name']} --mode {o['mode']} --rate {o['rate']} "
                             f"--rotate {o['rotation']} --pos {o['pos'][0]}x{o['pos'][1]}{extra}")
            else:
                lines.append(f"{o['name']} --off")
        os.makedirs(util.CONFIG_DIR, exist_ok=True)
        with open(DISPLAYS, "w") as f:
            f.write("\n".join(lines) + "\n")

    # --- Luz noturna -----------------------------------------------------------------
    def _night_subtitle(self):
        s = util.settings()
        if s["NIGHT_LIGHT"] != "on":
            text = "Desligada"
        elif s["NIGHT_SCHEDULE"] == "always":
            text = "Ligada"
        else:
            text = f"Das {s['NIGHT_FROM']} às {s['NIGHT_TO']}"
        self.night_row.set_subtitle(text)

    def _night(self, **changes):
        util.save(**changes)
        util.shell(NIGHT_APPLY)
        self._night_subtitle()

    def show_night(self):
        s = util.settings()
        page = ui.Page()
        group = page.group(None, "Deixa as cores da tela mais quentes, o que cansa menos "
                                 "a vista à noite.")
        group.append(ui.SwitchRow("Luz noturna", active=s["NIGHT_LIGHT"] == "on",
                                  on_toggle=lambda on: self._night(
                                      NIGHT_LIGHT="on" if on else "off")))
        when = page.group("Horário")
        ui.radio_rows(when, [("times", "Programada", "Liga e desliga nos horários abaixo",
                              None),
                             ("always", "Sempre ligada", None, None)],
                      s["NIGHT_SCHEDULE"], lambda v: self._night(NIGHT_SCHEDULE=v))
        times = [(f"{h:02d}:{m:02d}",) * 2 for h in range(24) for m in (0, 30)]
        when.append(ui.ComboRow("Das", times, s["NIGHT_FROM"],
                                lambda v: self._night(NIGHT_FROM=v)))
        when.append(ui.ComboRow("Até", times, s["NIGHT_TO"],
                                lambda v: self._night(NIGHT_TO=v)))
        color = page.group("Temperatura de cor")
        color.append(ui.ScaleRow(
            "", 2500, 5500, 8000 - int(s["NIGHT_TEMP"]), self._temperature, step=100,
            marks=[(2500, "Menos quente"), (5500, "Mais quente")], width=420))
        self.push(page, "Luz noturna")

    def _temperature(self, value):
        # The slider runs from cooler (left) to warmer (right).
        temp = 8000 - int(round(value / 100) * 100)
        util.save(NIGHT_TEMP=temp)
        # Show the new tint for a moment, then whatever the schedule says.
        util.run(["featheros-gamma", str(temp)])
        GLib.timeout_add_seconds(3, lambda: util.shell(NIGHT_APPLY) and False)
