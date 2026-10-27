"""Sistema: region and language, date and time, users, remote access, about
this computer and updates. Root changes go through settings-system."""
import grp
import os
import platform
import pwd
import re
import unicodedata
from datetime import datetime

from gi.repository import GdkPixbuf, GLib, Gtk

import ui
import util

LANGUAGES = [("pt_BR", "Português (Brasil)"), ("pt_PT", "Português (Portugal)"),
             ("en_US", "English (United States)"), ("es_ES", "Español"),
             ("fr_FR", "Français"), ("de_DE", "Deutsch"), ("it_IT", "Italiano")]
AUTOLOGIN = "/etc/systemd/system/getty@tty1.service.d/autologin.conf"
ZONES = "/usr/share/zoneinfo/zone1970.tab"



def link(icon_name):
    return ui.style(ui.icon(icon_name), "dim-label")


def fold(text):
    text = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in text if not unicodedata.combining(c))


def zones():
    """[(zone, place description)] from tzdata, Brazil's zones first."""
    found = []
    for line in util.read(ZONES).splitlines():
        parts = line.split("\t")
        if line.startswith("#") or len(parts) < 3:
            continue
        found.append((parts[2], parts[3] if len(parts) > 3 else "", "BR" in parts[0].split(",")))
    found.sort(key=lambda z: (not z[2], z[0]))
    return [(z, comment) for z, comment, _br in found]


def size(kib):
    gb = kib / 1024 / 1024
    return f"{gb:.1f} GB".replace(".", ",")


class Panel(ui.Panel):
    title = "Sistema"

    def build(self):
        page = ui.Page()
        group = page.group()
        for title, sub, icon_name, show in (
                ("Região e idioma", "Idioma do sistema e teclado",
                 "org.gnome.Settings-region-symbolic", self.show_region),
                ("Data e hora", "Fuso horário e ajuste do relógio",
                 "org.gnome.Settings-time-symbolic", self.show_time),
                ("Usuários", "Senha e login automático",
                 "org.gnome.Settings-users-symbolic", self.show_users),
                ("Acesso remoto", "Deixar o computador de atualizações acessar este",
                 "org.gnome.Settings-remote-desktop-symbolic", self.show_remote),
                ("Sobre", "Detalhes do hardware e versões do software",
                 "org.gnome.Settings-about-symbolic", self.show_about)):
            group.append(ui.Row(title, sub, icon_name, on_activate=show, arrow=True))
        page.group().append(ui.Row("Atualizações", None, "software-update-available-symbolic",
                                   suffix=[link("adw-external-link-symbolic")],
                                   on_activate=lambda: util.launch("featheros-updates")))
        return page

    def _done(self, ok, out):
        if not ok:
            ui.message(self.win, "Não foi possível mudar esta configuração", out)

    # --- region and language -------------------------------------------------------------
    def show_region(self):
        page = ui.Page()
        group = page.group(None, "O novo idioma vale a partir do próximo login. O Firefox "
                                 "tem o próprio idioma, nas configurações dele.")
        current = re.search(r"^LANG=(\w+)", util.read("/etc/locale.conf"), re.M)
        spinner = Gtk.Spinner()
        row = ui.ComboRow("Idioma", LANGUAGES, current.group(1) if current else "pt_BR",
                          lambda code: self._language(code, row, spinner))
        row.get_child().pack_start(spinner, False, False, 0)
        group.append(row)
        page.group().append(ui.Row("Teclado", "Layouts e atalhos", "input-keyboard-symbolic",
                                   on_activate=lambda: self.win.show_panel("keyboard"),
                                   arrow=True))
        self.push(page, "Região e idioma")

    def _language(self, code, row, spinner):
        spinner.start()
        row.set_subtitle("Preparando o idioma…")

        def done(ok, out):
            spinner.stop()
            row.set_subtitle("Vale a partir do próximo login" if ok else "")
            self._done(ok, out)
        util.system("language", code, done=done)

    # --- date and time ---------------------------------------------------------------------
    def show_time(self):
        page = ui.Page()
        group = page.group()
        now = group.append(ui.ValueRow("Data e hora", ""))
        def tick():
            now.value.set_text(datetime.now().strftime("%d/%m/%Y  %H:%M"))
            return True
        tick()
        timer = GLib.timeout_add_seconds(10, tick)
        page.connect("destroy", lambda *_: GLib.source_remove(timer))

        ntp = util.output("timedatectl", "show", "-p", "NTP", "--value").strip() == "yes"
        group.append(ui.SwitchRow("Data e hora automáticas", "Acerta o relógio pela internet",
                                  ntp, lambda on: util.system("ntp", "on" if on else "off",
                                                              done=self._done)))
        tz = util.output("timedatectl", "show", "-p", "Timezone", "--value").strip()
        self.tz_row = group.append(ui.Row("Fuso horário", tz.replace("_", " "),
                                          on_activate=self.show_zones, arrow=True))
        self.push(page, "Data e hora")

    def show_zones(self):
        page = ui.Page()
        search = Gtk.SearchEntry(placeholder_text="Buscar cidade ou país", margin_top=18)
        page.append(search)
        group = page.group()
        all_zones = [(z, comment, fold(f"{z} {comment}")) for z, comment in zones()]
        rows = []

        def choose(zone):
            def done(ok, out):
                self._done(ok, out)
                if ok:
                    self.tz_row.set_subtitle(zone.replace("_", " "))
                    self.pop()
            util.system("timezone", zone, done=done)

        def fill():
            for r in rows:
                r.destroy()
            rows.clear()
            query = fold(search.get_text().strip()).replace(" ", "_")
            for zone, comment, words in all_zones:
                if query in words or query.replace("_", " ") in words:
                    city = zone.rsplit("/", 1)[-1].replace("_", " ")
                    rows.append(group.append(ui.Row(city, f"{zone.replace('_', ' ')} · {comment}"
                                                    if comment else zone,
                                                    on_activate=lambda z=zone: choose(z))))
                    if len(rows) >= 60:
                        break
        search.connect("search-changed", lambda *_: fill())
        fill()
        self.push(page, "Fuso horário")
        search.grab_focus()

    # --- users --------------------------------------------------------------------------------
    def show_users(self):
        me = pwd.getpwuid(os.getuid())
        try:
            admin = me.pw_name in grp.getgrnam("wheel").gr_mem
        except KeyError:
            admin = False
        page = ui.Page()
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=18)
        head.pack_start(ui.style(ui.icon("avatar-default-symbolic", 80), "dim-label"),
                        False, False, 0)
        head.pack_start(ui.label(f"<big><b>{ui.esc(me.pw_gecos.split(',')[0] or me.pw_name)}"
                                 "</b></big>", markup=True, xalign=0.5), False, False, 0)
        head.pack_start(ui.label(me.pw_name + (" · Administrador" if admin else ""),
                                 "dim-label", xalign=0.5), False, False, 0)
        page.append(head)
        group = page.group()
        group.append(ui.Row("Senha", "Usada para entrar e para tarefas de administrador",
                            suffix=[ui.button("Alterar…", on_click=lambda: util.terminal(
                                "Alterar senha", "passwd"))]))
        auto = f"--autologin {me.pw_name} " in util.read(AUTOLOGIN)
        group.append(ui.SwitchRow("Login automático",
                                  "Entra sem pedir a senha ao ligar o computador", auto,
                                  lambda on: util.system("autologin", "on" if on else "off",
                                                         done=self._done)))
        self.push(page, "Usuários")

    # --- remote access ------------------------------------------------------------------------
    def show_remote(self):
        page = ui.Page()
        group = page.group(None, "Deixa o computador que gera as atualizações do FeatherOS "
                                 "entrar neste por SSH, para ajudar a resolver problemas. "
                                 "Só ele pode entrar (com a chave dele; senhas são "
                                 "recusadas), e o acesso desliga sozinho ao reiniciar.")
        address = ui.ValueRow("Endereço", "")
        active = util.output("systemctl", "is-active", "sshd.service").strip() == "active"

        def show_address(on):
            ip = re.search(r"inet (\S+)/", util.output("ip", "-4", "-o", "addr", "show",
                                                       "scope", "global"))
            address.value.set_text(
                f"{pwd.getpwuid(os.getuid()).pw_name}@{ip.group(1) if ip else '?'}")
            address.set_visible(on)

        def toggle(on):
            def done(ok, out):
                self._done(ok, out)
                show_address(ok and on)
            util.run(["sudo", "-n", "systemctl", "start" if on else "stop", "sshd.service"],
                     done)
        group.append(ui.SwitchRow("Acesso remoto", None, active, toggle))
        group.append(address)
        self.push(page, "Acesso remoto")
        show_address(active)

    # --- about --------------------------------------------------------------------------------
    def show_about(self):
        page = ui.Page()
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=18)
        try:
            logo = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(
                "/usr/share/featheros/logo.svg", 96, 96))
        except GLib.Error:
            logo = ui.icon("featheros", 96)
        head.pack_start(logo, False, False, 0)
        head.pack_start(ui.label("<big><b>FeatherOS</b></big>", markup=True, xalign=0.5),
                        False, False, 0)
        version = util.output("pacman", "-Q", "featheros-desktop").split()
        if len(version) == 2:
            head.pack_start(ui.label(f"Versão {version[1].rsplit('-', 1)[0]}", "dim-label",
                                     xalign=0.5), False, False, 0)
        page.append(head)

        name = page.group()
        host = util.read("/etc/hostname") or platform.node()
        name_row = name.append(ui.ValueRow("Nome do computador", host))
        name_row.get_child().pack_start(ui.button(icon_name="document-edit-symbolic",
                                                  tooltip="Mudar o nome",
                                                  on_click=lambda: self._rename(name_row)),
                                        False, False, 0)

        hw = page.group("Hardware")
        model = " ".join(util.read(f"/sys/class/dmi/id/{f}") for f in
                         ("sys_vendor", "product_name")).strip()
        if model:
            hw.append(ui.ValueRow("Modelo", model))
        cpu = util.read("/proc/cpuinfo")
        m = re.search(r"^model name\s*:\s*(.+)$", cpu, re.M)
        cores = len(re.findall(r"^processor\s*:", cpu, re.M))
        if m:
            hw.append(ui.ValueRow("Processador", re.sub(r"\s+", " ", m.group(1)) +
                                (f" × {cores}" if cores > 1 else "")))
        mem = re.search(r"^MemTotal:\s*(\d+)", util.read("/proc/meminfo"), re.M)
        if mem:
            hw.append(ui.ValueRow("Memória", size(int(mem.group(1)))))
        gpu = re.search(r"VGA compatible controller: (.+)", util.output("lspci"))
        if gpu:
            hw.append(ui.ValueRow("Gráficos", gpu.group(1)))
        st = os.statvfs("/")
        hw.append(ui.ValueRow("Disco", f"{size(st.f_bavail * st.f_frsize / 1024)} livres de "
                                     f"{size(st.f_blocks * st.f_frsize / 1024)}"))

        sw = page.group("Software")
        sw.append(ui.ValueRow("Sistema", "FeatherOS, baseado no Arch Linux (64 bits)"))
        sw.append(ui.ValueRow("Kernel", platform.release()))
        sw.append(ui.ValueRow("Área de trabalho", "Openbox (X11)"))
        self.push(page, "Sobre")

    def _rename(self, row):
        def done(text):
            if text is None:
                return
            name = re.sub(r"[^a-z0-9-]+", "-", fold(text.strip())).strip("-")[:63]
            if not name:
                return
            util.system("hostname", name, done=lambda ok, out: (
                ok and row.value.set_text(name), self._done(ok, out)))
        ui.prompt(self.win, "Nome do computador",
                  "Aparece na rede (por exemplo, nome.local). Use letras, números e hífens.",
                  done, ok="Mudar", initial=row.value.get_text())
