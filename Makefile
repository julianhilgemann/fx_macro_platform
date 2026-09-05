.PHONY: up down psql check reset

up:            ## Start Postgres and wait until healthy
	docker compose up -d --wait

down:          ## Stop and remove containers (keeps the pgdata volume)
	docker compose down

psql:          ## Open a psql shell on the warehouse DB (as superuser)
	docker compose exec postgres psql -U postgres -d warehouse

check:         ## Verify M0: 6 schemas + raw.source_fetch present
	@n=$$(docker compose exec -T postgres psql -U postgres -d warehouse -tAc \
	  "SELECT count(*) FROM information_schema.schemata WHERE schema_name IN ('raw','staging','intermediate','marts','meta','elementary');"); \
	if [ "$$n" = "6" ]; then echo "M0 OK: 6 schemas present"; else echo "M0 FAIL: expected 6 schemas, got $$n"; exit 1; fi
	@t=$$(docker compose exec -T postgres psql -U postgres -d warehouse -tAc \
	  "SELECT count(*) FROM information_schema.tables WHERE table_schema='raw' AND table_name='source_fetch';"); \
	if [ "$$t" = "1" ]; then echo "M0 OK: raw.source_fetch present"; else echo "M0 FAIL: raw.source_fetch missing"; exit 1; fi

reset:         ## Down + drop the volume so init scripts re-run on next up
	docker compose down -v
