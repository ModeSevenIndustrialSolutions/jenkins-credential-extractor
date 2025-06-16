# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Error handling and retry mechanisms for Jenkins automation."""

import time
import random
from typing import Any, Callable, Optional, Type, Union
from functools import wraps
import requests
from rich.console import Console

console = Console()


class JenkinsError(Exception):
    """Base exception for Jenkins-related errors."""
    pass


class AuthenticationError(JenkinsError):
    """Raised when authentication fails."""
    pass


class NetworkError(JenkinsError):
    """Raised when network operations fail."""
    pass


class ScriptExecutionError(JenkinsError):
    """Raised when Jenkins script execution fails."""
    pass


class ConfigurationError(JenkinsError):
    """Raised when configuration is invalid."""
    pass


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        backoff_factor: float = 1.0
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.backoff_factor = backoff_factor


def calculate_retry_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay before next retry attempt."""
    # Exponential backoff
    delay = config.base_delay * (config.exponential_base ** attempt) * config.backoff_factor

    # Cap at maximum delay
    delay = min(delay, config.max_delay)

    # Add jitter to prevent thundering herd
    if config.jitter:
        jitter_amount = delay * 0.1  # 10% jitter
        delay += random.uniform(-jitter_amount, jitter_amount)

    return max(0, delay)


def retry_with_backoff(
    retry_config: Optional[RetryConfig] = None,
    exceptions: tuple = (requests.RequestException, NetworkError),
    on_retry: Optional[Callable[[int, Exception], None]] = None
):
    """Decorator for retrying function calls with exponential backoff."""
    if retry_config is None:
        retry_config = RetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(retry_config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == retry_config.max_retries:
                        # Final attempt failed
                        console.print(f"[red]Final retry attempt failed: {e}[/red]")
                        break

                    # Calculate delay for next attempt
                    delay = calculate_retry_delay(attempt, retry_config)

                    if on_retry:
                        on_retry(attempt + 1, e)
                    else:
                        console.print(
                            f"[yellow]Attempt {attempt + 1} failed: {e}. "
                            f"Retrying in {delay:.1f}s...[/yellow]"
                        )

                    time.sleep(delay)

            # All retries exhausted
            raise last_exception

        return wrapper
    return decorator


class CircuitBreaker:
    """Circuit breaker pattern for handling cascading failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time >= self.timeout:
                self.state = "HALF_OPEN"
                console.print("[yellow]Circuit breaker: Attempting recovery[/yellow]")
            else:
                raise JenkinsError("Circuit breaker is OPEN - service unavailable")

        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                console.print("[green]Circuit breaker: Service recovered[/green]")
            return result
        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                console.print(
                    f"[red]Circuit breaker: OPEN due to {self.failure_count} failures[/red]"
                )

            raise e


class ErrorRecoveryManager:
    """Manages error recovery strategies for Jenkins operations."""

    def __init__(self):
        self.circuit_breakers = {}
        self.error_counts = {}
        self.last_errors = {}

    def get_circuit_breaker(self, operation: str) -> CircuitBreaker:
        """Get or create circuit breaker for an operation."""
        if operation not in self.circuit_breakers:
            self.circuit_breakers[operation] = CircuitBreaker(
                failure_threshold=3,
                timeout=30.0,
                expected_exception=JenkinsError
            )
        return self.circuit_breakers[operation]

    def record_error(self, operation: str, error: Exception) -> None:
        """Record an error for tracking and analysis."""
        if operation not in self.error_counts:
            self.error_counts[operation] = 0

        self.error_counts[operation] += 1
        self.last_errors[operation] = {
            "error": str(error),
            "type": type(error).__name__,
            "timestamp": time.time()
        }

        console.print(f"[red]Error recorded for {operation}: {error}[/red]")

    def get_error_statistics(self) -> dict:
        """Get error statistics for all operations."""
        return {
            "error_counts": self.error_counts.copy(),
            "last_errors": self.last_errors.copy(),
            "circuit_breaker_states": {
                op: cb.state for op, cb in self.circuit_breakers.items()
            }
        }

    def reset_statistics(self) -> None:
        """Reset all error statistics."""
        self.error_counts.clear()
        self.last_errors.clear()
        for cb in self.circuit_breakers.values():
            cb.failure_count = 0
            cb.state = "CLOSED"
        console.print("[green]Error statistics reset[/green]")


def handle_jenkins_errors(func: Callable) -> Callable:
    """Decorator to handle and categorize Jenkins-specific errors."""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except requests.exceptions.ConnectionError as e:
            raise NetworkError(f"Connection failed: {e}") from e
        except requests.exceptions.Timeout as e:
            raise NetworkError(f"Request timeout: {e}") from e
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Authentication failed") from e
            elif e.response.status_code == 403:
                raise AuthenticationError("Access forbidden") from e
            elif e.response.status_code >= 500:
                raise NetworkError(f"Server error: {e}") from e
            else:
                raise JenkinsError(f"HTTP error: {e}") from e
        except Exception as e:
            # Log unexpected errors
            console.print(f"[red]Unexpected error in {func.__name__}: {e}[/red]")
            raise JenkinsError(f"Unexpected error: {e}") from e

    return wrapper


class ProgressiveBackoff:
    """Progressive backoff strategy that adapts based on success/failure patterns."""

    def __init__(self):
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.current_delay = 1.0
        self.min_delay = 0.5
        self.max_delay = 120.0

    def record_success(self) -> None:
        """Record a successful operation."""
        self.consecutive_successes += 1
        self.consecutive_failures = 0

        # Reduce delay on consecutive successes
        if self.consecutive_successes >= 3:
            self.current_delay = max(self.min_delay, self.current_delay * 0.8)
            self.consecutive_successes = 0

    def record_failure(self) -> None:
        """Record a failed operation."""
        self.consecutive_failures += 1
        self.consecutive_successes = 0

        # Increase delay on consecutive failures
        self.current_delay = min(self.max_delay, self.current_delay * 1.5)

    def get_delay(self) -> float:
        """Get current delay with small random jitter."""
        jitter = random.uniform(0.9, 1.1)
        return self.current_delay * jitter


# Global error recovery manager instance
error_recovery = ErrorRecoveryManager()


def log_performance_metrics(operation: str, duration: float, success: bool) -> None:
    """Log performance metrics for operations."""
    status = "SUCCESS" if success else "FAILURE"
    console.print(
        f"[blue]PERF[/blue] {operation}: {duration:.2f}s [{status}]"
    )


class RateLimiter:
    """Rate limiter to prevent overwhelming Jenkins server."""

    def __init__(self, requests_per_second: float = 5.0):
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0

    def wait_if_needed(self) -> None:
        """Wait if necessary to respect rate limit."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            time.sleep(sleep_time)

        self.last_request_time = time.time()


# Default rate limiter instance
default_rate_limiter = RateLimiter(requests_per_second=3.0)


def validate_jenkins_response(response: requests.Response) -> None:
    """Validate Jenkins response and raise appropriate errors."""
    if response.status_code == 404:
        raise JenkinsError("Jenkins endpoint not found")
    elif response.status_code == 401:
        raise AuthenticationError("Authentication required")
    elif response.status_code == 403:
        raise AuthenticationError("Access forbidden - check permissions")
    elif response.status_code >= 500:
        raise NetworkError(f"Jenkins server error: {response.status_code}")
    elif not response.ok:
        raise JenkinsError(f"Request failed: {response.status_code} - {response.text}")


def safe_execute_with_recovery(
    operation: str,
    func: Callable,
    *args,
    recovery_manager: Optional[ErrorRecoveryManager] = None,
    **kwargs
) -> Any:
    """Safely execute a function with comprehensive error recovery."""
    if recovery_manager is None:
        recovery_manager = error_recovery

    circuit_breaker = recovery_manager.get_circuit_breaker(operation)
    start_time = time.time()
    success = False

    try:
        result = circuit_breaker.call(func, *args, **kwargs)
        success = True
        duration = time.time() - start_time
        log_performance_metrics(operation, duration, True)
        return result
    except Exception as e:
        duration = time.time() - start_time
        log_performance_metrics(operation, duration, False)
        recovery_manager.record_error(operation, e)
        raise e
