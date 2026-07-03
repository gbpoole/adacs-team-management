#!/bin/bash
# Create (or replace) a Nectar DNS A record using the OpenStack CLI.
#
# Usage:
#   bash scripts/setup-dns.sh --zone <zone> --ip <ip> [--domain <fqdn>]
#
# Arguments:
#   --zone    DNS zone (e.g. adacs-gpoole.cloud.edu.au.)  — trailing dot required
#   --ip      Instance public IP address
#   --domain  Hostname within the zone (e.g. myapp)
#             Defaults to the hostname part of DOMAIN_NAME in .env
#
# The OpenStack RC file must already be sourced in the current shell:
#   . ~/openrc.sh

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[setup-dns]${NC} $*"; }
warn() { echo -e "${YELLOW}[setup-dns]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

ZONE=""
IP=""
DOMAIN_HOST=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --zone)   ZONE="$2";        shift 2 ;;
        --ip)     IP="$2";          shift 2 ;;
        --domain) DOMAIN_HOST="$2"; shift 2 ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: bash scripts/setup-dns.sh --zone <zone> --ip <ip> [--domain <host>]"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$ZONE" ]] || [[ -z "$IP" ]]; then
    echo "Usage: bash scripts/setup-dns.sh --zone <zone.cloud.edu.au.> --ip <instance-ip> [--domain <hostname>]"
    echo
    echo "The zone must include a trailing dot, e.g.: adacs-gpoole.cloud.edu.au."
    echo "Run 'openstack zone list' to see your available zones."
    exit 1
fi

# If --domain not provided, infer from .env
if [[ -z "$DOMAIN_HOST" ]]; then
    if [[ -f "$REPO_DIR/.env" ]]; then
        FULL_DOMAIN=$(grep '^DOMAIN_NAME=' "$REPO_DIR/.env" | cut -d= -f2-)
        # Strip the zone suffix (without trailing dot) from the full domain
        ZONE_NO_DOT="${ZONE%.}"
        DOMAIN_HOST="${FULL_DOMAIN%.${ZONE_NO_DOT}}"
        info "Inferred hostname from .env: ${DOMAIN_HOST}"
    else
        echo "ERROR: --domain is required when .env does not exist."
        exit 1
    fi
fi

# Validate openstack CLI is available and credentials are sourced
if ! command -v openstack &>/dev/null; then
    echo "ERROR: openstack CLI not found. Run 'sudo bash scripts/vm-bootstrap.sh' first."
    exit 1
fi
if ! openstack zone list &>/dev/null; then
    echo "ERROR: Cannot connect to OpenStack API."
    echo "Have you sourced your OpenStack RC file?  . ~/openrc.sh"
    exit 1
fi

RECORD_FQDN="${DOMAIN_HOST}.${ZONE}"

info "Zone:   ${ZONE}"
info "Host:   ${DOMAIN_HOST}"
info "Record: ${RECORD_FQDN} → ${IP}"
echo

# Check for an existing record and offer to delete it
if openstack recordset show "$ZONE" "$RECORD_FQDN" &>/dev/null; then
    warn "An existing DNS record was found for ${RECORD_FQDN}."
    read -rp "Delete it and create a new one? [y/N] " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        info "Deleting existing record..."
        openstack recordset delete "$ZONE" "$RECORD_FQDN"
        info "Deleted."
    else
        info "Aborted. Existing DNS record unchanged."
        exit 0
    fi
fi

info "Creating A record: ${RECORD_FQDN} → ${IP}"
openstack recordset create "$ZONE" "$DOMAIN_HOST" \
    --type A --record "$IP"

info ""
info "DNS record created. Propagation may take a few minutes."
info "Verify with: host ${RECORD_FQDN}"
info ""
info "Next: sudo bash scripts/deploy.sh"
