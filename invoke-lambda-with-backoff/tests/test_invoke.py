"""Exercise the real action shell with a fake AWS CLI; never contact AWS."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ACTION = Path(__file__).resolve().parents[1]


@pytest.fixture
def runner(tmp_path):
    binary = tmp_path / "bin"
    binary.mkdir()
    aws = binary / "aws"
    aws.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
request = args[args.index('--payload')+1]
record = {'args': args, 'payload': Path(request.removeprefix('fileb://')).read_text(),
          'attempts': os.environ['AWS_MAX_ATTEMPTS'], 'retry_mode': os.environ['AWS_RETRY_MODE']}
log = Path(os.environ['CALLS'])
previous = log.read_text().splitlines() if log.exists() else []
with log.open('a') as out: out.write(json.dumps(record)+'\n')
mode = os.environ.get('MODE', 'success')
if mode == 'throttle' or mode == 'recover' and len(previous) < 2:
    print('An error occurred (TooManyRequestsException) when calling the Invoke operation: sensitive-error', file=sys.stderr)
    sys.exit(254)
if mode == 'transport':
    print('Read timeout; sensitive-error', file=sys.stderr)
    sys.exit(255)
if mode == 'denied':
    print('An error occurred (AccessDeniedException) when calling the Invoke operation: sensitive-error', file=sys.stderr)
    sys.exit(254)
if mode != 'missing': Path(args[-1]).write_text(os.environ.get('BODY', '{"ok": true}'))
metadata = {'StatusCode': 500 if mode == 'status' else 200, 'LogResult': 'sensitive-log-tail'}
if mode == 'function': metadata['FunctionError'] = 'Unhandled'
print(json.dumps(metadata))
"""
    )
    aws.chmod(0o755)
    sleep = binary / "sleep"
    sleep.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "$SLEEPS"\n')
    sleep.chmod(0o755)
    output, calls, sleeps = [tmp_path / name for name in ("outputs", "calls", "sleeps")]

    def run(**updates):
        env = dict(
            os.environ,
            PATH=str(binary) + ":" + os.environ["PATH"],
            GITHUB_OUTPUT=str(output),
            CALLS=str(calls),
            SLEEPS=str(sleeps),
            RUNNER_TEMP=str(tmp_path),
            FUNCTION_NAME="test-function",
            REGION="eu-central-2",
            MAX_ATTEMPTS="4",
            INITIAL_DELAY="5",
            LOG_RESPONSE="false",
        )
        env.update(updates)
        result = subprocess.run(
            ["bash", str(ACTION / "invoke.sh")],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        records = (
            [json.loads(line) for line in calls.read_text().splitlines()]
            if calls.exists()
            else []
        )
        outputs = {}
        lines = iter(output.read_text().splitlines())
        for line in lines:
            if "<<" in line:
                key, delimiter = line.split("<<", 1)
                content = []
                for value in lines:
                    if value == delimiter:
                        break
                    content.append(value)
                outputs[key] = "\n".join(content)
            elif "=" in line:
                key, value = line.split("=", 1)
                outputs[key] = value
        return result, records, outputs

    return run, tmp_path, sleeps


@pytest.mark.parametrize("source", ["inline", "file", "at", "file-uri", "binary-uri"])
def test_payload_sources_are_literal_and_preserve_bytes(runner, source):
    run, root, _ = runner
    payload = '{"text": "quotes \\" and apostrophe \' $(touch injected) `touch injected`",\n"value": false}'
    request = root / "request with spaces ' $.json"
    request.write_text(payload)
    updates = {"PAYLOAD": payload}
    if source == "file":
        updates = {"PAYLOAD_FILE": str(request)}
    elif source == "at":
        updates = {"PAYLOAD": "@" + str(request)}
    elif source == "file-uri":
        updates = {"PAYLOAD": "file://" + str(request)}
    elif source == "binary-uri":
        updates = {"PAYLOAD": "fileb://" + str(request)}
    result, calls, outputs = run(**updates)
    assert result.returncode == 0, result.stderr
    assert calls[0]["payload"] == payload
    assert outputs["success"] == "true"
    assert not (root / "injected").exists()
    assert not list(root.glob("lambda-invoke.*"))
    assert payload not in result.stdout


def test_defaults_and_timeouts_disable_sdk_retries(runner):
    run, _, _ = runner
    result, calls, _ = run(READ_TIMEOUT="310", CONNECT_TIMEOUT="5")
    assert result.returncode == 0, result.stderr
    record = calls[0]
    assert json.loads(record["payload"]) == {}
    assert record["attempts"] == "1"
    assert record["retry_mode"] == "standard"
    args = record["args"]
    assert args[args.index("--cli-read-timeout") + 1] == "310"
    assert args[args.index("--cli-connect-timeout") + 1] == "5"
    assert args[args.index("--invocation-type") + 1] == "RequestResponse"


@pytest.mark.parametrize("payload", ["{invalid-sensitive}", "{} {}", ""])
def test_invalid_payload_is_rejected_without_printing_it(runner, payload):
    run, _, _ = runner
    # An omitted/empty input uses the documented default {}.
    if not payload:
        payload = "not-json-sensitive"
    result, calls, outputs = run(PAYLOAD=payload)
    assert result.returncode != 0
    assert calls == []
    assert outputs["success"] == "false"
    assert payload not in result.stdout + result.stderr


@pytest.mark.parametrize("fault", ["conflict", "missing", "invalid-file"])
def test_file_failures_prevent_invocation(runner, fault):
    run, root, _ = runner
    request = root / "request.json"
    request.write_text("sensitive-invalid" if fault == "invalid-file" else "{}")
    result, calls, _ = run(
        PAYLOAD_FILE=str(request if fault != "missing" else root / "missing"),
        PAYLOAD='{"explicit":true}' if fault == "conflict" else "{}",
    )
    assert result.returncode != 0
    assert not calls
    assert "sensitive-invalid" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "mode,attempts,success",
    [
        ("throttle", 4, False),
        ("recover", 3, True),
        ("transport", 1, False),
        ("denied", 1, False),
    ],
)
def test_only_explicit_throttling_retries(runner, mode, attempts, success):
    run, _, sleeps = runner
    result, calls, outputs = run(MODE=mode)
    assert (result.returncode == 0) is success
    assert len(calls) == attempts
    assert outputs["success"] == str(success).lower()
    delays = sleeps.read_text().splitlines() if sleeps.exists() else []
    assert len(delays) == (attempts - 1 if mode in ("throttle", "recover") else 0)
    for i, value in enumerate(delays):
        assert 5 * 2**i <= float(value) < 5 * 2**i + 1
    assert "sensitive-error" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "mode,body",
    [
        ("function", '{"details":"sensitive-body"}'),
        ("status", '{"ok":true}'),
        ("missing", "{}"),
        ("success", '{"errorMessage":"sensitive-body"}'),
        ("success", ""),
    ],
)
def test_metadata_body_errors_and_missing_responses_fail_without_retry(
    runner, mode, body
):
    run, _, _ = runner
    result, calls, outputs = run(MODE=mode, BODY=body)
    assert result.returncode != 0
    assert len(calls) == 1
    assert outputs["success"] == "false"
    assert "sensitive-body" not in result.stdout + result.stderr
    assert "sensitive-log-tail" not in result.stdout + result.stderr


def test_multiline_output_and_opt_in_response_logging(runner):
    run, _, _ = runner
    body = '{\n"value": "EOF",\n"nested": true\n}'
    result, _, outputs = run(BODY=body, LOG_RESPONSE="true")
    assert result.returncode == 0
    assert outputs["response"] == body
    assert body in result.stdout
    assert "sensitive-log-tail" not in result.stdout


def test_action_passes_inputs_as_environment_and_preserves_contract():
    action = yaml.safe_load((ACTION / "action.yml").read_text())
    inputs = action["inputs"]
    for key, value in {
        "payload-file": "",
        "read-timeout": "60",
        "connect-timeout": "60",
        "log-response": "true",
    }.items():
        assert inputs[key]["default"] == value
    assert set(action["outputs"]) == {"response", "success"}
    steps = action["runs"]["steps"]
    assert steps[0]["uses"].startswith("aws-actions/configure-aws-credentials@")
    assert "${{ inputs." not in steps[1]["run"]
    assert steps[1]["env"]["PAYLOAD"] == "${{ inputs.payload }}"
