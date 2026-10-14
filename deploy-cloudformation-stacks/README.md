# Deploy CloudFormation Stacks

A reusable GitHub Action for deploying CloudFormation stacks with hash-based lambda version support.

## Features

- **Hash-based Lambda Versions**: Supports individual lambda version resolution using hash-based lookup
- **Traditional Repo-wide Versions**: Backward compatible with existing version schemes
- **Parallel Deployment**: Configurable parallel deployment of stacks
- **Dry-run Support**: Test deployments without making actual changes
- **Force Deployment**: Override change detection for forced updates

## Usage

### Lambda-based Deployment (Current Pattern)
```yaml
- name: Deploy CloudFormation Stacks
  uses: poemAI-ch/poemai-github-actions/deploy-cloudformation-stacks@v5.9.4
  with:
    role-to-assume: arn:aws:iam::123456789012:role/deployment-role
    region: eu-central-1
    config-file: serverless_environments/staging/stacks.yaml
    lambda-function-name: poemai-deploy-lambda-staging
    command: deploy
```

### Direct Deployment
```yaml
- name: Deploy CloudFormation Stacks
  uses: poemAI-ch/poemai-github-actions/deploy-cloudformation-stacks@v5.9.4
  with:
    role-to-assume: arn:aws:iam::123456789012:role/deployment-role
    region: eu-central-1
    config-file: serverless_environments/staging/stacks.yaml
    environment: staging
    command: deploy
```

## Inputs

- `role-to-assume` (required): Full ARN of the IAM role to assume for deployment
- `region` (optional, default: "eu-central-1"): AWS region for deployment
- `config-file` (required): Path to the stacks configuration file (stacks.yaml)
- `lambda-function-name` (optional): Name of the Lambda function to call for deployment
- `environment` (optional): Deployment environment (development, staging, production)
- `stack-name` (optional): Specific stack name to deploy
- `command` (optional, default: "deploy"): Command to run (deploy, dump, dump_graph)

## Version Resolution

This action supports two types of version resolution:

### Traditional Repo-wide Versions
```yaml
globals:
  SomeLambdaVersion:
    $version: "poemAI-ch/poemai-lambdas"
```
Results in using the first 7 characters of the commit SHA.

### Hash-based Individual Lambda Versions
```yaml
globals:
  BotAdminLambdaVersion:
    $version: "poemAI-ch/poemai-lambdas#BotAdminLambdaVersion"
```
Results in using the full hash from the version key `BotAdminLambdaVersion`.

## Testing

Local testing can be done with:

```bash
cd deploy-cloudformation-stacks
pip install -r requirements.txt
python -m pytest tests/ -v
```

## Version History

- **v1.0.0**: Initial release with hash-based lambda version support

## Invocation and operation timeouts

Synchronous Lambda connections allow up to 930 seconds, covering Lambda's maximum
900-second execution time. Automatic SDK invocation retries are disabled. A Lambda
throttling response can be retried because the invocation was rejected; a read
timeout has an unknown outcome and fails the build without invoking the deployer
again. Inspect the stack before rerunning after this error.

The action validates deployer responses, including function errors and explicit
stack errors, before polling CloudFormation. An accepted response with
`operation_pending: true` means CloudFormation is still working: the action polls
its final state without invoking the deployer again. Polling uses bounded API
calls and a monotonic deadline. Individual stacks can configure
`stable_state_timeout_seconds` for long custom resource operations.
