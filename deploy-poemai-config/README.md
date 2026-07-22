# Deploy poeMAI Config GitHub Action

This GitHub Action deploys poeMAI configuration files to AWS Lambda using the poeMAI config deployer lambda function.

## Features

- **Configuration Deployment**: Deploy corpus keys, assistants, case managers, and corpus metadata
- **Temporary Deployments**: Create temporary test deployments with automatic TTL cleanup
- **URL Generation**: Generate test bot URLs for easy access to temporary deployments
- **Version Management**: Support for version IDs and deployment tracking
- **Multi-format Support**: Handle both single and multi-document YAML files
- **Messaging Configuration**: Validate and deploy provider records separately from corpus configuration
- **Derived Route Aliases**: Generate direct document-table lookup items from active corpus messaging routes

## Usage

### Basic Configuration Deployment

```yaml
- name: Deploy Configuration
  uses: poemAI-ch/poemai-github-actions/deploy-poemai-config@v5.8.2
  with:
    environment: 'production'
    lambda-function-name: 'poemai-config-deployer-lambda'
    role-to-assume: 'arn:aws:iam::ACCOUNT:role/poemai-github-role-environment'
```

### Temporary Test Deployment

```yaml
- name: Deploy Temporary Test Bot
  uses: poemAI-ch/poemai-github-actions/deploy-poemai-config@v5.8.2
  with:
    environment: 'staging'
    lambda-function-name: 'poemai-config-deployer-lambda'
    role-to-assume: 'arn:aws:iam::ACCOUNT:role/poemai-github-role-environment'
    temporary-corpus-key: 'auto'  # Auto-generates TEMP_ABC123DEF0
    temporary-corpus-key-ttl-hours: '24'
    test-bot-url-template: 'https://app.staging.poemai.ch/ui/town_bot/app/{corpus_key}/'
```

### Messaging Provider Deployment

```yaml
- name: Deploy Messaging Provider Configuration
  uses: poemAI-ch/poemai-github-actions/deploy-poemai-config@v5.8.2
  with:
    environment: 'staging'
    configuration-scope: 'messaging'
    lambda-function-name: 'poemai-messaging-config-deployer-staging'
    role-to-assume: 'arn:aws:iam::ACCOUNT:role/poemai-github-role-devops'
```

Messaging provider records are read from
`environments/<environment>/messaging/provider_connections.yaml`. The validator
requires deterministic Standard SSM `SecureString` parameter names below:

```text
/poemai/{environment}/messaging/providers/{provider}/channels/{channel}/callbacks/{callback_id}/credentials/{credential}
/poemai/{environment}/messaging/providers/{provider}/channels/{channel}/connections/{provider_connection_id}/credentials/{credential}
```

Credential values are rejected. Corpus deployments continue to read
`corpus_keys/**` and append a derived direct-lookup item for each active
messaging route. Provision credential parameters as Standard-tier
`SecureString` values with the default AWS-managed SSM key and these tags:
`poemai-environment=<environment>`, `poemai-application=messaging`,
`poemai-purpose=provider-credential`, `poemai-provider=<provider>`, and
`poemai-channel=<channel>`.

## Input Parameters

| Parameter | Description | Required | Default |
|-----------|-------------|----------|---------|
| `environment` | Target environment (staging, production, etc.) | Yes | - |
| `lambda-function-name` | Name of the config deployer lambda function | Yes | - |
| `role-to-assume` | AWS IAM role ARN for deployment permissions | Yes | - |
| `project-root-path` | Path to project root containing environments/ | No | `.` |
| `version-id` | Version identifier for tracking deployments | No | - |
| `temporary-corpus-key` | Temporary corpus key for test deployments (use 'auto' for auto-generation) | No | - |
| `temporary-corpus-key-ttl-hours` | TTL in hours for temporary deployments | No | `24` |
| `test-bot-url-template` | Jinja2 URL template for test bot access | No | - |
| `configuration-scope` | Deploy `corpus` objects or `messaging` provider records | No | `corpus` |

## Temporary Deployment Features

### Auto-Expiring Test Deployments
- Temporary corpus keys with configurable TTL
- Automatic cleanup via DynamoDB TTL
- Safe ID remapping using UUIDs
- Single deployment validation

### URL Generation
- Template-based URL generation for easy test bot access
- Support for `{corpus_key}` and `{{ corpus_key }}` placeholders
- GitHub Actions notices for prominent URL display

See [TEMPORARY_DEPLOYMENT.md](TEMPORARY_DEPLOYMENT.md) for detailed examples and usage patterns.

## Directory Structure Expected

```
project-root/
  environments/
    staging/
      messaging/
        provider_connections.yaml
      corpus_keys/
        BOT_NAME/
          assistant.yaml
          corpus_metadata.yaml
          case_manager.yaml
    production/
      corpus_keys/
        BOT_NAME/
          assistant.yaml
          corpus_metadata.yaml
```

## Development

### Running Tests

This action includes a comprehensive test suite for local development and debugging:

```bash
# Install test dependencies
pip install -r test-requirements.txt

# Run all tests
./run_tests.sh

# Or run pytest directly
python -m pytest tests/ -v
```

See [tests/README.md](tests/README.md) for detailed information about the test suite.

### Test Coverage

The test suite covers:
- Object type recognition and validation
- Temporary corpus key transformation
- URL template generation
- YAML file processing
- AWS Lambda integration (mocked)
- Command-line argument parsing
- Error handling and edge cases

## Error Handling

The action provides comprehensive error handling for:
- Missing or invalid configuration files
- AWS authentication and permission issues
- Lambda function errors
- Malformed YAML files
- Validation failures

## Security

- Uses AWS IAM roles for secure authentication
- Temporary deployments are restricted to staging environments
- Automatic cleanup prevents resource accumulation
- Version tracking for audit trails

## Contributing

1. Make changes to the action code
2. Run the test suite: `./run_tests.sh`
3. Test with real deployments in staging
4. Update version in `action.yaml`
5. Create pull request

## Version History

- **v5.8.2**: Require canonical Standard SSM Parameter Store credential paths
- **v5.8.1**: Install the DynamoDB SDK required by messaging validation
- **v5.8.0**: Added messaging provider validation/deployment and derived corpus-route aliases
- **v5.1.1**: Added temporary corpus key deployment with URL generation
- **v5.0.0**: Enhanced configuration deployment with wildcard support
- **v4.x**: Previous versions (see git history)

## License

This project is licensed under the MIT License - see the LICENSE file for details.
