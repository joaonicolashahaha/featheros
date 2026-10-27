"""Shared helpers: the FeatherOS settings file, commands, D-Bus."""
import os
import shlex
import subprocess
import threading

from gi.repository import Gio, GLib

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or f"{HOME}/.config",
                          "featheros")
DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME") or f"{HOME}/.local/share",
                        "featheros")
SETTINGS = os.path.join(CONFIG_DIR, "settings")
HELPER = "/usr/lib/featheros/settings-system"
INPUT_CONF = "/etc/X11/xorg.conf.d/40-featheros-input.conf"
COMMON = "/usr/lib/featheros/common.sh"
ENV_C = dict(os.environ, LC_ALL="C")

# The same defaults as /usr/lib/featheros/common.sh.
DEFAULTS = {
    "MODE": "light", "EFFECTS": "on", "WARMUP": "on", "WALLPAPER": "",
    "SCREEN_BLANK": "", "SUSPEND_AFTER": "0",
    "KB_REPEAT": "on", "KB_DELAY": "", "KB_RATE": "",
    "NIGHT_LIGHT": "off", "NIGHT_SCHEDULE": "times", "NIGHT_FROM": "20:00",
    "NIGHT_TO": "06:00", "NIGHT_TEMP": "4000",
    "SCREEN_LIMIT": "0", "BREAKS": "off", "BREAK_EVERY": "60", "EYE_BREAKS": "off",
}


# --- ~/.config/featheros/settings ---------------------------------------------
def settings():
    """The settings file as a dict, on top of the defaults."""
    values = dict(DEFAULTS)
    try:
        with open(SETTINGS) as f:
            for line in f:
                key, sep, value = line.strip().partition("=")
                if sep and key.isidentifier():
                    try:
                        words = shlex.split(value)
                    except ValueError:
                        continue
                    values[key] = words[0] if words else ""
    except OSError:
        pass
    return values


def setting(key):
    return settings()[key]


def save(**changes):
    """Set KEY=value lines, shell-quoted: common.sh sources the file."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(SETTINGS) as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    for key, value in changes.items():
        line = f"{key}={shlex.quote(str(value))}"
        for i, old in enumerate(lines):
            if old.split("=", 1)[0] == key:
                lines[i] = line
                break
        else:
            lines.append(line)
    with open(SETTINGS + ".new", "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(SETTINGS + ".new", SETTINGS)


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def input_saved():
    """Keyboard/mouse values in settings-system's Xorg file ("#@ KEY=VALUE")."""
    values = {}
    for line in read(INPUT_CONF).splitlines():
        if line.startswith("#@ ") and "=" in line:
            key, value = line[3:].split("=", 1)
            values[key] = value
    return values


# --- Commands ----------------------------------------------------------------
def output(*argv, timeout=5):
    """stdout of a quick command ("" if it fails)."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, env=ENV_C,
                              timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def run(argv, done=None):
    """Run a command in a thread; then done(ok, output) in the main loop."""
    def work():
        try:
            r = subprocess.run(argv, capture_output=True, text=True)
            ok, out = r.returncode == 0, (r.stdout + r.stderr).strip()
        except OSError as e:
            ok, out = False, str(e)
        if done:
            GLib.idle_add(done, ok, out)
    threading.Thread(target=work, daemon=True).start()


def system(*args, done=None):
    """The root helper, settings-system, through sudo without a password."""
    run(["sudo", "-n", HELPER, *args], done)


def shell(code, done=None):
    """Shell code with common.sh loaded, e.g. shell("featheros_wallpaper")."""
    run(["sh", "-c", f". {COMMON}; {code}"], done)


def launch(*argv):
    """Start a program and leave it running on its own."""
    try:
        subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def terminal(title, command):
    """Run a shell command in a terminal window that stays until Enter."""
    launch("featheros-terminal", "--title", title, "--geometry=90x24", "-x", "sh", "-c",
           f"{command}; echo; printf 'Pressione Enter para fechar. '; read _")


# --- D-Bus (system bus) -------------------------------------------------------
_bus = None


def bus():
    global _bus
    if _bus is None:
        _bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
    return _bus


def objects(name):
    """{path: {interface: {property: value}}} of a service ({} if it isn't there)."""
    try:
        v = bus().call_sync(name, "/", "org.freedesktop.DBus.ObjectManager",
                            "GetManagedObjects", None, None,
                            Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
        return v.unpack()[0]
    except GLib.Error:
        return {}


def call(name, path, iface, method, args=None, done=None, timeout=30000):
    """Asynchronous method call; done(result, error) where error is the D-Bus
    error name (None on success)."""
    def finish(conn, res):
        try:
            result, error = conn.call_finish(res).unpack(), None
        except GLib.Error as e:
            result, error = None, Gio.DBusError.get_remote_error(e) or e.message
        if done:
            done(result, error)
    bus().call(name, path, iface, method, args, None, Gio.DBusCallFlags.NONE,
               timeout, None, finish)


def set_property(name, path, iface, prop, value, done=None):
    call(name, path, "org.freedesktop.DBus.Properties", "Set",
         GLib.Variant("(ssv)", (iface, prop, value)), done)


def get_property(name, path, iface, prop, default=None):
    try:
        v = bus().call_sync(name, path, "org.freedesktop.DBus.Properties", "Get",
                            GLib.Variant("(ss)", (iface, prop)), None,
                            Gio.DBusCallFlags.NONE, 3000, None)
        return v.unpack()[0]
    except GLib.Error:
        return default


def watch(name, callback):
    """Call callback() (at most every 300 ms) when the service changes:
    objects added or removed, properties changed, the service (re)starting.
    Returns an id list for unwatch()."""
    pending = []

    def fire():
        pending.clear()
        callback()
        return False

    def changed(*_):
        if not pending:
            pending.append(GLib.timeout_add(300, fire))

    ids = [bus().signal_subscribe(name, iface, None, None, None,
                                  Gio.DBusSignalFlags.NONE, changed)
           for iface in ("org.freedesktop.DBus.Properties",
                         "org.freedesktop.DBus.ObjectManager")]
    owner = Gio.bus_watch_name_on_connection(bus(), name, Gio.BusNameWatcherFlags.NONE,
                                             changed, changed)
    return ids, owner


def unwatch(handle):
    ids, owner = handle
    for i in ids:
        bus().signal_unsubscribe(i)
    Gio.bus_unwatch_name(owner)


def export(path, xml, handler):
    """Export an object (the iwd or BlueZ agent); handler(method, args, invocation)."""
    info = Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0]

    def on_call(conn, sender, obj, iface, method, params, invocation):
        handler(method, params.unpack(), invocation)
    return bus().register_object(path, info, on_call, None, None)
