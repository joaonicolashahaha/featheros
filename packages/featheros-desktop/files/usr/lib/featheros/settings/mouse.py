"""Mouse e touchpad: libinput settings. Applied at once with xinput, and kept
in /etc/X11/xorg.conf.d/40-featheros-input.conf (through settings-system),
so they hold at every login and for devices plugged in later."""
import ui
import util

DEFAULTS = {"LEFT_HANDED": "off", "MOUSE_SPEED": "0", "MOUSE_ACCEL": "on",
            "MOUSE_NATURAL": "off", "TP_ENABLED": "on", "TP_SPEED": "0",
            "TP_NATURAL": "off", "TP_TAP": "on", "TP_DWT": "on",
            "TP_SCROLL": "twofinger", "TP_CLICK": "buttonareas"}

CHOICES = {"TP_SCROLL": ("twofinger", "edge"), "TP_CLICK": ("buttonareas", "clickfinger")}
# KEY -> (device kinds, libinput property, value -> property values)
ON = {"on": ["1"], "off": ["0"]}
PROPS = {
    "LEFT_HANDED": ("mouse touchpad", "libinput Left Handed Enabled", ON.get),
    "MOUSE_SPEED": ("mouse", "libinput Accel Speed", lambda v: [v]),
    "MOUSE_ACCEL": ("mouse", "libinput Accel Profile Enabled",
                    lambda v: ["1", "0"] if v == "on" else ["0", "1"]),
    "MOUSE_NATURAL": ("mouse", "libinput Natural Scrolling Enabled", ON.get),
    "TP_ENABLED": ("touchpad", "libinput Send Events Mode Enabled",
                   lambda v: ["0", "0"] if v == "on" else ["1", "0"]),
    "TP_SPEED": ("touchpad", "libinput Accel Speed", lambda v: [v]),
    "TP_NATURAL": ("touchpad", "libinput Natural Scrolling Enabled", ON.get),
    "TP_TAP": ("touchpad", "libinput Tapping Enabled", ON.get),
    "TP_DWT": ("touchpad", "libinput Disable While Typing Enabled", ON.get),
    "TP_SCROLL": ("touchpad", "libinput Scroll Method Enabled",
                  lambda v: ["1", "0", "0"] if v == "twofinger" else ["0", "1", "0"]),
    "TP_CLICK": ("touchpad", "libinput Click Method Enabled",
                 lambda v: ["1", "0"] if v == "buttonareas" else ["0", "1"]),
}


def devices():
    """libinput mice and touchpads: [(id, kind, {property: [values]})]."""
    found = []
    ids = util.output("xinput", "list", "--id-only").split()
    names = util.output("xinput", "list", "--name-only").splitlines()
    for id_, name in zip(ids, names):
        if "XTEST" in name:
            continue
        props = {}
        for line in util.output("xinput", "list-props", id_).splitlines():
            head, sep, values = line.strip().rpartition(":")
            if sep and head.endswith(")"):
                props[head.rsplit(" (", 1)[0]] = [v.strip() for v in values.split(",")]
        if "libinput Tapping Enabled" in props:
            found.append((id_, "touchpad", props))
        elif "libinput Accel Speed" in props:
            found.append((id_, "mouse", props))
    return found


def live(devs):
    """Current values, read from the first mouse and touchpad."""
    values = {}
    for key, (kinds, prop, convert) in PROPS.items():
        props = next((p for _id, kind, p in devs if kind in kinds.split() and prop in p),
                     None)
        if props is None:
            continue
        current = props[prop]
        if key.endswith("SPEED"):
            values[key] = f"{float(current[0]):.2f}"
            continue
        for choice in CHOICES.get(key, ("on", "off")):
            want = convert(choice)
            if want == current[:len(want)]:
                values[key] = choice
                break
    return values


class Panel(ui.Panel):
    title = "Mouse e touchpad"

    def build(self):
        self.devs = devices()
        self.values = {**DEFAULTS, **live(self.devs), **util.input_saved()}
        v = self.values
        kinds = {kind for _id, kind, _p in self.devs}
        page = ui.Page()

        general = page.group("Geral")
        general.append(ui.Row("Botão principal", "Ordem dos botões em mouses e touchpads",
                              suffix=[ui.toggle_group([("off", "Esquerdo"), ("on", "Direito")],
                                                      v["LEFT_HANDED"],
                                                      lambda x: self.set("LEFT_HANDED", x))]))

        mouse = page.group("Mouse", None if "mouse" in kinds else
                           "Nenhum mouse conectado agora; as escolhas valem quando "
                           "um for conectado.")
        mouse.append(ui.ScaleRow("Velocidade do ponteiro", -1, 1, float(v["MOUSE_SPEED"]),
                                 lambda x: self.set("MOUSE_SPEED", f"{x:.2f}"), step=0.05,
                                 marks=[(-1, "Lenta"), (1, "Rápida")]))
        mouse.append(ui.SwitchRow("Aceleração do mouse",
                                  "Recomendada para a maioria das pessoas e aplicativos",
                                  v["MOUSE_ACCEL"] == "on",
                                  lambda on: self.set("MOUSE_ACCEL", "on" if on else "off")))
        scroll = page.group("Direção da rolagem do mouse")
        ui.radio_rows(scroll, [("off", "Tradicional", "A rolagem move a visualização", None),
                               ("on", "Natural", "A rolagem move o conteúdo", None)],
                      v["MOUSE_NATURAL"], lambda x: self.set("MOUSE_NATURAL", x))

        if "touchpad" in kinds:
            tp = page.group("Touchpad")
            tp.append(ui.SwitchRow("Touchpad", None, v["TP_ENABLED"] == "on",
                                   lambda on: self.set("TP_ENABLED", "on" if on else "off")))
            tp.append(ui.ScaleRow("Velocidade do ponteiro", -1, 1, float(v["TP_SPEED"]),
                                  lambda x: self.set("TP_SPEED", f"{x:.2f}"), step=0.05,
                                  marks=[(-1, "Lenta"), (1, "Rápida")]))
            tp.append(ui.SwitchRow("Tocar para clicar", "Um toque leve conta como clique",
                                   v["TP_TAP"] == "on",
                                   lambda on: self.set("TP_TAP", "on" if on else "off")))
            tp.append(ui.SwitchRow("Desativar ao digitar",
                                   "Evita mover o ponteiro sem querer enquanto digita",
                                   v["TP_DWT"] == "on",
                                   lambda on: self.set("TP_DWT", "on" if on else "off")))
            tp.append(ui.SwitchRow("Rolagem natural", "O conteúdo acompanha os dedos",
                                   v["TP_NATURAL"] == "on",
                                   lambda on: self.set("TP_NATURAL", "on" if on else "off")))
            how = page.group("Rolagem no touchpad")
            ui.radio_rows(how, [("twofinger", "Com dois dedos",
                                 "Deslize dois dedos em qualquer lugar", None),
                                ("edge", "Pela borda", "Deslize um dedo na borda direita",
                                 None)],
                          v["TP_SCROLL"], lambda x: self.set("TP_SCROLL", x))
            click = page.group("Clique secundário")
            ui.radio_rows(click, [("clickfinger", "Dois dedos",
                                   "Clique com dois dedos em qualquer lugar", None),
                                  ("buttonareas", "Canto",
                                   "Clique no canto inferior direito", None)],
                          v["TP_CLICK"], lambda x: self.set("TP_CLICK", x))
        return page

    def set(self, key, value):
        self.values[key] = value
        kinds, prop, convert = PROPS[key]
        for id_, kind, props in self.devs:
            if kind in kinds.split() and prop in props:
                values = convert(value)
                if prop == "libinput Accel Profile Enabled":
                    values += ["0"] * (len(props[prop]) - len(values))  # + "custom"
                util.run(["xinput", "set-prop", id_, prop, *values])
        util.system("input", f"{key}={value}", done=self._saved)

    def _saved(self, ok, out):
        if not ok:
            ui.message(self.win, "A mudança vale só até sair da sessão",
                       f"Não foi possível salvá-la: {out}")
