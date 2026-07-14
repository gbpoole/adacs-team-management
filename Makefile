.PHONY: help bootstrap configure dns deploy update backup logs status shell createsuperuser check-users set-role verify-user check-mail-queue

SCRIPTS := scripts

# DNS target requires ZONE and IP to be passed on the command line:
#   make dns ZONE=adacs-gpoole.cloud.edu.au. IP=203.0.113.42
ZONE ?=
IP   ?=

# check-users takes an optional EMAIL to inspect a single account; verify-user
# requires EMAIL to mark that account's email verified:
#   make check-users EMAIL=someone@example.com
#   make verify-user EMAIL=someone@example.com
EMAIL ?=

# set-role target requires EMAIL and ROLE:
#   make set-role EMAIL=someone@example.com ROLE=pm
ROLE ?=

help:
	@echo ""
	@echo "adacs-team-management — deployment helpers"
	@echo ""
	@echo "FIRST-TIME DEPLOYMENT (run these in order)"
	@echo "  1. On the Nectar dashboard, create an Ubuntu 26.04 LTS instance:"
	@echo "     Flavor:          m3.small (2 vCPU, 4 GB RAM, 30 GB disk)"
	@echo "     Security groups: default, ssh, http, https"
	@echo "                      (these together open ports 22, 80, and 443)"
	@echo "     Key pair:        your SSH public key"
	@echo "     Allocate a floating IP and attach it to the instance."
	@echo "  2. Copy your OpenStack credentials to the VM (run this locally):"
	@echo "     scp -i ~/.ssh/adacs_nectar ~/openrc.sh ubuntu@<IP>:~/openrc.sh"
	@echo "  3. SSH into the VM with agent forwarding:  ssh -A ubuntu@<IP>"
	@echo "     Install make (not present by default):  sudo apt install -y make"
	@echo "     Clone the repo:                         git clone git@github.com:gbpoole/adacs-team-management.git"
	@echo "     Enter the repo:                         cd adacs-team-management"
	@echo "  4. make bootstrap     Install Docker, Nginx, Certbot, ufw (sudo)"
	@echo "     Then log out and back in so docker group membership takes effect."
	@echo "  5. Source OpenStack credentials:  . ~/openrc.sh"
	@echo "     Create the Swift backup container:  openstack container create <SWIFT_BACKUP_CONTAINER>"
	@echo "     (If the container already exists this is safe to re-run — it is idempotent.)"
	@echo "  6. make configure     Create .env with auto-generated secrets (interactive)"
	@echo "  7. make dns ZONE=<project>.cloud.edu.au. IP=<instance-ip>"
	@echo "     Wait a few minutes for DNS to propagate, then verify: host <DOMAIN_NAME>"
	@echo "  8. make deploy        Build images, start services, configure Nginx & TLS (sudo)"
	@echo "     Visit https://<DOMAIN_NAME> to confirm the app is live."
	@echo "  9. make createsuperuser   Create the initial admin account (bypasses email verification)"
	@echo ""
	@echo "ONGOING OPERATIONS"
	@echo "  make update           Pull latest code and rebuild/restart changed services"
	@echo "  make createsuperuser  Create a new admin account (bypasses email verification)"
	@echo "  make check-users      List users + email-verification status (EMAIL=<addr> for one)"
	@echo "  make set-role         Set a user's role: EMAIL=<addr> ROLE=<pm|user>"
	@echo "  make verify-user      Manually verify a user's email (bypass link): EMAIL=<addr>"
	@echo "  make check-mail-queue Show outbound mail queue depth + recent send failures"
	@echo "  make backup           Run a one-off database backup (sudo)"
	@echo "  make logs             Follow all service logs"
	@echo "  make status           Show service health/status"
	@echo "  make shell            Open a bash shell inside the Django container"
	@echo ""
	@echo "See ~/DEPLOYMENT.md for full documentation including restore procedures,"
	@echo "offsite backups, and optional GitHub Actions CD."
	@echo ""

bootstrap:
	sudo bash $(SCRIPTS)/vm-bootstrap.sh

configure:
	bash $(SCRIPTS)/configure.sh

dns:
	@if [ -z "$(ZONE)" ] || [ -z "$(IP)" ]; then \
		echo "Usage: make dns ZONE=<zone.cloud.edu.au.> IP=<instance-ip>"; \
		exit 1; \
	fi
	bash $(SCRIPTS)/setup-dns.sh --zone "$(ZONE)" --ip "$(IP)"

deploy:
	sudo bash $(SCRIPTS)/deploy.sh

update:
	bash $(SCRIPTS)/update.sh

backup:
	sudo bash $(SCRIPTS)/backup-db.sh

logs:
	docker compose logs -f

status:
	docker compose ps

shell:
	docker compose exec django bash

createsuperuser:
	docker compose exec django poetry run python manage.py createsuperuser

check-users:
	bash $(SCRIPTS)/check_users.sh $(EMAIL)

set-role:
	@if [ -z "$(EMAIL)" ] || [ -z "$(ROLE)" ]; then \
		echo "Usage: make set-role EMAIL=<addr> ROLE=<pm|user>"; \
		exit 2; \
	fi
	bash $(SCRIPTS)/set_role.sh $(EMAIL) $(ROLE)

verify-user:
	@if [ -z "$(EMAIL)" ]; then \
		echo "Usage: make verify-user EMAIL=<addr>"; \
		exit 2; \
	fi
	bash $(SCRIPTS)/verify_user.sh $(EMAIL)

check-mail-queue:
	bash $(SCRIPTS)/check_mail_queue.sh
