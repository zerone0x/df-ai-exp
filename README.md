# df-ai-exp

Experiments for running Dwarf Fortress + DFHack in an automated agent loop.

## Goal
Build a reproducible loop:
1. launch DF/DFHack
2. capture session logs
3. extract structured state
4. feed state to an agent policy
5. execute next actions

## Current status
- DFHack launch detection works (`dfhack_ready=true` in extracted state)
- Session logs and JSON state files are generated
- Main blocker: floating point exception in headless terminal mode after DFHack prompt

## Repository structure
- `scripts/auto_start.exp` — launch/expect automation
- `scripts/agent_loop.py` — run one loop iteration
- `scripts/state_extractor.py` — parse log into JSON state

## Quick start
```bash
python3 scripts/agent_loop.py
```

## Next milestones
- [ ] Stabilize runtime via Xvfb
- [ ] Reach game menu/worldgen state reliably
- [ ] Implement action planner/executor bridge
- [ ] Add regression test fixtures for log parser


## Smoke test

```bash
make smoke
# optional custom path
DF_ROOT=/absolute/path/to/your/df make smoke
```


## FPE repro matrix

```bash
# in your DF install root (where ./dfhack exists)
./tools/repro_fpe.sh none
./tools/repro_fpe.sh help
./tools/repro_fpe.sh ls
./tools/repro_fpe.sh exit
```

Current observation: `none` can pass, but interactive modes (`help/ls/exit`) trigger FPE in this environment.


## Non-interactive workaround

Interactive console input currently triggers FPE in this environment.
A stable workaround is:
1. start DF/DFHack as a background host process
2. send commands with `dfhack-run` (non-interactive)

```bash
DF_ROOT=/absolute/path/to/your/df ./scripts/noninteractive_runner.sh
```

## Worldgen automation (MVP)

Worldgen is now supported as a mixed-action goal:
- `dfhack` actions: executed with `dfhack-run`
- `keystroke` actions: sent to the DF window via `xdotool`

Use:
```bash
python3 scripts/goal_runner.py --goal worldgen
```

Notes:
- requires an X display host (`xvfb-run` is already used by `goal_runner.py`)
- requires `xdotool` installed on the host
- completion is verified with DFHack Lua state probes plus presence of `data/save/region*`
