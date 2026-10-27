# Shared helpers for the featheros-* scripts (POSIX sh, sourced).

FEATHEROS_SETTINGS="${XDG_CONFIG_HOME:-$HOME/.config}/featheros/settings"
FEATHEROS_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/featheros"
FEATHEROS_SHARE=/usr/share/featheros

# Defaults, overridden by the user's settings file (KEY=value lines; most
# are set from Configurações, featheros-settings, which keeps the same
# defaults in /usr/lib/featheros/settings/util.py).
MODE=light      # light | dark
EFFECTS=on      # on | off  (picom compositor)
WARMUP=on       # on | off  (read the dock apps into RAM after login)
WALLPAPER=      # image file; empty: the FeatherOS wallpaper of the current mode
SCREEN_BLANK=   # minutes of inactivity before the screen blanks; 0: never;
                # empty: the X server's default (10)
SUSPEND_AFTER=0 # minutes of inactivity before suspending; 0: never
KB_REPEAT=on    # key repeat on | off; KB_DELAY (ms) and KB_RATE (keys/s),
KB_DELAY=       # empty: the X server's defaults
KB_RATE=
NIGHT_LIGHT=off       # Luz noturna: on | off
NIGHT_SCHEDULE=times  # times (from NIGHT_FROM to NIGHT_TO) | always
NIGHT_FROM=20:00
NIGHT_TO=06:00
NIGHT_TEMP=4000       # kelvin (6500: neutral)
SCREEN_LIMIT=0  # Bem-estar: daily screen time limit in minutes; 0: none
BREAKS=off      # reminder to move every BREAK_EVERY minutes of use
BREAK_EVERY=60
EYE_BREAKS=off  # reminder to look away every 20 minutes of use
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

featheros_wallpaper() {
    _w=$WALLPAPER
    [ -n "$_w" ] && [ -r "$_w" ] || _w="$FEATHEROS_SHARE/wallpapers/$MODE.jpg"
    hsetroot -cover "$_w" >/dev/null
}

# Resolution, refresh rate and orientation chosen in Configurações:
# ~/.config/featheros/displays has "OUTPUT xrandr-arguments" lines; only
# the monitors connected now are set.
featheros_displays() {
    _f="${XDG_CONFIG_HOME:-$HOME/.config}/featheros/displays"
    [ -r "$_f" ] || return 0
    _on=" $(xrandr --query | awk '$2 == "connected" { printf "%s ", $1 }')"
    _args=
    while read -r _o _rest; do
        case $_on in *" $_o "*) _args="$_args --output $_o $_rest" ;; esac
    done <"$_f"
    # shellcheck disable=SC2086  # one argument per word
    [ -z "$_args" ] || xrandr $_args
}

featheros_screen_blank() {
    case $SCREEN_BLANK in
        '') ;;
        0) xset s off -dpms ;;
        *) _s=$((SCREEN_BLANK * 60))
           xset s "$_s" "$_s" +dpms dpms "$_s" "$_s" "$_s" ;;
    esac
}

featheros_key_repeat() {
    if [ "$KB_REPEAT" = off ]; then
        xset r off
    elif [ -n "$KB_DELAY" ] && [ -n "$KB_RATE" ]; then
        xset r on r rate "$KB_DELAY" "$KB_RATE"
    fi
}

# Luz noturna: the colour temperature for now, for featheros-gamma.
featheros_night_temp() {
    if [ "$NIGHT_LIGHT" != on ]; then
        echo 6500
        return
    fi
    if [ "$NIGHT_SCHEDULE" = always ]; then
        echo "$NIGHT_TEMP"
        return
    fi
    # HHMM numbers ("test" reads 0600 as 600; $(( )) would read octal).
    _now=$(date +%H%M)
    _from=$(echo "$NIGHT_FROM" | tr -d :) _to=$(echo "$NIGHT_TO" | tr -d :)
    if [ "$_from" -le "$_to" ]; then       # e.g. 13:00-18:00
        [ "$_now" -ge "$_from" ] && [ "$_now" -lt "$_to" ]
    else                                   # over midnight, e.g. 20:00-06:00
        [ "$_now" -ge "$_from" ] || [ "$_now" -lt "$_to" ]
    fi && echo "$NIGHT_TEMP" || echo 6500
}

# First sound card with a "Master" control (the laptop's HDA, or the VM's).
featheros_card() {
    for _n in /proc/asound/card[0-9]*; do
        _n=${_n##*card}
        amixer -c "$_n" sget Master >/dev/null 2>&1 && { echo "$_n"; return; }
    done
}
