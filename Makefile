.PHONY: install up verify

install:
	python -m pip install -e "./backend[dev]"

up:
	docker compose up -d

verify: up
	python scripts/verify_falkordb.py
