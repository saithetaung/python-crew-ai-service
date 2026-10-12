# MarineOn AI Service API Contract (OpenAPI)

This package documents the internal API between Spring Boot and the MarineOn FastAPI service.

## Files
- `marineon-openapi.yaml` — OpenAPI 3.1 contract.
- `README-marineon-api-contract.md` — integration and error-handling guidance.

## Error status codes

| HTTP | Error code | Meaning | Suggested Java behavior |
|---|---|---|---|
| 400 | `INVALID_REQUEST` | Request cannot be processed semantically | Correct request; do not retry unchanged |
| 401 | `UNAUTHENTICATED` | Missing/invalid internal service token | Fix credentials; do not retry unchanged |
| 403 | `FORBIDDEN` | Authenticated caller/actor context is not authorized | Stop and review authorization |
| 409 | `CONVERSATION_BUSY` | Another turn is processing for the same conversation | Retry briefly with a bounded policy, or ask user to retry |
| 413 | `MESSAGE_TOO_LARGE` | Message/request exceeds configured limit | Shorten request |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Content-Type is not `application/json` | Correct request headers |
| 422 | validation error | Request schema validation failed | Correct the fields; do not retry unchanged |
| 429 | `RATE_LIMITED` | Rate limit or provider throttling | Honor `Retry-After`; bounded exponential backoff with jitter |
| 500 | `INTERNAL_ERROR` | Unexpected application error | Log request ID; retry only if safe and policy allows |
| 502 | `UPSTREAM_PROVIDER_ERROR` | Bedrock/provider returned an upstream error | Retry only if marked retryable and safe |
| 503 | `SERVICE_UNAVAILABLE` | AI service or dependency unavailable | Bounded retry with jitter if safe |
| 504 | `UPSTREAM_TIMEOUT` | Timed out waiting for Bedrock/dependency | Do not blindly retry POST until idempotency/deduplication exists |

## Important implementation note

This OpenAPI file describes the target contract. Adding a response to OpenAPI does not make FastAPI emit it automatically. Implement normalized exception handlers and explicit provider-error mapping, then compare `http://127.0.0.1:8000/openapi.json` with this contract and test each status code. Default FastAPI validation responses may currently use a different shape; preserve `detail` for compatibility while adding stable `errorCode`, `requestId`, `retryable`, and optional safe `details`.

## Edge cases to account for

1. **Timeout after Bedrock may have processed a request:** `requestId` is currently a trace ID, not an idempotency key. A retry may generate a second answer. Add server-side idempotency storage before enabling automatic retries for ambiguous chat POST failures.
2. **Concurrent turns in one conversation:** serialize turns per conversation; return `409 CONVERSATION_BUSY` if the lock cannot be acquired. Do not serialize unrelated conversations.
3. **Session expiry:** if the Redis session key expires, start a fresh Bedrock session and do not assume previous context remains available.
4. **Redis outage:** return `503` when Redis is required and unavailable; avoid silently mixing conversations or using another user's session.
5. **Provider throttling and timeouts:** map known Bedrock throttling/timeouts to controlled `429`, `502`, `503`, or `504` responses rather than leaking raw AWS exceptions.
6. **Sensitive error details:** never expose stack traces, AWS credentials, raw prompts, internal S3 details beyond authorized citations, or secrets. Log safe diagnostics server-side with the correlation ID.
7. **Request limits:** enforce JSON content type, maximum body size, message length, and rate limits at both the service and ingress/proxy layers.
8. **Trust boundary:** derive user and tenant IDs from authenticated Spring Boot context; never accept browser-supplied identity as authoritative. Keep the AI endpoint on private networking where possible.

## Java client recommendations

- Branch on HTTP status and stable `errorCode`, never parse the human-readable `detail`.
- Honor `Retry-After`; use a small maximum retry count, exponential backoff, and jitter.
- Do not retry `400`, `401`, `403`, `413`, `415`, or `422` without correcting the cause.
- Treat `requestId` as correlation only unless a separate idempotency key and server-side deduplication are implemented.
- Set connect and response timeouts; keep them aligned with the expected Bedrock generation time.
- Do not return internal service tokens to the frontend.
