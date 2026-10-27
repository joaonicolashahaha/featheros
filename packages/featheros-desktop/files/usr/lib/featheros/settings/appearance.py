"""Aparência: light or dark style (featheros-theme), wallpaper and visual
effects (featheros-effects)."""
import os
import shutil

from gi.repository import GdkPixbuf, GLib, Gtk

import ui
import util

WALLPAPERS = "/usr/share/featheros/wallpapers"
MINE = os.path.expanduser("~/.local/share/backgrounds")
IMAGES = (".jpg", ".jpeg", ".png", ".webp")


def thumbnail(path, width, height):
    """The image scaled and centre-cropped to width x height (None if unreadable)."""
    try:
        src = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, width * 2, height * 2, True)
    except GLib.Error:
        return None
    scale = max(width / src.get_width(), height / src.get_height())
    w, h = max(width, round(src.get_width() * scale)), max(height, round(src.get_height() * scale))
    scaled = src.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
    return scaled.new_subpixbuf((w - width) // 2, (h - height) // 2, width, height)


def card(pixbuf, text, on_click):
    b = ui.style(Gtk.Button(relief=Gtk.ReliefStyle.NONE), "fs-card")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    img = Gtk.Image.new_from_pixbuf(pixbuf) if pixbuf else ui.icon("image-missing", 48)
    box.pack_start(img, False, False, 0)
    if text:
        box.pack_start(ui.label(text, xalign=0.5), False, False, 0)
    b.add(box)
    b.connect("clicked", lambda *_: on_click())
    return b


class Panel(ui.Panel):
    title = "Aparência"

    def build(self):
        s = util.settings()
        page = ui.Page()
        style = page.group("Estilo")
        box = Gtk.Box(spacing=24, halign=Gtk.Align.CENTER, margin=14)
        self.styles = {}
        for mode, text in (("light", "Claro"), ("dark", "Escuro")):
            self.styles[mode] = card(thumbnail(f"{WALLPAPERS}/{mode}.jpg", 200, 125), text,
                                     lambda m=mode: self._mode(m))
            box.pack_start(self.styles[mode], False, False, 0)
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        row.add(box)
        style.append(row)

        self.backgrounds = page.group("Plano de fundo")
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3,
                                min_children_per_line=3, homogeneous=True, margin=10,
                                row_spacing=6, column_spacing=6)
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        row.add(self.flow)
        self.backgrounds.append(row)

        effects = page.group("Efeitos visuais")
        effects.append(ui.SwitchRow("Sombras e cantos arredondados",
                                    "Usam um pouco mais de memória e de processador",
                                    s["EFFECTS"] == "on", self._effects))
        self.mode = s["MODE"]
        self._fill_backgrounds()
        self._mark()
        return page

    def _mark(self):
        wallpaper = util.setting("WALLPAPER")
        for mode, b in self.styles.items():
            (b.get_style_context().add_class if mode == self.mode
             else b.get_style_context().remove_class)("selected")
        for child in self.flow.get_children():
            b = child.get_child()
            if getattr(b, "path", None) is not None:
                ctx = b.get_style_context()
                (ctx.add_class if b.path == wallpaper else ctx.remove_class)("selected")

    def _mode(self, mode):
        self.mode = mode
        self._mark()
        util.run(["featheros-theme", mode], lambda *_: self._fill_backgrounds())

    def _effects(self, on):
        util.run(["featheros-effects", "on" if on else "off"])

    # --- wallpapers --------------------------------------------------------------------
    def _fill_backgrounds(self):
        for child in self.flow.get_children():
            child.destroy()
        items = [("", f"{WALLPAPERS}/{self.mode}.jpg")]
        if os.path.isdir(MINE):
            items += [(os.path.join(MINE, f),) * 2 for f in sorted(os.listdir(MINE))
                      if f.lower().endswith(IMAGES)]
        for value, path in items:
            b = card(thumbnail(path, 160, 100), None, lambda v=value: self._wallpaper(v))
            b.path = value
            b.set_tooltip_text("Padrão do FeatherOS (acompanha o estilo)" if not value
                               else os.path.basename(value))
            if value:
                menu = Gtk.Menu()
                item = Gtk.MenuItem(label="Remover")
                item.connect("activate", lambda *_, v=value: self._remove(v))
                menu.append(item)
                menu.show_all()
                b.connect("button-press-event", lambda _b, e, m=menu:
                          e.button == 3 and (m.popup_at_pointer(e) or True))
            self.flow.add(b)
        add = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
        add.add(ui.icon("list-add-symbolic", 24))
        add.set_tooltip_text("Adicionar imagem…")
        add.connect("clicked", lambda *_: self._add())
        self.flow.add(add)
        self.flow.show_all()
        self._mark()

    def _wallpaper(self, path):
        util.save(WALLPAPER=path)
        util.shell("featheros_wallpaper")
        self._mark()

    def _add(self):
        d = Gtk.FileChooserNative(title="Escolher imagem", transient_for=self.win,
                                  action=Gtk.FileChooserAction.OPEN, accept_label="Usar")
        f = Gtk.FileFilter()
        f.set_name("Imagens")
        for ext in IMAGES:
            f.add_pattern(f"*{ext}")
            f.add_pattern(f"*{ext.upper()}")
        d.add_filter(f)
        pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        if pictures:
            d.set_current_folder(pictures)
        if d.run() == Gtk.ResponseType.ACCEPT:
            src = d.get_filename()
            os.makedirs(MINE, exist_ok=True)
            dest = os.path.join(MINE, os.path.basename(src))
            if os.path.abspath(src) != dest:
                shutil.copyfile(src, dest)
            self._wallpaper(dest)
            self._fill_backgrounds()
        d.destroy()

    def _remove(self, path):
        try:
            os.remove(path)
        except OSError:
            pass
        if util.setting("WALLPAPER") == path:
            self._wallpaper("")
        self._fill_backgrounds()
