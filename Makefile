.PHONY: up down build psql check reset

build:         ## Build the app image
	docker compose build

up:            ## Build and start the full stack (postgres, dagster, api, metabase)
	docker compose up -d --build

down:          ## Stop and remove containers (keeps volumes)
	docker compose down

psql:          ## Open a psql shell on the warehouse DB (as superuser)
	docker compose exec postgres psql -U postgres -d warehouse

check:         ## Verify the stack is wired and healthy
	@docker compose exec -T postgres psql -U postgres -d warehouse -tAc \
	  "SELECT count(*) FROM information_schema.schemata WHERE schema_name IN ('raw','staging','intermediate','marts','meta','elementary');" | grep -q '^6' && echo "postgres: 6 schemas OK" || echo "postgres: FAIL"
	@curl -sf -o /dev/null http://127.0.0.1:3000/ && echo "dagster UI (:3000): OK" || echo "dagster UI: FAIL"
	@curl -sf -o /dev/null http://127.0.0.1:8000/health && echo "api (:8000): OK" || echo "api: FAIL"

reset:         ## Down + drop volumes so init scripts re-run on next up
	docker compose down -v
