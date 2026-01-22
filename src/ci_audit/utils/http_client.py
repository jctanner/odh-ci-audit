"""HTTP client with retry logic and exponential backoff."""

import time
import logging
from typing import Optional, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .rate_limiter import RateLimiter


logger = logging.getLogger(__name__)


class RetryHTTPClient:
    """HTTP client with automatic retry and exponential backoff.

    Features:
    - Automatic retry on transient errors (5xx, connection errors)
    - Exponential backoff between retries
    - Rate limiting
    - Timeout handling
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        rate_limiter: Optional[RateLimiter] = None,
        timeout: int = 30,
    ):
        """Initialize HTTP client.

        Args:
            max_retries: Maximum number of retry attempts
            backoff_factor: Exponential backoff factor
            rate_limiter: Optional rate limiter
            timeout: Request timeout in seconds
        """
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.rate_limiter = rate_limiter
        self.timeout = timeout

        # Create session with retry logic
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retry configuration.

        Returns:
            Configured requests Session
        """
        session = requests.Session()

        # Configure retry strategy
        # Retry on: 500, 502, 503, 504, connection errors, read errors
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=[500, 502, 503, 504, 429],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
            raise_on_status=False,
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> requests.Response:
        """Perform HTTP GET request with retry logic.

        Args:
            url: URL to fetch
            params: Query parameters
            headers: HTTP headers
            **kwargs: Additional arguments passed to requests.get

        Returns:
            Response object

        Raises:
            requests.RequestException: On request failure after all retries
        """
        # Apply rate limiting
        if self.rate_limiter:
            self.rate_limiter.acquire()

        # Set default timeout
        kwargs.setdefault('timeout', self.timeout)

        try:
            response = self.session.get(url, params=params, headers=headers, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP GET failed for {url}: {e}")
            raise

    def post(
        self,
        url: str,
        data: Optional[Any] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> requests.Response:
        """Perform HTTP POST request with retry logic.

        Args:
            url: URL to post to
            data: Form data
            json: JSON data
            headers: HTTP headers
            **kwargs: Additional arguments passed to requests.post

        Returns:
            Response object

        Raises:
            requests.RequestException: On request failure after all retries
        """
        # Apply rate limiting
        if self.rate_limiter:
            self.rate_limiter.acquire()

        # Set default timeout
        kwargs.setdefault('timeout', self.timeout)

        try:
            response = self.session.post(url, data=data, json=json, headers=headers, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP POST failed for {url}: {e}")
            raise

    def download_file(self, url: str, destination: str, chunk_size: int = 8192) -> None:
        """Download file from URL to destination.

        Args:
            url: URL to download from
            destination: Local file path to save to
            chunk_size: Chunk size for streaming download

        Raises:
            requests.RequestException: On download failure
        """
        # Apply rate limiting
        if self.rate_limiter:
            self.rate_limiter.acquire()

        try:
            with self.session.get(url, stream=True, timeout=self.timeout) as response:
                response.raise_for_status()
                with open(destination, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:  # filter out keep-alive new chunks
                            f.write(chunk)
            logger.debug(f"Downloaded {url} to {destination}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Download failed for {url}: {e}")
            raise

    def close(self):
        """Close the session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
