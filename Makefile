PY ?= .venv/bin/python

.PHONY: data freeze test app demo api

data:      ## Phases 1-3 done. Download raw inputs into data/raw (needs network + .env keys)
	set -a; [ -f .env ] && . ./.env; set +a; PYTHONPATH=src $(PY) -m metric_grid.ingest.run

freeze:    ## Phase 3: write data/frozen/ (the only runtime inputs); run `make data` first
	PYTHONPATH=src $(PY) -m metric_grid.ingest.freeze

test:
	$(PY) -m pytest -q

app:       ## Phase 4: run the Streamlit app (reads only data/frozen/, works offline)
	PYTHONPATH=src $(PY) -m streamlit run src/metric_grid/app/streamlit_app.py --server.port 8765

demo:      ## Phase 6: load frozen scenario and open the app
	@echo "TODO: not implemented (Phase 6)"; exit 1

api:       ## Phase 5 (optional node)
	@echo "TODO: not implemented (Phase 5)"; exit 1
