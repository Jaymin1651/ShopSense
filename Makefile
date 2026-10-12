.PHONY: up down test seed migrate
up:
	docker compose up --build -d

down:
	docker compose down

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python -m scripts.seed_demo

test:
	python -m pytest -q
