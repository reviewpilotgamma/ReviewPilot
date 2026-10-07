"""Exception hierarchy shared by services and the worker.

``retryable`` tells the worker whether a failed job should be re-queued.
``user_reason`` is a short, safe string that may appear in a public GitHub comment.
"""

from __future__ import annotations


class ServiceError(Exception):
    retryable: bool = False
    user_reason: str = "unexpected error"


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


class ReauthRequired(ServiceError):
    """The user's GitHub token is expired or revoked."""


class GeminiNotConfigured(NotConfiguredError):
    user_reason = "AI model not configured"


class GeminiError(ServiceError):
    user_reason = "AI model unavailable"


class GeminiPermanentError(GeminiError):
    pass


class GeminiTransientError(GeminiError):
    retryable = True
