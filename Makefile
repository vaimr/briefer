.PHONY: build test run clean docker-up docker-down

# Build all Docker images
build:
	docker compose build

# Run tests
test:
	python -m pytest tests/ -v

# Run bot locally
run-bot:
	python -m bot

# Run worker locally
run-worker:
	python -m worker

# Start all services
docker-up:
	docker compose up -d

# Stop all services
docker-down:
	docker compose down

# Clean up
clean:
	rm -rf data/*
	rm -rf __pycache__ bot/__pycache__ worker/__pycache__ tests/__pycache__
