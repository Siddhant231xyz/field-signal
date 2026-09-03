"""Agent process executed as root inside the ingestion container."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any

try:
    from .ingest_agent import (
        IngestionError,
        ShellExecution,
        build_initial_input,
        run_agent,
        validate_outputs,
    )
except ImportError:
    from ingest_agent import (
        IngestionError,
        ShellExecution,
        build_initial_input,
        run_agent,
        validate_outputs,
    )


class RootShell:
    """Run model-requested commands directly in this container as UID 0."""

    def __init__(self, max_output_chars: int = 40_000) -> None:
        if os.geteuid() != 0:
            raise IngestionError("container agent must run as root")
        self.max_output_chars = max_output_chars

    def execute(
        self,
        command: str,
        timeout_seconds: int,
        attachment_paths: list[str] | None = None,
    ) -> ShellExecution:
        timeout_seconds = max(1, min(int(timeout_seconds), 600))
        shell_environment = dict(os.environ)
        shell_environment.pop("OPENAI_API_KEY", None)
        try:
            completed = subprocess.run(
                [
                    "timeout",
                    "--signal=KILL",
                    f"{timeout_seconds}s",
                    "bash",
                    "-lc",
                    command,
                ],
                cwd="/work",
                env=shell_environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds + 15,
                check=False,
            )
            stdout, stdout_cut = _truncate(completed.stdout, self.max_output_chars)
            stderr, stderr_cut = _truncate(completed.stderr, self.max_output_chars)
            result: dict[str, Any] = {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": completed.returncode,
                "timed_out": completed.returncode == 124,
                "truncated": stdout_cut or stderr_cut,
            }
        except subprocess.TimeoutExpired as exc:
            result = {
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "exit_code": -1,
                "timed_out": True,
                "truncated": False,
            }

        attachments: list[dict[str, Any]] = []
        errors: list[str] = []
        for path in attachment_paths or []:
            try:
                attachments.append(self._image_attachment(path))
            except IngestionError as exc:
                errors.append(f"{path}: {exc}")
        if errors:
            result["attachment_errors"] = errors
        return ShellExecution(json.dumps(result, ensure_ascii=True), tuple(attachments))

    def _image_attachment(self, value: str) -> dict[str, Any]:
        path = PurePosixPath(value)
        if not path.is_absolute() or ".." in path.parts:
            raise IngestionError("attachment path must be absolute without '..'")
        if len(path.parts) < 3 or path.parts[1] not in {"packet", "work"}:
            raise IngestionError("attachment must be under /packet or /work")
        mime = subprocess.run(
            ["file", "--brief", "--mime-type", "--", str(path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        media_type = mime.stdout.strip()
        if mime.returncode != 0 or not media_type.startswith("image/"):
            raise IngestionError(
                f"binary MIME type is {media_type or 'unreadable'}, not an image"
            )
        raw = Path(path).read_bytes()
        if len(raw) > 20 * 1024 * 1024:
            raise IngestionError("attachment exceeds the 20 MiB binary limit")
        encoded = base64.b64encode(raw).decode("ascii")
        return {
            "type": "input_image",
            "image_url": f"data:{media_type};base64,{encoded}",
            "detail": "original",
        }


def _truncate(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    half = limit // 2
    return value[:half] + "\n... output truncated ...\n" + value[-half:], True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.getenv("INGEST_MODEL", "gpt-5.5"))
    parser.add_argument(
        "--effort", default=os.getenv("INGEST_REASONING_EFFORT", "high")
    )
    parser.add_argument("--max-tool-calls", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("OPENAI_API_KEY is empty", file=sys.stderr)
        return 2
    if not Path("/packet").is_dir() or not Path("/output").is_dir():
        print("/packet and /output must be mounted directories", file=sys.stderr)
        return 2
    context = Path("/context") if Path("/context").is_dir() else None

    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=1800.0, max_retries=2)
    print(
        f"Container agent: model={args.model}, effort={args.effort}, "
        f"uid={os.geteuid()}",
        flush=True,
    )
    try:
        final_text = run_agent(
            client,
            RootShell(),
            build_initial_input(context_available=context is not None),
            model=args.model,
            effort=args.effort,
            max_tool_calls=args.max_tool_calls,
            completion_check=lambda: validate_outputs(
                Path("/output"), context_directory=context
            ),
        )
        print(f"\nAgent result\n{final_text}", flush=True)
        validate_outputs(Path("/output"), context_directory=context)
        print("Container validation passed", flush=True)
        return 0
    except (IngestionError, OSError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
