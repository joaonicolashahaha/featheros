"""Teclado: layouts (applied at once with setxkbmap, kept in the Xorg config
through settings-system), key repeat (xset; the settings file, applied at
login) and the keyboard shortcuts (Openbox's rc.xml)."""
import gettext
import os
import re
import xml.etree.ElementTree as ET

from gi.repository import Gtk

import ui
import util

RULES = "/usr/share/X11/xkb/rules/base.lst"
SWITCH = [("grp:alt_shift_toggle", "Alt+Shift"), ("grp:ctrl_shift_toggle", "Ctrl+Shift"),
          ("grp:caps_toggle", "Caps Lock")]
COMMON = ["br", "br:nodeadkeys", "us", "us:intl", "pt", "es", "latam", "fr", "de", "it",
          "gb"]
KEYS = {"W": "Super", "A": "Alt", "C": "Ctrl", "S": "Shift", "space": "Espaço",
        "Return": "Enter", "Escape": "Esc", "Up": "↑", "Down": "↓", "Left": "←",
        "Right": "→", "XF86AudioRaiseVolume": "Aumentar volume",
        "XF86AudioLowerVolume": "Diminuir volume", "XF86AudioMute": "Mudo",
        "XF86MonBrightnessUp": "Aumentar brilho", "XF86MonBrightnessDown": "Diminuir brilho"}
ACTIONS = {
    "featheros-launcher": "Buscar aplicativos", "featheros-terminal": "Abrir o Terminal",
    "pcmanfm": "Abrir Arquivos", "featheros-effects toggle": "Ligar ou desligar os efeitos visuais",
    "featheros-volume up": "Aumentar o volume", "featheros-volume down": "Diminuir o volume",
    "featheros-volume mute": "Silenciar", "brightnessctl -q set +10%": "Aumentar o brilho",
    "brightnessctl -q set 10%-": "Diminuir o brilho", "Close": "Fechar a janela",
    "ToggleMaximize": "Maximizar ou restaurar a janela", "Iconify": "Minimizar a janela",
    "NextWindow": "Alternar entre janelas", "PreviousWindow": "Alternar entre janelas (voltar)",
    "ToggleShowDesktop": "Mostrar a área de trabalho", "ShowMenu": "Menu da janela",
    "Lower": "Mandar a janela para trás", "DirectionalCycleWindows": "Ir para a janela ao lado",
}


def catalogue():
    """{"layout" or "layout:variant": description}, in Portuguese when possible."""
    tr = None
    for domain in ("xkeyboard-config-2", "xkeyboard-config"):
        try:
            tr = gettext.translation(domain, languages=["pt_BR"]).gettext
            break
        except OSError:
            pass
    tr = tr or (lambda text: text)
    items, section = {}, None
    try:
        with open(RULES) as f:
            for line in f:
                if line.startswith("! "):
                    section = line[2:].strip()
                elif line.strip() and section in ("layout", "variant"):
                    name, desc = line.strip().split(None, 1)
                    if section == "variant":
                        layout, desc = desc.split(":", 1)
                        name = f"{layout}:{name}"
                    items[name] = tr(desc.strip())
    except OSError:
        pass
    return items


def current_layouts():
    """[("br", ""), ("us", "intl")] and the switching option."""
    saved = util.input_saved()
    if saved.get("KB_LAYOUT"):
        layouts, variants = saved["KB_LAYOUT"], saved.get("KB_VARIANT", "")
        options = saved.get("KB_OPTIONS", "")
    else:
        q = dict(re.findall(r"^(\w+):\s*(.*)$", util.output("setxkbmap", "-query"), re.M))
        layouts, variants = q.get("layout", "br"), q.get("variant", "")
        options = q.get("options", "")
    layouts = layouts.split(",")
    variants = (variants.split(",") + [""] * len(layouts))[:len(layouts)]
    switch = next((o for o in options.split(",") if o.startswith("grp:")), SWITCH[0][0])
    return list(zip(layouts, variants)), switch


class Panel(ui.Panel):
    title = "Teclado"

    def build(self):
        self.names = catalogue()
        self.layouts, self.switch = current_layouts()
        page = ui.Page()
        self.layout_group = page.group("Layouts do teclado",
                                       "O primeiro é o padrão. Com mais de um, alterne "
                                       "entre eles com o atalho abaixo.")
        self.switch_row = ui.ComboRow("Alternar entre layouts", SWITCH, self.switch,
                                      self._switch)
        self.switch_group = page.group()
        self.switch_group.append(self.switch_row)
        self._fill_layouts()

        repeat = page.group("Repetição de teclas")
        s = util.settings()
        q = util.output("xset", "q")
        m = re.search(r"auto repeat delay:\s*(\d+)\s+repeat rate:\s*(\d+)", q)
        delay = int(s["KB_DELAY"] or (m.group(1) if m else 600))
        rate = int(s["KB_RATE"] or (m.group(2) if m else 25))
        self.delay = ui.ScaleRow("Atraso", 150, 1000, delay, lambda v: self._repeat(),
                                 step=10, marks=[(150, "Curto"), (1000, "Longo")])
        self.rate = ui.ScaleRow("Velocidade", 5, 60, rate, lambda v: self._repeat(),
                                step=1, marks=[(5, "Lenta"), (60, "Rápida")])
        repeat.append(ui.SwitchRow("Repetir teclas", "Uma tecla mantida pressionada se repete",
                                   s["KB_REPEAT"] != "off", self._repeat_switch))
        repeat.append(self.delay)
        repeat.append(self.rate)
        self._repeat_switch(s["KB_REPEAT"] != "off", save=False)

        page.group().append(ui.Row("Atalhos de teclado", "Teclas para abrir apps e "
                                   "controlar as janelas", on_activate=self.show_shortcuts,
                                   arrow=True))
        return page

    # --- layouts ---------------------------------------------------------------------
    def _name(self, layout, variant):
        return (self.names.get(f"{layout}:{variant}" if variant else layout)
                or f"{layout} {variant}".strip())

    def _fill_layouts(self):
        self.layout_group.clear()
        for i, (layout, variant) in enumerate(self.layouts):
            suffix = []
            if i > 0:
                suffix.append(ui.button(icon_name="go-up-symbolic", tooltip="Tornar padrão",
                                        on_click=lambda i=i: self._first(i)))
            if len(self.layouts) > 1:
                suffix.append(ui.button(icon_name="user-trash-symbolic", tooltip="Remover",
                                        on_click=lambda i=i: self._remove(i)))
            self.layout_group.append(ui.Row(self._name(layout, variant),
                                            "Padrão" if i == 0 and len(self.layouts) > 1
                                            else None, "input-keyboard-symbolic", suffix))
        if len(self.layouts) < 4:
            self.layout_group.append(ui.Row("Adicionar layout…", icon_name="list-add-symbolic",
                                            on_activate=self.show_add))
        self.switch_group.set_visible(len(self.layouts) > 1)

    def _apply(self):
        layouts = ",".join(l for l, _v in self.layouts)
        variants = ",".join(v for _l, v in self.layouts)
        options = self.switch if len(self.layouts) > 1 else ""
        util.run(["setxkbmap", "-layout", layouts, "-variant", variants,
                  "-option", "", *(["-option", options] if options else [])])
        util.system("input", f"KB_LAYOUT={layouts}", f"KB_VARIANT={variants}",
                    f"KB_OPTIONS={options}", done=self._saved)
        self._fill_layouts()

    def _saved(self, ok, out):
        if not ok:
            ui.message(self.win, "A mudança vale só até sair da sessão",
                       f"Não foi possível salvá-la: {out}")

    def _first(self, i):
        self.layouts.insert(0, self.layouts.pop(i))
        self._apply()

    def _remove(self, i):
        del self.layouts[i]
        self._apply()

    def _switch(self, option):
        self.switch = option
        self._apply()

    def show_add(self):
        page = ui.Page()
        search = Gtk.SearchEntry(placeholder_text="Buscar idioma ou país", margin_top=18)
        page.append(search)
        group = page.group()
        have = {f"{l}:{v}" if v else l for l, v in self.layouts}
        names = sorted(self.names.items(), key=lambda kv: (kv[0] not in COMMON, kv[1]))
        rows = []

        def add(name):
            layout, _, variant = name.partition(":")
            self.layouts.append((layout, variant))
            self.pop()
            self._apply()

        def fill():
            for row in rows:
                row.destroy()
            rows.clear()
            query = search.get_text().strip().casefold()
            for name, desc in names:
                if name in have or (query and query not in desc.casefold()):
                    continue
                if not query and name not in COMMON:
                    continue  # the common ones until a search
                rows.append(group.append(ui.Row(desc, on_activate=lambda n=name: add(n))))
                if len(rows) >= 80:
                    break
        search.connect("search-changed", lambda *_: fill())
        fill()
        self.push(page, "Adicionar layout")
        search.grab_focus()

    # --- key repeat ------------------------------------------------------------------
    def _repeat_switch(self, on, save=True):
        self.delay.set_sensitive(on)
        self.rate.set_sensitive(on)
        if save:
            self._repeat(on)

    def _repeat(self, on=None):
        if on is None:
            on = self.delay.get_sensitive()
        util.save(KB_REPEAT="on" if on else "off",
                  KB_DELAY=int(self.delay.scale.get_value()),
                  KB_RATE=int(self.rate.scale.get_value()))
        util.shell("featheros_key_repeat")

    # --- shortcuts ---------------------------------------------------------------------
    def show_shortcuts(self):
        page = ui.Page()
        group = page.group(None, "Para mudar um atalho, edite ~/.config/openbox/rc.xml e "
                                 "saia da sessão.")
        rc = os.path.expanduser("~/.config/openbox/rc.xml")
        try:
            root = ET.parse(rc if os.path.exists(rc) else "/etc/skel/.config/openbox/rc.xml")
        except (OSError, ET.ParseError):
            root = None
        ns = "{http://openbox.org/3.4/rc}"
        for kb in root.iter(f"{ns}keybind") if root is not None else []:
            action = kb.find(f"{ns}action")
            if action is None:
                continue
            name = action.get("name", "")
            command = (action.findtext(f"{ns}command") or action.findtext(f"{ns}execute")
                       or "").strip()
            what = ACTIONS.get(command) or ACTIONS.get(name) or command or name
            keys = " + ".join(KEYS.get(k, k.upper() if len(k) == 1 else k)
                              for k in kb.get("key", "").split("-"))
            group.append(ui.Row(what, suffix=[ui.label(keys, "dim-label")]))
        if not group.rows():
            group.append(ui.Row("Nenhum atalho encontrado."))
        self.push(page, "Atalhos de teclado")
