PY ?= .venv/bin/python

.PHONY: data freeze test app demo api

data:      ## Phases 1-2 done; Phase 3 pending. Download raw inputs into data/raw (needs network + .env keys)
	set -a; [ -f .env ] && . ./.env; set +a; PYTHONPATH=src $(PY) -m metric_grid.ingest.run

freeze:    ## Phase 3: write data/frozen/ (the only runtime inputs)
	@echo "TODO: not implemented (Phase 3)"; exit 1

test:
	$(PY) -m pytest -q

app:       ## Phase 4
	@echo "TODO: not implemented (Phase 4)"; exit 1

demo:      ## Phase 6: load frozen scenario and open the app
	@echo "TODO: not implemented (Phase 6)"; exit 1

api:       ## Phase 5 (optional node)
	@echo "TODO: not implemented (Phase 5)"; exit 1
