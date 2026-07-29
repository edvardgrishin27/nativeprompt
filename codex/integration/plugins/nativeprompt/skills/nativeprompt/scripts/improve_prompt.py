#!/usr/bin/env python3
"""Safely invoke nativeprompt for the Codex skill.

The prompt is accepted only on stdin and is never passed through a shell.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REQUIRED_KEYS = {"target", "findings", "harness", "improved", "metaprompt"}


def _nativeprompt_checkout() -> Path | None:
    starts = (Path.cwd().resolve(), Path(__file__).resolve().parent)
    seen: set[Path] = set()
    for start in starts:
        for candidate in (start, *start.parents):
            if candidate in seen:
                continue
            seen.add(candidate)
            if (
                (candidate / "pyproject.toml").is_file()
                and (candidate / "nativeprompt" / "__main__.py").is_file()
            ):
                return candidate
    return None


def _command(explicit: str | None) -> tuple[list[str], Path | None]:
    if explicit:
        executable = Path(explicit).expanduser()
        if not executable.is_file():
            raise RuntimeError(f"nativeprompt executable not found: {executable}")
        return [str(executable.resolve())], None

    executable = shutil.which("nativeprompt")
    if executable:
        return [executable], None

    if importlib.util.find_spec("nativeprompt") is not None:
        return [sys.executable, "-m", "nativeprompt"], None

    checkout = _nativeprompt_checkout()
    if checkout:
        return [sys.executable, "-m", "nativeprompt"], checkout

    raise RuntimeError(
        "nativeprompt CLI not found. Install it from a trusted local checkout: "
        "python3 -m pip install -e /absolute/path/to/nativeprompt"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run nativeprompt safely and validate its Codex JSON report."
    )
    parser.add_argument(
        "--model",
        default="codex",
        help="OpenAI/Codex model identifier (default: codex)",
    )
    parser.add_argument(
        "--executable",
        help="Explicit path to the nativeprompt executable",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="CLI timeout in seconds (default: 30)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    prompt = sys.stdin.read()
    if not prompt.strip():
        print("Expected a non-empty prompt on stdin.", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("--timeout must be greater than zero.", file=sys.stderr)
        return 2

    try:
        base_command, cwd = _command(args.executable)
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                *base_command,
                "improve",
                "--model",
                args.model,
                "--json",
            ],
            input=prompt,
            text=True,
            capture_output=True,
            cwd=cwd,
            env=environment,
            timeout=args.timeout,
            check=False,
        )
    except (RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 127
    except subprocess.TimeoutExpired:
        print(
            f"nativeprompt timed out after {args.timeout:g} seconds.",
            file=sys.stderr,
        )
        return 124

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        print(
            detail or f"nativeprompt failed with exit code {completed.returncode}.",
            file=sys.stderr,
        )
        return completed.returncode

    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        print(f"nativeprompt returned invalid JSON: {exc}", file=sys.stderr)
        return 1

    missing = sorted(REQUIRED_KEYS.difference(report))
    if missing:
        print(
            "nativeprompt report is missing required keys: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1

    target = report.get("target")
    if not isinstance(target, dict) or target.get("family") != "openai":
        print(
            "This Codex skill accepts only OpenAI/Codex targets.",
            file=sys.stderr,
        )
        return 2

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
