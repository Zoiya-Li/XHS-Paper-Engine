"""
Retry mechanism module - Provides unified retry logic for API calls

Usage:
    from dp_core.retry import call_api_with_retry

    response = call_api_with_retry(
        lambda: requests.post(url, json=data, timeout=60),
        max_retries=3,
        api_name="OpenRouter"
    )
"""

import time
import functools
from typing import Callable, Type, Tuple, Optional, Any

# Try to import requests exception types
try:
    import requests
    REQUESTS_EXCEPTIONS = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.HTTPError,
        requests.exceptions.ChunkedEncodingError,  # Add ChunkedEncodingError support
    )
except ImportError:
    REQUESTS_EXCEPTIONS = ()

# Default retryable exception types
DEFAULT_RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
) + REQUESTS_EXCEPTIONS


def call_api_with_retry(
    api_call: Callable[[], Any],
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    api_name: str = "API",
    retryable_exceptions: Tuple[Type[Exception], ...] = None,
    on_retry: Optional[Callable[[int, int, Exception, float], None]] = None
) -> Any:
    """
    API call helper function with exponential backoff

    Args:
        api_call: API call to execute (lambda or function)
        max_retries: Maximum retry count (default 3)
        base_delay: Base delay time in seconds (default 2.0)
        max_delay: Maximum delay time in seconds (default 60.0)
        backoff_factor: Backoff factor (default 2.0, exponential growth)
        api_name: API name (for logging)
        retryable_exceptions: Exception types that trigger retry
        on_retry: Callback function on retry (attempt, max_retries, error, delay)

    Returns:
        Return value of API call

    Raises:
        Exception from last call (if all retries fail)

    Example:
        >>> response = call_api_with_retry(
        ...     lambda: requests.post(url, json=data, timeout=60),
        ...     max_retries=3,
        ...     api_name="OpenRouter"
        ... )
    """
    if retryable_exceptions is None:
        retryable_exceptions = DEFAULT_RETRYABLE_EXCEPTIONS

    def default_on_retry(attempt: int, max_attempts: int, error: Exception, delay: float):
        print(f"  ⚠️  {api_name} call failed: {type(error).__name__}: {str(error)[:100]}")
        print(f"      Retry {attempt}/{max_attempts}, waiting {delay:.1f} seconds...")

    if on_retry is None:
        on_retry = default_on_retry

    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return api_call()
        except retryable_exceptions as e:
            last_exception = e
            if attempt < max_retries:
                # Calculate exponential backoff delay
                delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                on_retry(attempt + 1, max_retries, e, delay)
                time.sleep(delay)
            else:
                # Last retry also failed
                print(f"  ❌ {api_name} call failed, retried {max_retries} times: {e}")
                raise
        except Exception as e:
            # Non-retryable exception, throw directly
            print(f"  ❌ {api_name} encountered non-retryable error: {type(e).__name__}: {e}")
            raise

    # Theoretically shouldn't reach here
    raise last_exception


def retry_decorator(
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = None,
    api_name: str = None
):
    """
    Retry decorator with exponential backoff

    Args:
        max_retries: Maximum retry count
        base_delay: Base delay time in seconds
        max_delay: Maximum delay time in seconds
        backoff_factor: Backoff factor
        retryable_exceptions: Exception types that trigger retry
        api_name: API name (for logging, defaults to function name)

    Example:
        >>> @retry_decorator(max_retries=3, api_name="MyAPI")
        ... def call_external_api():
        ...     return requests.get(url)
    """
    if retryable_exceptions is None:
        retryable_exceptions = DEFAULT_RETRYABLE_EXCEPTIONS

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            name = api_name or func.__name__
            return call_api_with_retry(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                backoff_factor=backoff_factor,
                api_name=name,
                retryable_exceptions=retryable_exceptions
            )
        return wrapper
    return decorator


# Pre-configured retry functions for common scenarios
def retry_llm_call(api_call: Callable, api_name: str = "LLM") -> Any:
    """LLM API call retry (longer timeout, more retries)"""
    return call_api_with_retry(
        api_call,
        max_retries=3,
        base_delay=3.0,
        max_delay=60.0,
        api_name=api_name
    )


def retry_search_api(api_call: Callable, api_name: str = "Search") -> Any:
    """Search API call retry (standard configuration)"""
    return call_api_with_retry(
        api_call,
        max_retries=3,
        base_delay=2.0,
        max_delay=30.0,
        api_name=api_name
    )


def retry_local_service(api_call: Callable, api_name: str = "LocalService") -> Any:
    """Local service call retry (shorter delay)"""
    return call_api_with_retry(
        api_call,
        max_retries=5,
        base_delay=1.0,
        max_delay=10.0,
        api_name=api_name
    )
