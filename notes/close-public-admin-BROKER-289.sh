#!/usr/bin/env bash
# BROKER-289. Runs ON the ddp-api host (the EC2 server with nginx for api.* and dev.*), as root:  sudo bash <this file> close|reopen
# Closes /admin and /static on the PUBLIC dev address (dev.digitaldemocracyproject.org): the three blocks that pass them to the
# website answer 404 instead. Staff use https://admin-dev.digitaldemocracyproject.org now (BROKER-285). Nothing else is touched.
# Read it before running it.
set -euo pipefail
MODE="${1:-close}"
SITE=/etc/nginx/sites-available/dev.digitaldemocracyproject.org
MARK="# BROKER-289: closed, staff use admin-dev"
say() { printf '%s\n' "$*"; }
die() { printf 'STOPPED: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "this must run as root (use sudo)"
command -v nginx >/dev/null || die "nginx was not found on this machine"
[ -f "$SITE" ] || die "$SITE does not exist"
nginx -t >/dev/null 2>&1 || { nginx -t; die "nginx is already failing its own test BEFORE any change; nothing was touched"; }

if [ "$MODE" = reopen ]; then
  # filter with grep, not sed: the marker text itself contains a '#'
  TMP="$(mktemp)"; { grep -vF -- "$MARK" "$SITE" || true; } > "$TMP"; cat "$TMP" > "$SITE"; rm -f "$TMP"
  nginx -t || die "nginx rejected the config after reopening; restore a backup by hand ($SITE.before-289*)"
  systemctl reload nginx
  say "Reopened: the three blocks pass /admin and /static to the website again, as before. (Backups named $SITE.before-289* were left in place.)"
  exit 0
fi
[ "$MODE" = close ] || die "unknown mode '$MODE' (use close or reopen)"

if grep -qF "$MARK" "$SITE"; then
  say "Already closed (the marker is in $SITE). Nothing changed."
  nginx -t
  exit 0
fi

# Each of the three blocks must be present exactly once, on a line of its own, or nothing is touched.
for loc in 'location = /admin {' 'location ^~ /admin/ {' 'location ^~ /static/ {'; do
  n=$(awk -v loc="$loc" '{t=$0; gsub(/^[ \t]+|[ \t]+$/,"",t)} t==loc{c++} END{print c+0}' "$SITE")
  [ "$n" = 1 ] || die "expected exactly one '$loc' line in $SITE but found $n. Nothing was touched."
done

BACKUP="$SITE.before-289"
[ -e "$BACKUP" ] && BACKUP="$BACKUP.$(date +%Y%m%d%H%M%S)"
cp -p "$SITE" "$BACKUP"
say "Backup: $BACKUP"

TMP="$(mktemp)"
awk -v mark="$MARK" '
  { print }
  { t=$0; gsub(/^[ \t]+|[ \t]+$/,"",t) }
  t=="location = /admin {" || t=="location ^~ /admin/ {" || t=="location ^~ /static/ {" { print "    return 404; " mark }
' "$SITE" > "$TMP"
cat "$TMP" > "$SITE"; rm -f "$TMP"

if ! nginx -t 2>/tmp/ddp-close-admin-nginx-test.txt; then
  cat /tmp/ddp-close-admin-nginx-test.txt >&2
  cp -p "$BACKUP" "$SITE"
  die "nginx rejected the change. The site file was put back exactly as it was (see the message above)."
fi
systemctl reload nginx
say "Closed and nginx reloaded: /admin and /static on the public dev address now answer 404. To undo: run this script again with 'reopen'."
