#!/usr/bin/env bash
# StockPilot — one-time VPS preparation (Ubuntu 22.04 / 24.04).
#
# Installs Docker, Nginx and Certbot, and closes the firewall down to SSH + web.
# Run it ONCE on a fresh Cyber_Folks VPS, as a user with sudo rights:
#
#   sudo bash deploy/vps-setup.sh
#
# It is safe to re-run: every step checks whether the work is already done.
# It does NOT deploy the app — run deploy/deploy.sh for that.

set -euo pipefail

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo:  sudo bash deploy/vps-setup.sh" >&2
  exit 1
fi

# The unprivileged account that will own the checkout and run docker.
DEPLOY_USER="${SUDO_USER:-$(logname 2>/dev/null || echo root)}"

say "1/6 Updating the package index"
apt-get update -y

say "2/6 Installing Docker Engine + Compose plugin"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "Docker with the compose plugin is already installed — skipping."
else
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
  fi
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

say "3/6 Letting '$DEPLOY_USER' use docker without sudo"
if [[ "$DEPLOY_USER" != "root" ]]; then
  usermod -aG docker "$DEPLOY_USER"
  echo "Done. '$DEPLOY_USER' must log out and back in for this to take effect."
fi

say "4/6 Installing Nginx and Certbot (TLS certificates)"
apt-get install -y nginx certbot python3-certbot-nginx
systemctl enable --now nginx

say "5/6 Configuring the firewall (UFW): allow SSH, HTTP, HTTPS only"
apt-get install -y ufw
ufw allow OpenSSH
ufw allow 'Nginx Full'      # opens 80 and 443
ufw --force enable
ufw status verbose

say "6/6 Enabling unattended security updates"
apt-get install -y unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

cat <<'DONE'

──────────────────────────────────────────────────────────────────────────────
Server prepared. Next steps (see agent/DEPLOYMENT.md for the full walkthrough):

  1. Log out and back in   (so docker works without sudo)
  2. git clone <your repo> ~/stockpilot && cd ~/stockpilot
  3. cp .env.prod.example .env.prod && nano .env.prod    (set DOMAIN + password)
  4. bash deploy/deploy.sh
  5. Install the Nginx site + certificate:
       sudo cp deploy/nginx/stockpilot.conf /etc/nginx/sites-available/stockpilot
       sudo nano /etc/nginx/sites-available/stockpilot     (put in your domain)
       sudo ln -s /etc/nginx/sites-available/stockpilot /etc/nginx/sites-enabled/
       sudo rm -f /etc/nginx/sites-enabled/default
       sudo nginx -t && sudo systemctl reload nginx
       sudo certbot --nginx -d YOURDOMAIN.pl -d www.YOURDOMAIN.pl
──────────────────────────────────────────────────────────────────────────────
DONE
