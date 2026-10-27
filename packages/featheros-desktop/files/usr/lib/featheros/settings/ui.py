"""Widgets for the panels, GNOME Settings-style: a page is a centred column
of groups; a group is a title over a boxed list of rows."""
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

COLUMN = 580  # width of a page's column

CSS = b"""
/* WhiteSur makes placeholder text orange (its warning colour). */
@define-color placeholder_text_color alpha(@theme_fg_color, 0.45);
.fs-sidebar { background-color: mix(@theme_bg_color, @theme_fg_color, 0.04); }
.fs-sidebar list { background-color: transparent; }
.fs-sidebar list row { border-radius: 8px; margin: 1px 8px; }
.fs-sidebar list row:hover { background-color: alpha(@theme_fg_color, 0.05); }
.fs-sidebar list row:selected,
.fs-sidebar list row:selected:hover { background-color: alpha(@theme_fg_color, 0.11); }
.fs-sidebar list row:selected label,
.fs-sidebar list row:selected image { color: @theme_fg_color; }
.fs-sidebar list separator { margin: 5px 14px; }

list.fs-boxed { background-color: @theme_base_color; border-radius: 10px;
                border: 1px solid alpha(@theme_fg_color, 0.13); }
list.fs-boxed > row { border-bottom: 1px solid alpha(@theme_fg_color, 0.08); }
list.fs-boxed > row:first-child { border-top-left-radius: 10px; border-top-right-radius: 10px; }
list.fs-boxed > row:last-child { border-bottom-width: 0; border-bottom-left-radius: 10px;
                                 border-bottom-right-radius: 10px; }
list.fs-boxed > row:hover { background-color: transparent; }
list.fs-boxed > row.activatable:hover { background-color: alpha(@theme_fg_color, 0.04); }
list.fs-boxed > row.activatable:active { background-color: alpha(@theme_fg_color, 0.08); }

.fs-group-title { font-weight: bold; }
.fs-subtitle { font-size: smaller; }
.fs-header-title { font-weight: bold; }
.fs-big { font-size: 19pt; font-weight: 800; }
.fs-caption { font-size: smaller; font-weight: bold; }
.fs-card { padding: 2px; border-radius: 12px; border: 3px solid transparent;
           background: none; box-shadow: none; }
.fs-card.selected { border-color: @theme_selected_bg_color; }
.fs-status-icon { color: alpha(@theme_fg_color, 0.45); }
"""


def install_css():
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def esc(text):
    return GLib.markup_escape_text(text or "")


def style(widget, *classes):
    ctx = widget.get_style_context()
    for c in classes:
        ctx.add_class(c)
    return widget


def label(text="", *classes, markup=False, wrap=False, xalign=0, **kw):
    lab = Gtk.Label(xalign=xalign, **kw)
    (lab.set_markup if markup else lab.set_text)(text)
    if wrap:
        lab.set_line_wrap(True)
        lab.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if "max_width_chars" not in kw:
            lab.set_max_width_chars(64)  # else it widens the page column
    return style(lab, *classes)


def icon(name, size=16):
    img = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.BUTTON)
    img.set_pixel_size(size)
    return img


def button(text=None, icon_name=None, on_click=None, *classes, tooltip=None):
    b = Gtk.Button(label=text) if text else Gtk.Button()
    if icon_name:
        b.set_image(icon(icon_name))
        if text:
            b.set_always_show_image(True)
    if not text:
        b.set_relief(Gtk.ReliefStyle.NONE)
    if tooltip:
        b.set_tooltip_text(tooltip)
    if on_click:
        b.connect("clicked", lambda *_: on_click())
    b.set_valign(Gtk.Align.CENTER)
    return style(b, *classes)


# --- Pages, groups, rows -------------------------------------------------------
class Hideable:
    """set_visible() that holds when the page is shown later with show_all()
    (panels decide what to hide while they build the page)."""

    def set_visible(self, visible):
        self.set_no_show_all(not visible)
        if visible:
            self.show_all()
        else:
            self.hide()


class Page(Gtk.ScrolledWindow):
    """A scrolled page with a centred column."""

    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                              halign=Gtk.Align.CENTER, margin_start=24,
                              margin_end=24, margin_top=6, margin_bottom=30)
        self.column.set_size_request(COLUMN, -1)
        self.add(self.column)

    def append(self, widget):
        self.column.pack_start(widget, False, False, 0)
        return widget

    def group(self, title=None, description=None, suffix=None):
        return self.append(Group(title, description, suffix))


class Group(Hideable, Gtk.Box):
    """A title (optional, with widgets at its end) over a boxed list."""

    def __init__(self, title=None, description=None, suffix=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=18)
        if title or suffix:
            head = Gtk.Box(spacing=6)
            self.title = label(title or "", "fs-group-title", hexpand=True)
            head.pack_start(self.title, True, True, 0)
            for w in suffix if isinstance(suffix, (list, tuple)) else [suffix]:
                if w is not None:
                    head.pack_end(w, False, False, 0)
            self.pack_start(head, False, False, 0)
        if description:
            self.description = label(description, "dim-label", "fs-subtitle", wrap=True)
            self.pack_start(self.description, False, False, 0)
        self.list = style(Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE), "fs-boxed")
        self.list.connect("row-activated", lambda _l, row: row.activate_row())
        self.pack_start(self.list, False, False, 0)

    def append(self, row):
        self.list.add(row)
        row.show_all()
        return row

    def clear(self):
        for row in self.list.get_children():
            row.destroy()

    def rows(self):
        return self.list.get_children()


class Row(Hideable, Gtk.ListBoxRow):
    """Optional icon or prefix widgets, title and subtitle, suffix widgets,
    and an arrow for rows that open a subpage."""

    def __init__(self, title, subtitle=None, icon_name=None, suffix=(), prefix=(),
                 on_activate=None, arrow=False, gicon=None, icon_size=16):
        super().__init__(activatable=on_activate is not None, selectable=False)
        self.on_activate = on_activate
        box = Gtk.Box(spacing=12, margin_start=14, margin_end=14)
        box.set_size_request(-1, 52)
        for w in prefix:
            w.set_valign(Gtk.Align.CENTER)
            box.pack_start(w, False, False, 0)
        if gicon is not None:
            img = Gtk.Image.new_from_gicon(gicon, Gtk.IconSize.DND)
            img.set_pixel_size(icon_size)
            box.pack_start(img, False, False, 0)
        elif icon_name:
            box.pack_start(icon(icon_name, icon_size), False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1,
                       valign=Gtk.Align.CENTER, margin_top=7, margin_bottom=7)
        self.title_label = label(title or "", ellipsize=Pango.EllipsizeMode.END)
        self.subtitle_label = label(subtitle or "", "dim-label", "fs-subtitle", wrap=True)
        self.subtitle_label.set_no_show_all(True)
        self.subtitle_label.set_visible(bool(subtitle))
        text.pack_start(self.title_label, False, False, 0)
        text.pack_start(self.subtitle_label, False, False, 0)
        box.pack_start(text, bool(title or subtitle), True, 0)
        for w in suffix:
            w.set_valign(Gtk.Align.CENTER)
            box.pack_start(w, False, False, 0)
        if arrow:
            box.pack_start(style(icon("go-next-symbolic"), "dim-label"), False, False, 0)
        self.add(box)

    def set_title(self, text):
        self.title_label.set_text(text or "")

    def set_subtitle(self, text):
        self.subtitle_label.set_text(text or "")
        self.subtitle_label.set_visible(bool(text))

    def activate_row(self):
        if self.on_activate:
            self.on_activate()


class SwitchRow(Row):
    def __init__(self, title, subtitle=None, active=False, on_toggle=None, icon_name=None):
        self.switch = Gtk.Switch(active=active)
        super().__init__(title, subtitle, icon_name, suffix=[self.switch],
                         on_activate=lambda: self.switch.set_active(not self.switch.get_active()))
        self._quiet = False
        self._on_toggle = on_toggle
        self.switch.connect("notify::active", self._toggled)

    def _toggled(self, *_):
        if not self._quiet and self._on_toggle:
            self._on_toggle(self.switch.get_active())

    @property
    def active(self):
        return self.switch.get_active()

    def set_active(self, value):
        """Change the switch without calling on_toggle."""
        self._quiet = True
        self.switch.set_active(bool(value))
        self._quiet = False


class ValueRow(Row):
    """A title and a value (selectable text) at the end."""

    def __init__(self, title, value="", subtitle=None, icon_name=None):
        self.value = label(value, "dim-label", selectable=True, xalign=1, wrap=True,
                           max_width_chars=36)
        super().__init__(title, subtitle, icon_name, suffix=[self.value])


class ComboRow(Row):
    """A row with a drop-down; options are (id, label) pairs, ids are strings."""

    def __init__(self, title, options, active=None, on_change=None, subtitle=None,
                 icon_name=None):
        self.combo = Gtk.ComboBoxText()
        super().__init__(title, subtitle, icon_name, suffix=[self.combo])
        self._quiet = False
        self._on_change = on_change
        self.set_options(options, active)
        self.combo.connect("changed", self._changed)

    def set_options(self, options, active=None):
        self._quiet = True
        self.combo.remove_all()
        for id_, text in options:
            self.combo.append(str(id_), text)
        if active is not None:
            self.combo.set_active_id(str(active))
        self._quiet = False

    def _changed(self, combo):
        if not self._quiet and self._on_change and combo.get_active_id() is not None:
            self._on_change(combo.get_active_id())

    @property
    def value(self):
        return self.combo.get_active_id()

    def set_active(self, id_):
        self._quiet = True
        self.combo.set_active_id(str(id_))
        self._quiet = False


class ScaleRow(Row):
    """A slider; on_change(value) runs once the slider stops moving."""

    def __init__(self, title, lo, hi, value, on_change, step=0.1, marks=(),
                 subtitle=None, width=250):
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
        self.scale.set_draw_value(False)
        self.scale.set_size_request(width, -1)
        for at, text in marks:
            self.scale.add_mark(at, Gtk.PositionType.BOTTOM, text)
        self.scale.set_value(value)
        self.scale.set_hexpand(not title)  # no title: the whole row
        super().__init__(title, subtitle, suffix=[self.scale])
        self._timer = None
        self._quiet = False
        self._on_change = on_change
        self.scale.connect("value-changed", self._changed)

    def _changed(self, *_):
        if self._quiet:
            return
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(250, self._fire)

    def _fire(self):
        self._timer = None
        self._on_change(self.scale.get_value())
        return False

    def set_value(self, value):
        self._quiet = True
        self.scale.set_value(value)
        self._quiet = False


def radio_rows(group, options, active, on_change):
    """Add one row per option to group, each with a radio button.
    options: (id, title, subtitle, icon_name). Returns {id: radio}."""
    radios, first, quiet = {}, None, [True]
    for id_, title, subtitle, icon_name in options:
        radio = Gtk.RadioButton.new_from_widget(first)
        first = first or radio
        radios[id_] = radio
        radio.connect("toggled", lambda r, i=id_: r.get_active() and not quiet[0]
                      and on_change(i))
        group.append(Row(title, subtitle, icon_name, prefix=[radio],
                         on_activate=lambda r=radio: r.set_active(True)))
    if active in radios:
        radios[active].set_active(True)
    quiet[0] = False
    return radios


def toggle_group(options, active, on_change):
    """Linked toggle buttons ("Esquerdo | Direito"); options: (id, label)."""
    box = style(Gtk.Box(valign=Gtk.Align.CENTER), "linked")
    first, quiet = None, [True]
    for id_, text in options:
        b = Gtk.RadioButton.new_with_label_from_widget(first, text)
        b.set_mode(False)
        first = first or b
        b.set_active(id_ == active)
        b.connect("toggled", lambda r, i=id_: r.get_active() and not quiet[0] and on_change(i))
        box.pack_start(b, False, False, 0)
    quiet[0] = False
    return box


def status_page(icon_name, title, text=""):
    """Centred big icon + title + text, for empty or unavailable panels."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                  valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER, margin=40)
    box.pack_start(style(icon(icon_name, 96), "fs-status-icon"), False, False, 6)
    box.pack_start(label(f"<big><b>{esc(title)}</b></big>", markup=True, xalign=0.5),
                   False, False, 0)
    if text:
        t = label(text, "dim-label", wrap=True, xalign=0.5, justify=Gtk.Justification.CENTER)
        t.set_max_width_chars(52)
        box.pack_start(t, False, False, 0)
    return box


# --- Dialogs (non-blocking: they answer through a callback) --------------------
def message(parent, title, text=""):
    d = Gtk.MessageDialog(transient_for=parent, modal=True,
                          message_type=Gtk.MessageType.INFO,
                          buttons=Gtk.ButtonsType.OK, text=title)
    if text:
        d.format_secondary_text(text)
    d.connect("response", lambda d, _r: d.destroy())
    d.show()
    return d


def confirm(parent, title, text, ok, done, destructive=False):
    d = Gtk.MessageDialog(transient_for=parent, modal=True,
                          message_type=Gtk.MessageType.QUESTION, text=title)
    if text:
        d.format_secondary_text(text)
    d.add_button("Cancelar", Gtk.ResponseType.CANCEL)
    b = d.add_button(ok, Gtk.ResponseType.OK)
    style(b, "destructive-action" if destructive else "suggested-action")

    def response(d, r):
        d.destroy()
        done(r == Gtk.ResponseType.OK)
    d.connect("response", response)
    d.show()
    return d


def prompt(parent, title, text, done, ok="OK", password=False, initial=""):
    """Ask for a line of text; done(text) or done(None) when cancelled."""
    d = Gtk.MessageDialog(transient_for=parent, modal=True,
                          message_type=Gtk.MessageType.QUESTION, text=title)
    if text:
        d.format_secondary_text(text)
    entry = Gtk.Entry(text=initial, visibility=not password, activates_default=True)
    if password:
        entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
    d.get_message_area().pack_start(entry, False, False, 0)
    d.add_button("Cancelar", Gtk.ResponseType.CANCEL)
    style(d.add_button(ok, Gtk.ResponseType.OK), "suggested-action")
    d.set_default_response(Gtk.ResponseType.OK)

    def response(d, r):
        value = entry.get_text() if r == Gtk.ResponseType.OK else None
        d.destroy()
        done(value)
    d.connect("response", response)
    d.show_all()
    return d


# --- Panels --------------------------------------------------------------------
class Panel:
    """A sidebar entry. build() returns the main page; push() opens a subpage
    (the window shows a back button), pop() goes back."""
    title = ""

    def __init__(self, win):
        self.win = win
        self.stack = Gtk.Stack()
        self.pages = []
        self._show_page(self.build(), self.title)

    def build(self):
        raise NotImplementedError

    def _show_page(self, widget, title):
        self.stack.add(widget)
        self.pages.append((widget, title))
        widget.show_all()
        self.stack.set_visible_child(widget)

    def push(self, widget, title):
        self._show_page(widget, title)
        self.win.update_header()

    def pop(self):
        widget, _ = self.pages.pop()
        self.stack.set_visible_child(self.pages[-1][0])
        widget.destroy()
        self.win.update_header()

    @property
    def page_title(self):
        return self.pages[-1][1]

    def shown(self):
        """The panel became visible."""

    def hidden(self):
        """Another panel was selected, or the window is closing."""
