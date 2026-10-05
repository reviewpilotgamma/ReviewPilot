### Executive Summary
This PR adds naive retries to the payment charge call. Retries without idempotency keys risk double charges.

### Architectural Findings
- **Critical** Non-idempotent retries — `app/payments.py`: retrying a POST without an idempotency key can charge twice.
- **Warning** Missing timeout — `app/payments.py`: `requests.post` has no timeout.

### Specific Recommendations
1. Send an idempotency key with each charge.
2. Add a timeout and exponential backoff.

### What Looks Solid
- Retry count is bounded.

<!-- reviewpilot-meta: {"score": 3.5, "verdict": "critical"} -->
