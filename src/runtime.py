"""
Runtime Executor - Executes API calls based on ConnectorConfig

This is the core engine that:
1. Reads a ConnectorConfig
2. Builds the HTTP request (with auth, body mapping)
3. Makes the call with retry logic
4. Extracts the response

Design decisions:
- Uses httpx for modern HTTP client features
- Synchronous for simplicity (async can be added later)
- Exponential backoff for retries
- Classifies errors (rate limit, auth, server, network)
"""

import httpx
import copy
import time
import logging
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from .config_schema import ConnectorConfig

# Configure logging
logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Classification of API errors for better handling."""
    SUCCESS = "success"
    AUTH_ERROR = "auth_error"           # 401, 403
    RATE_LIMIT = "rate_limit"           # 429
    BAD_REQUEST = "bad_request"         # 400
    SERVER_ERROR = "server_error"       # 500+
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    PARSE_ERROR = "parse_error"
    UNKNOWN = "unknown"


@dataclass
class ConnectorResponse:
    """Unified response from any AI API."""
    success: bool
    content: Optional[str] = None  # The actual response text
    raw_response: Optional[dict] = None  # Full API response for debugging
    error: Optional[str] = None  # Error message if failed
    error_type: ErrorType = ErrorType.SUCCESS
    status_code: Optional[int] = None
    latency_ms: Optional[int] = None  # Request latency
    retries: int = 0  # Number of retries attempted


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0  # Base delay in seconds
    max_delay: float = 30.0  # Maximum delay
    exponential_base: float = 2.0
    retry_on: tuple = (ErrorType.RATE_LIMIT, ErrorType.SERVER_ERROR, ErrorType.TIMEOUT)


class ConnectorRuntime:
    """
    Executes API calls based on ConnectorConfig.
    
    This is the universal adapter - it treats all AI APIs uniformly.
    Features:
    - Automatic retry with exponential backoff
    - Error classification
    - Request latency tracking
    """
    
    def __init__(
        self, 
        config: ConnectorConfig, 
        credential: str,
        retry_config: Optional[RetryConfig] = None,
        verbose: bool = False
    ):
        """
        Initialize the runtime with a config and credential.
        
        Args:
            config: The ConnectorConfig defining how to talk to this API
            credential: The API key/token (kept separate from config for security)
            retry_config: Optional retry configuration
            verbose: Enable verbose logging
        """
        self.config = config
        self.credential = credential
        self.retry_config = retry_config or RetryConfig()
        self.verbose = verbose
        self.client = httpx.Client(timeout=config.timeout_seconds)
        
        if verbose:
            logging.basicConfig(level=logging.DEBUG)
    
    def _build_headers(self) -> dict:
        """Build request headers including auth if configured."""
        headers = {
            "Content-Type": self.config.request.content_type,
        }
        
        # Add any extra headers required by the API
        if self.config.request.extra_headers:
            headers.update(self.config.request.extra_headers)
        
        # Inject auth into headers if type is "header"
        if self.config.auth and self.config.auth.type == "header":
            auth_value = self.config.auth.value_template.format(
                credential=self.credential
            )
            headers[self.config.auth.key_name] = auth_value
        
        return headers
    
    def _build_body(self, prompt: str) -> dict:
        """Build request body with prompt injected at the right location."""
        body = copy.deepcopy(self.config.request.static_fields)  # Deep copy static fields
        
        # Handle the prompt injection
        prompt_field = self.config.request.prompt_field
        
        # Check if this is a "messages" style API (OpenAI, Anthropic, etc.)
        # Convention: if prompt_field contains "messages", we look for {prompt} placeholder
        if "{prompt}" in str(body):
            # Template-based injection - replace {prompt} anywhere in the structure
            body = self._replace_prompt_placeholder(body, prompt)
        else:
            # Simple field injection
            self._set_nested_value(body, prompt_field, prompt)
        
        # Inject auth into body if type is "body"
        if self.config.auth and self.config.auth.type == "body":
            auth_value = self.config.auth.value_template.format(
                credential=self.credential
            )
            self._set_nested_value(body, self.config.auth.key_name, auth_value)
        
        return body
    
    def _replace_prompt_placeholder(self, obj: Any, prompt: str) -> Any:
        """Recursively replace {prompt} placeholder in the body structure."""
        if isinstance(obj, str):
            return obj.replace("{prompt}", prompt)
        elif isinstance(obj, dict):
            return {k: self._replace_prompt_placeholder(v, prompt) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_prompt_placeholder(item, prompt) for item in obj]
        else:
            return obj
    
    def _set_nested_value(self, obj: dict, path: str, value: Any) -> None:
        """
        Set a value at a nested path using dot notation.
        
        Examples:
            - "prompt" -> obj["prompt"] = value
            - "messages" -> obj["messages"] = value (for arrays, value should be the array)
        
        Note: For complex nested structures like OpenAI's messages array,
        we handle this in static_fields + special prompt injection.
        """
        parts = path.split(".")
        current = obj
        
        for i, part in enumerate(parts[:-1]):
            if part.isdigit():
                # Array index - skip, handled differently
                continue
            if part not in current:
                current[part] = {}
            current = current[part]
        
        final_key = parts[-1]
        if final_key.isdigit():
            # This shouldn't happen in our schema, but handle gracefully
            return
        current[final_key] = value
    
    def _get_nested_value(self, obj: dict, path: str) -> Any:
        """
        Get a value from a nested path using dot notation.
        
        Examples:
            - "choices.0.message.content" -> obj["choices"][0]["message"]["content"]
            - "response" -> obj["response"]
        """
        parts = path.split(".")
        current = obj
        
        for part in parts:
            if current is None:
                return None
            if part.isdigit():
                # Array index
                idx = int(part)
                if isinstance(current, list) and len(current) > idx:
                    current = current[idx]
                else:
                    return None
            else:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None
        
        return current
    
    def _classify_error(self, status_code: Optional[int], exception: Optional[Exception] = None) -> ErrorType:
        """Classify the error type based on status code or exception."""
        if exception:
            if isinstance(exception, httpx.TimeoutException):
                return ErrorType.TIMEOUT
            elif isinstance(exception, httpx.RequestError):
                return ErrorType.NETWORK_ERROR
            else:
                return ErrorType.UNKNOWN
        
        if status_code is None:
            return ErrorType.UNKNOWN
        
        if status_code == 401 or status_code == 403:
            return ErrorType.AUTH_ERROR
        elif status_code == 429:
            return ErrorType.RATE_LIMIT
        elif status_code == 400:
            return ErrorType.BAD_REQUEST
        elif status_code >= 500:
            return ErrorType.SERVER_ERROR
        elif status_code >= 400:
            return ErrorType.UNKNOWN
        
        return ErrorType.SUCCESS
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for retry with exponential backoff."""
        delay = self.retry_config.base_delay * (self.retry_config.exponential_base ** attempt)
        return min(delay, self.retry_config.max_delay)
    
    def _should_retry(self, error_type: ErrorType, attempt: int) -> bool:
        """Determine if we should retry based on error type and attempt count."""
        if attempt >= self.retry_config.max_retries:
            return False
        return error_type in self.retry_config.retry_on
    
    def send_prompt(self, prompt: str) -> ConnectorResponse:
        """
        Send a prompt to the configured API and return the response.
        
        This is the main interface - all APIs are called the same way.
        Includes automatic retry logic for transient failures.
        """
        url = f"{self.config.base_url.rstrip('/')}{self.config.request.endpoint}"
        headers = self._build_headers()
        body = self._build_body(prompt)
        
        last_response = None
        attempt = 0
        
        while True:
            start_time = time.time()
            
            try:
                if self.verbose:
                    logger.debug(f"Attempt {attempt + 1}: POST {url}")
                    logger.debug(f"Headers: {headers}")
                    logger.debug(f"Body: {body}")
                
                response = self.client.request(
                    method=self.config.request.method,
                    url=url,
                    headers=headers,
                    json=body,
                )
                
                latency_ms = int((time.time() - start_time) * 1000)
                
                # Parse response
                if response.status_code >= 400:
                    error_type = self._classify_error(response.status_code)
                    
                    # Check if we should retry
                    if self._should_retry(error_type, attempt):
                        delay = self._calculate_delay(attempt)
                        if self.verbose:
                            logger.debug(f"Retrying in {delay:.1f}s (error: {error_type.value})")
                        time.sleep(delay)
                        attempt += 1
                        continue
                    
                    # Build error message
                    error_msg = f"API returned status {response.status_code}"
                    try:
                        error_data = response.json()
                        if self.config.response.error_field:
                            error_detail = self._get_nested_value(
                                error_data, 
                                self.config.response.error_field
                            )
                            if error_detail:
                                error_msg = f"{error_msg}: {error_detail}"
                        else:
                            error_msg = f"{error_msg}: {error_data}"
                    except:
                        error_msg = f"{error_msg}: {response.text}"
                    
                    return ConnectorResponse(
                        success=False,
                        error=error_msg,
                        error_type=error_type,
                        status_code=response.status_code,
                        raw_response=error_data if 'error_data' in locals() else None,
                        latency_ms=latency_ms,
                        retries=attempt,
                    )
                
                # Success - extract response content
                response_data = response.json()
                content = self._get_nested_value(
                    response_data,
                    self.config.response.response_field
                )
                
                if content is None:
                    return ConnectorResponse(
                        success=False,
                        error=f"Could not extract response from path '{self.config.response.response_field}'",
                        error_type=ErrorType.PARSE_ERROR,
                        raw_response=response_data,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        retries=attempt,
                    )
                
                return ConnectorResponse(
                    success=True,
                    content=str(content),
                    raw_response=response_data,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    retries=attempt,
                )
                
            except httpx.TimeoutException:
                latency_ms = int((time.time() - start_time) * 1000)
                error_type = ErrorType.TIMEOUT
                
                if self._should_retry(error_type, attempt):
                    delay = self._calculate_delay(attempt)
                    if self.verbose:
                        logger.debug(f"Retrying in {delay:.1f}s (timeout)")
                    time.sleep(delay)
                    attempt += 1
                    continue
                
                return ConnectorResponse(
                    success=False,
                    error=f"Request timed out after {self.config.timeout_seconds}s",
                    error_type=error_type,
                    latency_ms=latency_ms,
                    retries=attempt,
                )
                
            except httpx.RequestError as e:
                latency_ms = int((time.time() - start_time) * 1000)
                error_type = ErrorType.NETWORK_ERROR
                
                if self._should_retry(error_type, attempt):
                    delay = self._calculate_delay(attempt)
                    if self.verbose:
                        logger.debug(f"Retrying in {delay:.1f}s (network error)")
                    time.sleep(delay)
                    attempt += 1
                    continue
                
                return ConnectorResponse(
                    success=False,
                    error=f"Request failed: {str(e)}",
                    error_type=error_type,
                    latency_ms=latency_ms,
                    retries=attempt,
                )
                
            except Exception as e:
                latency_ms = int((time.time() - start_time) * 1000)
                return ConnectorResponse(
                    success=False,
                    error=f"Unexpected error: {str(e)}",
                    error_type=ErrorType.UNKNOWN,
                    latency_ms=latency_ms,
                    retries=attempt,
                )
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
