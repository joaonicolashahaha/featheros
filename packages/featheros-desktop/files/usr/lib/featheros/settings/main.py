"""Configurações: the FeatherOS settings app, modelled on GNOME Settings.

Each panel is a module next to this one. It is imported and built the first
time it is opened, so the window shows up quickly on the Core 2 Duo.

    featheros-settings [panel]      e.g. featheros-settings bluetooth
"""
import importlib
import sys
import traceback
import unicodedata

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk  # noqa: E402

import ui  # noqa: E402

# Sidebar: (module, title, icon, search keywords); None separates groups.
PANELS = [
    ("network", "Rede", "org.gnome.Settings-network-symbolic",
     "wi-fi wifi wireless internet cabo ethernet ip dns senha conectar"),
    ("bluetooth", "Bluetooth", "org.gnome.Settings-bluetooth-symbolic",
     "fone headset caixa de som mouse teclado sem fio parear"),
    None,
    ("displays", "Telas", "org.gnome.Settings-display-symbolic",
     "monitor tela resolução taxa de atualização orientação girar luz noturna"),
    ("power", "Energia", "org.gnome.Settings-power-symbolic",
     "bateria desempenho economia suspender desligar tampa apagar tela"),
    ("appearance", "Aparência", "org.gnome.Settings-appearance-symbolic",
     "tema claro escuro modo plano de fundo papel de parede efeitos sombras"),
    None,
    ("apps", "Aplicativos", "org.gnome.Settings-applications-symbolic",
     "programas desinstalar remover padrão navegador abrir com"),
    ("accounts", "Contas online", "org.gnome.Settings-online-accounts-symbolic",
     "firefox google gmail microsoft outlook github sincronizar mozilla"),
    ("wellbeing", "Bem-estar", "org.gnome.Settings-wellbeing-symbolic",
     "tempo de uso tela limite pausa descanso olhos"),
    None,
    ("mouse", "Mouse e touchpad", "org.gnome.Settings-mouse-symbolic",
     "ponteiro velocidade rolagem natural clique toque botão canhoto"),
    ("keyboard", "Teclado", "org.gnome.Settings-keyboard-symbolic",
     "layout abnt2 idioma repetição atalhos teclas"),
    None,
    ("system", "Sistema", "org.gnome.Settings-system-symbolic",
     "região idioma data hora fuso horário usuários senha login automático "
     "acesso remoto ssh sobre nome do computador atualizações"),
]

ALIASES = {
    "rede": "network", "wifi": "network", "wi-fi": "network", "telas": "displays",
    "energia": "power", "aparencia": "appearance", "aplicativos": "apps",
    "contas": "accounts", "bem-estar": "wellbeing", "teclado": "keyboard",
    "sistema": "system", "sobre": "system",
}


def fold(text):
    """Lower case without accents, for searching."""
    text = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in text if not unicodedata.combining(c))


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Configurações")
        self.set_default_size(960, 640)
        self.set_icon_name("preferences-system")
        self.panels = {}
        self.current = None
        self.connect("delete-event", lambda *_: self.current and self.current.hidden())

        root = Gtk.Box()
        self.add(root)

        # Sidebar: search + panel list
        side = ui.style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "fs-sidebar")
        side.set_size_request(232, -1)
        self.search = Gtk.SearchEntry(placeholder_text="Buscar", margin=8)
        self.search.connect("search-changed", lambda *_: self._filter())
        side.pack_start(self.search, False, False, 0)
        self.sidebar = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.rows = {}
        group = 0
        for entry in PANELS:
            if entry is None:
                group += 1
                continue
            name, title, icon_name, keywords = entry
            box = Gtk.Box(spacing=12, margin_start=10, margin_end=10, margin_top=8,
                          margin_bottom=8)
            box.pack_start(ui.icon(icon_name), False, False, 0)
            box.pack_start(ui.label(title), False, False, 0)
            row = Gtk.ListBoxRow()
            row.add(box)
            row.name, row.group = name, group
            row.words = fold(f"{title} {keywords}")
            self.sidebar.add(row)
            self.rows[name] = row
        self.sidebar.set_filter_func(self._visible)
        self.sidebar.set_header_func(self._separator)
        self.sidebar.connect("row-selected", self._selected)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.add(self.sidebar)
        side.pack_start(scroll, True, True, 0)
        root.pack_start(side, False, False, 0)
        root.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)

        # Content: header (back button, title) + the panels
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        head = Gtk.Box(margin=6)
        head.set_size_request(-1, 40)
        self.back = ui.button(icon_name="go-previous-symbolic", tooltip="Voltar",
                              on_click=lambda: self.current.pop())
        self.back.set_no_show_all(True)
        head.pack_start(self.back, False, False, 0)
        self.title_label = ui.label("", "fs-header-title", xalign=0.5)
        head.set_center_widget(self.title_label)
        content.pack_start(head, False, False, 0)
        self.stack = Gtk.Stack()
        content.pack_start(self.stack, True, True, 0)
        root.pack_start(content, True, True, 0)
        self.show_all()

    # --- sidebar ---------------------------------------------------------------
    def _filter(self):
        self.sidebar.invalidate_filter()
        self.sidebar.invalidate_headers()
        query = fold(self.search.get_text().strip())
        if query:
            first = next((r for r in self.sidebar.get_children()
                          if self._visible(r)), None)
            if first:
                self.sidebar.select_row(first)

    def _visible(self, row):
        query = fold(self.search.get_text().strip())
        return all(word in row.words for word in query.split())

    def _separator(self, row, before):
        searching = bool(self.search.get_text().strip())
        if before is not None and before.group != row.group and not searching:
            row.set_header(Gtk.Separator())
        else:
            row.set_header(None)

    def _selected(self, _listbox, row):
        if row is None:
            return
        if self.current:
            self.current.hidden()
        panel = self.panels.get(row.name)
        if panel is None:
            panel = self._load(row.name)
            self.panels[row.name] = panel
            self.stack.add_named(panel.stack, row.name)
            panel.stack.show_all()
        self.stack.set_visible_child_name(row.name)
        self.current = panel
        self.update_header()
        panel.shown()

    def _load(self, name):
        title = next(e[1] for e in PANELS if e and e[0] == name)
        try:
            return importlib.import_module(name).Panel(self)
        except Exception:  # a broken panel must not take the app down
            traceback.print_exc()
            win = self

            class Broken(ui.Panel):
                def build(self):
                    self.title = title
                    return ui.status_page("dialog-error-symbolic",
                                          "Não foi possível abrir este painel",
                                          traceback.format_exc(limit=1).strip())
            return Broken(win)

    def update_header(self):
        panel = self.current
        self.title_label.set_text(panel.page_title if panel else "")
        self.back.set_visible(bool(panel) and len(panel.pages) > 1)

    def show_panel(self, name):
        name = ALIASES.get(name, name)
        row = self.rows.get(name) or self.rows["network"]
        self.sidebar.select_row(row)
        if self.panels.get(name) and len(self.panels[name].pages) > 1:
            while len(self.panels[name].pages) > 1:
                self.panels[name].pop()


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.featheros.Settings",
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        win = self.get_active_window()
        if win is None:
            ui.install_css()
            win = Window(self)
            win.show_panel(args[0] if args else "network")
        elif args:
            win.show_panel(args[0])
        win.present()
        return 0


def run(argv):
    return App().run([sys.argv[0], *argv])
