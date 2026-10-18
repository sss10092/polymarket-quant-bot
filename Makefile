.PHONY: install test lint demo backtest docker
install:
	python -m pip install -e '.[dev]'
test:
	pytest -q
lint:
	ruff check src tests
demo:
	python -m polymarket_bot.cli run --mode demo
backtest:
	python -m polymarket_bot.cli backtest data/sample_prices.csv
docker:
	docker compose up --build
