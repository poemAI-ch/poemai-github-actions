# Tests for deploy-poemai-config GitHub Action

This directory contains comprehensive tests for the `deploy-poemai-config` GitHub Action.

## Test Structure

### `test_deploy_config_with_lambda.py`
Core functionality tests including:
- **Object Type Recognition**: Tests for identifying assistants, corpus metadata, and case managers
- **Data Conversion**: Tests for float/Decimal conversion for DynamoDB compatibility  
- **Temporary Corpus Key**: Tests for temporary deployment transformation and ID remapping
- **URL Generation**: Tests for test bot URL template generation
- **File Gathering**: Tests for YAML configuration file loading
- **Integration Scenarios**: End-to-end workflow tests

### `test_cli_integration.py`
Command-line interface tests including:
- **Argument Parsing**: Tests for all CLI parameters and options
- **Error Handling**: Tests for various error conditions and exit codes
- **Real Execution**: Tests that actually run the script as subprocess
- **AWS Integration**: Tests that verify AWS credential handling (with mocked credentials)

### `test_edge_cases.py`
Edge cases and error conditions including:
- **Empty/Invalid Data**: Tests for handling empty YAML files, invalid configurations
- **Complex Transformations**: Tests for deeply nested objects and large datasets
- **Performance**: Tests with large object sets to ensure scalability
- **Compatibility**: Tests for backward compatibility with different object formats

## Running Tests

### Quick Test Run
```bash
python -m pytest tests/ -v
```

### Using the Test Runner Script
```bash
./run_tests.sh
```

### Run Specific Test Categories
```bash
# Core functionality only
python -m pytest tests/test_deploy_config_with_lambda.py -v

# CLI integration only  
python -m pytest tests/test_cli_integration.py -v

# Edge cases only
python -m pytest tests/test_edge_cases.py -v
```

### Run with Coverage (if pytest-cov is installed)
```bash
python -m pytest tests/ --cov=deploy_config_with_lambda_call --cov-report=term-missing
```

## Test Coverage

The test suite provides comprehensive coverage of:
- ✅ Object type recognition and validation
- ✅ Temporary corpus key transformation with TTL
- ✅ ID remapping and consistency validation
- ✅ URL template generation for test bots
- ✅ YAML file loading and parsing
- ✅ AWS Lambda integration (mocked)
- ✅ Command-line argument parsing
- ✅ Error handling and exit conditions
- ✅ Edge cases and performance scenarios

## Key Features Tested

### Temporary Deployment Functionality
- Auto-generation of temporary corpus keys (`TEMP_ABC123DEF0`)
- Object transformation with ID remapping using UUIDs
- TTL (Time To Live) field addition for auto-cleanup
- Validation ensuring single corpus key after transformation

### URL Generation
- Template substitution with `{corpus_key}` and `{{ corpus_key }}` formats
- GitHub Actions notice output for prominent URL display
- Support for complex URL templates with multiple placeholders

### AWS Integration
- Lambda function invocation with proper error handling
- DynamoDB-compatible data conversion (floats to Decimals)
- Credential validation and error reporting

### File Processing
- Multi-document YAML support
- Error handling for malformed/empty files
- Recursive directory traversal for configuration discovery

## Dependencies

Test dependencies are listed in `test-requirements.txt`:
- `pytest>=7.0.0` - Testing framework
- `pyyaml>=6.0` - YAML processing
- `boto3>=1.26.0` - AWS SDK (for mocking)

## Notes

- CLI integration tests use mocked AWS credentials to avoid actual AWS calls
- Some tests expect Lambda invocation to fail (since we can't mock Lambda responses in subprocess calls)
- The test suite focuses on local functionality validation rather than end-to-end AWS deployment
- Performance tests ensure the action can handle large configuration sets efficiently
