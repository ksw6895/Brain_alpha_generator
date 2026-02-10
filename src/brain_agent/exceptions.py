"""Custom exceptions for the agent."""

from __future__ import annotations


class BrainAgentError(Exception):
    """Base exception for this project."""


class BrainAPIError(BrainAgentError):
    """Raised for API-level errors."""


class ManualActionRequired(BrainAgentError):
    """Raised when a manual login step is required."""

    def __init__(self, message: str, action_url: str | None = None):
        super().__init__(message)
        self.action_url = action_url


class ValidationError(BrainAgentError):
    """Raised when expression validation fails."""
