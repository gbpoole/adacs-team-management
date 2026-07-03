.PHONY: help bootstrap configure dns deploy update backup logs status shell

SCRIPTS := scripts

# DNS target requires ZONE and IP to be passed on the command line:
#   make dns ZONE=adacs-gpoole.cloud.edu.au. IP=203.0.113.42
ZONE ?=
IP   ?=

help:
	@echo ""
	@echo "adacs-team-management — deployment helpers"
	@echo ""
	@echo "FIRST-TIME DEPLOYMENT (run these in order)"
	@echo "  1. SSH into the VM with agent forwarding:  ssh -A ubuntu@<IP>"
	@echo "     Clone the repo:                         git clone git@github.com:gbpoole/adacs-team-management.git"
	@echo "     Enter the repo:                         cd adacs-team-management"
	@echo "  2. make bootstrap     Install Docker, Nginx, Certbot, ufw (sudo)"
	@echo "     Then log out and back in so docker group membership takes effect."
	@echo "  3. make configure     Create .env with auto-generated secrets (interactive)"
	@echo "  4. Source OpenStack credentials:  . ~/openrc.sh"
	@echo "     make dns ZONE=<project>.cloud.edu.au. IP=<instance-ip>"
	@echo "     Wait a few minutes for DNS to propagate, then verify: host <DOMAIN_NAME>"
	@echo "  5. make deploy        Build images, start services, configure Nginx & TLS (sudo)"
	@echo "     Visit https://<DOMAIN_NAME> to confirm the app is live."
	@echo ""
	@echo "ONGOING OPERATIONS"
	@echo "  make update           Pull latest code and rebuild/restart changed services"
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
