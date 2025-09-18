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
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


class VersionsFileUpdater:
    """Handles updating versions files for both hash-based and regular builds."""

    def __init__(self, versions_file_path: str, aws_region: str = "eu-central-2"):
        self.versions_file_path = Path(versions_file_path)
        self.aws_region = aws_region
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

    def _parse_s3_url(self, s3_url: str) -> tuple[str, str]:
        """
        Parse S3 URL to extract bucket and key.

        Args:
            s3_url: S3 URL like s3://bucket-name/path/to/file

        Returns:
            Tuple of (bucket, key)
        """
        if not s3_url.startswith("s3://"):
            raise ValueError(f"Invalid S3 URL format: {s3_url}")

        # Remove s3:// prefix and split on first /
        s3_path = s3_url[5:]
        parts = s3_path.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URL format: {s3_url}")

        return parts[0], parts[1]

    def _download_s3_manifest(self, manifest_url: str) -> Optional[Dict[str, Any]]:
        """
        Download and parse YAML manifest from S3.

        Args:
            manifest_url: S3 URL to the manifest file

        Returns:
            Parsed YAML data or None if failed
        """
        if not BOTO3_AVAILABLE:
            print("❌ boto3 not available, cannot download S3 manifest")
            return None

        try:
            bucket, key = self._parse_s3_url(manifest_url)
            print(f"📥 Downloading manifest from s3://{bucket}/{key}")

            # Create S3 client
            s3_client = boto3.client("s3", region_name=self.aws_region)

            # Download the manifest
            response = s3_client.get_object(Bucket=bucket, Key=key)
            manifest_content = response["Body"].read().decode("utf-8")

            # Parse YAML
            manifest_data = yaml.safe_load(manifest_content)
            print(f"✅ Successfully downloaded and parsed manifest")
            return manifest_data

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            print(
                f"❌ AWS error downloading manifest: {error_code} - {e.response['Error']['Message']}"
            )
            return None
        except NoCredentialsError:
            print("❌ AWS credentials not available for S3 access")
            return None
        except Exception as e:
            print(f"❌ Error downloading manifest: {e}")
            return None

    def _extract_lambda_versions(
        self, manifest_data: Dict[str, Any], upstream_repo: str
    ) -> Dict[str, str]:
        """
        Extract individual lambda versions from manifest data.

        Args:
            manifest_data: Parsed manifest YAML data
            upstream_repo: Repository name (e.g., poemAI-ch/poemai-lambdas)

        Returns:
            Dictionary of lambda_name -> version
        """
        lambda_versions = {}

        # The manifest should contain lambda versions in a 'versions' section like:
        # versions:
        #   lambda_name: version_hash
        if isinstance(manifest_data, dict) and "versions" in manifest_data:
            versions_section = manifest_data["versions"]
            if isinstance(versions_section, dict):
                for lambda_name, version in versions_section.items():
                    if isinstance(version, str):
                        # Create the full lambda reference
                        lambda_ref = f"{upstream_repo}#{lambda_name}"
                        lambda_versions[lambda_ref] = version
                        print(f"  📦 Found lambda: {lambda_ref} -> {version}")
            else:
                print("⚠️ Versions section is not a dictionary")
        else:
            print("⚠️ No 'versions' section found in manifest")

        return lambda_versions

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
        print(
            f"Updating {self.versions_file_path} with {upstream_repo} -> {upstream_sha}"
        )
        self.data["versions"][upstream_repo] = upstream_sha
        self._save_file()

        print("Updated file contents:")
        print(yaml.safe_dump(self.data, sort_keys=False))
        return True

    def update_hash_based_build(self, upstream_repo: str, manifest_url: str) -> bool:
        """
        Update versions file for a hash-based build.

        This method:
        1. Updates the hash_based_lambdas section with the manifest URL
        2. Downloads the S3 manifest (if AWS credentials available)
        3. Extracts individual lambda versions and updates the versions section

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

        # Check if manifest URL update is needed
        current_manifest = self.data["hash_based_lambdas"].get(upstream_repo)
        manifest_updated = current_manifest != manifest_url

        # Download and parse the manifest to get individual lambda versions
        manifest_data = self._download_s3_manifest(manifest_url)
        lambda_versions_updated = False

        if manifest_data:
            # Extract individual lambda versions
            lambda_versions = self._extract_lambda_versions(
                manifest_data, upstream_repo
            )

            if lambda_versions:
                print(f"🔄 Updating individual lambda versions from manifest...")

                # Check if any individual lambda versions need updating
                for lambda_ref, version in lambda_versions.items():
                    current_version = self.data["versions"].get(lambda_ref)
                    if current_version != version:
                        print(
                            f"  📝 Updating {lambda_ref}: {current_version} -> {version}"
                        )
                        self.data["versions"][lambda_ref] = version
                        lambda_versions_updated = True
                    else:
                        print(f"  ✓ {lambda_ref} already at {version}")
            else:
                print("⚠️ No lambda versions found in manifest")
        else:
            print("⚠️ Could not download manifest, only updating manifest URL")

        # Update the manifest URL if needed
        if manifest_updated:
            print(f"📝 Updating manifest URL: {upstream_repo} -> {manifest_url}")
            self.data["hash_based_lambdas"][upstream_repo] = manifest_url

        # Check if any updates were made
        if manifest_updated or lambda_versions_updated:
            self._save_file()
            print("Updated file contents:")
            print(yaml.safe_dump(self.data, sort_keys=False))
            return True
        else:
            print(
                f"No update needed: {upstream_repo} manifest and lambda versions are current"
            )
            return False


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
        return "hash_based"
    elif has_sha:
        return "regular"
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
        help="Path to the versions file (e.g., .poemai-upstream-versions.yaml)",
    )
    parser.add_argument(
        "--upstream-repo",
        required=True,
        help="Upstream repository name (e.g., poemAI-ch/repo-name)",
    )
    parser.add_argument(
        "--upstream-sha", default="", help="Upstream repository SHA for regular builds"
    )
    parser.add_argument(
        "--manifest-url", default="", help="Manifest URL for hash-based builds"
    )
    parser.add_argument(
        "--build-number", default="", help="Build number for hash-based builds"
    )
    parser.add_argument(
        "--aws-region",
        default="eu-central-2",
        help="AWS region for S3 access (default: eu-central-2)",
    )

    args = parser.parse_args()

    try:
        # Detect build type
        build_type = detect_build_type(args)
        print(f"🔍 Detected build type: {build_type}")

        # Create updater with AWS region
        updater = VersionsFileUpdater(args.versions_file, args.aws_region)

        # Update based on build type
        if build_type == "hash_based":
            file_updated = updater.update_hash_based_build(
                args.upstream_repo, args.manifest_url
            )
        else:  # regular
            file_updated = updater.update_regular_build(
                args.upstream_repo, args.upstream_sha
            )

        # Set GitHub Actions outputs
        if os.getenv("GITHUB_OUTPUT"):
            with open(os.getenv("GITHUB_OUTPUT"), "a") as f:
                f.write(f"build_type={build_type}\n")
                f.write(f"file_updated={'true' if file_updated else 'false'}\n")

        print(
            f"✅ Process completed. Build type: {build_type}, File updated: {file_updated}"
        )

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
