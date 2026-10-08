### Executive Summary
- **What it does:** Adds naive retries to the payment charge call.
- **Overall risk:** Critical. Retries without idempotency keys can charge a customer twice.
- **Main concern:** Non-idempotent retries in `app/payments.py`.

### Architectural Findings
- **Critical** · **Non-idempotent retries**
  - **File(s):** `app/payments.py`
  - **Problem:** `charge()` retries a POST without an idempotency key.
  - **Impact:** A retried request can charge the customer twice.
- **Warning** · **Missing timeout**
  - **File(s):** `app/payments.py`
  - **Problem:** `requests.post` has no timeout.
  - **Impact:** A slow gateway can hang the worker.

### Specific Recommendations
1. **Send an idempotency key with each charge** in `app/payments.py`
   - Generate one key per charge and reuse it on every retry.
2. **Add a timeout and exponential backoff** in `app/payments.py`
   - Pass `timeout=` to `requests.post` and back off between attempts.

### What Looks Solid
- **Bounded retries** in `app/payments.py`: the retry count is capped.

<!-- reviewpilot-meta: {"score": 3.5, "verdict": "critical"} -->
