.PHONY: dev worker test test-slow lint fmt migrate seed bench up down shell

# This machine has only the standalone docker-compose v1 binary (no `docker
# compose` plugin), and the shell user isn't in the `docker` group — `sudo` is
# passwordless for these two binaries only (see sudoers). If your machine has
# the docker group set up normally, drop `sudo` and use `docker compose`.
up:
	sudo docker-compose up -d

down:
	sudo docker-compose down

dev:
	python manage.py runserver

worker:
	celery -A config worker -l info

migrate:
	python manage.py makemigrations
	python manage.py migrate

shell:
	python manage.py shell

test:
	pytest --cov=ai --cov=apps --cov-report=term-missing

test-slow:
	pytest -m slow

lint:
	ruff check .
	black --check .

fmt:
	ruff check --fix .
	black .

seed:
	python scripts/seed_demo.py

bench:
	python scripts/benchmark.py
