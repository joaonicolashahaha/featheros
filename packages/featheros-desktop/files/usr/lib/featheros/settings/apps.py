"""Aplicativos: installed apps (details from pacman, open, uninstall) and the
default apps for links and file types (~/.config/mimeapps.list, via Gio)."""
from gi.repository import Gio, GLib, Gtk

import ui
import util

DEFAULTS = [
    ("Navegador", ["x-scheme-handler/http", "x-scheme-handler/https", "text/html"]),
    ("E-mail", ["x-scheme-handler/mailto"]),
    ("Músicas", ["audio/mpeg", "audio/ogg", "audio/flac", "audio/x-wav", "audio/mp4"]),
    ("Vídeos", ["video/mp4", "video/x-matroska", "video/webm", "video/quicktime",
                "video/x-msvideo"]),
    ("Imagens", ["image/jpeg", "image/png", "image/gif", "image/webp"]),
    ("PDF", ["application/pdf"]),
    ("Texto", ["text/plain"]),
    ("Pastas", ["inode/directory"]),
]


def package_info(path):
    """Owning package of a file: {"name", "version", "size", "required_by"} or None."""
    owner = util.output("pacman", "-Qqo", path).strip()
    if not owner:
        return None
    info = {"name": owner}
    for line in util.output("pacman", "-Qi", owner).splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "Version":
            info["version"] = value
        elif key == "Installed Size":
            info["size"] = value.replace("MiB", "MB").replace("KiB", "KB").replace(".", ",")
        elif key == "Required By":
            info["required_by"] = value.split() if value != "None" else []
    return info


class Panel(ui.Panel):
    title = "Aplicativos"

    def build(self):
        page = ui.Page()
        self.search = Gtk.SearchEntry(placeholder_text="Buscar aplicativos", margin_top=18)
        self.search.connect("search-changed", lambda *_: self.list.list.invalidate_filter())
        page.append(self.search)
        page.group().append(ui.Row("Aplicativos padrão",
                                   "Quais apps abrem links, músicas, vídeos e arquivos",
                                   "org.gnome.Settings-default-apps-symbolic",
                                   on_activate=self.show_defaults, arrow=True))
        self.list = page.group()
        self.list.list.set_filter_func(self._match)
        apps = [a for a in Gio.AppInfo.get_all() if a.should_show()]
        apps.sort(key=lambda a: a.get_display_name().casefold())
        for app in apps:
            row = ui.Row(app.get_display_name(), gicon=app.get_icon(), icon_size=32,
                         on_activate=lambda a=app: self.show_app(a), arrow=True)
            row.words = f"{app.get_display_name()} {app.get_description() or ''}".casefold()
            self.list.append(row)
        return page

    def _match(self, row):
        query = self.search.get_text().strip().casefold()
        return not query or query in row.words

    # --- one app -------------------------------------------------------------------------
    def show_app(self, app):
        page = ui.Page()
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=18)
        img = Gtk.Image.new_from_gicon(app.get_icon() or Gio.ThemedIcon.new("application-x-executable"),
                                       Gtk.IconSize.DIALOG)
        img.set_pixel_size(96)
        head.pack_start(img, False, False, 0)
        head.pack_start(ui.label(f"<big><b>{ui.esc(app.get_display_name())}</b></big>",
                                 markup=True, xalign=0.5), False, False, 0)
        if app.get_description():
            head.pack_start(ui.label(app.get_description(), "dim-label", wrap=True,
                                     xalign=0.5, justify=Gtk.Justification.CENTER),
                            False, False, 0)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_top=6)
        buttons.pack_start(ui.button("Abrir", None, lambda: app.launch([], None),
                                     "suggested-action"), False, False, 0)
        head.pack_start(buttons, False, False, 0)
        page.append(head)

        details = page.group("Detalhes")
        path = app.get_filename() or ""
        info = package_info(path) if path.startswith("/usr/") else None
        if info:
            details.append(self._value("Pacote", info["name"]))
            details.append(self._value("Versão", info.get("version", "")))
            details.append(self._value("Tamanho instalado", info.get("size", "")))
            # FeatherOS's own packages, and the apps it is built around.
            essential = (info["name"].startswith("featheros") or
                         "featheros-desktop" in info.get("required_by", []))
            remove = ui.button("Desinstalar…", None, lambda: self._uninstall(app, info["name"]),
                               "destructive-action")
            remove.set_sensitive(not essential)
            if essential:
                remove.set_tooltip_text("Faz parte do FeatherOS")
            buttons.pack_start(remove, False, False, 0)
        else:
            details.append(self._value("Origem", "Instalado na sua pasta pessoal"
                                       if path.startswith(util.HOME) else "—"))

        types = []
        for title, mimes in DEFAULTS:
            default = Gio.AppInfo.get_default_for_type(mimes[0], False)
            if default and default.get_id() == app.get_id():
                types.append(title)
        if types:
            details.append(self._value("Abre por padrão", ", ".join(types)))
        self.push(page, app.get_display_name())

    @staticmethod
    def _value(title, value):
        return ui.Row(title, suffix=[ui.label(value, "dim-label", selectable=True, xalign=1,
                                              wrap=True, max_width_chars=34)])

    def _uninstall(self, app, package):
        def go(ok):
            if ok:
                util.terminal(f"Desinstalar {app.get_display_name()}",
                              f"sudo pacman -Rns {package}")
        ui.confirm(self.win, f"Desinstalar {app.get_display_name()}?",
                   f"O pacote “{package}” será removido, junto com o que só ele usava. "
                   "Um terminal vai pedir a sua senha.", "Desinstalar", go, destructive=True)

    # --- default apps ----------------------------------------------------------------------
    def show_defaults(self):
        page = ui.Page()
        group = page.group(None, "O aplicativo que abre cada tipo de link ou arquivo.")
        for title, mimes in DEFAULTS:
            apps = Gio.AppInfo.get_all_for_type(mimes[0])
            if not apps:
                continue
            current = Gio.AppInfo.get_default_for_type(mimes[0], False)
            options = [(a.get_id(), a.get_display_name()) for a in apps]
            group.append(ui.ComboRow(title, options, current.get_id() if current else None,
                                     lambda id_, m=mimes, a=apps: self._set_default(id_, m, a)))
        self.push(page, "Aplicativos padrão")

    @staticmethod
    def _set_default(app_id, mimes, apps):
        app = next(a for a in apps if a.get_id() == app_id)
        for mime in mimes:
            try:
                app.set_as_default_for_type(mime)
            except GLib.Error:
                pass

