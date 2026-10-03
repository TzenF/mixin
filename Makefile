# Raccourcis de développement. DOCKER_BUILDKIT=0 : requis sur Chromebook (Crostini).
export DOCKER_BUILDKIT := 0
COMPOSE := docker compose

.PHONY: up down logs test test-back test-front lint reset-db psql

up:            ## Construit et démarre tout (front, API, worker, base, Redis)
	$(COMPOSE) up --build -d
	@echo "Front : http://localhost:4200   API : http://localhost:8000/docs"

down:          ## Arrête tout (les données de la base sont conservées)
	$(COMPOSE) down

logs:          ## Affiche les logs en continu
	$(COMPOSE) logs -f --tail=50

test: test-back test-front

test-back:     ## Tests backend (unitaires + intégration sur la vraie base)
	$(COMPOSE) exec api pytest -q

test-front:    ## Tests Angular
	$(COMPOSE) exec web npx ng test --watch=false

lint:          ## Vérifie le style du backend
	$(COMPOSE) exec api sh -c "ruff check . && ruff format --check ."

reset-db:      ## Efface la base et rejoue les migrations (perte des données !)
	$(COMPOSE) down -v
	$(COMPOSE) up -d db

psql:          ## Ouvre un terminal SQL sur la base
	$(COMPOSE) exec db psql -U dj -d dj
