# Shared helpers for the featheros-* scripts (POSIX sh, sourced).

FEATHEROS_SETTINGS="${XDG_CONFIG_HOME:-$HOME/.config}/featheros/settings"
FEATHEROS_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/featheros"
FEATHEROS_SHARE=/usr/share/featheros

# Defaults, overridden by the user's settings file (KEY=value lines).
MODE=light      # light | dark
EFFECTS=on      # on | off  (picom compositor)
WARMUP=on       # on | off  (read the dock apps into RAM after login)
[ -r "$FEATHEROS_SETTINGS" ] && . "$FEATHEROS_SETTINGS"

featheros_set() {  # featheros_set KEY VALUE
    mkdir -p "$(dirname "$FEATHEROS_SETTINGS")"
    touch "$FEATHEROS_SETTINGS"
    if grep -q "^$1=" "$FEATHEROS_SETTINGS"; then
        sed -i "s|^$1=.*|$1=$2|" "$FEATHEROS_SETTINGS"
    else
        echo "$1=$2" >>"$FEATHEROS_SETTINGS"
    fi
}

# Path of a symbolic icon matching the current mode (cached: the icon trees
# have ~100k files, too many to search on every panel refresh).
featheros_icon() {
    _c="$FEATHEROS_CACHE/icons-$MODE"
    if [ ! -e "$_c/$1" ] || [ ! -e "$(cat "$_c/$1")" ]; then
        mkdir -p "$_c"
        # Light bar: WhiteSur's */symbolic/ icons are dark glyphs (its status/22
        # ones are white, for dark panels); WhiteSur-light fills the gaps.
        if [ "$MODE" = dark ]; then
            _p=$(find /usr/share/icons/WhiteSur-dark -name "$1.svg" -print -quit 2>/dev/null)
        else
            _p=$(find /usr/share/icons/WhiteSur -path '*/symbolic/*' -name "$1.svg" -print -quit 2>/dev/null)
            [ -n "$_p" ] || _p=$(find /usr/share/icons/WhiteSur-light -name "$1.svg" -print -quit 2>/dev/null)
        fi
        printf '%s' "$_p" >"$_c/$1"
    fi
    cat "$_c/$1"
}

# xsettingsd config for the current mode. xsettingsd (~1 MB) lets running
# GTK apps follow light/dark switches live.
featheros_xsettings() {
    if [ "$MODE" = dark ]; then _g=WhiteSur-Dark-solid _i=WhiteSur-dark
    else _g=WhiteSur-Light-solid _i=WhiteSur-light; fi
    mkdir -p "$FEATHEROS_CACHE"
    cat >"$FEATHEROS_CACHE/xsettingsd.conf" <<EOF
Net/ThemeName "$_g"
Net/IconThemeName "$_i"
Net/EnableEventSounds 0
Gtk/CursorThemeName "WhiteSur-cursors"
Gtk/CursorThemeSize 24
Gtk/FontName "Inter 10"
Gtk/DecorationLayout "close,minimize,maximize:"
Gtk/EnableAnimations 0
Xft/Antialias 1
Xft/Hinting 1
Xft/HintStyle "hintslight"
Xft/RGBA "none"
EOF
}

# First sound card with a "Master" control (the laptop's HDA, or the VM's).
featheros_card() {
    for _n in /proc/asound/card[0-9]*; do
        _n=${_n##*card}
        amixer -c "$_n" sget Master >/dev/null 2>&1 && { echo "$_n"; return; }
    done
}
