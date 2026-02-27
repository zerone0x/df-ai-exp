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

## LLM Planner

Instead of the hardcoded rule-based policy, let Claude decide the next action:

```bash
# Agent control loop with LLM
ANTHROPIC_API_KEY=sk-... python3 scripts/agent_control_loop.py --planner llm

# Goal runner with LLM (dynamic steps instead of static plan)
ANTHROPIC_API_KEY=sk-... python3 scripts/goal_runner.py --goal worldgen --policy llm

# Custom model
DF_AI_MODEL=claude-sonnet-4-20250514 ANTHROPIC_API_KEY=sk-... python3 scripts/agent_control_loop.py --planner llm
```

The LLM receives current game state, command catalog, and recent action history.
It outputs structured JSON actions and can signal "done" to stop early.
Falls back to rule-based policy on API failure.

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

## macOS Development (OrbStack)

DF + DFHack only ship x86_64 Linux/Windows binaries — no native macOS support.
The recommended setup on Mac is an **OrbStack x86_64 Linux VM** with Rosetta emulation.

### Prerequisites

- [OrbStack](https://orbstack.dev/) installed on macOS
- [DepotDownloader](https://github.com/SteamRE/DepotDownloader) for fetching Steam game files (`brew tap steamre/tools && brew install depotdownloader`)
- A Steam account that owns Dwarf Fortress

> **Note:** `steamcmd` segfaults under Rosetta due to a glibc futex/pthreads incompatibility.
> Use DepotDownloader instead — it is a pure .NET Steam client that runs natively on Apple Silicon.

### One-time setup

```bash
# 1. Create an x86_64 Ubuntu VM
orbctl create --arch amd64 ubuntu:24.04 df-ai

# 2. Install runtime dependencies
orb -m df-ai -u root bash -c "apt-get update && apt-get install -y \
  xvfb xdotool python3 python3-pip python3-venv \
  libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-ttf-2.0-0"

# 3. Download DF + DFHack via DepotDownloader (on Mac side)
depotdownloader -app 975370 -os linux -dir /tmp/df-download/df -username YOUR_STEAM_USER -remember-password
# DFHack (free DLC)
depotdownloader -app 2346660 -os linux -dir /tmp/df-download/df -username YOUR_STEAM_USER -remember-password

# 4. Copy into VM and fix permissions
orb -m df-ai -u root bash -c "mkdir -p /opt/df && cp -r /mnt/mac/tmp/df-download/df/* /opt/df/"
orb -m df-ai -u root bash -c "chmod +x /opt/df/dwarfort /opt/df/dfhack /opt/df/dfhack-run /opt/df/hack/dfhack-run /opt/df/hack/launchdf"

# 5. Set DF_ROOT for this project
echo '/opt/df' > config/df_root.txt

# 6. Create Python venv inside VM (via Mac mount)
orb -m df-ai bash -c "cd /mnt/mac$(pwd) && python3 -m venv .venv-linux && source .venv-linux/bin/activate && pip install -r requirements.txt"
```

### Verify

```bash
orb -m df-ai -u root -s <<'EOF'
cd /opt/df
nohup xvfb-run -a -s "-screen 0 1280x720x24" ./dfhack > /tmp/df_test.log 2>&1 &
sleep 10
/opt/df/dfhack-run ls | head -5
echo "=== OK ==="
pkill -9 dwarfort
EOF
```

### Daily workflow

```bash
# Mac side — edit code with your IDE
code ~/Downloads/df-ai-exp

# VM side — run scripts
orb -m df-ai
cd /mnt/mac/Users/YOUR_USER/Downloads/df-ai-exp
source .venv-linux/bin/activate
export DF_ROOT=/opt/df

python3 scripts/agent_control_loop.py --planner llm
```

OrbStack mounts the Mac filesystem at `/mnt/mac/`, so code edits on Mac are immediately visible in the VM.
