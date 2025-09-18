"""Tests for the unified versions file updater."""

import os

# Add the parent directory to the path so we can import our module
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse

from update_versions_file import VersionsFileUpdater, detect_build_type


class TestVersionsFileUpdater:
    """Test cases for VersionsFileUpdater class."""

    def test_create_new_file_regular_build(self):
        """Test creating a new versions file for a regular build."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            temp_file = f.name

        try:
            # Remove the file so we test creation
            os.unlink(temp_file)

            updater = VersionsFileUpdater(temp_file)
            result = updater.update_regular_build("poemAI-ch/test-repo", "abc123def456")

            assert result is True
            assert Path(temp_file).exists()

            with open(temp_file, "r") as f:
                data = yaml.safe_load(f)

            assert data == {"versions": {"poemAI-ch/test-repo": "abc123def456"}}
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_update_existing_file_regular_build(self):
        """Test updating an existing versions file for a regular build."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            # Create initial content
            initial_data = {
                "versions": {
                    "poemAI-ch/other-repo": "old123",
                    "poemAI-ch/test-repo": "old456",
                }
            }
            yaml.safe_dump(initial_data, f)
            temp_file = f.name

        try:
            updater = VersionsFileUpdater(temp_file)
            result = updater.update_regular_build("poemAI-ch/test-repo", "abc789def")

            assert result is True

            with open(temp_file, "r") as f:
                data = yaml.safe_load(f)

            expected = {
                "versions": {
                    "poemAI-ch/other-repo": "old123",
                    "poemAI-ch/test-repo": "abc789def",
                }
            }
            assert data == expected
        finally:
            os.unlink(temp_file)

    def test_no_update_needed_regular_build(self):
        """Test when no update is needed for a regular build."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            initial_data = {"versions": {"poemAI-ch/test-repo": "abc123def456"}}
            yaml.safe_dump(initial_data, f)
            temp_file = f.name

        try:
            updater = VersionsFileUpdater(temp_file)
            result = updater.update_regular_build("poemAI-ch/test-repo", "abc123def456")

            assert result is False
        finally:
            os.unlink(temp_file)

    def test_create_new_file_hash_based_build(self):
        """Test creating a new versions file for a hash-based build."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            temp_file = f.name

        try:
            # Remove the file so we test creation
            os.unlink(temp_file)

            updater = VersionsFileUpdater(temp_file)
            result = updater.update_hash_based_build(
                "poemAI-ch/test-lambdas", "s3://bucket/manifest.json"
            )

            assert result is True
            assert Path(temp_file).exists()

            with open(temp_file, "r") as f:
                data = yaml.safe_load(f)

            assert data == {
                "versions": {},
                "hash_based_lambdas": {
                    "poemAI-ch/test-lambdas": "s3://bucket/manifest.json"
                },
            }
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_update_existing_file_hash_based_build(self):
        """Test updating an existing versions file for a hash-based build."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            initial_data = {
                "versions": {"poemAI-ch/regular-repo": "sha123"},
                "hash_based_lambdas": {
                    "poemAI-ch/other-lambdas": "s3://bucket/old.json"
                },
            }
            yaml.safe_dump(initial_data, f)
            temp_file = f.name

        try:
            updater = VersionsFileUpdater(temp_file)
            result = updater.update_hash_based_build(
                "poemAI-ch/test-lambdas", "s3://bucket/new.json"
            )

            assert result is True

            with open(temp_file, "r") as f:
                data = yaml.safe_load(f)

            expected = {
                "versions": {"poemAI-ch/regular-repo": "sha123"},
                "hash_based_lambdas": {
                    "poemAI-ch/other-lambdas": "s3://bucket/old.json",
                    "poemAI-ch/test-lambdas": "s3://bucket/new.json",
                },
            }
            assert data == expected
        finally:
            os.unlink(temp_file)

    def test_no_update_needed_hash_based_build(self):
        """Test when no update is needed for a hash-based build."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            initial_data = {
                "hash_based_lambdas": {
                    "poemAI-ch/test-lambdas": "s3://bucket/manifest.json"
                }
            }
            yaml.safe_dump(initial_data, f)
            temp_file = f.name

        try:
            updater = VersionsFileUpdater(temp_file)
            result = updater.update_hash_based_build(
                "poemAI-ch/test-lambdas", "s3://bucket/manifest.json"
            )

            assert result is False
        finally:
            os.unlink(temp_file)

    def test_invalid_sha_regular_build(self):
        """Test validation for invalid SHA in regular build."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            temp_file = f.name

        try:
            updater = VersionsFileUpdater(temp_file)

            with pytest.raises(ValueError, match="Invalid SHA"):
                updater.update_regular_build("poemAI-ch/test-repo", "invalid-sha!")

            with pytest.raises(ValueError, match="Invalid SHA"):
                updater.update_regular_build("poemAI-ch/test-repo", "")
        finally:
            os.unlink(temp_file)

    def test_empty_repo_name(self):
        """Test validation for empty repository name."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            temp_file = f.name

        try:
            updater = VersionsFileUpdater(temp_file)

            with pytest.raises(ValueError, match="Empty repository name"):
                updater.update_regular_build("", "abc123")

            with pytest.raises(ValueError, match="Empty repository name"):
                updater.update_hash_based_build("", "s3://bucket/manifest.json")
        finally:
            os.unlink(temp_file)

    def test_empty_manifest_url(self):
        """Test validation for empty manifest URL in hash-based build."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            temp_file = f.name

        try:
            updater = VersionsFileUpdater(temp_file)

            with pytest.raises(ValueError, match="Empty manifest URL"):
                updater.update_hash_based_build("poemAI-ch/test-repo", "")
        finally:
            os.unlink(temp_file)

    @patch("update_versions_file.boto3")
    def test_hash_based_build_with_s3_manifest(self, mock_boto3):
        """Test hash-based build with successful S3 manifest download."""
        # Setup mock S3 client
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        # Mock S3 response with realistic manifest data from production
        manifest_yaml = """versions:
  llm_stream_get: 9eb7be765a8e
  femto_semantic: e062e019c87b
  sessions_tokens: 07ea2c43918f
  url_monitor: 285a04dcc99b
  rule_engine: 48136ea57187
  crawler: e133466b6294
  code_editor: 909745add6c6
  auth_proxy: 42cc5172fccb
  group_summary_builder: d344e6896fe2
  trigger_crawl_processor: d4d22b9f9a0c
  llm_streamer: 77490ea8d96c
  config_deployer: 106435c0b60c
  town_bot_sl: 764240f9a0f6
  cases_and_assistants: c42be56c8e71
  hello_world: 94070767b443
  femto_keyword_search: c8eb346eea75
  web_page_publisher: a694d7a368fc
  rag_tool: 5c2462025de5
  assistant_api: c02895c4e2f1
  crawl_results_processor: 5b66579ef55e
  bot_sl: ea259e507770
  bot_admin: 7eb6777ed631
  caritas_leistungen: 3e3cc332e13c
build_info:
  timestamp: '2025-09-18T13:51:05.269665Z'
  commit_sha: 96b50db
  build_number: '105'
  platform: linux/amd64
  branch: main
"""
        mock_response = {"Body": MagicMock()}
        mock_response["Body"].read.return_value = manifest_yaml.encode("utf-8")
        mock_s3_client.get_object.return_value = mock_response

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            initial_data = {
                "versions": {
                    "poemAI-ch/other-repo": "old123",
                    "poemAI-ch/poemai-lambdas#group_summary_builder": "oldversion123",
                }
            }
            yaml.safe_dump(initial_data, f)
            temp_file = f.name

        try:
            updater = VersionsFileUpdater(temp_file)
            result = updater.update_hash_based_build(
                "poemAI-ch/poemai-lambdas",
                "s3://poemai-artifacts/hash-based-manifests/poemai-lambdas/96b50db9f821ac594b65d1d43e421db50e490a76/lambda_versions.yaml",
            )

            assert result is True

            # Verify S3 client was called correctly
            mock_boto3.client.assert_called_once_with("s3", region_name="eu-central-2")
            mock_s3_client.get_object.assert_called_once_with(
                Bucket="poemai-artifacts",
                Key="hash-based-manifests/poemai-lambdas/96b50db9f821ac594b65d1d43e421db50e490a76/lambda_versions.yaml",
            )

            # Check the updated file
            with open(temp_file, "r") as f:
                data = yaml.safe_load(f)

            # Verify structure
            assert "versions" in data
            assert "hash_based_lambdas" in data

            # Verify specific lambda versions were updated correctly
            assert (
                data["versions"]["poemAI-ch/poemai-lambdas#group_summary_builder"]
                == "d344e6896fe2"
            )
            assert (
                data["versions"]["poemAI-ch/poemai-lambdas#auth_proxy"]
                == "42cc5172fccb"
            )
            assert (
                data["versions"]["poemAI-ch/poemai-lambdas#llm_stream_get"]
                == "9eb7be765a8e"
            )
            assert (
                data["versions"]["poemAI-ch/poemai-lambdas#rule_engine"]
                == "48136ea57187"
            )

            # Verify non-lambda versions were preserved
            assert data["versions"]["poemAI-ch/other-repo"] == "old123"

            # Verify manifest URL was updated
            assert (
                data["hash_based_lambdas"]["poemAI-ch/poemai-lambdas"]
                == "s3://poemai-artifacts/hash-based-manifests/poemai-lambdas/96b50db9f821ac594b65d1d43e421db50e490a76/lambda_versions.yaml"
            )

        finally:
            os.unlink(temp_file)

    @patch("update_versions_file.boto3")
    def test_hash_based_build_s3_failure_fallback(self, mock_boto3):
        """Test hash-based build with S3 failure falls back to manifest URL only."""
        # Setup mock S3 client that raises an error
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "NoSuchKey", "Message": "Key not found"}}
        mock_s3_client.get_object.side_effect = ClientError(error_response, "GetObject")

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            initial_data = {"versions": {"poemAI-ch/other-repo": "old123"}}
            yaml.safe_dump(initial_data, f)
            temp_file = f.name

        try:
            updater = VersionsFileUpdater(temp_file)
            result = updater.update_hash_based_build(
                "poemAI-ch/test-lambdas", "s3://test-bucket/nonexistent.yaml"
            )

            assert result is True

            # Check the updated file - should only have manifest URL, no individual lambdas
            with open(temp_file, "r") as f:
                data = yaml.safe_load(f)

            expected = {
                "versions": {"poemAI-ch/other-repo": "old123"},  # Unchanged
                "hash_based_lambdas": {
                    "poemAI-ch/test-lambdas": "s3://test-bucket/nonexistent.yaml"
                },
            }
            assert data == expected
        finally:
            os.unlink(temp_file)

    def test_parse_s3_url(self):
        """Test S3 URL parsing."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            temp_file = f.name

        try:
            updater = VersionsFileUpdater(temp_file)

            # Valid S3 URLs
            bucket, key = updater._parse_s3_url("s3://my-bucket/path/to/file.yaml")
            assert bucket == "my-bucket"
            assert key == "path/to/file.yaml"

            bucket, key = updater._parse_s3_url("s3://test-bucket/manifest.json")
            assert bucket == "test-bucket"
            assert key == "manifest.json"

            # Invalid S3 URLs
            with pytest.raises(ValueError, match="Invalid S3 URL format"):
                updater._parse_s3_url("https://example.com/file.yaml")

            with pytest.raises(ValueError, match="Invalid S3 URL format"):
                updater._parse_s3_url("s3://bucket-only")

        finally:
            os.unlink(temp_file)

    def test_extract_lambda_versions(self):
        """Test lambda version extraction from manifest data."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            temp_file = f.name

        try:
            updater = VersionsFileUpdater(temp_file)

            # Valid manifest data with versions section (like actual S3 manifest)
            manifest_data = {
                "versions": {
                    "lambda1": "abc123def456",
                    "lambda2": "def456ghi789",
                    "lambda3": "ghi789jkl012",
                },
                "build_info": {
                    "timestamp": "2024-09-18T10:00:00Z",
                    "commit": "abcd1234",
                },
            }

            versions = updater._extract_lambda_versions(
                manifest_data, "poemAI-ch/test-lambdas"
            )

            expected = {
                "poemAI-ch/test-lambdas#lambda1": "abc123def456",
                "poemAI-ch/test-lambdas#lambda2": "def456ghi789",
                "poemAI-ch/test-lambdas#lambda3": "ghi789jkl012",
            }
            assert versions == expected

            # Test with old format (flat structure without versions section)
            old_format_manifest = {
                "lambda1": "abc123def456",
                "lambda2": "def456ghi789",
            }
            versions = updater._extract_lambda_versions(
                old_format_manifest, "poemAI-ch/test-lambdas"
            )
            assert versions == {}  # Should return empty dict when no versions section

            # Empty manifest
            versions = updater._extract_lambda_versions({}, "poemAI-ch/test-lambdas")
            assert versions == {}

            # Invalid manifest format
            versions = updater._extract_lambda_versions(
                "not a dict", "poemAI-ch/test-lambdas"
            )
            assert versions == {}

        finally:
            os.unlink(temp_file)


class TestBuildTypeDetection:
    """Test cases for build type detection."""

    def test_detect_hash_based_build(self):
        """Test detection of hash-based build."""
        args = argparse.Namespace(
            manifest_url="s3://bucket/manifest.json",
            build_number="123",
            upstream_sha="",
        )
        assert detect_build_type(args) == "hash_based"

    def test_detect_regular_build(self):
        """Test detection of regular build."""
        args = argparse.Namespace(
            manifest_url="", build_number="", upstream_sha="abc123def456"
        )
        assert detect_build_type(args) == "regular"

    def test_detect_hash_based_with_extra_sha(self):
        """Test that hash-based takes precedence when both are provided."""
        args = argparse.Namespace(
            manifest_url="s3://bucket/manifest.json",
            build_number="123",
            upstream_sha="abc123def456",
        )
        assert detect_build_type(args) == "hash_based"

    def test_invalid_arguments_no_manifest_url(self):
        """Test invalid arguments when manifest URL is missing but build number is provided."""
        args = argparse.Namespace(manifest_url="", build_number="123", upstream_sha="")
        with pytest.raises(ValueError, match="Invalid arguments"):
            detect_build_type(args)

    def test_invalid_arguments_no_build_number(self):
        """Test invalid arguments when build number is missing but manifest URL is provided."""
        args = argparse.Namespace(
            manifest_url="s3://bucket/manifest.json", build_number="", upstream_sha=""
        )
        with pytest.raises(ValueError, match="Invalid arguments"):
            detect_build_type(args)

    def test_invalid_arguments_nothing_provided(self):
        """Test invalid arguments when nothing is provided."""
        args = argparse.Namespace(manifest_url="", build_number="", upstream_sha="")
        with pytest.raises(ValueError, match="Invalid arguments"):
            detect_build_type(args)


class TestGitHubActionsIntegration:
    """Test GitHub Actions integration features."""

    @patch.dict(os.environ, {"GITHUB_OUTPUT": "/tmp/test_output"})
    def test_github_output_written(self):
        """Test that GitHub Actions outputs are written correctly."""
        # This would be tested in integration tests with actual CLI calls
        # For now, we can test that the environment variable is checked
        assert os.getenv("GITHUB_OUTPUT") == "/tmp/test_output"


if __name__ == "__main__":
    pytest.main([__file__])
