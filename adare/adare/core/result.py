"""
Result pattern for API operations.

Provides a standardized way to return success/failure from service operations,
enabling any frontend (CLI, Web, REST API) to handle results consistently.
"""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from adare.exceptions import LoggedErrorException

T = TypeVar('T')


@dataclass
class ErrorInfo:
    """
    Serializable error information for any frontend.

    Attributes:
        code: Error code for programmatic handling (e.g., "NOT_FOUND", "DUPLICATE")
        message: Human-readable error message
        solutions: List of actionable suggestions to resolve the error
        context: Additional debug information (optional)
    """
    code: str
    message: str
    solutions: list[str] | None = None
    context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'code': self.code,
            'message': self.message,
        }
        if self.solutions:
            result['solutions'] = self.solutions
        if self.context:
            result['context'] = self.context
        return result


@dataclass
class Result(Generic[T]):
    """
    Standardized result container for all API operations.

    Every service method returns a Result[T] where T is the expected data type.
    This ensures consistent handling across all frontends.

    Usage:
        # Success case
        return Result.ok(ProjectInfo(name="test", ...))

        # Failure case
        return Result.fail("DUPLICATE", "Project already exists", ["Use a different name"])

        # From exception
        return Result.from_exception(caught_exception)

    Handling:
        result = api.project.create(request)
        if result.success:
            print(result.data.name)
        else:
            print(f"Error {result.error.code}: {result.error.message}")
    """
    success: bool
    data: T | None = None
    error: ErrorInfo | None = None
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls, data: T, warnings: list[str] | None = None) -> "Result[T]":
        """Create a successful result with data."""
        return cls(success=True, data=data, warnings=warnings or [])

    @classmethod
    def fail(
        cls,
        code: str,
        message: str,
        solutions: list[str] | None = None,
        context: dict[str, Any] | None = None
    ) -> "Result[T]":
        """Create a failure result with error information."""
        return cls(
            success=False,
            error=ErrorInfo(
                code=code,
                message=message,
                solutions=solutions,
                context=context
            )
        )

    @classmethod
    def from_exception(cls, exc: "LoggedErrorException") -> "Result[T]":
        """
        Convert an existing LoggedErrorException to a Result.

        Preserves error_name as code, message, and possible_solutions.
        This bridges the existing exception system with the Result pattern.
        """
        return cls(
            success=False,
            error=ErrorInfo(
                code=exc.error_name,
                message=exc.message,
                solutions=exc.possible_solutions if hasattr(exc, 'possible_solutions') else None
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {'success': self.success}
        if self.success and self.data is not None:
            # If data has to_dict method, use it; otherwise try __dict__ or str
            if hasattr(self.data, 'to_dict'):
                result['data'] = self.data.to_dict()
            elif hasattr(self.data, '__dict__'):
                result['data'] = self.data.__dict__
            else:
                result['data'] = str(self.data)
        if not self.success and self.error:
            result['error'] = self.error.to_dict()
        if self.warnings:
            result['warnings'] = self.warnings
        return result
