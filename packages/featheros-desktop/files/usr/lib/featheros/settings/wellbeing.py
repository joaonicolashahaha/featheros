"""Bem-estar: screen time (counted by sessiond: minutes with keyboard or mouse
use), a daily limit and break reminders (shown by sessiond)."""
import math
import os
from datetime import date, timedelta

from gi.repository import Gtk

import ui
import util

LOG = os.path.join(util.DATA_DIR, "screen-time")
DAYS = "DSTQQSS"  # Sunday first, as in Brazil
WEEKDAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def history():
    """{date: minutes} from sessiond's log."""
    days = {}
    try:
        with open(LOG) as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2 and parts[1].isdigit():
                    try:
                        days[date.fromisoformat(parts[0])] = int(parts[1])
                    except ValueError:
                        pass
    except OSError:
        pass
    return days


def hm(minutes):
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def sunday(day):
    return day - timedelta(days=(day.weekday() + 1) % 7)


class Chart(Gtk.DrawingArea):
    """A week of screen time as bars, with hour lines and the daily limit."""

    def __init__(self):
        super().__init__()
        self.set_size_request(-1, 170)
        self.values, self.today_index, self.limit = [0] * 7, -1, 0
        self.connect("draw", self._draw)

    def set(self, values, today_index, limit):
        self.values, self.today_index, self.limit = values, today_index, limit
        self.queue_draw()

    def _draw(self, widget, cr):
        ctx = widget.get_style_context()
        fg = ctx.get_color(ctx.get_state())
        found, accent = ctx.lookup_color("theme_selected_bg_color")
        if not found:
            accent = fg
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        left, right, top, bottom = 4, 34, 8, 22
        plot_w, plot_h = w - left - right, h - top - bottom

        top_hours = max(2, math.ceil(max(self.values + [self.limit]) / 60))
        step = 1 if top_hours <= 4 else 2 if top_hours <= 10 else 4
        top_hours = math.ceil(top_hours / step) * step

        def y_of(minutes):
            return top + plot_h - plot_h * minutes / (top_hours * 60)

        cr.set_font_size(10)
        cr.set_line_width(1)
        for hour in range(0, top_hours + 1, step):
            y = round(y_of(hour * 60)) + 0.5
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.15)
            cr.move_to(left, y)
            cr.line_to(left + plot_w, y)
            cr.stroke()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
            cr.move_to(left + plot_w + 6, y + 3)
            cr.show_text(f"{hour}h")

        if self.limit:
            y = round(y_of(self.limit)) + 0.5
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.55)
            cr.set_dash([5, 4])
            cr.move_to(left, y)
            cr.line_to(left + plot_w, y)
            cr.stroke()
            cr.set_dash([])

        slot = plot_w / 7
        bar = min(44, slot * 0.6)
        for i, minutes in enumerate(self.values):
            x = left + slot * i + (slot - bar) / 2
            if minutes:
                y = y_of(minutes)
                r = min(4, (top + plot_h - y) / 2)
                alpha = 1 if i == self.today_index else 0.5
                cr.set_source_rgba(accent.red, accent.green, accent.blue, alpha)
                cr.new_sub_path()
                cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
                cr.arc(x + bar - r, y + r, r, 1.5 * math.pi, 2 * math.pi)
                cr.line_to(x + bar, top + plot_h)
                cr.line_to(x, top + plot_h)
                cr.close_path()
                cr.fill()
            cr.set_source_rgba(fg.red, fg.green, fg.blue,
                               1 if i == self.today_index else 0.7)
            ext = cr.text_extents(DAYS[i])
            cr.move_to(x + bar / 2 - ext.width / 2, h - 5)
            cr.show_text(DAYS[i])


def stat(caption, average_caption):
    """Caption, big number, average caption, average: returns the box and labels."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
    labels = [ui.label(caption), ui.label("", "fs-big"),
              ui.label(average_caption, "dim-label", "fs-caption", margin_top=4),
              ui.label("")]
    for lab in labels:
        box.pack_start(lab, False, False, 0)
    return box, *labels


class Panel(ui.Panel):
    title = "Bem-estar"

    def build(self):
        s = util.settings()
        self.week = sunday(date.today())
        page = ui.Page()

        menu = Gtk.Menu()
        clear = Gtk.MenuItem(label="Apagar o histórico de uso…")
        clear.connect("activate", lambda *_: self._clear())
        menu.append(clear)
        menu.show_all()
        more = Gtk.MenuButton(popup=menu, relief=Gtk.ReliefStyle.NONE)
        more.set_image(ui.icon("view-more-symbolic"))
        group = page.group("Tempo de uso", suffix=more)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=16)
        stats = Gtk.Box(spacing=12)
        today, _, self.today_value, self.today_avg_caption, self.today_avg = stat(
            "Hoje", "")
        week, self.week_title, self.week_value, _, self.week_avg = stat(
            "Esta semana", "MÉDIA SEMANAL")
        stats.pack_start(today, True, True, 0)
        stats.pack_start(week, True, True, 0)
        box.pack_start(stats, False, False, 0)
        self.chart = Chart()
        box.pack_start(self.chart, False, False, 0)
        nav = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        self.prev = ui.button(icon_name="go-previous-symbolic", tooltip="Semana anterior",
                              on_click=lambda: self._move(-7))
        self.next = ui.button(icon_name="go-next-symbolic", tooltip="Próxima semana",
                              on_click=lambda: self._move(7))
        nav.pack_start(self.prev, False, False, 0)
        nav.pack_start(self.next, False, False, 0)
        box.pack_start(nav, False, False, 0)
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        row.add(box)
        group.append(row)

        limits = page.group("Limite de uso")
        limit = int(s["SCREEN_LIMIT"] or 0)
        self.limit_hours = ui.ComboRow(
            "Limite diário", [(h, f"{h} hora" + ("s" if h > 1 else "")) for h in range(1, 13)],
            str(limit // 60 if limit else 8), lambda v: self._limit(True))
        limits.append(ui.SwitchRow("Limite de tempo de uso",
                                   "Avisa quando o uso do dia chegar ao limite",
                                   bool(limit), self._limit))
        limits.append(self.limit_hours)
        self.limit_hours.set_sensitive(bool(limit))

        breaks = page.group("Lembretes de pausa")
        self.break_every = ui.ComboRow(
            "Frequência", [(30, "A cada 30 minutos"), (45, "A cada 45 minutos"),
                           (60, "A cada hora"), (90, "A cada 1 h 30 min"),
                           (120, "A cada 2 horas")],
            s["BREAK_EVERY"], lambda v: util.save(BREAK_EVERY=v))
        breaks.append(ui.SwitchRow("Pausas para se movimentar",
                                   "Lembra de levantar e alongar o corpo",
                                   s["BREAKS"] == "on", self._breaks))
        breaks.append(self.break_every)
        self.break_every.set_sensitive(s["BREAKS"] == "on")
        breaks.append(ui.SwitchRow("Descanso para os olhos",
                                   "A cada 20 minutos, lembra de olhar para longe por "
                                   "20 segundos",
                                   s["EYE_BREAKS"] == "on",
                                   lambda on: util.save(EYE_BREAKS="on" if on else "off")))
        page.append(ui.label("O tempo de uso conta os minutos em que o teclado ou o mouse "
                             "foram usados.", "dim-label", "fs-subtitle", wrap=True,
                             margin_top=12))
        self.update()
        return page

    def shown(self):
        self.update()

    def update(self):
        data = history()
        today = date.today()
        days = [self.week + timedelta(days=i) for i in range(7)]
        values = [data.get(d, 0) for d in days]
        limit = int(util.setting("SCREEN_LIMIT") or 0)
        self.chart.set(values, days.index(today) if today in days else -1, limit)

        self.today_value.set_text(hm(data.get(today, 0)))
        same_day = [m for d, m in data.items() if d.weekday() == today.weekday() and d < today]
        self.today_avg_caption.set_text(f"MÉDIA DE {WEEKDAYS[today.weekday()].upper()}")
        self.today_avg.set_text(hm(sum(same_day) / len(same_day)) if same_day else "—")

        current = self.week == sunday(today)
        self.week_title.set_text("Esta semana" if current else
                                 f"Semana de {self.week:%d/%m}")
        self.week_value.set_text(hm(sum(values)))
        weeks = {}
        for d, m in data.items():
            if sunday(d) < sunday(today):
                weeks[sunday(d)] = weeks.get(sunday(d), 0) + m
        self.week_avg.set_text(hm(sum(weeks.values()) / len(weeks)) if weeks else "—")

        oldest = min(data, default=today)
        self.prev.set_sensitive(self.week > sunday(oldest))
        self.next.set_sensitive(not current)

    def _move(self, days):
        self.week += timedelta(days=days)
        self.update()

    def _limit(self, on):
        self.limit_hours.set_sensitive(on)
        util.save(SCREEN_LIMIT=int(self.limit_hours.value) * 60 if on else 0)
        self.update()

    def _breaks(self, on):
        self.break_every.set_sensitive(on)
        util.save(BREAKS="on" if on else "off")

    def _clear(self):
        def go(ok):
            if ok:
                try:
                    os.remove(LOG)
                except OSError:
                    pass
                self.week = sunday(date.today())
                self.update()
        ui.confirm(self.win, "Apagar o histórico de uso?",
                   "O tempo de uso de todos os dias será apagado.", "Apagar", go,
                   destructive=True)

