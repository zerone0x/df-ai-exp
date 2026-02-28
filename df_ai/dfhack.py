"""DFHack interaction via RPC protocol and orb VM execution."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import List, Sequence


# ---------------------------------------------------------------------------
# RPC client script that runs *inside* the VM via `orb run`.
# Kept as a string constant to avoid file-sync issues with the VM filesystem.
# ---------------------------------------------------------------------------
_RPC_SCRIPT = r'''
import socket, struct, sys, json

def _varint(v):
    b = bytearray()
    while v > 0x7f: b.append((v & 0x7f) | 0x80); v >>= 7
    b.append(v & 0x7f)
    return bytes(b)

def _dvarint(d, o):
    r = s = c = 0
    while o < len(d):
        b = d[o]; o += 1; c += 1
        r |= (b & 0x7f) << s; s += 7
        if not (b & 0x80): break
    return r, c

def _pb_str(fn, s):
    enc = s.encode("utf-8")
    return bytes([(fn << 3) | 2]) + _varint(len(enc)) + enc

def _recv(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk: raise ConnectionError("closed")
        buf += chunk
    return buf

def _pb_extract_text(data):
    texts = []; i = 0
    while i < len(data):
        tag = data[i]; i += 1; wt = tag & 7
        if wt == 2:
            ln, c = _dvarint(data, i); i += c
            sub = data[i:i+ln]; i += ln
            j = 0
            while j < len(sub):
                st = sub[j]; j += 1; sw = st & 7; sf = st >> 3
                if sw == 2:
                    sl, sc = _dvarint(sub, j); j += sc
                    if sf == 1: texts.append(sub[j:j+sl].decode("utf-8", errors="replace"))
                    j += sl
                elif sw == 0: _, sc = _dvarint(sub, j); j += sc
                else: break
        elif wt == 0: _, c = _dvarint(data, i); i += c
        else: break
    return "".join(texts)

# RPC reply IDs (DFHack 0.47.05-r7)
TEXT = -3
RESULT = -1
FAIL = -2

def rpc_run(args, host="127.0.0.1", port=5000, timeout=30):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect((host, port))
    sock.send(b"DFHack?\n" + struct.pack("<i", 1))
    resp = _recv(sock, 12)
    if resp[:8] != b"DFHack!\n":
        sock.close()
        return {"ok": False, "error": "handshake_failed"}

    payload = _pb_str(1, args[0])
    for a in args[1:]:
        payload += _pb_str(2, a)
    sock.send(struct.pack("<hhI", 1, 0, len(payload)) + payload)

    output = []
    fail = False
    while True:
        hdr = _recv(sock, 8)
        rid = struct.unpack_from("<h", hdr, 0)[0]
        rsize = struct.unpack_from("<I", hdr, 4)[0]
        rdata = _recv(sock, rsize) if rsize > 0 else b""
        if rid == TEXT:
            output.append(_pb_extract_text(rdata))
        elif rid == RESULT:
            break
        elif rid == FAIL:
            fail = True; break
        else:
            break
    sock.close()
    text = "".join(output)
    return {"ok": not fail, "text": text}

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(json.dumps({"ok": False, "error": "no_args"}))
        sys.exit(1)
    try:
        result = rpc_run(args)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
'''


@dataclass
class CommandResult:
    command: Sequence[str]
    returncode: int
    stdout: str
    stderr: str
    attempts: int
    duration: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class DfHackCommandError(RuntimeError):
    pass


def _split_command(command: str | list[str]) -> list[str]:
    """Split a DFHack command string into [command, arg1, arg2, ...]."""
    if isinstance(command, list):
        return list(command)
    # For commands like "lua dfhack.println(df.global.cur_year)",
    # split on first space only so the Lua expression stays intact.
    # For commands like "quickfort run library/dreamfort.csv -n /setup",
    # split on all spaces so each flag is a separate arg.
    parts = command.split()
    if not parts:
        return []
    cmd = parts[0]
    if cmd == "lua":
        # lua commands: keep everything after "lua" as a single arg
        rest = command[len("lua"):].strip()
        return ["lua", rest] if rest else ["lua"]
    return parts


def run_dfhack(
    command: list[str] | str,
    *,
    timeout: float = 30.0,
    retries: int = 1,
    retry_delay: float = 1.0,
    check: bool = False,
    vm_name: str = "df-ai",
) -> CommandResult:
    """Execute a DFHack command via RPC, running inside the VM.

    The command is sent to DFHack's RPC server (port 5000) using a Python
    script executed through ``orb run``.
    """
    import json

    parts = _split_command(command)
    if not parts:
        raise ValueError("Empty command")

    # Build the orb run command that executes our RPC script in the VM.
    orb_cmd = [
        "orb", "run", "-m", vm_name,
        "python3", "-c", _RPC_SCRIPT, *parts,
    ]

    attempts = 0
    start_ts = time.monotonic()
    last_exc: Exception | None = None
    stdout = ""
    stderr = ""
    returncode = -1

    for attempt in range(retries + 1):
        attempts = attempt + 1
        try:
            completed = subprocess.run(
                orb_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr

            # Parse JSON result from our RPC script
            try:
                result_data = json.loads(stdout.strip())
                if result_data.get("ok"):
                    returncode = 0
                    stdout = result_data.get("text", "")
                else:
                    returncode = 1
                    error = result_data.get("error", "")
                    stdout = result_data.get("text", error)
            except (json.JSONDecodeError, ValueError):
                # Script output wasn't JSON — treat raw output as result
                returncode = completed.returncode

            if returncode == 0:
                break
        except subprocess.TimeoutExpired as exc:
            last_exc = exc
            stdout = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = (exc.stderr or b"").decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            returncode = -1

        if attempt < retries:
            time.sleep(retry_delay)

    duration = time.monotonic() - start_ts

    result = CommandResult(
        command=parts,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        attempts=attempts,
        duration=duration,
    )

    if check and not result.ok:
        if last_exc is not None:
            raise DfHackCommandError(
                f"DFHack RPC timed out after {attempts} attempts"
            ) from last_exc
        raise DfHackCommandError(
            f"DFHack RPC failed: {stdout.strip() or stderr.strip()}"
        )

    return result
