#!/usr/bin/env bash
# BROKER-284. Runs ON the ddp-api host (the EC2 server with nginx for api.* and dev.*), as root:  sudo bash <this file> install|undo
# Installs or removes the staff Google sign-in rules for dev.digitaldemocracyproject.org. Read it before running it.
set -euo pipefail
MODE="${1:-install}"
SITE=/etc/nginx/sites-available/dev.digitaldemocracyproject.org
SNIPPET=/etc/nginx/snippets/ddp-broker-sign-in.conf
ZONE=/etc/nginx/conf.d/ddp-broker-sign-in-zone.conf
say() { printf '%s\n' "$*"; }
die() { printf 'STOPPED: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "this must run as root (use sudo)"
command -v nginx >/dev/null || die "nginx was not found on this machine"
[ -f "$SITE" ] || die "$SITE does not exist"
nginx -t >/dev/null 2>&1 || { nginx -t; die "nginx is already failing its own test BEFORE any change; nothing was touched"; }

if [ "$MODE" = undo ]; then
  sed -i "\#$SNIPPET#d" "$SITE"
  rm -f "$SNIPPET" "$ZONE"
  nginx -t || die "nginx rejected the config after removing the rules; restore a backup by hand ($SITE.before-284*)"
  systemctl reload nginx
  say "Removed. The sign-in rules are gone and nginx was reloaded. (Backups named $SITE.before-284* were left in place.)"
  exit 0
fi
[ "$MODE" = install ] || die "unknown mode '$MODE' (use install or undo)"

if grep -qF "$SNIPPET" "$SITE"; then
  say "Already installed (the include line is in $SITE). Nothing changed."
  nginx -t
  exit 0
fi
count=$(grep -cE '^[[:space:]]*listen[[:space:]]+443[[:space:]]+ssl' "$SITE" || true)
[ "$count" = 1 ] || die "expected exactly one 'listen 443 ssl' line in $SITE but found $count. Nothing was touched; use the manual steps in the runbook."
FULL_CONFIG="$(nginx -T 2>/dev/null || true)"
grep -qE 'include[[:space:]]+/etc/nginx/conf\.d/\*\.conf' <<<"$FULL_CONFIG" || die "this nginx does not include /etc/nginx/conf.d/*.conf, which the one-line limit needs. Nothing was touched; use the manual steps."

BACKUP="$SITE.before-284"
[ -e "$BACKUP" ] && BACKUP="$BACKUP.$(date +%Y%m%d%H%M%S)"
cp -p "$SITE" "$BACKUP"
say "Backup: $BACKUP"

mkdir -p /etc/nginx/snippets
cat > "$ZONE" <<'ZONE_EOF'
# BROKER-284: rate-limit zone for the staff sign-in paths (used by /etc/nginx/snippets/ddp-broker-sign-in.conf).
limit_req_zone $binary_remote_addr zone=broker_sign_in:10m rate=10r/s;
ZONE_EOF
cat > "$SNIPPET" <<'SNIPPET_EOF'
# BROKER-284: staff Google sign-in, sent straight to the broker over the VPN (VPN addresses only).
# Source: infra/front-door/dev-sign-in.conf in ddp-broker-py.
  # Start of a sign-in, the Google callback, who-is-signed-in, sign-out.
  location ^~ /_allauth/ {
    allow 10.0.0.0/24;
    deny all;

    limit_req zone=broker_sign_in burst=20 nodelay;
    limit_req_status 429;

    # The Mac Studio's broker nginx (443). Its certificate is self-signed for "localhost"; nginx does not
    # check an upstream certificate unless told to, and the hop is inside the VPN tunnel.
    proxy_pass https://10.0.0.8;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_redirect off;
    proxy_read_timeout 60s;
  }

  # The routes Google sends the browser back to: /accounts/google/login/callback/ (and the other providers').
  location ^~ /accounts/ {
    allow 10.0.0.0/24;
    deny all;

    limit_req zone=broker_sign_in burst=20 nodelay;
    limit_req_status 429;

    proxy_pass https://10.0.0.8;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_redirect off;
    proxy_read_timeout 60s;
  }
SNIPPET_EOF

sed -i "/^[[:space:]]*listen[[:space:]]\+443[[:space:]]\+ssl/a\\
  include $SNIPPET;" "$SITE"

if ! nginx -t 2>/tmp/ddp-front-door-nginx-test.txt; then
  cat /tmp/ddp-front-door-nginx-test.txt >&2
  cp -p "$BACKUP" "$SITE"
  rm -f "$SNIPPET" "$ZONE"
  die "nginx rejected the new rules. Everything was put back exactly as it was (see the message above). The website was not touched."
fi
systemctl reload nginx
say "Installed and nginx reloaded. To undo: run this script again with 'undo'."
