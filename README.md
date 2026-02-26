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
