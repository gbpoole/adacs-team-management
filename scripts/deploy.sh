#!/bin/bash
# Initial deployment: build Docker images, start services, configure host Nginx,
# obtain a TLS certificate, and install the backup cron job.
#
# Must be run as root: sudo bash scripts/deploy.sh
#
# Idempotent — each step is guarded so re-running skips already-completed work.
# The Nginx site config and TLS certificate are only configured once.

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NGINX_SITE=/etc/nginx/sites-available/adacs-team-management
BACKUP_WRAPPER=/usr/local/bin/backup-adacs-db.sh

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root."
    echo "Usage: sudo bash scripts/deploy.sh"
    exit 1
fi

cd "$REPO_DIR"

# ---------------------------------------------------------------------------
# 1. Validate .env
# ---------------------------------------------------------------------------
if [[ ! -f .env ]]; then
    echo "ERROR: .env not found. Run 'bash scripts/configure.sh' first."
    exit 1
fi

if grep -q '__CHANGEME__' .env; then
    warn "WARNING: .env contains __CHANGEME__ placeholders."
    warn "Edit .env and re-run this script."
    exit 1
fi

DOMAIN_NAME=$(grep '^DOMAIN_NAME=' .env | cut -d= -f2-)
if [[ -z "$DOMAIN_NAME" ]]; then
    echo "ERROR: DOMAIN_NAME is not set in .env."
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Build Docker images
# ---------------------------------------------------------------------------
info "Building Docker images..."
docker compose build

# ---------------------------------------------------------------------------
# 3. Start all services
# ---------------------------------------------------------------------------
info "Starting services..."
docker compose up -d

# ---------------------------------------------------------------------------
# 4. Wait for the application to become healthy
# ---------------------------------------------------------------------------
info "Waiting for application health check (up to 3 minutes)..."
MAX_ATTEMPTS=36
ATTEMPT=0
while [[ $ATTEMPT -lt $MAX_ATTEMPTS ]]; do
    if curl -fsS http://localhost:8000/health/ &>/dev/null; then
        info "Application is healthy."
        break
    fi
    sleep 5
    ATTEMPT=$((ATTEMPT + 1))
    printf '.'
done
echo

if [[ $ATTEMPT -ge $MAX_ATTEMPTS ]]; then
    warn "Health check timed out. The application may still be starting."
    warn "Check logs with: docker compose logs -f"
fi

# ---------------------------------------------------------------------------
# 5. Configure host-level Nginx (skip if already configured)
# ---------------------------------------------------------------------------
if [[ -f "$NGINX_SITE" ]]; then
    info "Host Nginx site config already exists — skipping."
else
    info "Writing host Nginx site config for ${DOMAIN_NAME}..."
    cat > "$NGINX_SITE" << NGINX_EOF
server {
    listen 80;
    server_name ${DOMAIN_NAME};

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_http_version 1.1;
    }
}
NGINX_EOF

    # Enable site, remove default placeholder
    ln -sf "$NGINX_SITE" /etc/nginx/sites-enabled/adacs-team-management
    if [[ -L /etc/nginx/sites-enabled/default ]]; then
        rm /etc/nginx/sites-enabled/default
        info "Removed Nginx default site."
    fi

    nginx -t
    systemctl reload nginx
    info "Host Nginx configured for ${DOMAIN_NAME}."
fi

# ---------------------------------------------------------------------------
# 6. Obtain TLS certificate via Certbot (skip if cert already exists)
# ---------------------------------------------------------------------------
if certbot certificates 2>/dev/null | grep -q "Domains: .*${DOMAIN_NAME}"; then
    info "TLS certificate for ${DOMAIN_NAME} already exists — skipping Certbot."
else
    # Read admin email from .env (set by configure.sh)
    ADMIN_EMAIL=$(grep '^ADMIN_EMAIL=' .env 2>/dev/null | cut -d= -f2- || true)
    if [[ -z "$ADMIN_EMAIL" ]]; then
        warn "ADMIN_EMAIL not found in .env."
        read -rp "Email address for Let's Encrypt registration: " ADMIN_EMAIL
        [[ -n "$ADMIN_EMAIL" ]] || { echo "ERROR: email is required for Certbot."; exit 1; }
    fi

    info "Obtaining TLS certificate from Let's Encrypt..."
    certbot --nginx -d "$DOMAIN_NAME" \
        --non-interactive --agree-tos -m "$ADMIN_EMAIL"
    systemctl reload nginx
    info "TLS certificate obtained and Nginx reloaded."
fi

# ---------------------------------------------------------------------------
# 7. Certbot auto-renewal timer (skip if already configured)
# ---------------------------------------------------------------------------
CERTBOT_SERVICE=/etc/systemd/system/certbot-renew.service
CERTBOT_TIMER=/etc/systemd/system/certbot-renew.timer

if systemctl is-enabled certbot-renew.timer &>/dev/null; then
    info "Certbot renewal timer already active — skipping."
else
    info "Installing Certbot renewal timer..."
    cat > "$CERTBOT_SERVICE" << 'SVC_EOF'
[Unit]
Description=Let's Encrypt certificate renewal

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --quiet --agree-tos
ExecStartPost=/bin/systemctl reload nginx.service
SVC_EOF

    cat > "$CERTBOT_TIMER" << 'TMR_EOF'
[Unit]
Description=Twice-daily renewal of Let's Encrypt certificates

[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
TMR_EOF

    systemctl daemon-reload
    systemctl enable --now certbot-renew.timer
    info "Certbot renewal timer enabled."
fi

# ---------------------------------------------------------------------------
# 8. Install database backup (skip if already installed)
# ---------------------------------------------------------------------------
if [[ -f "$BACKUP_WRAPPER" ]]; then
    info "Backup wrapper already installed — skipping."
else
    info "Installing database backup..."
    cat > "$BACKUP_WRAPPER" << WRAPPER_EOF
#!/bin/bash
# Wrapper installed by scripts/deploy.sh — calls the repo backup script.
APP_DIR="${REPO_DIR}"
export APP_DIR
exec "\${APP_DIR}/scripts/backup-db.sh" "\$@"
WRAPPER_EOF
    chmod 700 "$BACKUP_WRAPPER"

    # Add cron job to root's crontab (avoid duplicates)
    if ! crontab -l 2>/dev/null | grep -q 'backup-adacs-db'; then
        ( crontab -l 2>/dev/null || true
          echo "0 2 * * * ${BACKUP_WRAPPER} >> /var/log/adacs-backup.log 2>&1"
        ) | crontab -
        info "Backup cron job installed (daily at 02:00 UTC)."
    fi
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
info ""
info "Deployment complete."
info "  Application: https://${DOMAIN_NAME}"
info "  Status:      docker compose ps"
info "  Logs:        docker compose logs -f"
info ""
info "To update after a code change: bash scripts/update.sh"
