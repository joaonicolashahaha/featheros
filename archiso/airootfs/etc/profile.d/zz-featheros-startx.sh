# "zz-": runs after locale.sh, so the desktop gets LANG (pt_BR).
# Start the FeatherOS desktop after logging in on tty1 (no display manager).
# Not exec'd: if X fails or the session ends, you get a shell instead of a
# login loop.
if [ -z "$DISPLAY" ] && [ "$XDG_VTNR" = 1 ] && [ "$(id -u)" -ne 0 ] &&
   [ ! -e "$HOME/.config/featheros/no-desktop" ]; then
    startx
    echo "Sessão gráfica encerrada. Digite 'startx' para voltar ou 'exit' para sair."
fi
