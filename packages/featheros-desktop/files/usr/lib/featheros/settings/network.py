"""Rede: Wi-Fi through iwd's D-Bus API (the daemon the top bar's Wi-Fi menu
also uses), wired connections and the addresses of the connection in use."""
import glob
import json
import os
from datetime import datetime

from gi.repository import GLib, Gtk

import ui
import util

IWD = "net.connman.iwd"
DEVICE, STATION = "net.connman.iwd.Device", "net.connman.iwd.Station"
NETWORK, KNOWN = "net.connman.iwd.Network", "net.connman.iwd.KnownNetwork"
AGENT_PATH = "/org/featheros/Settings/WifiAgent"
AGENT_XML = """<node><interface name="net.connman.iwd.Agent">
  <method name="Release"/>
  <method name="RequestPassphrase">
    <arg type="o" direction="in"/><arg type="s" direction="out"/></method>
  <method name="RequestPrivateKeyPassphrase">
    <arg type="o" direction="in"/><arg type="s" direction="out"/></method>
  <method name="RequestUserNameAndPassword">
    <arg type="o" direction="in"/><arg type="s" direction="out"/><arg type="s" direction="out"/></method>
  <method name="RequestUserPassword">
    <arg type="o" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
  <method name="Cancel"><arg type="s" direction="in"/></method>
</interface></node>"""
CANCELED = "net.connman.iwd.Agent.Error.Canceled"
SECURITY = {"open": "Aberta", "psk": "Protegida", "8021x": "Corporativa (802.1X)",
            "wep": "WEP (insegura)"}


def signal_icon(level):
    """iwd's signal level (dBm * 100) -> top bar-like icon."""
    dbm = level / 100
    name = ("excellent" if dbm >= -60 else "good" if dbm >= -67 else
            "ok" if dbm >= -75 else "weak")
    return f"network-wireless-signal-{name}-symbolic"


def blocked(ifname):
    return any(util.read(f) == "1" for f in
               glob.glob(f"/sys/class/net/{ifname}/phy80211/rfkill*/soft") +
               glob.glob(f"/sys/class/net/{ifname}/phy80211/rfkill*/hard"))



class Panel(ui.Panel):
    title = "Rede"

    def build(self):
        self.objs, self.device, self.station = {}, None, {}
        self.connecting = None        # network path being connected to
        self.pending = None           # agent request waiting for a password
        self.agent_ok = False
        self.timers = []
        self._quiet = False
        self._shown_addresses = None  # (wired, details) rows on screen

        page = ui.Page()
        self.spinner = Gtk.Spinner()
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.switch.connect("notify::active", self._toggle)
        self.wifi = page.group("Wi-Fi", suffix=[self.switch, self.spinner])
        self.more = page.group()
        self.more.append(ui.Row("Redes conhecidas", "Redes salvas neste computador",
                                on_activate=self.show_known, arrow=True))
        self.more.append(ui.Row("Conectar a uma rede oculta…",
                                on_activate=self.hidden_network))
        self.wired = page.group("Cabo")
        self.details = page.group("Detalhes da conexão")

        util.export(AGENT_PATH, AGENT_XML, self._agent)
        util.watch(IWD, self.refresh)
        GLib.idle_add(self.refresh)
        return page

    def shown(self):
        self._scan()
        self.timers = [GLib.timeout_add_seconds(15, self._scan),
                       GLib.timeout_add_seconds(5, self._addresses)]

    def hidden(self):
        for t in self.timers:
            GLib.source_remove(t)
        self.timers = []

    # --- state -----------------------------------------------------------------
    def _pick_device(self):
        """The adapter the Wi-Fi menu uses too: a USB one if present (the
        built-in card is switched off then), skipping blocked radios."""
        best = None
        for path, ifaces in self.objs.items():
            dev = ifaces.get(DEVICE)
            if not dev or dev.get("Mode") != "station" or blocked(dev["Name"]):
                continue
            usb = "/usb" in os.path.realpath(f"/sys/class/net/{dev['Name']}/device")
            if usb or best is None:
                best = path
                if usb:
                    break
        return best

    def refresh(self):
        self.objs = util.objects(IWD)
        if not self.objs:
            self.agent_ok = False
        elif not self.agent_ok:
            util.call(IWD, "/net/connman/iwd", "net.connman.iwd.AgentManager",
                      "RegisterAgent", GLib.Variant("(o)", (AGENT_PATH,)),
                      lambda _r, e: setattr(self, "agent_ok",
                                            e is None or "AlreadyExists" in e))
        self.device = self._pick_device()
        dev = self.objs.get(self.device, {}).get(DEVICE, {})
        self.station = self.objs.get(self.device, {}).get(STATION, {})

        self._quiet = True
        self.switch.set_active(bool(dev.get("Powered")))
        self._quiet = False
        self.switch.set_visible(bool(self.device))
        self.more.set_visible(bool(self.station))
        scanning = bool(self.station.get("Scanning"))
        self.spinner.set_visible(scanning)
        (self.spinner.start if scanning else self.spinner.stop)()

        if not self.objs:
            self._placeholder("O serviço de Wi-Fi (iwd) não está funcionando.")
        elif not self.device:
            self._placeholder("Nenhum adaptador Wi-Fi encontrado.")
        elif not self.station:
            self._placeholder("O Wi-Fi está desligado.")
        else:
            util.call(IWD, self.device, STATION, "GetOrderedNetworks", None,
                      lambda r, e: self._networks(r[0] if r else []))
        self._addresses()
        return False

    def _placeholder(self, text):
        self.wifi.clear()
        self.wifi.append(ui.Row(text))

    def _networks(self, ordered):
        self.wifi.clear()
        for path, level in ordered:
            net = self.objs.get(path, {}).get(NETWORK)
            if not net:
                continue
            if net.get("Connected"):
                state = {"connecting": "Conectando…", "roaming": "Conectado"}.get(
                    self.station.get("State"), "Conectado")
            elif path == self.connecting:
                state = "Conectando…"
            elif net.get("KnownNetwork"):
                state = "Salva"
            else:
                state = ""
            suffix = []
            if net.get("Connected"):
                suffix.append(ui.icon("object-select-symbolic"))
            if net.get("Type") != "open":
                suffix.append(ui.style(ui.icon("network-wireless-encrypted-symbolic"),
                                       "dim-label"))
            self.wifi.append(ui.Row(net["Name"], state, signal_icon(level), suffix,
                                    on_activate=lambda p=path: self.activate(p)))
        if not self.wifi.rows():
            self._placeholder("Procurando redes…" if self.station.get("Scanning")
                              else "Nenhuma rede encontrada.")

    def _scan(self):
        if self.station:
            util.call(IWD, self.device, STATION, "Scan")
        return True

    # --- actions ---------------------------------------------------------------
    def _toggle(self, switch, _pspec):
        if not self._quiet and self.device:
            util.set_property(IWD, self.device, DEVICE, "Powered",
                              GLib.Variant("b", switch.get_active()),
                              lambda *_: self.refresh())

    def activate(self, path):
        net = self.objs.get(path, {}).get(NETWORK, {})
        name = net.get("Name", "")
        if net.get("Connected"):
            ui.confirm(self.win, f"Desconectar de “{name}”?", "", "Desconectar",
                       lambda ok: ok and util.call(IWD, self.device, STATION, "Disconnect"))
            return
        if net.get("Type") == "8021x" and not net.get("KnownNetwork"):
            ui.message(self.win, "Rede corporativa",
                       f"“{name}” usa login corporativo (802.1X), que precisa de um "
                       "arquivo de configuração em /var/lib/iwd. Veja “man iwd.network”.")
            return
        self.connecting = path
        self.refresh()

        def done(_result, error):
            self.connecting = None
            if error and not error.endswith(("Canceled", "Aborted")):
                hint = ("Verifique a senha e tente de novo." if error.endswith("Failed")
                        else error)
                ui.message(self.win, f"Não foi possível conectar a “{name}”", hint)
            self.refresh()
        util.call(IWD, path, NETWORK, "Connect", None, done, timeout=120000)

    def hidden_network(self):
        def connect(ssid):
            if ssid:
                util.call(IWD, self.device, STATION, "ConnectHiddenNetwork",
                          GLib.Variant("(s)", (ssid,)),
                          lambda _r, e: e and not e.endswith(("Canceled", "Aborted")) and
                          ui.message(self.win, f"Não foi possível conectar a “{ssid}”",
                                     "Confira o nome da rede e a senha."),
                          timeout=120000)
        ui.prompt(self.win, "Conectar a uma rede oculta",
                  "Digite o nome (SSID) da rede.", connect, ok="Conectar")

    def show_known(self):
        page = ui.Page()
        group = page.group(None, "O computador se conecta sozinho a estas redes "
                                 "quando estão ao alcance.")
        known = sorted(((p, i[KNOWN]) for p, i in self.objs.items() if KNOWN in i),
                       key=lambda k: k[1]["Name"].casefold())
        for path, net in known:
            sub = SECURITY.get(net.get("Type"), "")
            try:
                last = datetime.fromisoformat(net["LastConnectedTime"].replace("Z", "+00:00"))
                sub += f" · última conexão em {last.astimezone():%d/%m/%Y}"
            except (KeyError, ValueError):
                pass
            forget = ui.button("Esquecer")
            row = group.append(ui.Row(net["Name"], sub, "network-wireless-symbolic",
                                      suffix=[forget]))
            forget.connect("clicked", lambda _b, p=path, n=net["Name"], r=row:
                           self.forget(p, n, r))
        if not known:
            group.append(ui.Row("Nenhuma rede salva."))
        self.push(page, "Redes conhecidas")

    def forget(self, path, name, row):
        def go(ok):
            if ok:
                util.call(IWD, path, KNOWN, "Forget", None,
                          lambda _r, e: e is None and row.destroy())
        ui.confirm(self.win, f"Esquecer “{name}”?",
                   "A senha salva será apagada e o computador não vai mais se "
                   "conectar sozinho a esta rede.", "Esquecer", go, destructive=True)

    # --- agent: iwd asks for the password while connecting -----------------------
    def _agent(self, method, args, invocation):
        if method == "RequestPassphrase":
            net = self.objs.get(args[0], {}).get(NETWORK) or {}
            name = net.get("Name") or util.get_property(IWD, args[0], NETWORK, "Name", "")
            self._cancel_pending()

            def answer(password):
                if self.pending and self.pending[0] is invocation:
                    self.pending = None
                    if password:
                        invocation.return_value(GLib.Variant("(s)", (password,)))
                    else:
                        invocation.return_dbus_error(CANCELED, "Canceled")
            dialog = ui.prompt(self.win, f"Senha da rede “{name}”",
                               "Digite a senha do Wi-Fi.", answer, ok="Conectar",
                               password=True)
            self.pending = (invocation, dialog)
        elif method == "Cancel":
            self._cancel_pending()
            invocation.return_value(None)
        elif method == "Release":
            self.agent_ok = False
            invocation.return_value(None)
        else:  # enterprise networks: not supported here
            invocation.return_dbus_error(CANCELED, "Not supported")

    def _cancel_pending(self):
        if self.pending:
            invocation, dialog = self.pending
            self.pending = None
            invocation.return_dbus_error(CANCELED, "Canceled")
            dialog.destroy()

    # --- wired and addresses -------------------------------------------------------
    def _addresses(self):
        """Wired links and the connection in use; rows are rebuilt only when
        something changed (they may hold a selection being copied)."""
        try:
            links = json.loads(util.output("ip", "-j", "addr", "show") or "[]")
            routes = json.loads(util.output("ip", "-j", "route", "show", "default") or "[]")
        except ValueError:
            links, routes = [], []

        wired = []
        for link in links:
            name = link.get("ifname", "")
            sys_dir = f"/sys/class/net/{name}"
            if not os.path.exists(f"{sys_dir}/device") or os.path.exists(f"{sys_dir}/wireless"):
                continue
            if util.read(f"{sys_dir}/carrier") == "1":
                speed = util.read(f"{sys_dir}/speed", "-1")
                state = "Conectado" + (f" · {speed} Mb/s" if speed.isdigit() and
                                       int(speed) > 0 else "")
            else:
                state = "Cabo desconectado"
            wired.append((f"Cabo de rede ({name})", state))

        details = []
        route = routes[0] if routes else {}
        link = next((l for l in links if l.get("ifname") == route.get("dev")), None)
        if link:
            name = link["ifname"]
            kind = "Wi-Fi" if os.path.exists(f"/sys/class/net/{name}/wireless") else "Cabo"
            details.append(("Conexão", f"{kind} ({name})"))
            for a in link.get("addr_info", []):
                if a.get("family") == "inet":
                    details.append(("Endereço IPv4", f"{a['local']}/{a['prefixlen']}"))
            details.append(("Gateway", route.get("gateway", "—")))
            dns = util.output("resolvectl", "dns", name).partition(":")[2].split()
            if dns:
                details.append(("DNS", ", ".join(dns[:3])))
            details.append(("Endereço físico", link.get("address", "")))

        if (wired, details) != self._shown_addresses:
            self._shown_addresses = (wired, details)
            self.wired.clear()
            for title, state in wired:
                self.wired.append(ui.Row(title, state, "network-wired-symbolic"))
            self.details.clear()
            for title, value in details:
                self.details.append(ui.ValueRow(title, value))
        self.wired.set_visible(bool(wired))
        self.details.set_visible(bool(details))
        return True
