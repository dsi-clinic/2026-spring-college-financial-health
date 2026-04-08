.PHONY: install lab clean download-ipeds download-peps download-scorecard download-frc download-bea download-saipe download-bls download-all

install: ## Install project dependencies with uv
	uv sync

lab: ## Start JupyterLab
	uv run jupyter lab

clean: ## Remove build artifacts and caches
	rm -rf .venv __pycache__ .pytest_cache .ruff_cache *.egg-info

download-ipeds: ## Download IPEDS survey data (Finance, Enrollment, HR, IC) 2002-2023
	uv run python scripts/download_ipeds.py

download-peps: ## Download PEPS closed schools data (1996-2023)
	uv run python scripts/download_peps.py

download-scorecard: ## Download College Scorecard data (requires SCORECARD_API_KEY in .env)
	uv run python scripts/download_scorecard.py

download-frc: ## Download FRC composite scores (2006-2020)
	uv run python scripts/download_frc.py

download-bea: ## Download BEA county income and population (requires BEA_API_KEY in .env)
	uv run python scripts/download_bea.py

download-saipe: ## Download Census SAIPE county poverty rates (1997-2022)
	uv run python scripts/download_saipe.py

download-bls: ## Download BLS LAUS county unemployment rates (1990-2022)
	uv run python scripts/download_bls.py

download-all: download-ipeds download-peps download-scorecard download-frc download-bea download-saipe download-bls ## Download all data sources

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
