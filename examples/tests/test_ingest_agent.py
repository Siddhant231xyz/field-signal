from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from examples.ingest_agent import (
    SYSTEM_PROMPT,
    IngestionError,
    ShellExecution,
    build_initial_input,
    run_agent,
    validate_outputs,
)
from examples.run_containerized import docker_run_command, parse_args


def _write_valid_ledger(directory: Path) -> None:
    (directory / "people.json").write_text(
        json.dumps(
            {
                "people": [
                    {
                        "id": "alex",
                        "name": "Alex Example",
                        "org": "Example Org",
                        "role": "Reviewer",
                        "capabilities": ["review"],
                        "capability_basis": "S-01 section A: Alex may review.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (directory / "sources.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "S-01",
                        "file": "packet/example.txt",
                        "type": "text",
                        "author": "Example Org",
                        "logical_time": "2026-01-01",
                        "locator_model": "line",
                        "limitations": [],
                        "present": True,
                        "revision": 0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (directory / "claims.json").write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "id": "CL-01",
                        "source": "S-01",
                        "locator": "line 1",
                        "stated_by": "alex",
                        "stated_at": "2026-01-01T09:00:00",
                        "kind": "assertion",
                        "subject": "review",
                        "predicate": "status",
                        "value": "complete",
                        "support": "The review is complete.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_prompt_is_schema_driven_not_packet_answer_driven() -> None:
    lower = SYSTEM_PROMPT.lower()
    for packet_specific_answer in (
        "maya chen",
        "north soffit",
        "ca-118",
        "$2,850",
        "cascade air",
        "75 claims",
    ):
        assert packet_specific_answer not in lower


def test_host_input_contains_no_extension_based_file_routing() -> None:
    initial_input = build_initial_input()
    assert len(initial_input) == 1
    assert initial_input[0]["role"] == "user"
    assert isinstance(initial_input[0]["content"], str)
    assert ".pdf" not in initial_input[0]["content"].lower()
    assert "file contents" in initial_input[0]["content"].lower()


def test_standalone_validation_accepts_the_generic_contract(tmp_path: Path) -> None:
    _write_valid_ledger(tmp_path)
    validate_outputs(tmp_path)


def test_standalone_validation_rejects_a_dangling_source(tmp_path: Path) -> None:
    _write_valid_ledger(tmp_path)
    path = tmp_path / "claims.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["claims"][0]["source"] = "missing"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(IngestionError, match="unknown source"):
        validate_outputs(tmp_path)


def test_standalone_validation_reports_list_relation_without_crashing(
    tmp_path: Path,
) -> None:
    _write_valid_ledger(tmp_path)
    path = tmp_path / "claims.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["claims"][0]["cites_basis"] = ["S-01"]
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(IngestionError, match="cites_basis must be one string id"):
        validate_outputs(tmp_path)


def test_container_runs_as_root_without_privileged_mode(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    output = tmp_path / "output"
    work = tmp_path / "work"
    args = parse_args(["--image", "test-image"])
    command = docker_run_command(args, packet, work, output)

    assert command[command.index("--user") + 1] == "0:0"
    assert "--privileged" not in command
    assert any(value.endswith("dst=/packet,readonly") for value in command)


def test_agent_loop_uses_gpt_5_5_high_and_returns_tool_output() -> None:
    first = SimpleNamespace(
        id="resp-1",
        output=[
            SimpleNamespace(
                type="function_call",
                name="shell",
                arguments=json.dumps(
                    {
                        "command": "find /packet -type f",
                        "timeout_seconds": 30,
                        "attachments": [],
                    }
                ),
                call_id="call-1",
            )
        ],
        output_text="",
    )
    second = SimpleNamespace(id="resp-2", output=[], output_text="done")

    class FakeResponses:
        def __init__(self) -> None:
            self.requests = []
            self.responses = [first, second]

        def create(self, **kwargs):
            self.requests.append(kwargs)
            return self.responses.pop(0)

    class FakeShell:
        def execute(
            self,
            command: str,
            timeout_seconds: int,
            attachment_paths: list[str],
        ) -> ShellExecution:
            assert command == "find /packet -type f"
            assert timeout_seconds == 30
            assert attachment_paths == []
            return ShellExecution(
                json.dumps({"stdout": "/packet/example.txt", "exit_code": 0})
            )

    responses = FakeResponses()
    client = SimpleNamespace(responses=responses)
    result = run_agent(
        client,
        FakeShell(),
        [{"role": "user", "content": "process"}],
        model="gpt-5.5",
        effort="high",
    )

    assert result == "done"
    assert responses.requests[0]["model"] == "gpt-5.5"
    assert responses.requests[0]["reasoning"] == {"effort": "high"}
    assert responses.requests[1]["previous_response_id"] == "resp-1"
    assert responses.requests[1]["input"][0]["type"] == "function_call_output"
