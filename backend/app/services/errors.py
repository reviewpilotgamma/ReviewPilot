"""Exception hierarchy shared by services and the worker.

``retryable`` tells the worker whether a failed job should be re-queued.
``user_reason`` is a short, safe string that may appear in a public GitHub comment.
``code`` is an optional stable identifier the UI can key on (exposed as ``error_code`` on jobs).
"""

from __future__ import annotations


class ServiceError(Exception):
    retryable: bool = False
    user_reason: str = "unexpected error"
    code: str | None = None


class NotConfiguredError(ServiceError):
    """A required integration is not configured (surfaced as HTTP 503 by the API)."""


class GitHubNotConfigured(NotConfiguredError):
    user_reason = "GitHub App not configured"


class GitHubError(ServiceError):
    user_reason = "GitHub API unavailable"

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubPermanentError(GitHubError):
    pass


class GitHubTransientError(GitHubError):
    retryable = True


class GitHubRateLimited(GitHubTransientError):
    def __init__(self, message: str, retry_after: float = 60.0, status_code: int | None = None) -> None:
        super().__init__(message, status_code)
        self.retry_after = retry_after


class DiffFetchError(GitHubPermanentError):
    user_reason = "PR diff could not be fetched"


class DiffTooLargeError(DiffFetchError):
    """GitHub refused to render the PR diff (HTTP 406). Not retried and not worked around."""

    code = "diff_too_large"
    user_reason = (
        "this PR's diff is larger than GitHub allows ReviewPilot to fetch — "
        "split the PR into smaller ones and comment @review again"
    )


class ReauthRequired(ServiceError):
    """The user's GitHub token is expired or revoked."""


class GeminiNotConfigured(NotConfiguredError):
    user_reason = "AI model not configured"


class GeminiError(ServiceError):
    user_reason = "AI model unavailable"


class GeminiPermanentError(GeminiError):
    pass


class ContextTooLargeError(GeminiPermanentError):
    """The system prompt and repository documents leave no room in the context window for the diff."""

    user_reason = "repository documents are too large to review alongside this diff"


class GeminiTransientError(GeminiError):
    retryable = True


ERROR_CODES = {cls.__name__: cls.code for cls in (DiffTooLargeError,) if cls.code}


def error_code_for(last_error: str | None) -> str | None:
    """Map a stored job error (``"<ClassName>: message"``, as written by the worker) to its stable code."""
    if not last_error:
        return None
    return ERROR_CODES.get(last_error.split(":", 1)[0].strip())
