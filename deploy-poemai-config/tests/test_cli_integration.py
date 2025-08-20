import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


class TestCLIIntegration:
    """Test command-line interface integration"""

    def test_help_output(self):
        """Test that --help shows all expected arguments"""
        script_path = Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"

        result = subprocess.run(
            [sys.executable, str(script_path), "--help"], capture_output=True, text=True
        )

        assert result.returncode == 0
        help_text = result.stdout

        # Check for key arguments
        assert "--environment" in help_text
        assert "--target-environment" in help_text
        assert "--lambda-function-name" in help_text
        assert "--temporary-corpus-key" in help_text
        assert "--temporary-corpus-key-ttl-hours" in help_text
        assert "--test-bot-url-template" in help_text
        assert "--version-id" in help_text
        assert "--project-root-path" in help_text

    def test_minimal_required_args(self):
        """Test script with minimal required arguments (mocked with environment variables)"""
        script_path = Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"

        # Set mock AWS credentials to avoid boto3 credential errors
        env = {
            **dict(os.environ),
            "AWS_ACCESS_KEY_ID": "test_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret",
            "AWS_DEFAULT_REGION": "us-east-1",
        }

        # Create a simple mock environment structure
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_keys_dir = Path(tmpdir) / "environments" / "test" / "corpus_keys"
            corpus_keys_dir.mkdir(parents=True)

            # Create a simple config
            test_config = {
                "pk": "CORPUS_KEY#test",
                "sk": "ASSISTANT_ID#test",
                "assistant_id": "test",
                "corpus_key": "test",
            }

            with open(corpus_keys_dir / "test.yaml", "w") as f:
                yaml.dump(test_config, f)

            # Run with mock AWS credentials - it will fail at Lambda invoke but that's expected
            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--environment",
                    "test",
                    "--lambda-function-name",
                    "test-function",
                    "--project-root-path",
                    tmpdir,
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            # Should fail at Lambda invocation (expected since we can't mock that in subprocess)
            # but should successfully process the config file first
            assert "Object 0:" in result.stderr
            assert '"assistant_id": "test"' in result.stderr

    def test_temporary_corpus_key_auto_generation(self):
        """Test automatic temporary corpus key generation"""
        script_path = Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"

        # Set mock AWS credentials
        env = {
            **dict(os.environ),
            "AWS_ACCESS_KEY_ID": "test_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret",
            "AWS_DEFAULT_REGION": "us-east-1",
        }

        # Create a simple mock environment structure
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_keys_dir = (
                Path(tmpdir) / "environments" / "staging" / "corpus_keys" / "TEST_BOT"
            )
            corpus_keys_dir.mkdir(parents=True)

            # Create a simple config
            test_config = {
                "pk": "CORPUS_KEY#TEST_BOT",
                "sk": "ASSISTANT_ID#test",
                "assistant_id": "test",
                "corpus_key": "TEST_BOT",
            }

            with open(corpus_keys_dir / "test.yaml", "w") as f:
                yaml.dump(test_config, f)

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--environment",
                    "staging",
                    "--lambda-function-name",
                    "test-function",
                    "--project-root-path",
                    tmpdir,
                    "--temporary-corpus-key",
                    "auto",
                    "--temporary-corpus-key-ttl-hours",
                    "48",
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            # Should process the auto generation and show in logs
            assert "Generated automatic temporary corpus key: TEMP_" in result.stderr
            assert (
                "Successfully transformed 1 objects for temporary deployment"
                in result.stderr
            )

    def test_missing_required_args(self):
        """Test script fails gracefully with missing required arguments"""
        script_path = Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"

        # Test missing environment
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--lambda-function-name",
                "test-function",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "required" in result.stderr.lower()

        # Test missing lambda function name
        result = subprocess.run(
            [sys.executable, str(script_path), "--environment", "test"],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "required" in result.stderr.lower()

    def test_url_template_generation_output(self):
        """Test URL template generates proper output"""
        script_path = Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"

        # Set mock AWS credentials
        env = {
            **dict(os.environ),
            "AWS_ACCESS_KEY_ID": "test_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret",
            "AWS_DEFAULT_REGION": "us-east-1",
        }

        # Create a simple mock environment structure
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_keys_dir = (
                Path(tmpdir) / "environments" / "staging" / "corpus_keys" / "TEST_BOT"
            )
            corpus_keys_dir.mkdir(parents=True)

            # Create a simple config
            test_config = {
                "pk": "CORPUS_KEY#TEST_BOT",
                "sk": "ASSISTANT_ID#test",
                "assistant_id": "test",
                "corpus_key": "TEST_BOT",
            }

            with open(corpus_keys_dir / "test.yaml", "w") as f:
                yaml.dump(test_config, f)

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--environment",
                    "staging",
                    "--lambda-function-name",
                    "test-function",
                    "--project-root-path",
                    tmpdir,
                    "--temporary-corpus-key",
                    "TEMP_TEST123",
                    "--test-bot-url-template",
                    "https://app.staging.poemai.ch/ui/town_bot/app/{corpus_key}/",
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            # Check for URL generation in output (before Lambda failure)
            assert (
                "Test Bot URL: https://app.staging.poemai.ch/ui/town_bot/app/TEMP_TEST123/"
                in result.stderr
            )
            # Check for GitHub Actions notice
            assert (
                "::notice title=Test Bot URL::🔗 https://app.staging.poemai.ch/ui/town_bot/app/TEMP_TEST123/"
                in result.stdout
            )

    def test_version_id_parameter(self):
        """Test version ID parameter functionality"""
        script_path = Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"

        # Set mock AWS credentials
        env = {
            **dict(os.environ),
            "AWS_ACCESS_KEY_ID": "test_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret",
            "AWS_DEFAULT_REGION": "us-east-1",
        }

        # Create a temporary environment structure
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_keys_dir = Path(tmpdir) / "environments" / "test" / "corpus_keys"
            corpus_keys_dir.mkdir(parents=True)

            # Create a test config file
            test_config = {
                "pk": "CORPUS_KEY#test",
                "sk": "ASSISTANT_ID#test",
                "assistant_id": "test",
                "corpus_key": "test",
            }

            with open(corpus_keys_dir / "test.yaml", "w") as f:
                yaml.dump(test_config, f)

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--environment",
                    "test",
                    "--lambda-function-name",
                    "test-function",
                    "--project-root-path",
                    tmpdir,
                    "--version-id",
                    "v1.2.3",
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            # Check that version ID appears in the object output (before Lambda failure)
            assert '"version_id": "v1.2.3"' in result.stderr
            assert '"_version_id": "v1.2.3"' in result.stderr


class TestErrorScenarios:
    """Test error scenarios and exit conditions"""

    def test_missing_pk_sk_validation(self, tmpdir):
        """Test validation fails for objects missing pk or sk"""
        # Create a temporary environment with invalid config
        tempdir = Path(tmpdir)
        corpus_keys_dir = tempdir / "environments" / "test" / "corpus_keys"
        corpus_keys_dir.mkdir(parents=True)

        # Create config missing pk
        invalid_config = {
            "sk": "ASSISTANT_ID#test",
            "assistant_id": "test",
            # Missing pk
        }

        with open(corpus_keys_dir / "invalid.yaml", "w") as f:
            yaml.dump(invalid_config, f)

        script_path = Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--environment",
                "test",
                "--lambda-function-name",
                "test-function",
                "--project-root-path",
                str(tempdir),
            ],
            capture_output=True,
            text=True,
        )

        # Should exit with error code
        assert result.returncode == 1
        assert "does not have a primary key" in result.stderr

    def test_lambda_function_error_response(self):
        """Test handling of Lambda function error responses"""
        # This test mainly checks that the error code path exists
        # Since we can't easily mock Lambda responses in subprocess calls
        script_path = Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"

        # Set mock AWS credentials
        env = {
            **dict(os.environ),
            "AWS_ACCESS_KEY_ID": "test_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret",
            "AWS_DEFAULT_REGION": "us-east-1",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_keys_dir = Path(tmpdir) / "environments" / "test" / "corpus_keys"
            corpus_keys_dir.mkdir(parents=True)

            test_config = {
                "pk": "CORPUS_KEY#test",
                "sk": "ASSISTANT_ID#test",
                "assistant_id": "test",
                "corpus_key": "test",
            }

            with open(corpus_keys_dir / "test.yaml", "w") as f:
                yaml.dump(test_config, f)

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--environment",
                    "test",
                    "--lambda-function-name",
                    "test-function",
                    "--project-root-path",
                    tmpdir,
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            # Will fail at Lambda invocation stage, which is expected
            assert result.returncode == 1
            assert "Failed to invoke lambda function" in result.stderr

    @patch("deploy_config_with_lambda_call.gather_json_representations")
    def test_lambda_invocation_exception(self, mock_gather):
        """Test handling of Lambda invocation exceptions"""
        mock_gather.return_value = [
            {
                "pk": "CORPUS_KEY#test",
                "sk": "ASSISTANT_ID#test",
                "assistant_id": "test",
                "corpus_key": "test",
            }
        ]

        with patch("deploy_config_with_lambda_call.boto3") as mock_boto3:
            mock_lambda_client = MagicMock()
            mock_boto3.client.return_value = mock_lambda_client
            # Mock Lambda invocation exception
            mock_lambda_client.invoke.side_effect = Exception("Network error")

            script_path = (
                Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--environment",
                    "test",
                    "--lambda-function-name",
                    "test-function",
                ],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 1
            assert "Failed to invoke lambda function" in result.stderr

    def test_temporary_corpus_key_validation_failure(self):
        """Test that the transformation actually works correctly with different source corpus keys"""
        script_path = Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"

        # Set mock AWS credentials
        env = {
            **dict(os.environ),
            "AWS_ACCESS_KEY_ID": "test_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret",
            "AWS_DEFAULT_REGION": "us-east-1",
        }

        # Create objects with different corpus keys
        # The transformation should actually succeed and give them all the same temporary corpus key
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_keys_dir = Path(tmpdir) / "environments" / "test" / "corpus_keys"
            corpus_keys_dir.mkdir(parents=True)

            # Create configs with different original corpus keys
            config1 = {
                "pk": "CORPUS_KEY#bot1",
                "sk": "ASSISTANT_ID#test1",
                "assistant_id": "test1",
                "corpus_key": "bot1",  # Different original corpus key
            }

            config2 = {
                "pk": "CORPUS_KEY#bot2",
                "sk": "ASSISTANT_ID#test2",
                "assistant_id": "test2",
                "corpus_key": "bot2",  # Different original corpus key
            }

            with open(corpus_keys_dir / "config1.yaml", "w") as f:
                yaml.dump(config1, f)

            with open(corpus_keys_dir / "config2.yaml", "w") as f:
                yaml.dump(config2, f)

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--environment",
                    "test",
                    "--lambda-function-name",
                    "test-function",
                    "--project-root-path",
                    tmpdir,
                    "--temporary-corpus-key",
                    "TEMP_SUCCESS",
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            # Should succeed because transformation gives both objects the same temporary corpus key
            # The failure will be at Lambda invocation stage, which is expected
            assert (
                "Successfully transformed 2 objects for temporary deployment"
                in result.stderr
            )
            assert '"corpus_key": "TEMP_SUCCESS"' in result.stderr
            assert result.returncode == 1  # Fails at Lambda stage, not at validation

    def test_target_environment_cross_deployment(self):
        """Test cross-deployment with target-environment parameter"""
        script_path = Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"

        # Set mock AWS credentials
        env = {
            **dict(os.environ),
            "AWS_ACCESS_KEY_ID": "test_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret",
            "AWS_DEFAULT_REGION": "us-east-1",
        }

        # Create production environment structure
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_keys_dir = (
                Path(tmpdir)
                / "environments"
                / "production"
                / "corpus_keys"
                / "PROD_BOT"
            )
            corpus_keys_dir.mkdir(parents=True)

            # Create production config
            test_config = {
                "pk": "CORPUS_KEY#PROD_BOT",
                "sk": "ASSISTANT_ID#prod_assistant",
                "assistant_id": "prod_assistant",
                "corpus_key": "PROD_BOT",
                "name": "Production Assistant",
            }

            with open(corpus_keys_dir / "assistant.yaml", "w") as f:
                yaml.dump(test_config, f)

            # Test cross-deployment: production config to staging
            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--environment",
                    "production",
                    "--target-environment",
                    "staging",
                    "--lambda-function-name",
                    "staging-function",
                    "--project-root-path",
                    tmpdir,
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            # Should show cross-deployment logging
            assert (
                "Cross-deployment: Loading config from 'production' environment, deploying to 'staging' environment"
                in result.stderr
            )

            # Should load production config
            assert '"name": "Production Assistant"' in result.stderr
            assert '"corpus_key": "PROD_BOT"' in result.stderr

            # Will fail at Lambda stage (expected), but should process config correctly
            assert result.returncode == 1

    def test_target_environment_same_as_source(self):
        """Test that empty target-environment defaults to source environment"""
        script_path = Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"

        # Set mock AWS credentials
        env = {
            **dict(os.environ),
            "AWS_ACCESS_KEY_ID": "test_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret",
            "AWS_DEFAULT_REGION": "us-east-1",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_keys_dir = (
                Path(tmpdir) / "environments" / "staging" / "corpus_keys" / "TEST_BOT"
            )
            corpus_keys_dir.mkdir(parents=True)

            test_config = {
                "pk": "CORPUS_KEY#TEST_BOT",
                "sk": "ASSISTANT_ID#test",
                "assistant_id": "test",
                "corpus_key": "TEST_BOT",
            }

            with open(corpus_keys_dir / "test.yaml", "w") as f:
                yaml.dump(test_config, f)

            # Test without target-environment (should default to source)
            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--environment",
                    "staging",
                    "--lambda-function-name",
                    "test-function",
                    "--project-root-path",
                    tmpdir,
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            # Should show standard deployment logging
            assert (
                "Standard deployment: Using 'staging' environment for both source and target"
                in result.stderr
            )
            assert result.returncode == 1  # Fails at Lambda stage, not at parsing

    def test_validation_skipped_for_temporary_corpus_key_cli(self):
        """Test that CLI properly skips pk/sk validation for temporary corpus key deployments"""
        script_path = Path(__file__).parent.parent / "deploy_config_with_lambda_call.py"

        # Set mock AWS credentials
        env = {
            **dict(os.environ),
            "AWS_ACCESS_KEY_ID": "test_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret",
            "AWS_DEFAULT_REGION": "us-east-1",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_keys_dir = (
                Path(tmpdir) / "environments" / "staging" / "corpus_keys" / "TEST_BOT"
            )
            corpus_keys_dir.mkdir(parents=True)

            # Create config that will have pk/sk removed by transformation
            test_config = {
                "pk": "CORPUS_KEY#TEST_BOT",
                "sk": "ASSISTANT_ID#test_assistant",
                "assistant_id": "test_assistant",
                "corpus_key": "TEST_BOT",
                "name": "Test Assistant",
            }

            with open(corpus_keys_dir / "assistant.yaml", "w") as f:
                yaml.dump(test_config, f)

            # Run with temporary corpus key
            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--environment",
                    "staging",
                    "--lambda-function-name",
                    "test-function",
                    "--project-root-path",
                    tmpdir,
                    "--temporary-corpus-key",
                    "TEMP_VALIDATION_TEST",
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            # Should show validation being skipped
            assert (
                "Skipping pk/sk validation for temporary corpus key deployment"
                in result.stderr
            )

            # Should show successful transformation
            assert (
                "Successfully transformed 1 objects for temporary deployment"
                in result.stderr
            )

            # Should show temporary deployment preparation
            assert (
                "Temporary deployment prepared with corpus key: TEMP_VALIDATION_TEST"
                in result.stderr
            )

            # Should NOT show pk/sk validation errors
            assert "does not have a primary key" not in result.stderr
            assert "does not have a sort key" not in result.stderr

            # Should fail at Lambda invocation (expected in test), not at validation
            assert result.returncode == 1


if __name__ == "__main__":
    pytest.main([__file__])
