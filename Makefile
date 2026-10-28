.PHONY: up down test seed seed-m2 migrate data evaluate
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

seed-m2:
	docker compose exec api python -m scripts.seed_milestone2

data:
	python -m scripts.generate_milestone2_data

evaluate:
	python -m scripts.evaluate_milestone2
