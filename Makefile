PY ?= .venv/bin/python

.PHONY: data freeze test app demo api

data:      ## Phase 1-3: download raw inputs into data/raw (needs network + API keys)
	@echo "TODO: not implemented (Phase 1-3)"; exit 1

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
