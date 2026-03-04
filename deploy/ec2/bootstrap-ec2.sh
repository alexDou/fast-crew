#!/usr/bin/env bash

set -euo pipefail

SWAP_SIZE_GB="${SWAP_SIZE_GB:-2}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/ec2/bootstrap-ec2.sh"
  exit 1
fi

echo "[1/7] Updating apt packages"
apt-get update -y
apt-get upgrade -y

if ! swapon --show | grep -q "/swapfile"; then
  echo "[2/7] Creating ${SWAP_SIZE_GB}G swapfile"
  fallocate -l "${SWAP_SIZE_GB}G" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q "^/swapfile" /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
else
  echo "[2/7] Swapfile already configured"
fi

echo "[3/7] Installing Docker"
apt-get install -y ca-certificates curl gnupg lsb-release
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

if ! getent group docker >/dev/null; then
  groupadd docker
fi

if [[ -n "${SUDO_USER:-}" ]]; then
  usermod -aG docker "$SUDO_USER"
fi

echo "[4/7] Installing Node.js 22"
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs

echo "[5/7] Installing Yarn via Corepack"
corepack enable
corepack prepare yarn@4.12.0 --activate

echo "[6/7] Installing PM2"
npm install -g pm2

echo "[7/7] Installing Nginx + Certbot"
apt-get install -y nginx certbot python3-certbot-nginx
systemctl enable --now nginx

echo "Bootstrap complete. Log out and back in before using Docker as non-root user."
