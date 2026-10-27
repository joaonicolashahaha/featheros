"""Contas online, through Firefox: FeatherOS has no account daemon (GNOME
Online Accounts would cost RAM and mostly serve apps it doesn't ship), so
accounts live in Firefox. This panel reads the Firefox profile, read-only and
locally, to show where you are signed in, and opens Firefox to sign in, manage
or sign out, and to go straight to each service."""
import configparser
import json
import os
import shutil
import sqlite3
import tempfile

from gi.repository import Gtk

import ui
import util

PROVIDERS = [
    {"name": "Google", "icon": "goa-account-google",
     "about": "Gmail, Agenda, Drive, Fotos e YouTube",
     "cookies": [("google.com", "SID"), ("google.com", "__Secure-1PSID")],
     "login": "https://accounts.google.com/", "manage": "https://myaccount.google.com/",
     "logout": "https://accounts.google.com/Logout",
     "services": [("Gmail", "https://mail.google.com/"),
                  ("Agenda", "https://calendar.google.com/"),
                  ("Drive", "https://drive.google.com/"),
                  ("Fotos", "https://photos.google.com/"),
                  ("YouTube", "https://www.youtube.com/")]},
    {"name": "Microsoft", "icon": "goa-account-microsoft",
     "about": "Outlook, OneDrive e Office na web",
     "cookies": [("login.live.com", "MSPAuth"),
                 ("login.microsoftonline.com", "ESTSAUTHPERSISTENT")],
     "login": "https://login.live.com/", "manage": "https://account.microsoft.com/",
     "logout": "https://login.live.com/logout.srf",
     "services": [("Outlook", "https://outlook.live.com/mail/"),
                  ("OneDrive", "https://onedrive.live.com/"),
                  ("Office", "https://www.office.com/")]},
    {"name": "GitHub", "icon": "goa-account", "about": "Repositórios e notificações",
     "cookies": [("github.com", "logged_in")], "user_cookie": ("github.com", "dotcom_user"),
     "login": "https://github.com/login", "manage": "https://github.com/settings/profile",
     "logout": "https://github.com/logout",
     "services": [("Repositórios", "https://github.com/"),
                  ("Notificações", "https://github.com/notifications")]},
]
MOZILLA = {"name": "Conta Mozilla", "icon": "firefox",
           "about": "Sincroniza favoritos, senhas e abas com o Firefox de outros aparelhos",
           "login": "about:preferences#sync", "manage": "about:preferences#sync",
           "logout": "about:preferences#sync", "services": []}


def firefox_profile():
    """Directory of the profile Firefox uses (None before its first start)."""
    for base in (os.path.expanduser("~/.config/mozilla/firefox"),
                 os.path.expanduser("~/.mozilla/firefox")):
        ini = configparser.ConfigParser(interpolation=None)
        if not ini.read(os.path.join(base, "profiles.ini")):
            continue
        sections = ini.sections()
        path = next((ini[s]["Default"] for s in sections
                     if s.startswith("Install") and "Default" in ini[s]), None)
        if not path:
            profiles = [ini[s] for s in sections if s.startswith("Profile")]
            chosen = next((p for p in profiles if p.get("Default") == "1"),
                          profiles[0] if profiles else None)
            if chosen is None:
                continue
            path = chosen.get("Path", "")
            if chosen.get("IsRelative", "1") == "0":
                return path
        return os.path.join(base, path)
    return None


def cookies(profile):
    """[(host, name, value)] for the providers' sites. Copied first: Firefox
    keeps the database locked while it runs."""
    found = []
    with tempfile.TemporaryDirectory() as tmp:
        try:
            for suffix in ("", "-wal"):
                src = os.path.join(profile, "cookies.sqlite" + suffix)
                if os.path.exists(src):
                    shutil.copy(src, os.path.join(tmp, "cookies.sqlite" + suffix))
            db = sqlite3.connect(os.path.join(tmp, "cookies.sqlite"))
            found = db.execute(
                "SELECT host, name, value FROM moz_cookies WHERE host LIKE '%google.com' "
                "OR host LIKE '%live.com' OR host LIKE '%microsoftonline.com' "
                "OR host LIKE '%github.com'").fetchall()
            db.close()
        except (OSError, sqlite3.Error):
            pass
    return found


def mozilla_account(profile):
    try:
        with open(os.path.join(profile, "signedInUser.json")) as f:
            return json.load(f).get("accountData", {}).get("email")
    except (OSError, ValueError, AttributeError):
        return None


def firefox(url):
    util.launch("firefox", url)


class Panel(ui.Panel):
    title = "Contas online"

    def build(self):
        page = ui.Page()
        page.append(ui.label(
            "Suas contas ficam no Firefox: entre uma vez e o Gmail, o Outlook, o Drive e "
            "os outros serviços já abrem conectados. Esta tela só confere o perfil do "
            "Firefox neste computador; nada é enviado.", "dim-label", wrap=True,
            margin_top=12))
        self.group = page.group("Contas")
        self.win.connect("notify::is-active", self._focus)
        self.visible = False
        self.refresh()
        return page

    def shown(self):
        self.visible = True
        self.refresh()

    def hidden(self):
        self.visible = False

    def _focus(self, win, _pspec):
        # Back from signing in in Firefox: show the new state.
        if self.visible and win.is_active() and len(self.pages) == 1:
            self.refresh()

    def refresh(self):
        profile = firefox_profile()
        jar = cookies(profile) if profile else []
        self.group.clear()
        if not profile:
            self.group.append(ui.Row("O Firefox ainda não foi aberto",
                                     "Abra o Firefox uma vez para começar.", "firefox",
                                     icon_size=32,
                                     suffix=[ui.button("Abrir o Firefox",
                                                       on_click=lambda: firefox("about:home"))]))
            return
        email = mozilla_account(profile)
        self._row(MOZILLA, bool(email), email)
        for p in PROVIDERS:
            signed_in = any(h.endswith(site) and n == name
                            and (name != "logged_in" or v == "yes")
                            for h, n, v in jar for site, name in p["cookies"])
            user = None
            if signed_in and "user_cookie" in p:
                site, name = p["user_cookie"]
                user = next((v for h, n, v in jar if h.endswith(site) and n == name), None)
            self._row(p, signed_in, user)

    def _row(self, p, signed_in, user):
        if signed_in:
            sub = f"Conectada: {user}" if user else "Conectada no Firefox"
            self.group.append(ui.Row(p["name"], sub, p["icon"], icon_size=32,
                                     on_activate=lambda: self.show(p, sub), arrow=True))
        else:
            self.group.append(ui.Row(p["name"], p["about"], p["icon"], icon_size=32,
                                     suffix=[ui.button("Entrar",
                                                       on_click=lambda: firefox(p["login"]))]))

    def show(self, p, status):
        page = ui.Page()
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=18)
        head.pack_start(ui.icon(p["icon"], 80), False, False, 0)
        head.pack_start(ui.label(f"<big><b>{ui.esc(p['name'])}</b></big>", markup=True,
                                 xalign=0.5), False, False, 0)
        head.pack_start(ui.label(status, "dim-label", xalign=0.5), False, False, 0)
        page.append(head)
        if p["services"]:
            services = page.group("Abrir no Firefox")
            for name, url in p["services"]:
                services.append(ui.Row(name, on_activate=lambda u=url: firefox(u),
                                       suffix=[ui.style(ui.icon("adw-external-link-symbolic"),
                                                        "dim-label")]))
        account = page.group("Conta")
        account.append(ui.Row("Gerenciar a conta", on_activate=lambda: firefox(p["manage"]),
                              suffix=[ui.style(ui.icon("adw-external-link-symbolic"),
                                               "dim-label")]))
        account.append(ui.Row("Sair desta conta", "Abre a página de saída no Firefox",
                              on_activate=lambda: firefox(p["logout"])))
        self.push(page, p["name"])
