#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print('Usage: state_extractor.py <logfile>')
    sys.exit(1)

log = Path(sys.argv[1])
text = log.read_text(errors='ignore')

state = {
    'logfile': str(log),
    'dfhack_ready': 'DFHack is ready. Have a nice day!' in text,
    'dfhack_prompt_count': len(re.findall(r'\[DFHack\]#', text)),
    'running_scripts': re.findall(r'Running script: (.+)', text),
    'has_floating_point_exception': 'Floating point exception' in text,
    'has_audio_errors': 'ALSA lib' in text,
}

# keep a compact tail for LLM prompt-ing
lines = [l.strip() for l in text.splitlines() if l.strip()]
state['tail'] = lines[-30:]

out = log.with_suffix('.json')
out.write_text(json.dumps(state, indent=2, ensure_ascii=False))
print(out)
