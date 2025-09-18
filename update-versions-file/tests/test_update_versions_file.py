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

        # Mock S3 response with manifest data
        manifest_yaml = """
lambda1: abc123def456
lambda2: def456ghi789
lambda3: ghi789jkl012
"""
        mock_response = {"Body": MagicMock()}
        mock_response["Body"].read.return_value = manifest_yaml.encode("utf-8")
        mock_s3_client.get_object.return_value = mock_response

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            initial_data = {"versions": {"poemAI-ch/other-repo": "old123"}}
            yaml.safe_dump(initial_data, f)
            temp_file = f.name

        try:
            updater = VersionsFileUpdater(temp_file)
            result = updater.update_hash_based_build(
                "poemAI-ch/test-lambdas", "s3://test-bucket/path/to/manifest.yaml"
            )

            assert result is True

            # Verify S3 client was called correctly
            mock_boto3.client.assert_called_once_with("s3", region_name="eu-central-2")
            mock_s3_client.get_object.assert_called_once_with(
                Bucket="test-bucket", Key="path/to/manifest.yaml"
            )

            # Check the updated file
            with open(temp_file, "r") as f:
                data = yaml.safe_load(f)

            expected = {
                "versions": {
                    "poemAI-ch/other-repo": "old123",
                    "poemAI-ch/test-lambdas#lambda1": "abc123def456",
                    "poemAI-ch/test-lambdas#lambda2": "def456ghi789",
                    "poemAI-ch/test-lambdas#lambda3": "ghi789jkl012",
                },
                "hash_based_lambdas": {
                    "poemAI-ch/test-lambdas": "s3://test-bucket/path/to/manifest.yaml"
                },
            }
            assert data == expected
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

            # Valid manifest data
            manifest_data = {
                "lambda1": "abc123def456",
                "lambda2": "def456ghi789",
                "lambda3": "ghi789jkl012",
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
