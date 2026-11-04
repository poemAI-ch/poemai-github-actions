#!/usr/bin/env bash
set -euo pipefail

# Values arrive through env, never through shell source interpolation.
PAYLOAD=${PAYLOAD:-\{\}}
PAYLOAD_FILE=${PAYLOAD_FILE:-}
LOG_TYPE=${LOG_TYPE:-None}
MAX_ATTEMPTS=${MAX_ATTEMPTS:-8}
INITIAL_DELAY=${INITIAL_DELAY:-2}
READ_TIMEOUT=${READ_TIMEOUT:-60}
CONNECT_TIMEOUT=${CONNECT_TIMEOUT:-60}
LOG_RESPONSE=${LOG_RESPONSE:-true}

printf 'success=false\nresponse=\n' >> "$GITHUB_OUTPUT"
fail() { printf '%s\n' "$1" >&2; exit 1; }
for value in "$MAX_ATTEMPTS" "$READ_TIMEOUT" "$CONNECT_TIMEOUT"; do
    [[ "$value" =~ ^[1-9][0-9]*$ ]] || fail 'Attempts and timeouts must be positive integers.'
done
[[ "$INITIAL_DELAY" =~ ^[0-9]+([.][0-9]+)?$ ]] || fail 'Initial delay must be a nonnegative number.'
[[ "$LOG_RESPONSE" == true || "$LOG_RESPONSE" == false ]] || fail 'log-response must be true or false.'

work=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/lambda-invoke.XXXXXXXX")
trap 'rm -rf "$work"' EXIT

if [[ -n "$PAYLOAD_FILE" ]]; then
    [[ "$PAYLOAD" == '{}' ]] || fail 'Choose payload-file or payload, not both.'
elif [[ "$PAYLOAD" == @* ]]; then
    PAYLOAD_FILE=${PAYLOAD:1}
elif [[ "$PAYLOAD" == fileb://* ]]; then
    PAYLOAD_FILE=${PAYLOAD#fileb://}
elif [[ "$PAYLOAD" == file://* ]]; then
    PAYLOAD_FILE=${PAYLOAD#file://}
fi
if [[ -n "$PAYLOAD_FILE" ]]; then
    cp -- "$PAYLOAD_FILE" "$work/request.json" 2>/dev/null || fail 'Cannot read payload file.'
else
    printf '%s' "$PAYLOAD" > "$work/request.json"
fi
# Accept exactly one JSON value, including false/null. Suppress parser diagnostics
# because they can contain request data.
jq -e -s 'length == 1' "$work/request.json" >/dev/null 2>&1 || fail 'Payload must contain exactly one JSON value.'

emit_response() {
    local delimiter="lambda_${RANDOM}_${RANDOM}_${RANDOM}"
    while grep -qxF "$delimiter" "$work/response"; do
        delimiter="lambda_${RANDOM}_${RANDOM}_${RANDOM}"
    done
    {
        printf 'response<<%s\n' "$delimiter"
        cat "$work/response"
        printf '\n%s\n' "$delimiter"
    } >> "$GITHUB_OUTPUT"
}

for ((attempt=1; attempt<=MAX_ATTEMPTS; attempt++)); do
    printf 'Lambda invocation attempt %s/%s\n' "$attempt" "$MAX_ATTEMPTS"
    rm -f "$work/response"
    if AWS_MAX_ATTEMPTS=1 AWS_RETRY_MODE=standard aws lambda invoke \
        --function-name "$FUNCTION_NAME" --region "$REGION" \
        --invocation-type RequestResponse --log-type "$LOG_TYPE" \
        --payload "fileb://$work/request.json" --cli-binary-format raw-in-base64-out \
        --cli-read-timeout "$READ_TIMEOUT" --cli-connect-timeout "$CONNECT_TIMEOUT" \
        --output json --no-cli-pager \
        "$work/response" > "$work/metadata" 2> "$work/error"; then
        if [[ -f "$work/response" ]]; then
            emit_response
            if [[ "$LOG_RESPONSE" == true ]]; then
                cat "$work/response"
                printf '\n'
            fi
        fi
        jq -e '.StatusCode == 200 and (has("FunctionError") | not)' "$work/metadata" >/dev/null 2>&1 \
            || fail 'Lambda invocation metadata indicates failure.'
        [[ -s "$work/response" ]] || fail 'Lambda returned no response.'
        if jq -e 'type == "object" and (.errorMessage != null and .errorMessage != false)' "$work/response" >/dev/null 2>&1; then
            fail 'Lambda response indicates a function error.'
        fi
        printf 'success=true\n' >> "$GITHUB_OUTPUT"
        exit 0
    fi
    if [[ "$LOG_RESPONSE" == true ]]; then cat "$work/error" >&2; fi
    if grep -Eq 'An error occurred \((Throttling|ThrottlingException|TooManyRequestsException)\) when calling the Invoke operation' "$work/error"; then
        ((attempt < MAX_ATTEMPTS)) || fail 'Lambda throttling retry limit reached.'
        delay=$(awk -v initial="$INITIAL_DELAY" -v attempt="$attempt" -v jitter="$RANDOM" \
            'BEGIN {printf "%.2f", initial * (2 ^ (attempt - 1)) + (jitter % 100) / 100}')
        sleep "$delay"
    else
        fail 'Lambda invocation failed; not retrying an ambiguous or permanent error.'
    fi
done
