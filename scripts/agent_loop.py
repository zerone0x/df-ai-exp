#!/usr/bin/env python3
import json
import subprocess
import time
from pathlib import Path

ROOT = Path('/home/sober/dwarf-fortress')
LOGDIR = ROOT / 'logs'
LOGDIR.mkdir(exist_ok=True)


def run_once(seconds=25):
    ts = int(time.time())
    log = LOGDIR / f'df_session_{ts}.log'
    cmd = [str(ROOT / 'tools' / 'auto_start.exp'), str(log)]
    print('Running:', ' '.join(cmd))
    try:
        subprocess.run(cmd, timeout=seconds, check=False)
    except subprocess.TimeoutExpired:
        print('Timed out (continuing).')
    return log


def extract(log: Path):
    cmd = ['python3', str(ROOT / 'agent' / 'state_extractor.py'), str(log)]
    res = subprocess.check_output(cmd, text=True).strip()
    return Path(res)


def main():
    log = run_once()
    json_path = extract(log)
    state = json.loads(json_path.read_text())

    print(f'Log: {log}')
    print(f'State: {json_path}')
    print('--- summary ---')
    print('dfhack_ready:', state['dfhack_ready'])
    print('prompt_count:', state['dfhack_prompt_count'])
    print('floating_point_exception:', state['has_floating_point_exception'])
    print('audio_errors:', state['has_audio_errors'])
    print('tail_last_5:')
    for line in state['tail'][-5:]:
        print('  ', line)


if __name__ == '__main__':
    main()
