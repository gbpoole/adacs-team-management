#!/bin/bash
# Bootstrap a fresh Ubuntu 26.04 LTS VM for adacs-team-management.
# Must be run as root: sudo bash scripts/vm-bootstrap.sh
# Idempotent — safe to re-run.

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[bootstrap]${NC} $*"; }
warn() { echo -e "${YELLOW}[bootstrap]${NC} $*"; }

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root."
    echo "Usage: sudo bash scripts/vm-bootstrap.sh"
    exit 1
fi

# ---------------------------------------------------------------------------
# 1. System update
# ---------------------------------------------------------------------------
info "Updating system packages..."
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
    ca-certificates curl make git

# ---------------------------------------------------------------------------
# 2. Docker CE (official repository — not the ubuntu docker.io package)
# ---------------------------------------------------------------------------
if command -v docker &>/dev/null; then
    info "Docker already installed: $(docker --version)"
else
    info "Installing Docker CE..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu \
$(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -q
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    info "Docker installed: $(docker --version)"
fi

# ---------------------------------------------------------------------------
# 3. Add ubuntu to docker group (avoids needing sudo for docker commands)
# ---------------------------------------------------------------------------
if id -nG ubuntu 2>/dev/null | grep -qw docker; then
    info "ubuntu is already in the docker group."
else
    usermod -aG docker ubuntu
    warn "Added ubuntu to the docker group."
    warn "Log out and back in (or run 'newgrp docker') for this to take effect."
fi

# ---------------------------------------------------------------------------
# 4. Host-level Nginx (SSL terminator)
# ---------------------------------------------------------------------------
if command -v nginx &>/dev/null; then
    info "Nginx already installed."
else
    info "Installing Nginx..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q nginx
    systemctl enable nginx
    systemctl start nginx
    info "Nginx installed and started."
fi

# ---------------------------------------------------------------------------
# 5. Certbot via snap (works with any Python version, no venv needed)
# ---------------------------------------------------------------------------
if command -v certbot &>/dev/null; then
    info "Certbot already installed: $(certbot --version 2>&1 | head -1)"
else
    info "Installing Certbot via snap..."
    snap install --classic certbot
    ln -sf /snap/bin/certbot /usr/bin/certbot
    info "Certbot installed."
fi

# ---------------------------------------------------------------------------
# 6. OpenStack CLI (for DNS management)
# ---------------------------------------------------------------------------
if command -v openstack &>/dev/null; then
    info "OpenStack CLI already installed."
else
    info "Installing OpenStack CLI..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
        python3-openstackclient python3-designateclient
    info "OpenStack CLI installed."
fi

# ---------------------------------------------------------------------------
# 7. Firewall — allow only SSH, HTTP, and HTTPS
# ---------------------------------------------------------------------------
info "Configuring ufw..."
ufw allow OpenSSH
ufw allow 'Nginx Full'
# Explicitly block port 8000 so the Docker Nginx container is not reachable
# from the internet (only the host-level Nginx should reach it on 127.0.0.1).
ufw deny 8000/tcp 2>/dev/null || true
echo "y" | ufw enable
ufw status verbose

# ---------------------------------------------------------------------------
# 8. Automatic security upgrades
# ---------------------------------------------------------------------------
info "Enabling unattended security upgrades..."
DEBIAN_FRONTEND=noninteractive apt-get install -y -q unattended-upgrades
# Disable automatic reboots — reboot manually during a maintenance window.
sed -i 's|//Unattended-Upgrade::Automatic-Reboot "false"|Unattended-Upgrade::Automatic-Reboot "false"|' \
    /etc/apt/apt.conf.d/50unattended-upgrades 2>/dev/null || true
dpkg-reconfigure --priority=low --frontend=noninteractive unattended-upgrades

# ---------------------------------------------------------------------------
# 9. Backup directory
# ---------------------------------------------------------------------------
mkdir -p /var/backups/adacs
chmod 700 /var/backups/adacs
chown root:root /var/backups/adacs
info "Backup directory ready at /var/backups/adacs"

info ""
info "Bootstrap complete. Next steps:"
info "  1. bash scripts/configure.sh          — create production .env"
info "  2. bash scripts/setup-dns.sh ...      — register DNS record on Nectar"
info "  3. sudo bash scripts/deploy.sh        — build, start, configure TLS"
