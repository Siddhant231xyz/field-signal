"""Build and run the complete ingestion agent inside Docker."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

from examples.evaluate import compare, print_report
from examples.ingest_agent import IngestionError, promote_outputs, validate_outputs

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = Path(__file__).resolve().parent


# Set by an embedding caller (field_signal.agent) to watch progress. When it
# is None the output goes straight to the console, exactly as before.
ON_LINE = None


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        if ON_LINE is None:
            return subprocess.run(command, text=True, timeout=timeout, check=False)
        return _run_streaming(command, timeout)
    except FileNotFoundError as exc:
        raise IngestionError("docker CLI was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise IngestionError("Docker ingestion run timed out") from exc


def _run_streaming(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Same call, but each output line is echoed and handed to ON_LINE.

    A long container run is otherwise completely silent to anything embedding
    this, which leaves a caller unable to say whether it is still working.
    """
    process = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    try:
        for line in process.stdout:
            print(line, end="", flush=True)
            try:
                ON_LINE(line.rstrip())
            except Exception:  # a broken watcher must not kill the run
                pass
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        raise
    return subprocess.CompletedProcess(command, process.returncode)


def _env_value(name: str) -> str | None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name:
            return value.strip().strip("\"'")
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "packet")
    parser.add_argument("--output", type=Path, default=EXAMPLES_DIR / "data")
    parser.add_argument("--reference", type=Path, default=ROOT / "data")
    parser.add_argument("--no-compare", action="store_true")
    parser.add_argument(
        "--image",
        default=_env_value("INGEST_DOCKER_IMAGE")
        or "field-signal-ingestor-example:latest",
    )
    parser.add_argument(
        "--network",
        choices=("bridge", "none"),
        default=_env_value("INGEST_CONTAINER_NETWORK") or "bridge",
    )
    parser.add_argument("--max-tool-calls", type=int, default=200)
    parser.add_argument("--check-only", action="store_true")
    return parser.parse_args(argv)


def docker_run_command(
    args: argparse.Namespace,
    input_dir: Path,
    work: Path,
    staging: Path,
) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--user",
        "0:0",
        "--workdir",
        "/work",
        "--network",
        args.network,
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "256",
        "--memory",
        "4g",
        "--cpus",
        "2",
        "--env-file",
        str(ROOT / ".env"),
        "--mount",
        f"type=bind,src={input_dir},dst=/packet,readonly",
        "--mount",
        f"type=bind,src={work.resolve()},dst=/work",
        "--mount",
        f"type=bind,src={staging.resolve()},dst=/output",
        args.image,
        "--max-tool-calls",
        str(args.max_tool_calls),
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_dir = args.input.resolve()
    if not input_dir.is_dir():
        print(f"Input directory does not exist: {input_dir}", file=sys.stderr)
        return 2
    if not (_env_value("OPENAI_API_KEY") or "").strip() and not args.check_only:
        print("OPENAI_API_KEY is empty in .env", file=sys.stderr)
        return 2

    try:
        print(f"Building {args.image} ...", flush=True)
        built = _run(
            ["docker", "build", "--tag", args.image, str(EXAMPLES_DIR)],
            timeout=1800,
        )
        if built.returncode != 0:
            raise IngestionError("Docker image build failed")
        if args.check_only:
            checked = _run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--entrypoint",
                    "python",
                    args.image,
                    "-c",
                    "import os; print('container uid:', os.geteuid())",
                ],
                timeout=60,
            )
            return checked.returncode

        with tempfile.TemporaryDirectory(prefix=".ingest-", dir=EXAMPLES_DIR) as temp:
            run_dir = Path(temp)
            staging = run_dir / "output"
            work = run_dir / "work"
            staging.mkdir()
            work.mkdir()
            command = docker_run_command(args, input_dir, work, staging)
            print("Starting containerized agent ...", flush=True)
            completed = _run(command, timeout=7200)
            if completed.returncode != 0:
                raise IngestionError(
                    f"containerized agent exited with {completed.returncode}"
                )
            validate_outputs(staging)
            promote_outputs(staging, args.output.resolve())

        print(f"Validated output promoted to {args.output.resolve()}")
        if not args.no_compare:
            print_report(compare(args.output.resolve(), args.reference.resolve()))
        return 0
    except (IngestionError, OSError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
