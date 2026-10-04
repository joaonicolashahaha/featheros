#!/usr/bin/env bash
# Publish FeatherOS updates to the laptop over the home network.
#
#   ./build.sh packages     # build/sign what changed (repo/x86_64)
#   ./serve-updates.sh      # serve repo/ on port 8080 until Ctrl+C
#
# On the laptop: "Atualizar sistema" in the feather menu (or sudo pacman -Syu).
# The laptop finds this machine as <hostname>.local (mDNS) or by IP; see
# featheros-update-server on the laptop to change it.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
port=${PORT:-8080}
[[ -f repo/x86_64/featheros.db ]] || { echo "No repo yet: run ./build.sh packages first." >&2; exit 1; }
echo "Serving FeatherOS updates on port $port:"
echo "  http://$(hostname).local:$port/x86_64"
for ip in $(hostname -I 2>/dev/null || ip -4 -o addr show scope global | awk '{ sub(/\/.*/, "", $4); print $4 }'); do
    echo "  http://$ip:$port/x86_64"
done
echo "(If the laptop can't connect, allow TCP port $port in the firewall.)"
exec python3 -m http.server "$port" --bind 0.0.0.0 --directory repo
