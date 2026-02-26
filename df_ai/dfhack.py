"""Helpers for interacting with dfhack-run."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from .config import get_df_root


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


def _normalize_command(command: Iterable[str] | str) -> List[str]:
    if isinstance(command, str):
        return [command]
    return list(command)


def run_dfhack(
    command: Iterable[str] | str,
    *,
    df_root: Path | None = None,
    timeout: float = 10.0,
    retries: int = 1,
    retry_delay: float = 1.0,
    check: bool = False,
) -> CommandResult:
    """Execute ``dfhack-run`` with retries and timeouts.

    Args:
        command: The dfhack command (list of args for dfhack-run).
        df_root: Override the DF root path.
        timeout: Timeout per attempt.
        retries: Number of retries after the initial attempt.
        retry_delay: Seconds to wait between attempts.
        check: Raise ``DfHackCommandError`` if the command ultimately fails.

    Returns:
        CommandResult with details about execution.
    """

    root = df_root or get_df_root()
    executable = root / "dfhack-run"
    if not executable.exists():
        raise FileNotFoundError(f"dfhack-run not found at {executable}")

    cmd = [str(executable)] + _normalize_command(command)
    attempts = 0
    start_ts = time.monotonic()
    last_exc: subprocess.TimeoutExpired | None = None
    stdout = ""
    stderr = ""
    returncode = -1

    for attempt in range(retries + 1):
        attempts = attempt + 1
        try:
            completed = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            returncode = completed.returncode
            if returncode == 0:
                break
        except subprocess.TimeoutExpired as exc:
            last_exc = exc
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            returncode = -1

        if attempt < retries:
            time.sleep(retry_delay)

    duration = time.monotonic() - start_ts

    result = CommandResult(
        command=cmd,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        attempts=attempts,
        duration=duration,
    )

    if check and not result.ok:
        if last_exc is not None:
            raise DfHackCommandError(
                f"dfhack-run timed out after {attempts} attempts (timeout={timeout}s)"
            ) from last_exc
        raise DfHackCommandError(
            f"dfhack-run failed with exit code {returncode}: {stderr.strip()}"
        )

    return result
