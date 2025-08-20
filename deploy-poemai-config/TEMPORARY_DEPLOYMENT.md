# Temporary Corpus Key Deployment

The `deploy-poemai-config` acti## Key Features

- **Auto TTL**: Temporary deployments automatically expire and clean up
- **Safe ID Remapping**: Original corpus key IDs are preserved and restored using UUIDs
- **Staging Only**: Restricted to staging environment for safety
- **URL Generation**: Automatically generates test bot URLs for easy access
- **PR Integration**: Perfect for pull request testing workflowssupports deploying configurations to temporary corpus keys with automatic TTL expiration. This is perfect for:

- **PR Testing**: Create temporary bots for each pull request
- **Feature Testing**: Deploy temporary instances for testing new features
- **Demo Environments**: Create time-limited demo bots

## Usage Examples

### 1. Auto-Generated Temporary Corpus Key with URL

```yaml
- name: Deploy temporary bot
  uses: poemAI-ch/poemai-github-actions/deploy-poemai-config@v5.1.1
  with:
    environment: 'staging'
    lambda-function-name: 'poemai-config-deployer-lambda'
    role-to-assume: 'arn:aws:iam::ACCOUNT:role/poemai-github-role-environment'
    temporary-corpus-key: 'auto'  # Auto-generates TEMP_ABC123DEF0
    temporary-corpus-key-ttl-hours: '24'
    test-bot-url-template: 'https://app.staging.poemai.ch/ui/town_bot/app/{corpus_key}/'
```

### 2. Custom Temporary Corpus Key with URL

```yaml
- name: Deploy PR test bot
  uses: poemAI-ch/poemai-github-actions/deploy-poemai-config@v5.1.1
  with:
    environment: 'staging'
    lambda-function-name: 'poemai-config-deployer-lambda'
    role-to-assume: 'arn:aws:iam::ACCOUNT:role/poemai-github-role-environment'
    temporary-corpus-key: 'PR_${{ github.event.pull_request.number }}_${{ github.sha }}'
    temporary-corpus-key-ttl-hours: '48'
    test-bot-url-template: 'https://app.staging.poemai.ch/ui/town_bot/app/{corpus_key}/'
```

### 3. Pattern-Specific Deployment (with Wildcard Lambda)

```yaml
- name: Deploy RIGHTNOW_BOT temporary instance
  uses: poemAI-ch/poemai-github-actions/deploy-poemai-config@v5.1.1
  with:
    environment: 'staging'
    lambda-function-name: 'poemai-config-deployer-staging-wildcard-rightnow-lambda'
    role-to-assume: 'arn:aws:iam::ACCOUNT:role/poemai-github-role-environment'
    temporary-corpus-key: 'RIGHTNOW_BOT_TEMP_${{ github.run_id }}'
    temporary-corpus-key-ttl-hours: '12'
```

## New Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `temporary-corpus-key` | No | `''` | Temporary corpus key name. Use `'auto'` to auto-generate, or provide custom name |
| `temporary-corpus-key-ttl-hours` | No | `24` | TTL in hours before automatic cleanup |

## How It Works

1. **Object Transformation**: The action transforms your corpus key objects by:
   - Changing the corpus key ID to the temporary value
   - Adding a TTL field for automatic cleanup
   - Preserving original data structure

2. **Safe Deployment**: Objects are deployed only to staging environment

3. **URL Generation**: If a URL template is provided, generates clickable test bot URLs

4. **Auto Cleanup**: DynamoDB TTL automatically removes expired entries

5. **Status Output**: GitHub Actions provides the test bot URL in notices and outputs

## Key Features

✅ **Automatic Cleanup**: Objects automatically expire after the specified TTL  
✅ **ID Isolation**: Generated UUIDs prevent conflicts with existing deployments  
✅ **Reference Integrity**: Case manager and assistant references are properly updated  
✅ **Lambda Compatibility**: Works with both general and wildcard-restricted Lambda functions  
✅ **Corpus Key Validation**: Respects existing corpus key restrictions (RIGHTNOW_BOT_*, etc.)

## Use Cases

### PR-Based Testing
Create a unique test bot for each pull request:

```yaml
temporary-corpus-key: 'PR_${{ github.event.pull_request.number }}_$(git rev-parse --short HEAD)'
```

### Feature Branch Testing  
Deploy feature-specific test instances:

```yaml
temporary-corpus-key: 'FEATURE_${{ github.ref_name }}_${{ github.run_id }}'
```

### Time-Limited Demos
Create demo bots with specific expiration:

```yaml
temporary-corpus-key: 'DEMO_${{ github.event.inputs.demo_name }}'
temporary-corpus-key-ttl-hours: '168'  # 1 week
```

## Integration with Wildcard Lambda

The temporary corpus key feature works seamlessly with your new wildcard-enabled Lambda:

- **General Lambda**: Can deploy any temporary corpus key
- **RIGHTNOW_BOT Wildcard Lambda**: Can deploy `RIGHTNOW_BOT_TEMP_*` patterns
- **Pattern Validation**: Temporary keys must still match the Lambda's allowed patterns

## Automatic Expiration

Objects deployed with temporary corpus keys will automatically be cleaned up by DynamoDB TTL after the specified duration. No manual cleanup is required.
