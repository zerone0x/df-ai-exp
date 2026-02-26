DF_ROOT ?= /home/sober/df53/app

.PHONY: smoke
smoke:
	DF_ROOT=$(DF_ROOT) ./scripts/run_smoke.sh
