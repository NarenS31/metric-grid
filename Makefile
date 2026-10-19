PY ?= .venv/bin/python

.PHONY: data freeze test app demo api demand demand-train

data:      ## Phases 1-3 done. Download raw inputs into data/raw (needs network + .env keys)
	set -a; [ -f .env ] && . ./.env; set +a; PYTHONPATH=src $(PY) -m metric_grid.ingest.run

freeze:    ## Phase 3: write data/frozen/ (the only runtime inputs); run `make data` first
	PYTHONPATH=src $(PY) -m metric_grid.ingest.freeze

test:
	$(PY) -m pytest -q

app:       ## Phase 4: run the Streamlit app (reads only data/frozen/, works offline)
	PYTHONPATH=src $(PY) -m streamlit run src/metric_grid/app/streamlit_app.py --server.port 8765

HEADLESS ?= false   # `make demo HEADLESS=true` does not open a browser (used by the clean-clone check)

demo:      ## open the app on the frozen scenario (offline; needs only data/frozen/ and the installed packages)
	@test -f data/frozen/constants.json || (echo "data/frozen/ is missing: restore it from the repository or run make data && make freeze"; exit 1)
	PYTHONPATH=src $(PY) -m streamlit run src/metric_grid/app/streamlit_app.py --server.port 8765 --server.headless $(HEADLESS)

demand:    ## winter demand model: pull EIA-930 history + IEM temperatures (network + EIA_API_KEY), then train and validate
	set -a; [ -f .env ] && . ./.env; set +a; PYTHONPATH=src $(PY) -m metric_grid.ingest.demand_history && PYTHONPATH=src $(PY) -m metric_grid.train.demand

demand-train:  ## retrain and re-validate from the frozen training table (offline)
	PYTHONPATH=src $(PY) -m metric_grid.train.demand

api:       ## Phase 5 (optional node)
	@echo "TODO: not implemented (Phase 5)"; exit 1
