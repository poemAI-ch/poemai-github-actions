#!/usr/bin/env python3
"""
Unified versions file updater for both hash-based and regular builds.

This script can handle two types of builds:
1. Hash-based builds: Uses manifest URL and build number
2. Regular builds: Uses upstream repository SHA

The script detects the build type based on the provided arguments and updates
the versions file accordingly.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

import yaml


class VersionsFileUpdater:
    """Handles updating versions files for both hash-based and regular builds."""
    
    def __init__(self, versions_file_path: str):
        self.versions_file_path = Path(versions_file_path)
        self.data: Dict[str, Any] = {}
        self._load_existing_file()
    
    def _load_existing_file(self) -> None:
        """Load existing versions file or create empty structure."""
        if self.versions_file_path.exists():
            with self.versions_file_path.open("r") as f:
                self.data = yaml.safe_load(f) or {}
        else:
            print(f"Creating {self.versions_file_path} with empty versions block.")
            self.data = {}
    
    def _ensure_structure(self) -> None:
        """Ensure the versions file has the required structure."""
        if "versions" not in self.data or not isinstance(self.data["versions"], dict):
            self.data["versions"] = {}
    
    def _save_file(self) -> None:
        """Save the updated data to the versions file."""
        with self.versions_file_path.open("w") as f:
            yaml.safe_dump(self.data, f, sort_keys=False)
    
    def update_regular_build(self, upstream_repo: str, upstream_sha: str) -> bool:
        """
        Update versions file for a regular build.
        
        Args:
            upstream_repo: Repository name (e.g., poemAI-ch/repo-name)
            upstream_sha: Commit SHA
            
        Returns:
            True if file was updated, False if no changes needed
        """
        # Validate inputs
        if not upstream_repo.strip():
            raise ValueError("Empty repository name")
        
        upstream_sha = upstream_sha.strip()
        if not upstream_sha or set(upstream_sha) - set("0123456789abcdefABCDEF"):
            raise ValueError(f"Invalid SHA: {upstream_sha}")
        
        self._ensure_structure()
        
        # Check if update is needed
        current_sha = self.data["versions"].get(upstream_repo)
        if current_sha == upstream_sha:
            print(f"No update needed: {upstream_repo} is already at {upstream_sha}")
            return False
        
        # Update the version
        print(f"Updating {self.versions_file_path} with {upstream_repo} -> {upstream_sha}")
        self.data["versions"][upstream_repo] = upstream_sha
        self._save_file()
        
        print("Updated file contents:")
        print(yaml.safe_dump(self.data, sort_keys=False))
        return True
    
    def update_hash_based_build(self, upstream_repo: str, manifest_url: str) -> bool:
        """
        Update versions file for a hash-based build.
        
        Args:
            upstream_repo: Repository name (e.g., poemAI-ch/repo-name)
            manifest_url: S3 URL to the lambda manifest
            
        Returns:
            True if file was updated, False if no changes needed
        """
        # Validate inputs
        if not upstream_repo.strip():
            raise ValueError("Empty repository name")
        
        if not manifest_url.strip():
            raise ValueError("Empty manifest URL")
        
        self._ensure_structure()
        
        # For hash-based builds, we need to ensure the hash_based_lambdas structure exists
        if "hash_based_lambdas" not in self.data:
            self.data["hash_based_lambdas"] = {}
        
        # Check if update is needed
        current_manifest = self.data["hash_based_lambdas"].get(upstream_repo)
        if current_manifest == manifest_url:
            print(f"No update needed: {upstream_repo} is already at {manifest_url}")
            return False
        
        # Update the manifest URL
        print(f"Updating {self.versions_file_path} with hash-based {upstream_repo} -> {manifest_url}")
        self.data["hash_based_lambdas"][upstream_repo] = manifest_url
        self._save_file()
        
        print("Updated file contents:")
        print(yaml.safe_dump(self.data, sort_keys=False))
        return True


def detect_build_type(args: argparse.Namespace) -> str:
    """
    Detect whether this is a hash-based or regular build based on arguments.
    
    Returns:
        'hash_based' or 'regular'
    """
    has_manifest = args.manifest_url and args.manifest_url.strip()
    has_build_number = args.build_number and args.build_number.strip()
    has_sha = args.upstream_sha and args.upstream_sha.strip()
    
    if has_manifest and has_build_number:
        return 'hash_based'
    elif has_sha:
        return 'regular'
    else:
        raise ValueError(
            "Invalid arguments: Either provide (manifest-url AND build-number) for hash-based builds, "
            "or provide upstream-sha for regular builds"
        )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Update upstream versions file for both hash-based and regular builds"
    )
    parser.add_argument(
        "--versions-file",
        required=True,
        help="Path to the versions file (e.g., .poemai-upstream-versions.yaml)"
    )
    parser.add_argument(
        "--upstream-repo",
        required=True,
        help="Upstream repository name (e.g., poemAI-ch/repo-name)"
    )
    parser.add_argument(
        "--upstream-sha",
        default="",
        help="Upstream repository SHA for regular builds"
    )
    parser.add_argument(
        "--manifest-url",
        default="",
        help="Manifest URL for hash-based builds"
    )
    parser.add_argument(
        "--build-number",
        default="",
        help="Build number for hash-based builds"
    )
    
    args = parser.parse_args()
    
    try:
        # Detect build type
        build_type = detect_build_type(args)
        print(f"🔍 Detected build type: {build_type}")
        
        # Create updater
        updater = VersionsFileUpdater(args.versions_file)
        
        # Update based on build type
        if build_type == 'hash_based':
            file_updated = updater.update_hash_based_build(args.upstream_repo, args.manifest_url)
        else:  # regular
            file_updated = updater.update_regular_build(args.upstream_repo, args.upstream_sha)
        
        # Set GitHub Actions outputs
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.getenv('GITHUB_OUTPUT'), 'a') as f:
                f.write(f"build_type={build_type}\n")
                f.write(f"file_updated={'true' if file_updated else 'false'}\n")
        
        print(f"✅ Process completed. Build type: {build_type}, File updated: {file_updated}")
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
