DF_ROOT ?= /path/to/df

.PHONY: smoke
smoke:
	DF_ROOT=$(DF_ROOT) ./scripts/run_smoke.sh
