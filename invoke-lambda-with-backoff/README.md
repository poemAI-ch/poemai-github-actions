# Invoke Lambda with backoff

Invoke a Lambda synchronously using GitHub OIDC. The caller needs `id-token: write`
and a role allowing `lambda:InvokeFunction` for the target. This action does not
check out repository code, upload to S3, or manage application resources.

```yaml
- uses: poemAI-ch/poemai-github-actions/invoke-lambda-with-backoff@<reviewed-commit-or-release>
  id: invoke
  with:
    role-to-assume: arn:aws:iam::123456789012:role/my-invocation-role
    function-name: my-function
    region: eu-central-2
    payload-file: ${{ runner.temp }}/request.json
    read-timeout: '310'
    connect-timeout: '5'
    max-attempts: '4'
    initial-delay: '5'
    log-response: 'false'
```

Prepare a complete JSON request file locally before calling the action. The file
is sent directly to Lambda, without an S3 staging upload. Relative paths resolve
against the caller's working directory. Alternatively use inline `payload`,
`payload: '@request.json'`, `file://path`, or `fileb://path`. Omitted payload defaults
to `{}`. `payload-file` cannot be combined with a non-default `payload`.
Requests must contain exactly one JSON value; YAML conversion belongs to the caller.

| Input | Default | Meaning |
| --- | --- | --- |
| `role-to-assume` | Required | OIDC invocation role ARN |
| `function-name` | Required | Target function name or ARN |
| `region` | `eu-central-1` | AWS region |
| `payload` | `{}` | Inline JSON or a file shorthand |
| `payload-file` | Empty | Complete JSON request file |
| `read-timeout` | `60` | Positive socket read timeout in seconds |
| `connect-timeout` | `60` | Positive connection timeout in seconds |
| `max-attempts` | `8` | Total invocation attempts, including the first |
| `initial-delay` | `2` | Initial exponential delay in seconds; adds up to one second jitter |
| `log-type` | `None` | Lambda log request type; returned log tails are not printed |
| `log-response` | `true` | Print function response and CLI error bodies |

AWS CLI automatic retries are disabled. Only explicit AWS Invoke throttling errors
are retried, with exponential backoff and jitter. Transport timeouts, permission
errors and function errors fail immediately. A lost response can follow successful
execution; callers must account for this ambiguity before manually retrying.

The action requires synchronous status 200, no `FunctionError`, and a nonempty
response. The legacy JSON `errorMessage` check remains. `success` reports invocation
success, **not application-level success**: callers must validate their own response
contract. `response` preserves the function body as a multiline output, including
function error bodies when present. Treat that output as potentially sensitive.

Request payloads are never logged. Set `log-response: false` to suppress response,
raw CLI error and returned log bodies; outputs remain available for validation.
Use environment variables to consume outputs rather than interpolating them into
shell source. Temporary request/response files are cleaned up on exit.

Tests use a fake AWS CLI and never contact AWS:

```sh
python -m pytest invoke-lambda-with-backoff/tests -q
```
