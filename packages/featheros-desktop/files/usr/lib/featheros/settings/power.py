"""Energia: battery, power mode (CPU governor), power button and lid
(logind), screen blanking (X's DPMS) and automatic suspend (sessiond)."""
import glob
import os

from gi.repository import GLib, Gtk

import ui
import util

LOGIND = ("org.freedesktop.login1", "/org/freedesktop/login1",
          "org.freedesktop.login1.Manager")
MODES = [
    ("performance", "Desempenho", "Processador sempre na velocidade máxima",
     "power-profile-performance-symbolic"),
    ("balanced", "Equilibrado", "A velocidade acompanha o uso (padrão)",
     "power-profile-balanced-symbolic"),
    ("power-saver", "Economia de energia",
     "Processador na velocidade mínima: menos calor e mais bateria",
     "power-profile-power-saver-symbolic"),
]
GOVERNORS = {"performance": "performance", "powersave": "power-saver"}
BLANK = [(m, f"{m} minuto" + ("s" if m > 1 else "")) for m in (1, 2, 3, 5, 10, 15, 30)]
SUSPEND = [(m, f"{m} minutos") for m in (10, 15, 20, 30, 45, 60, 90)]


def battery():
    for b in glob.glob("/sys/class/power_supply/*"):
        if util.read(f"{b}/type") == "Battery":
            return b
    return None


def current_mode():
    saved = util.read("/etc/featheros/power-mode")
    if saved:
        return saved
    gov = util.read("/sys/devices/system/cpu/cpufreq/policy0/scaling_governor")
    return GOVERNORS.get(gov, "balanced")


class Panel(ui.Panel):
    title = "Energia"

    def build(self):
        s = util.settings()
        page = ui.Page()
        self.timer = None

        self.battery = battery()
        if self.battery:
            group = page.group("Bateria")
            self.level = Gtk.LevelBar(min_value=0, max_value=100, hexpand=True)
            self.level.set_size_request(-1, 10)
            self.battery_text = ui.label("", "dim-label", "fs-subtitle")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=14)
            box.pack_start(self.level, False, False, 0)
            box.pack_start(self.battery_text, False, False, 0)
            row = Gtk.ListBoxRow(activatable=False, selectable=False)
            row.add(box)
            group.append(row)
            self._battery()

        if os.path.exists("/sys/devices/system/cpu/cpufreq/policy0/scaling_governor"):
            group = page.group("Modo de energia")
            ui.radio_rows(group, MODES, current_mode(), self._mode)

        general = page.group("Geral")
        key = util.get_property(*LOGIND, "HandlePowerKey", "poweroff")
        general.append(ui.ComboRow(
            "Botão de ligar/desligar",
            [("poweroff", "Desligar"), ("suspend", "Suspender"), ("ignore", "Não fazer nada")],
            key if key in ("poweroff", "suspend", "ignore") else "poweroff",
            lambda v: util.system("power-key", v, done=self._failed)))
        if glob.glob("/proc/acpi/button/lid/*"):
            lid = util.get_property(*LOGIND, "HandleLidSwitch", "suspend")
            general.append(ui.ComboRow(
                "Ao fechar a tampa",
                [("suspend", "Suspender"), ("poweroff", "Desligar"),
                 ("ignore", "Não fazer nada")],
                lid if lid in ("suspend", "poweroff", "ignore") else "suspend",
                lambda v: util.system("lid", v, done=self._failed)))

        saving = page.group("Economia de energia")
        blank = s["SCREEN_BLANK"] or "10"  # empty: X's default, 10 minutes
        self.blank_delay = ui.ComboRow("Apagar a tela depois de", BLANK,
                                       blank if blank != "0" else "5",
                                       lambda v: self._blank(v))
        saving.append(ui.SwitchRow("Apagar a tela automaticamente",
                                   "Desliga a tela quando o computador não é usado",
                                   blank != "0", self._blank_switch))
        saving.append(self.blank_delay)
        self.blank_delay.set_sensitive(blank != "0")

        after = s["SUSPEND_AFTER"]
        self.suspend_delay = ui.ComboRow("Suspender depois de", SUSPEND,
                                         after if after != "0" else "20",
                                         lambda v: util.save(SUSPEND_AFTER=v))
        saving.append(ui.SwitchRow("Suspender automaticamente",
                                   "Não suspende enquanto toca música ou vídeo",
                                   after != "0", self._suspend_switch))
        saving.append(self.suspend_delay)
        self.suspend_delay.set_sensitive(after != "0")
        return page

    def shown(self):
        if self.battery and not self.timer:
            self.timer = GLib.timeout_add_seconds(30, self._battery)

    def hidden(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None

    def _battery(self):
        b = self.battery
        cap = int(util.read(f"{b}/capacity", "0") or 0)
        status = util.read(f"{b}/status")
        self.level.set_value(cap)
        text = f"{cap} % · " + {"Charging": "carregando", "Full": "carregada",
                                "Not charging": "na tomada"}.get(status, "na bateria")
        # Time left from energy (µWh) / power (µW), or charge (µAh) / current (µA).
        now = util.read(f"{b}/energy_now") or util.read(f"{b}/charge_now")
        rate = util.read(f"{b}/power_now") or util.read(f"{b}/current_now")
        if status == "Discharging" and now.isdigit() and rate.isdigit() and int(rate) > 0:
            hours = int(now) / int(rate)
            text += f" · cerca de {int(hours)} h {int(hours % 1 * 60):02d} min restantes"
        self.battery_text.set_text(text)
        return True

    def _mode(self, mode):
        util.system("power-mode", mode, done=self._failed)

    def _failed(self, ok, out):
        if not ok:
            ui.message(self.win, "Não foi possível mudar esta configuração", out)

    def _blank_switch(self, on):
        self.blank_delay.set_sensitive(on)
        self._blank(self.blank_delay.value if on else "0")

    def _blank(self, minutes):
        util.save(SCREEN_BLANK=minutes)
        util.shell("featheros_screen_blank")

    def _suspend_switch(self, on):
        self.suspend_delay.set_sensitive(on)
        util.save(SUSPEND_AFTER=self.suspend_delay.value if on else "0")
