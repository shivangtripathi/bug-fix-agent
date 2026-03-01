from __future__ import annotations

import subprocess
from typing import Any, Callable


PromptFn = Callable[[str], str]


def bash(command: str, prompt_fn: PromptFn = input) -> dict[str, Any]:
    approval = prompt_fn(f"Run bash command '{command}'? Type yes to continue: ").strip().lower()
    if approval != "yes":
        return {
            "ok": False,
            "status": "denied",
            "command": command,
            "message": "Command not executed; user denied permission.",
        }

    completed = subprocess.run(command, shell=True, text=True, capture_output=True)
    return {
        "ok": completed.returncode == 0,
        "status": "executed",
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
