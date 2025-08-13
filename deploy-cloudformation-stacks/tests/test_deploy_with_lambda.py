import logging
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from deploy_with_lambda_call import deploy, do_dump_graph, resolve_version_with_hash_support

_logger = logging.getLogger(__name__)


def test_deploy(tmpdir):

    tempdir = Path(tmpdir)
    environment = "devops"
    envdir = tempdir / environment

    envdir.mkdir(parents=True, exist_ok=True)

    with patch("poemai_devops.tools.deploy_with_lambda_call.boto3") as boto3_mock:

        stacks = {
            "environment": "devops",
            "stacks": [
                {
                    "stack_name": "test-stack",
                }
            ],
        }
        stacks_file = envdir / "stacks.yaml"
        with open(stacks_file, "w") as f:
            yaml.dump(stacks, f)

        stack_template = {
            "Resources": {
                "MyBucket": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {"BucketName": "my-bucket"},
                }
            }
        }

        stack_template_file = envdir / "test_stack.yaml"

        with open(stack_template_file, "w") as f:
            yaml.dump(stack_template, f)

        # print the content of the directory
        for path in tempdir.rglob("*"):
            _logger.info(f"Path: {path}")

        config = yaml.safe_load(open(stacks_file))
        do_dump_graph(config, stacks_file.as_posix())


def test_deploy_2(tmpdir):

    tempdir = Path(tmpdir)
    environment = "devops"
    envdir = tempdir / environment

    envdir.mkdir(parents=True, exist_ok=True)

    with patch(
        "poemai_devops.tools.deploy_with_lambda_call.boto3", name="boto3_mock"
    ) as boto3_mock:
        lambda_client_mock = MagicMock()
        boto3_mock.client.return_value = lambda_client_mock

        # Set up the exception as a real Exception class
        lambda_client_mock.exceptions = MagicMock()

        class TooManyRequestsException(Exception):
            def __init__(self, message):
                super().__init__(message)
                self.message = message

        lambda_client_mock.exceptions.TooManyRequestsException = (
            TooManyRequestsException
        )

        # Mock the invoke() return value
        payload_content = '[{"status": "success"}]'
        payload_stream = BytesIO(payload_content.encode("utf-8"))
        payload_mock = MagicMock()
        payload_mock.read.return_value = payload_stream.read()
        payload_mock.decode = lambda encoding="utf-8": payload_content

        lambda_client_mock.invoke.return_value = {"Payload": payload_mock}

        cf_client_mock = MagicMock()

        # Patch boto3.client to return cf_client_mock when called with "cloudformation"
        def client_side_effect(service_name, *args, **kwargs):
            if service_name == "lambda":
                return lambda_client_mock
            elif service_name == "cloudformation":
                return cf_client_mock
            else:
                raise ValueError(f"Unknown service: {service_name}")

        boto3_mock.client.side_effect = client_side_effect

        cf_client_mock.describe_stacks.return_value = {
            "Stacks": [{"StackStatus": "CREATE_COMPLETE"}]
        }

        stacks = {
            "environment": "devops",
            "stacks": [
                {
                    "stack_name": "test-stack",
                }
            ],
        }
        stacks_file = envdir / "stacks.yaml"
        with open(stacks_file, "w") as f:
            yaml.dump(stacks, f)

        stack_template = {
            "Resources": {
                "MyBucket": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {"BucketName": "my-bucket"},
                }
            }
        }

        stack_template_file = envdir / "test_stack.yaml"

        with open(stack_template_file, "w") as f:
            yaml.dump(stack_template, f)

        # print the content of the directory
        for path in tempdir.rglob("*"):
            _logger.info(f"Path: {path}")

        config = yaml.safe_load(open(stacks_file))
        do_dump_graph(config, stacks_file.as_posix())

def test_resolve_version_with_hash_support():
    """Test the hash-based version resolution functionality."""
    
    # Test traditional repo-wide version
    repo_versions = {
        "poemAI-ch/poemai-lambdas": "abcdef1234567890"
    }
    result = resolve_version_with_hash_support("poemAI-ch/poemai-lambdas", repo_versions, "SomeVersion")
    assert result == "abcdef1"
    
    # Test individual lambda version with new full format (repo#lambda_name)
    repo_versions = {
        "poemAI-ch/poemai-lambdas#bot_admin": "1234567890abcdef",
        "poemAI-ch/poemai-lambdas#assistant_api": "fedcba0987654321"
    }
    result = resolve_version_with_hash_support("poemAI-ch/poemai-lambdas#bot_admin", repo_versions, "BotAdminLambdaVersion")
    assert result == "1234567890abcdef"
    
    result = resolve_version_with_hash_support("poemAI-ch/poemai-lambdas#assistant_api", repo_versions, "AssistantAPILambdaVersion")
    assert result == "fedcba0987654321"
    
    # Test backward compatibility with old format (lambda names without repo prefix)
    repo_versions = {
        "bot_admin": "1234567890abcdef",
        "assistant_api": "fedcba0987654321"
    }
    result = resolve_version_with_hash_support("poemAI-ch/poemai-lambdas#bot_admin", repo_versions, "BotAdminLambdaVersion")
    assert result == "1234567890abcdef"
    
    result = resolve_version_with_hash_support("poemAI-ch/poemai-lambdas#assistant_api", repo_versions, "AssistantAPILambdaVersion")
    assert result == "fedcba0987654321"
    
    # Test mixed scenario (both repo-wide and individual versions)
    repo_versions = {
        "poemAI-ch/poemai-lambdas": "abcdef1234567890",
        "poemAI-ch/poemai-lambdas#bot_admin": "1234567890abcdef"
    }
    # Should use repo-wide version when no hash syntax
    result = resolve_version_with_hash_support("poemAI-ch/poemai-lambdas", repo_versions, "SomeVersion")
    assert result == "abcdef1"
    
    # Should use individual version when specified with hash syntax (new format takes precedence)
    result = resolve_version_with_hash_support("poemAI-ch/poemai-lambdas#bot_admin", repo_versions, "BotAdminLambdaVersion")
    assert result == "1234567890abcdef"
    
    # Test precedence: new format should take precedence over old format
    repo_versions = {
        "poemAI-ch/poemai-lambdas#bot_admin": "new_format_hash",
        "bot_admin": "old_format_hash"
    }
    result = resolve_version_with_hash_support("poemAI-ch/poemai-lambdas#bot_admin", repo_versions, "BotAdminLambdaVersion")
    assert result == "new_format_hash"
    
    # Test missing version
    result = resolve_version_with_hash_support("poemAI-ch/poemai-lambdas#nonexistent_lambda", repo_versions, "NonExistentVersion")
    assert result is None
    
    result = resolve_version_with_hash_support("poemAI-ch/nonexistent-repo", repo_versions, "SomeVersion")
    assert result is None
