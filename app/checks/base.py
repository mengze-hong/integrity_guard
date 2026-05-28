"""Base class for all gate checks."""

from abc import ABC, abstractmethod

from app.models import CheckResult, ParsedPaper


class BaseGate(ABC):
    """Abstract base class for integrity check gates."""

    name: str = "unnamed_gate"
    description: str = "No description"
    is_blocking: bool = True  # If True, failure means paper cannot be submitted

    @abstractmethod
    async def check(self, paper: ParsedPaper) -> CheckResult:
        """Run the check and return results."""
        ...
