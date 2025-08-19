import logging
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from deploy_with_lambda_call import deploy, do_dump_graph, do_dump, resolve_version_with_hash_support

_logger = logging.getLogger(__name__)


def test_deploy(tmpdir):

    tempdir = Path(tmpdir)
    environment = "devops"
    envdir = tempdir / environment

    envdir.mkdir(parents=True, exist_ok=True)

    with patch("deploy_with_lambda_call.boto3") as boto3_mock:

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
        "deploy_with_lambda_call.boto3", name="boto3_mock"
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


def test_compare_stack_names():
    """Test the stack name comparison function."""
    from deploy_with_lambda_call import compare_stack_names
    
    # Test exact match
    assert compare_stack_names("stack-two", "stack-two") == True
    
    # Test with environment suffix
    assert compare_stack_names("stack-two-development", "stack-two") == True
    assert compare_stack_names("stack-two", "stack-two-development") == True
    assert compare_stack_names("stack-two-development", "stack-two-development") == True
    
    # Test non-match
    assert compare_stack_names("stack-one", "stack-two") == False
    assert compare_stack_names("stack-one-development", "stack-two") == False


def test_stack_filtering_single_stack(tmpdir, caplog):
    """Test that single stack filtering works correctly."""
    tempdir = Path(tmpdir)
    environment = "development"  # Use valid environment from ENVIRONMENT_PRIORITY
    envdir = tempdir / environment

    envdir.mkdir(parents=True, exist_ok=True)

    # Create a simple stacks configuration with multiple stacks
    stacks = {
        "environment": environment,
        "globals": {
            "SomeGlobal": "test-value"
        },
        "stacks": [
            {
                "stack_name": "stack-one",
                "template_file": "stack_one.yaml",
                "parameters": {
                    "Environment": {"$ref": "Environment"}
                }
            },
            {
                "stack_name": "stack-two", 
                "template_file": "stack_two.yaml",
                "parameters": {
                    "Environment": {"$ref": "Environment"}
                }
            },
            {
                "stack_name": "stack-three",
                "template_file": "stack_three.yaml", 
                "parameters": {
                    "Environment": {"$ref": "Environment"}
                }
            }
        ],
    }
    stacks_file = envdir / "stacks.yaml"
    with open(stacks_file, "w") as f:
        yaml.dump(stacks, f)

    # Create simple template files
    for stack_name in ["stack_one", "stack_two", "stack_three"]:
        stack_template = {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Parameters": {
                "Environment": {
                    "Type": "String"
                }
            },
            "Resources": {
                "TestResource": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {
                        "BucketName": f"{stack_name}-bucket"
                    }
                }
            }
        }
        
        stack_template_file = envdir / f"{stack_name}.yaml"
        with open(stack_template_file, "w") as f:
            yaml.dump(stack_template, f)

    config = yaml.safe_load(open(stacks_file))
    
    # Test filtering for a specific stack
    with caplog.at_level(logging.DEBUG):  # Use DEBUG to see the filtering logs
        do_dump(config, stacks_file.as_posix(), environment, verbose=False, stack_name="stack-two")
    
    # Check that only one stack was processed
    summary_logs = [record.message for record in caplog.records if "Summary: Successfully processed" in record.message]
    assert len(summary_logs) == 1
    assert "1/1 templates" in summary_logs[0]
    
    # Check that the correct stack was processed
    stack_logs = [record.message for record in caplog.records if "✓" in record.message and "stack-two-development" in record.message]
    assert len(stack_logs) == 1
    
    # Ensure other stacks were NOT processed
    other_stack_logs = [record.message for record in caplog.records if "✓" in record.message and ("stack-one-development" in record.message or "stack-three-development" in record.message)]
    
    # Check that only one stack was processed
    summary_logs = [record.message for record in caplog.records if "Summary: Successfully processed" in record.message]
    assert len(summary_logs) == 1
    assert "1/1 templates" in summary_logs[0]
    
    # Check that the correct stack was processed
    stack_logs = [record.message for record in caplog.records if "✓" in record.message and "stack-two-development" in record.message]
    assert len(stack_logs) == 1
    
    # Ensure other stacks were NOT processed
    other_stack_logs = [record.message for record in caplog.records if "✓" in record.message and ("stack-one-development" in record.message or "stack-three-development" in record.message)]
    assert len(other_stack_logs) == 0


def test_stack_filtering_all_stacks(tmpdir, caplog):
    """Test that without stack filtering, all stacks are processed."""
    tempdir = Path(tmpdir)
    environment = "development"  # Use valid environment from ENVIRONMENT_PRIORITY
    envdir = tempdir / environment

    envdir.mkdir(parents=True, exist_ok=True)

    # Create a simple stacks configuration with multiple stacks
    stacks = {
        "environment": environment,
        "globals": {
            "SomeGlobal": "test-value"
        },
        "stacks": [
            {
                "stack_name": "stack-alpha",
                "template_file": "stack_alpha.yaml",
                "parameters": {
                    "Environment": {"$ref": "Environment"}
                }
            },
            {
                "stack_name": "stack-beta", 
                "template_file": "stack_beta.yaml",
                "parameters": {
                    "Environment": {"$ref": "Environment"}
                }
            }
        ],
    }
    stacks_file = envdir / "stacks.yaml"
    with open(stacks_file, "w") as f:
        yaml.dump(stacks, f)

    # Create simple template files
    for stack_name in ["stack_alpha", "stack_beta"]:
        stack_template = {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Parameters": {
                "Environment": {
                    "Type": "String"
                }
            },
            "Resources": {
                "TestResource": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {
                        "BucketName": f"{stack_name}-bucket"
                    }
                }
            }
        }
        
        stack_template_file = envdir / f"{stack_name}.yaml"
        with open(stack_template_file, "w") as f:
            yaml.dump(stack_template, f)

    config = yaml.safe_load(open(stacks_file))
    
    # Test without filtering (should process all stacks)
    with caplog.at_level(logging.INFO):
        do_dump(config, stacks_file.as_posix(), environment, verbose=False, stack_name=None)
    
    # Check that both stacks were processed
    summary_logs = [record.message for record in caplog.records if "Summary: Successfully processed" in record.message]
    assert len(summary_logs) == 1
    assert "2/2 templates" in summary_logs[0]
    
    # Check that both stacks were processed
    alpha_logs = [record.message for record in caplog.records if "✓" in record.message and "stack-alpha-development" in record.message]
    beta_logs = [record.message for record in caplog.records if "✓" in record.message and "stack-beta-development" in record.message]
    assert len(alpha_logs) == 1
    assert len(beta_logs) == 1


def test_stack_filtering_nonexistent_stack(tmpdir, caplog):
    """Test that filtering for a nonexistent stack shows helpful error message."""
    import pytest
    
    tempdir = Path(tmpdir)
    environment = "development"  # Use valid environment from ENVIRONMENT_PRIORITY
    envdir = tempdir / environment

    envdir.mkdir(parents=True, exist_ok=True)

    # Create a simple stacks configuration
    stacks = {
        "environment": environment,
        "globals": {},
        "stacks": [
            {
                "stack_name": "real-stack",
                "template_file": "real_stack.yaml",
                "parameters": {
                    "Environment": {"$ref": "Environment"}
                }
            }
        ],
    }
    stacks_file = envdir / "stacks.yaml"
    with open(stacks_file, "w") as f:
        yaml.dump(stacks, f)

    # Create template file
    stack_template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Parameters": {
            "Environment": {
                "Type": "String"
            }
        },
        "Resources": {
            "TestResource": {
                "Type": "AWS::S3::Bucket",
                "Properties": {
                    "BucketName": "real-stack-bucket"
                }
            }
        }
    }
    
    stack_template_file = envdir / "real_stack.yaml"
    with open(stack_template_file, "w") as f:
        yaml.dump(stack_template, f)

    config = yaml.safe_load(open(stacks_file))
    
    # Test filtering for a nonexistent stack should raise SystemExit
    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as exc_info:
            do_dump(config, stacks_file.as_posix(), environment, verbose=False, stack_name="nonexistent-stack")
    
    # Check that it exits with code 1
    assert exc_info.value.code == 1
    
    # Check that helpful error messages were logged
    error_logs = [record.message for record in caplog.records if record.levelname == "ERROR"]
    assert any("does not match any available stacks" in msg for msg in error_logs)
    assert any("real-stack" in msg for msg in error_logs)
    assert any("real-stack-development" in msg for msg in error_logs)


def test_stack_filtering_both_name_formats(tmpdir, caplog):
    """Test that both full stack names and base names work for filtering."""
    tempdir = Path(tmpdir)
    environment = "development"
    envdir = tempdir / environment

    envdir.mkdir(parents=True, exist_ok=True)

    # Create a simple stacks configuration
    stacks = {
        "environment": environment,
        "globals": {},
        "stacks": [
            {
                "stack_name": "test-stack-alpha",
                "template_file": "test_stack_alpha.yaml",
                "parameters": {
                    "Environment": {"$ref": "Environment"}
                }
            },
            {
                "stack_name": "test-stack-beta",
                "template_file": "test_stack_beta.yaml",
                "parameters": {
                    "Environment": {"$ref": "Environment"}
                }
            }
        ],
    }
    stacks_file = envdir / "stacks.yaml"
    with open(stacks_file, "w") as f:
        yaml.dump(stacks, f)

    # Create template files
    for stack_name in ["test_stack_alpha", "test_stack_beta"]:
        stack_template = {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Parameters": {
                "Environment": {
                    "Type": "String"
                }
            },
            "Resources": {
                "TestResource": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {
                        "BucketName": f"{stack_name}-bucket"
                    }
                }
            }
        }
        
        stack_template_file = envdir / f"{stack_name}.yaml"
        with open(stack_template_file, "w") as f:
            yaml.dump(stack_template, f)

    config = yaml.safe_load(open(stacks_file))
    
    # Test 1: Filter using base stack name (without environment suffix)
    caplog.clear()
    config1 = yaml.safe_load(open(stacks_file))  # Fresh config for each test
    with caplog.at_level(logging.INFO):
        do_dump(config1, stacks_file.as_posix(), environment, verbose=False, stack_name="test-stack-alpha")
    
    summary_logs = [record.message for record in caplog.records if "Summary: Successfully processed" in record.message]
    assert len(summary_logs) == 1
    assert "1/1 templates" in summary_logs[0]
    
    # Test 2: Filter using full stack name (with environment suffix)
    caplog.clear()
    config2 = yaml.safe_load(open(stacks_file))  # Fresh config for each test
    with caplog.at_level(logging.INFO):
        do_dump(config2, stacks_file.as_posix(), environment, verbose=False, stack_name="test-stack-beta-development")
    
    summary_logs = [record.message for record in caplog.records if "Summary: Successfully processed" in record.message]
    assert len(summary_logs) == 1
    assert "1/1 templates" in summary_logs[0]


def test_override_globals_file_functionality(tmpdir, caplog):
    """Test the --override-globals-file functionality."""
    tempdir = Path(tmpdir)
    environment = "development"
    envdir = tempdir / environment

    envdir.mkdir(parents=True, exist_ok=True)

    # Create a simple stacks configuration with a global variable
    stacks = {
        "environment": environment,
        "globals": {
            "TestVersion": "default-version-123",
            "Environment": environment,
        },
        "stacks": [
            {
                "stack_name": "test-stack",
                "template_file": "test_stack.yaml",
                "parameters": {
                    "Environment": {"$ref": "Environment"},
                    "Version": {"$ref": "TestVersion"}
                }
            }
        ],
    }
    stacks_file = envdir / "stacks.yaml"
    with open(stacks_file, "w") as f:
        yaml.dump(stacks, f)

    # Create a globals override file
    override_globals_file = tempdir / "override_globals.txt"
    with open(override_globals_file, "w") as f:
        f.write("TestVersion=overridden-version-456\n")
        f.write("AnotherVar=additional-value\n")

    # Create template file
    stack_template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Parameters": {
            "Environment": {"Type": "String"},
            "Version": {"Type": "String"}
        },
        "Resources": {
            "TestResource": {
                "Type": "AWS::S3::Bucket",
                "Properties": {
                    "BucketName": {"Fn::Sub": "test-bucket-${Version}"}
                }
            }
        }
    }
    
    stack_template_file = envdir / "test_stack.yaml"
    with open(stack_template_file, "w") as f:
        yaml.dump(stack_template, f)

    config = yaml.safe_load(open(stacks_file))
    
    # Test with override globals file
    from deploy_with_lambda_call import prepare_messages
    
    # Mock the override globals file loading by patching the load function
    with patch("deploy_with_lambda_call.load_globals_from_file") as mock_load:
        mock_load.return_value = {
            "TestVersion": "overridden-version-456",
            "AnotherVar": "additional-value"
        }
        
        with caplog.at_level(logging.DEBUG):
            # This should use the overridden values
            message_generations, dependency_graph = prepare_messages(config, stacks_file.as_posix())
        
        # Verify that load_globals_from_file was called
        mock_load.assert_called()
        
        # Check that the overridden version is used in the generated message
        messages = [msg for generation in message_generations for msg in generation]
        assert len(messages) == 1
        
        # The Version parameter should have the overridden value
        assert messages[0]["message"]["parameters"]["Version"] == "overridden-version-456"


def test_load_globals_from_file_functionality(tmpdir):
    """Test the load_globals_from_file function directly."""
    from deploy_with_lambda_call import load_globals_from_file
    
    tempdir = Path(tmpdir)
    
    # Create a globals file with different formats
    globals_file = tempdir / "test_globals.txt"
    with open(globals_file, "w") as f:
        f.write("# This is a comment\n")
        f.write("simple_var=simple_value\n")
        f.write("version_var=abc123def456\n")
        f.write("  spaced_var  =  spaced_value  \n")  # Test whitespace handling
        f.write("\n")  # Empty line
        f.write("equals_in_value=key=value=pair\n")  # Multiple equals signs
    
    # Test loading the file
    result = load_globals_from_file(globals_file.as_posix())
    
    expected = {
        "simple_var": "simple_value",
        "version_var": "abc123def456", 
        "spaced_var": "spaced_value",
        "equals_in_value": "key=value=pair"
    }
    
    assert result == expected
    
    # Test with non-existent file
    result = load_globals_from_file("non_existent_file.txt")
    assert result == {}


def test_override_globals_file_functionality(tmpdir, caplog):
    """Test that --override-globals-file parameter works correctly."""
    from deploy_with_lambda_call import prepare_messages, load_config
    
    tempdir = Path(tmpdir)
    environment = "development"
    envdir = tempdir / environment

    envdir.mkdir(parents=True, exist_ok=True)

    # Create a basic stacks configuration with version variables
    stacks = {
        "environment": environment,
        "globals": {
            "TestLambdaVersion": {"$version": "poemAI-ch/test-repo#test_lambda"},
            "AnotherVersion": "default-version"
        },
        "stacks": [
            {
                "stack_name": "test-stack",
                "template_file": "test_stack.yaml",
                "parameters": {
                    "Environment": {"$ref": "Environment"},
                    "LambdaS3Key": {"$sub": "lambdas/test_lambda/${TestLambdaVersion}/test_lambda.zip"},
                    "AnotherParam": {"$ref": "AnotherVersion"}
                }
            }
        ],
    }
    stacks_file = envdir / "stacks.yaml"
    with open(stacks_file, "w") as f:
        yaml.dump(stacks, f)

    # Create a template file
    stack_template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Parameters": {
            "Environment": {"Type": "String"},
            "LambdaS3Key": {"Type": "String"},
            "AnotherParam": {"Type": "String"}
        },
        "Resources": {
            "TestResource": {
                "Type": "AWS::S3::Bucket",
                "Properties": {
                    "BucketName": "test-bucket"
                }
            }
        }
    }
    
    stack_template_file = envdir / "test_stack.yaml"
    with open(stack_template_file, "w") as f:
        yaml.dump(stack_template, f)

    # Create a versions file (like .poemai-upstream-versions.yaml)
    versions_file = tempdir / "versions.yaml"
    versions_data = {
        "versions": {
            "poemAI-ch/test-repo#test_lambda": "abcdef123456"
        }
    }
    with open(versions_file, "w") as f:
        yaml.dump(versions_data, f)

    # Create an override globals file (like devops_lambda_versions.txt)
    override_globals_file = tempdir / "override_globals.txt"
    with open(override_globals_file, "w") as f:
        f.write("TestLambdaVersion=override123456\n")
        f.write("AnotherVersion=overridden-value\n")

    # Test 1: Load config without override file (should use version from versions.yaml)
    config = load_config(str(stacks_file))
    config["repo_versions_file"] = "../versions.yaml"  # Relative to the stacks.yaml file
    
    message_generations, dependency_graph = prepare_messages(config, str(stacks_file))
    messages = [msg for generation in message_generations for msg in generation]
    
    # Should use version from versions.yaml
    test_message = next(msg for msg in messages if msg["message"]["stack_name"] == "test-stack-development")
    assert "lambdas/test_lambda/abcdef123456/test_lambda.zip" in test_message["message"]["parameters"]["LambdaS3Key"]
    assert test_message["message"]["parameters"]["AnotherParam"] == "default-version"

    # Test 2: Test with override globals file using the correct parameter name
    import argparse
    import sys
    from unittest.mock import patch
    from io import StringIO
    
    # Mock sys.argv to include the override globals file parameter
    test_args = ["deploy_with_lambda_call.py", "dump", str(stacks_file), "--override-globals-file", str(override_globals_file)]
    
    # Capture stdout to check for override messages
    captured_output = StringIO()
    
    with patch.object(sys, 'argv', test_args), patch.object(sys, 'stdout', captured_output):
        from deploy_with_lambda_call import main
        
        # Capture the output to verify override worked
        with caplog.at_level(logging.INFO):
            try:
                main()
            except SystemExit:
                pass  # main() calls sys.exit(), which is normal
    
    # Check captured output for override messages
    output = captured_output.getvalue()
    
    # The override should result in TestLambdaVersion being "override123456"
    assert "Using override global TestLambdaVersion: override123456" in output
    assert "Using override global AnotherVersion: overridden-value" in output


def test_deploy_fails_with_missing_dependencies(tmpdir):
    """Test that deployment fails hard when dependencies are missing."""
    import sys
    import time
    
    tempdir = Path(tmpdir)
    environment = "development"
    envdir = tempdir / environment

    envdir.mkdir(parents=True, exist_ok=True)

    with patch("deploy_with_lambda_call.boto3") as boto3_mock:
        lambda_client_mock = MagicMock()
        cf_client_mock = MagicMock()
        
        # Mock boto3 client creation
        def client_side_effect(service_name, *args, **kwargs):
            if service_name == "lambda":
                return lambda_client_mock
            elif service_name == "cloudformation":
                return cf_client_mock
            return MagicMock()
        
        boto3_mock.client.side_effect = client_side_effect

        # Set up lambda client mock
        lambda_client_mock.exceptions = MagicMock()
        class TooManyRequestsException(Exception):
            pass
        lambda_client_mock.exceptions.TooManyRequestsException = TooManyRequestsException

        # Mock successful lambda response for stack-a
        payload_content = '[{"status": "success"}]'
        payload_stream = BytesIO(payload_content.encode("utf-8"))
        payload_mock = MagicMock()
        payload_mock.read.return_value = payload_stream.read()
        lambda_client_mock.invoke.return_value = {"Payload": payload_mock}

        # Mock CloudFormation to report success for deployed stacks
        cf_client_mock.describe_stacks.return_value = {
            "Stacks": [{"StackStatus": "CREATE_COMPLETE"}]
        }

        # Create stacks configuration with dependencies
        # stack-b depends on stack-a, stack-c depends on stack-b
        stacks = {
            "environment": environment,
            "globals": {},
            "stacks": [
                {
                    "stack_name": "stack-a",
                    "template_file": "stack_a.yaml",
                    "parameters": {
                        "Environment": {"$ref": "Environment"}
                    }
                },
                {
                    "stack_name": "stack-b",
                    "template_file": "stack_b.yaml", 
                    "parameters": {
                        "Environment": {"$ref": "Environment"}
                    },
                    "dependencies": ["stack-a"]
                },
                {
                    "stack_name": "stack-c",
                    "template_file": "stack_c.yaml",
                    "parameters": {
                        "Environment": {"$ref": "Environment"}
                    }, 
                    "dependencies": ["stack-b"]
                }
            ],
        }
        stacks_file = envdir / "stacks.yaml"
        with open(stacks_file, "w") as f:
            yaml.dump(stacks, f)

        # Create template files for all stacks
        for stack_name in ["stack_a", "stack_b", "stack_c"]:
            stack_template = {
                "AWSTemplateFormatVersion": "2010-09-09",
                "Parameters": {
                    "Environment": {"Type": "String"}
                },
                "Resources": {
                    "TestResource": {
                        "Type": "AWS::S3::Bucket",
                        "Properties": {
                            "BucketName": f"{stack_name}-bucket"
                        }
                    }
                }
            }
            
            stack_template_file = envdir / f"{stack_name}.yaml"
            with open(stack_template_file, "w") as f:
                yaml.dump(stack_template, f)

        # Mock a scenario where stack-a fails to deploy by making lambda throw an exception for stack-a
        def mock_invoke_side_effect(*args, **kwargs):
            payload = kwargs.get('Payload', '')
            if 'stack-a-development' in payload:
                # Simulate failure for stack-a
                raise Exception("Simulated deployment failure for stack-a")
            else:
                # For other stacks, return success
                payload_content = '[{"status": "success"}]'
                payload_stream = BytesIO(payload_content.encode("utf-8"))
                payload_mock = MagicMock()
                payload_mock.read.return_value = payload_stream.read()
                return {"Payload": payload_mock}
        
        lambda_client_mock.invoke.side_effect = mock_invoke_side_effect

        config = yaml.safe_load(open(stacks_file))
        
        # Test that deployment fails when stack-a fails and stack-b/c can't proceed
        with pytest.raises(ValueError) as exc_info:
            deploy(
                "test-lambda-function",
                config,
                stacks_file.as_posix(),
                stack_name=None
            )
        
        # The error should mention failed dependencies
        error_message = str(exc_info.value)
        assert "Cannot deploy" in error_message and "dependencies have not been successfully deployed" in error_message
        
        # Should specifically mention the missing dependency
        assert "stack-a-development" in error_message
