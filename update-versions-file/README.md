# Update Versions File Action

A GitHub Action that updates upstream versions files for both hash-based and regular builds.

## Features

- **Unified Handling**: Supports both hash-based and regular builds in a single action
- **Auto-Detection**: Automatically detects build type based on provided inputs
- **Tested**: Comprehensive test suite with pytest
- **Type-Safe**: Written in Python with proper error handling and validation

## Usage

### Regular Build (SHA-based)

```yaml
- name: Update versions for regular build
  uses: poemAI-ch/poemai-github-actions/update-versions-file@v2
  with:
    versions-file-path: '.poemai-upstream-versions.yaml'
    upstream-repo: 'poemAI-ch/upstream-repo'
    upstream-sha: '${{ github.event.client_payload.sha }}'
```

### Hash-Based Build

```yaml
- name: Update versions for hash-based build
  uses: poemAI-ch/poemai-github-actions/update-versions-file@v2
  with:
    versions-file-path: '.poemai-upstream-versions.yaml'
    upstream-repo: 'poemAI-ch/upstream-lambdas'
    manifest-url: '${{ github.event.client_payload.manifest_url }}'
    build-number: '${{ github.event.client_payload.build_number }}'
```

### Auto-Detection Example

```yaml
- name: Update versions (auto-detect build type)
  uses: poemAI-ch/poemai-github-actions/update-versions-file@v2
  with:
    versions-file-path: '.poemai-upstream-versions.yaml'
    upstream-repo: '${{ github.event.client_payload.upstream }}'
    upstream-sha: '${{ github.event.client_payload.sha }}'
    manifest-url: '${{ github.event.client_payload.manifest_url }}'
    build-number: '${{ github.event.client_payload.build_number }}'
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `versions-file-path` | Path to the versions file | Yes | `.poemai-upstream-versions.yaml` |
| `upstream-repo` | Upstream repository name (e.g., poemAI-ch/repo-name) | Yes | |
| `upstream-sha` | Upstream repository SHA for regular builds | No | |
| `manifest-url` | Manifest URL for hash-based builds | No | |
| `build-number` | Build number for hash-based builds | No | |
| `python-version` | Python version to use | No | `3.12` |

## Outputs

| Output | Description |
|--------|-------------|
| `build-type` | Type of build detected (`hash_based` or `regular`) |
| `file-updated` | Whether the versions file was updated (`true` or `false`) |

## Build Type Detection

The action automatically detects the build type based on the provided inputs:

- **Hash-based build**: If both `manifest-url` and `build-number` are provided
- **Regular build**: If `upstream-sha` is provided (and hash-based inputs are not)

## File Structure

### Regular Builds

```yaml
versions:
  poemAI-ch/repo-one: abc123def456
  poemAI-ch/repo-two: def456ghi789
```

### Hash-Based Builds

```yaml
versions:
  poemAI-ch/regular-repo: abc123def456
hash_based_lambdas:
  poemAI-ch/lambda-repo: s3://bucket/path/to/manifest.json
```

## Error Handling

The action validates inputs and provides clear error messages for:

- Invalid SHA formats
- Empty repository names
- Missing required parameters for detected build type
- File system errors

## Development

### Running Tests

```bash
cd update-versions-file
pip install pytest pyyaml
python -m pytest tests/ -v
```

### Test Coverage

The test suite covers:
- Creating new version files
- Updating existing files
- No-op scenarios (no changes needed)
- Input validation
- Error conditions
- Build type detection
- Both regular and hash-based workflows

## Migration from Individual Scripts

This action replaces the individual `update_versions_file.py` and `update_versions_file_hash_based.py` scripts, providing:

- Single source of truth
- Consistent behavior across repositories
- Better error handling and validation
- Comprehensive testing
- GitHub Actions integration
