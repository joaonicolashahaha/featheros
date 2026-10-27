"""Bluetooth through BlueZ's D-Bus API.

bluetoothd only runs when an adapter is plugged in: bluetooth.service is
wanted by bluetooth.target, which udev starts when an adapter appears. So it
costs nothing on a computer without Bluetooth (like the target laptop,
until a USB adapter is plugged in).
"""
from gi.repository import GLib, Gtk

import ui
import util

BLUEZ = "org.bluez"
ADAPTER, DEVICE = "org.bluez.Adapter1", "org.bluez.Device1"
AGENT_PATH = "/org/featheros/Settings/BluetoothAgent"
AGENT_XML = """<node><interface name="org.bluez.Agent1">
  <method name="Release"/>
  <method name="RequestPinCode">
    <arg type="o" direction="in"/><arg type="s" direction="out"/></method>
  <method name="DisplayPinCode">
    <arg type="o" direction="in"/><arg type="s" direction="in"/></method>
  <method name="RequestPasskey">
    <arg type="o" direction="in"/><arg type="u" direction="out"/></method>
  <method name="DisplayPasskey">
    <arg type="o" direction="in"/><arg type="u" direction="in"/><arg type="q" direction="in"/></method>
  <method name="RequestConfirmation">
    <arg type="o" direction="in"/><arg type="u" direction="in"/></method>
  <method name="RequestAuthorization"><arg type="o" direction="in"/></method>
  <method name="AuthorizeService">
    <arg type="o" direction="in"/><arg type="s" direction="in"/></method>
  <method name="Cancel"/>
</interface></node>"""
REJECTED, CANCELED = "org.bluez.Error.Rejected", "org.bluez.Error.Canceled"

KINDS = {  # Device1.Icon -> (icon, description)
    "audio-headset": ("audio-headset-symbolic", "Fone de ouvido"),
    "audio-headphones": ("audio-headphones-symbolic", "Fone de ouvido"),
    "audio-card": ("audio-speakers-symbolic", "Caixa de som"),
    "input-mouse": ("input-mouse-symbolic", "Mouse"),
    "input-keyboard": ("input-keyboard-symbolic", "Teclado"),
    "input-gaming": ("input-gaming-symbolic", "Controle de jogo"),
    "input-tablet": ("input-tablet-symbolic", "Mesa digitalizadora"),
    "phone": ("phone-symbolic", "Celular"),
    "computer": ("computer-symbolic", "Computador"),
}



class Panel(ui.Panel):
    title = "Bluetooth"

    def build(self):
        self.objs, self.adapter = {}, None
        self.pairing = None     # device being paired
        self.pending = None     # (invocation, dialog) of an agent request
        self.info = None        # dialog showing a code to type on the device
        self.device_page = None  # (path, connected switch row) of the open subpage
        self.visible = self.discovering = self.agent_ok = False

        self.views = Gtk.Stack()
        self.views.add_named(ui.status_page(
            "bluetooth-disabled-symbolic", "Nenhum adaptador Bluetooth",
            "Conecte um adaptador Bluetooth USB para usar fones, caixas de som, "
            "mouses e teclados sem fio."), "none")
        page = ui.Page()
        self.power = page.group().append(ui.SwitchRow("Bluetooth", on_toggle=self._power))
        self.spinner = Gtk.Spinner()
        self.devices = page.group("Dispositivos", suffix=self.spinner)
        self.views.add_named(page, "adapter")

        util.export(AGENT_PATH, AGENT_XML, self._agent)
        util.watch(BLUEZ, self.refresh)
        GLib.idle_add(self.refresh)
        return self.views

    def shown(self):
        self.visible = True
        self._discover()

    def hidden(self):
        self.visible = False
        self._discover()

    def _name(self, path):
        d = self.objs.get(path, {}).get(DEVICE, {})
        return d.get("Alias") or d.get("Name") or d.get("Address", "")

    # --- state -----------------------------------------------------------------
    def refresh(self):
        self.objs = util.objects(BLUEZ)
        adapters = sorted(p for p, i in self.objs.items() if ADAPTER in i)
        self.adapter = adapters[0] if adapters else None
        self.views.set_visible_child_name("adapter" if self.adapter else "none")
        if not self.adapter:
            self.agent_ok = self.discovering = False
            return False
        if not self.agent_ok:
            self._register()

        ad = self.objs[self.adapter][ADAPTER]
        powered = bool(ad.get("Powered"))
        self.power.set_active(powered)
        self.power.set_subtitle(
            f"Visível como “{ad.get('Alias', '')}” enquanto esta tela está aberta"
            if powered else "")
        if not powered:
            self.discovering = False
        self.devices.set_visible(powered)
        searching = bool(ad.get("Discovering"))
        self.spinner.set_visible(searching)
        (self.spinner.start if searching else self.spinner.stop)()
        self._discover()

        self.devices.clear()
        devs = [(p, i[DEVICE]) for p, i in self.objs.items()
                if DEVICE in i and i[DEVICE].get("Adapter") == self.adapter]
        devs.sort(key=lambda d: (not d[1].get("Paired"), not d[1].get("Connected"),
                                 self._name(d[0]).casefold()))
        for path, d in devs:
            if not d.get("Paired") and "Name" not in d:
                continue  # nameless devices nearby: not useful to list
            icon_name = KINDS.get(d.get("Icon", ""), ("bluetooth-symbolic", ""))[0]
            if path == self.pairing:
                state = "Conectando…"
            elif d.get("Connected"):
                state = "Conectado"
            elif d.get("Paired"):
                state = "Desconectado"
            else:
                state = "Não configurado"
            self.devices.append(ui.Row(self._name(path), state, icon_name,
                                       on_activate=lambda p=path: self.activate(p),
                                       arrow=bool(d.get("Paired"))))
        if not self.devices.rows():
            self.devices.append(ui.Row("Procurando dispositivos…"))

        if self.device_page:
            path, row = self.device_page
            d = self.objs.get(path, {}).get(DEVICE)
            if d:
                row.set_active(d.get("Connected"))
        return False

    def _register(self):
        def registered(_r, error):
            if error is None or "AlreadyExists" in error:
                self.agent_ok = True
                util.call(BLUEZ, "/org/bluez", "org.bluez.AgentManager1",
                          "RequestDefaultAgent", GLib.Variant("(o)", (AGENT_PATH,)))
        util.call(BLUEZ, "/org/bluez", "org.bluez.AgentManager1", "RegisterAgent",
                  GLib.Variant("(os)", (AGENT_PATH, "KeyboardDisplay")), registered)

    def _discover(self):
        """Search for devices, and be visible to them, only while the panel is
        open (like GNOME)."""
        ad = self.objs.get(self.adapter, {}).get(ADAPTER, {})
        want = self.visible and bool(ad.get("Powered"))
        if want != self.discovering:
            self.discovering = want
            util.call(BLUEZ, self.adapter, ADAPTER,
                      "StartDiscovery" if want else "StopDiscovery")
            util.set_property(BLUEZ, self.adapter, ADAPTER, "Discoverable",
                              GLib.Variant("b", want))

    # --- actions ---------------------------------------------------------------
    def _power(self, on):
        def done(_r, error):
            if error:
                ui.message(self.win, "Não foi possível ligar o Bluetooth",
                           "O adaptador pode estar bloqueado (rfkill) ou desconectado.")
            self.refresh()
        util.set_property(BLUEZ, self.adapter, ADAPTER, "Powered",
                          GLib.Variant("b", on), done)

    def activate(self, path):
        if self.objs.get(path, {}).get(DEVICE, {}).get("Paired"):
            self.show_device(path)
        else:
            self.pair(path)

    def pair(self, path):
        name = self._name(path)
        self.pairing = path
        self.refresh()

        def finished(_r=None, _e=None):
            self.pairing = None
            self._close_info()
            self.refresh()

        def paired(_r, error):
            if error and not error.endswith("AlreadyExists"):
                finished()
                if not error.endswith(("AuthenticationCanceled", "Canceled")):
                    ui.message(self.win, f"Não foi possível parear com “{name}”",
                               "Coloque o dispositivo em modo de pareamento (veja o "
                               "manual dele) e tente de novo.")
                return
            # Trusted: it may reconnect by itself later (headphones, mice).
            util.set_property(BLUEZ, path, DEVICE, "Trusted", GLib.Variant("b", True))
            util.call(BLUEZ, path, DEVICE, "Connect", None, finished, timeout=60000)
        util.call(BLUEZ, path, DEVICE, "Pair", None, paired, timeout=90000)

    def show_device(self, path):
        d = self.objs[path][DEVICE]
        name = self._name(path)
        page = ui.Page()
        group = page.group()

        def connect(on):
            def done(_r, error):
                if error:
                    ui.message(self.win, f"Não foi possível {'conectar' if on else 'desconectar'}"
                               f" “{name}”", "Verifique se o dispositivo está ligado e por perto.")
                self.refresh()
            util.call(BLUEZ, path, DEVICE, "Connect" if on else "Disconnect", None, done,
                      timeout=60000)
        row = group.append(ui.SwitchRow("Conectado", active=bool(d.get("Connected")),
                                        on_toggle=connect))
        kind = KINDS.get(d.get("Icon", ""), (None, ""))[1]
        if kind:
            group.append(ui.ValueRow("Tipo", kind))
        group.append(ui.ValueRow("Endereço", d.get("Address", "")))
        battery = self.objs[path].get("org.bluez.Battery1", {}).get("Percentage")
        if battery is not None:
            group.append(ui.ValueRow("Bateria", f"{battery} %"))
        forget = ui.button("Esquecer dispositivo", None, lambda: self.forget(path, name),
                           "destructive-action")
        forget.set_halign(Gtk.Align.CENTER)
        forget.set_margin_top(24)
        page.append(forget)
        self.device_page = (path, row)
        page.connect("destroy", lambda *_: setattr(self, "device_page", None))
        self.push(page, name)

    def forget(self, path, name):
        def go(ok):
            if ok:
                util.call(BLUEZ, self.adapter, ADAPTER, "RemoveDevice",
                          GLib.Variant("(o)", (path,)), lambda *_: self.refresh())
                self.pop()
        ui.confirm(self.win, f"Esquecer “{name}”?",
                   "Para usar o dispositivo de novo, será preciso pareá-lo outra vez.",
                   "Esquecer", go, destructive=True)

    # --- agent: codes and confirmations while pairing ------------------------------
    def _agent(self, method, args, invocation):
        dev = args[0] if args else None
        name = self._name(dev) if dev else ""
        if method == "RequestConfirmation":
            self._ask(invocation, lambda done: ui.confirm(
                self.win, f"Parear com “{name}”?",
                f"Confirme que o código {args[1]:06d} aparece em “{name}”.",
                "Parear", lambda ok: done(None, ok)))
        elif method == "RequestAuthorization":
            if dev == self.pairing:
                invocation.return_value(None)
            else:
                self._ask(invocation, lambda done: ui.confirm(
                    self.win, f"“{name}” quer parear com este computador",
                    "Só permita se foi você que iniciou o pareamento no dispositivo.",
                    "Permitir", lambda ok: done(None, ok)))
        elif method == "AuthorizeService":
            d = self.objs.get(dev, {}).get(DEVICE, {})
            if d.get("Paired") or d.get("Trusted") or dev == self.pairing:
                invocation.return_value(None)
            else:
                invocation.return_dbus_error(REJECTED, "Rejected")
        elif method == "RequestPinCode":
            self._ask(invocation, lambda done: ui.prompt(
                self.win, f"PIN de “{name}”",
                "Digite o PIN do dispositivo (muitas vezes é 0000; veja o manual dele).",
                lambda pin: done(GLib.Variant("(s)", (pin,)) if pin else None, bool(pin)),
                ok="Parear", initial="0000"))
        elif method == "RequestPasskey":
            def answer(text, done):
                ok = bool(text) and text.isdigit()
                done(GLib.Variant("(u)", (int(text),)) if ok else None, ok)
            self._ask(invocation, lambda done: ui.prompt(
                self.win, f"Código de “{name}”", "Digite o código mostrado no dispositivo.",
                lambda t: answer(t, done), ok="Parear"))
        elif method in ("DisplayPinCode", "DisplayPasskey"):
            code = args[1] if method == "DisplayPinCode" else f"{args[1]:06d}"
            if not self.info:
                self.info = ui.message(self.win, f"Pareando com “{name}”",
                                       f"Digite {code} no teclado de “{name}” e pressione Enter.")
                self.info.connect("destroy", lambda *_: setattr(self, "info", None))
            invocation.return_value(None)
        elif method == "Cancel":
            self._cancel()
            self._close_info()
            invocation.return_value(None)
        elif method == "Release":
            self.agent_ok = False
            invocation.return_value(None)

    def _ask(self, invocation, make_dialog):
        """Answer invocation from a dialog: done(reply variant or None, accepted)."""
        self._cancel()

        def done(reply, accepted):
            if self.pending and self.pending[0] is invocation:
                self.pending = None
                if accepted:
                    invocation.return_value(reply)
                else:
                    invocation.return_dbus_error(REJECTED, "Rejected")
        self.pending = (invocation, None)
        self.pending = (invocation, make_dialog(done))

    def _cancel(self):
        if self.pending:
            invocation, dialog = self.pending
            self.pending = None
            invocation.return_dbus_error(CANCELED, "Canceled")
            if dialog:
                dialog.destroy()

    def _close_info(self):
        if self.info:
            self.info.destroy()
