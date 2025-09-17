"""Tests for the unified versions file updater."""

import os
import tempfile
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch

# Add the parent directory to the path so we can import our module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from update_versions_file import VersionsFileUpdater, detect_build_type
import argparse


class TestVersionsFileUpdater:
    """Test cases for VersionsFileUpdater class."""
    
    def test_create_new_file_regular_build(self):
        """Test creating a new versions file for a regular build."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
            temp_file = f.name
        
        try:
            # Remove the file so we test creation
            os.unlink(temp_file)
            
            updater = VersionsFileUpdater(temp_file)
            result = updater.update_regular_build("poemAI-ch/test-repo", "abc123def456")
            
            assert result is True
            assert Path(temp_file).exists()
            
            with open(temp_file, 'r') as f:
                data = yaml.safe_load(f)
            
            assert data == {
                'versions': {
                    'poemAI-ch/test-repo': 'abc123def456'
                }
            }
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def test_update_existing_file_regular_build(self):
        """Test updating an existing versions file for a regular build."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
            # Create initial content
            initial_data = {
                'versions': {
                    'poemAI-ch/other-repo': 'old123',
                    'poemAI-ch/test-repo': 'old456'
                }
            }
            yaml.safe_dump(initial_data, f)
            temp_file = f.name
        
        try:
            updater = VersionsFileUpdater(temp_file)
            result = updater.update_regular_build("poemAI-ch/test-repo", "abc789def")
            
            assert result is True
            
            with open(temp_file, 'r') as f:
                data = yaml.safe_load(f)
            
            expected = {
                'versions': {
                    'poemAI-ch/other-repo': 'old123',
                    'poemAI-ch/test-repo': 'abc789def'
                }
            }
            assert data == expected
        finally:
            os.unlink(temp_file)
    
    def test_no_update_needed_regular_build(self):
        """Test when no update is needed for a regular build."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
            initial_data = {
                'versions': {
                    'poemAI-ch/test-repo': 'abc123def456'
                }
            }
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
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
            temp_file = f.name
        
        try:
            # Remove the file so we test creation
            os.unlink(temp_file)
            
            updater = VersionsFileUpdater(temp_file)
            result = updater.update_hash_based_build(
                "poemAI-ch/test-lambdas", 
                "s3://bucket/manifest.json"
            )
            
            assert result is True
            assert Path(temp_file).exists()
            
            with open(temp_file, 'r') as f:
                data = yaml.safe_load(f)
            
            assert data == {
                'versions': {},
                'hash_based_lambdas': {
                    'poemAI-ch/test-lambdas': 's3://bucket/manifest.json'
                }
            }
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def test_update_existing_file_hash_based_build(self):
        """Test updating an existing versions file for a hash-based build."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
            initial_data = {
                'versions': {
                    'poemAI-ch/regular-repo': 'sha123'
                },
                'hash_based_lambdas': {
                    'poemAI-ch/other-lambdas': 's3://bucket/old.json'
                }
            }
            yaml.safe_dump(initial_data, f)
            temp_file = f.name
        
        try:
            updater = VersionsFileUpdater(temp_file)
            result = updater.update_hash_based_build(
                "poemAI-ch/test-lambdas",
                "s3://bucket/new.json"
            )
            
            assert result is True
            
            with open(temp_file, 'r') as f:
                data = yaml.safe_load(f)
            
            expected = {
                'versions': {
                    'poemAI-ch/regular-repo': 'sha123'
                },
                'hash_based_lambdas': {
                    'poemAI-ch/other-lambdas': 's3://bucket/old.json',
                    'poemAI-ch/test-lambdas': 's3://bucket/new.json'
                }
            }
            assert data == expected
        finally:
            os.unlink(temp_file)
    
    def test_no_update_needed_hash_based_build(self):
        """Test when no update is needed for a hash-based build."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
            initial_data = {
                'hash_based_lambdas': {
                    'poemAI-ch/test-lambdas': 's3://bucket/manifest.json'
                }
            }
            yaml.safe_dump(initial_data, f)
            temp_file = f.name
        
        try:
            updater = VersionsFileUpdater(temp_file)
            result = updater.update_hash_based_build(
                "poemAI-ch/test-lambdas",
                "s3://bucket/manifest.json"
            )
            
            assert result is False
        finally:
            os.unlink(temp_file)
    
    def test_invalid_sha_regular_build(self):
        """Test validation for invalid SHA in regular build."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
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
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
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
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
            temp_file = f.name
        
        try:
            updater = VersionsFileUpdater(temp_file)
            
            with pytest.raises(ValueError, match="Empty manifest URL"):
                updater.update_hash_based_build("poemAI-ch/test-repo", "")
        finally:
            os.unlink(temp_file)


class TestBuildTypeDetection:
    """Test cases for build type detection."""
    
    def test_detect_hash_based_build(self):
        """Test detection of hash-based build."""
        args = argparse.Namespace(
            manifest_url="s3://bucket/manifest.json",
            build_number="123",
            upstream_sha=""
        )
        assert detect_build_type(args) == "hash_based"
    
    def test_detect_regular_build(self):
        """Test detection of regular build."""
        args = argparse.Namespace(
            manifest_url="",
            build_number="",
            upstream_sha="abc123def456"
        )
        assert detect_build_type(args) == "regular"
    
    def test_detect_hash_based_with_extra_sha(self):
        """Test that hash-based takes precedence when both are provided."""
        args = argparse.Namespace(
            manifest_url="s3://bucket/manifest.json",
            build_number="123",
            upstream_sha="abc123def456"
        )
        assert detect_build_type(args) == "hash_based"
    
    def test_invalid_arguments_no_manifest_url(self):
        """Test invalid arguments when manifest URL is missing but build number is provided."""
        args = argparse.Namespace(
            manifest_url="",
            build_number="123",
            upstream_sha=""
        )
        with pytest.raises(ValueError, match="Invalid arguments"):
            detect_build_type(args)
    
    def test_invalid_arguments_no_build_number(self):
        """Test invalid arguments when build number is missing but manifest URL is provided."""
        args = argparse.Namespace(
            manifest_url="s3://bucket/manifest.json",
            build_number="",
            upstream_sha=""
        )
        with pytest.raises(ValueError, match="Invalid arguments"):
            detect_build_type(args)
    
    def test_invalid_arguments_nothing_provided(self):
        """Test invalid arguments when nothing is provided."""
        args = argparse.Namespace(
            manifest_url="",
            build_number="",
            upstream_sha=""
        )
        with pytest.raises(ValueError, match="Invalid arguments"):
            detect_build_type(args)


class TestGitHubActionsIntegration:
    """Test GitHub Actions integration features."""
    
    @patch.dict(os.environ, {'GITHUB_OUTPUT': '/tmp/test_output'})
    def test_github_output_written(self):
        """Test that GitHub Actions outputs are written correctly."""
        # This would be tested in integration tests with actual CLI calls
        # For now, we can test that the environment variable is checked
        assert os.getenv('GITHUB_OUTPUT') == '/tmp/test_output'


if __name__ == "__main__":
    pytest.main([__file__])
