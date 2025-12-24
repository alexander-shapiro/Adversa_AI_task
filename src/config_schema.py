"""
ConnectorConfig Schema - The core abstraction for Universal AI API Connector

Design decisions:
1. JSON-serializable (no code in configs)
2. Explicit field mappings (not magic)
3. Extensible for future patterns (streaming, tools, MCP)
4. Auth-agnostic (supports header, query, body injection)
"""

from dataclasses import dataclass, field
from typing import Optional, Literal
import json


@dataclass
class AuthConfig:
    """Authentication configuration for API access."""
    type: Literal["header", "query", "body"]  # Where to inject the credential
    key_name: str  # Header name, query param, or body field
    value_template: str  # Template with {credential} placeholder
    # Example: "Bearer {credential}" or just "{credential}"


@dataclass
class RequestMapping:
    """Maps our unified interface to the specific API's request format."""
    endpoint: str  # Path to append to base_url (e.g., "/v1/chat/completions")
    method: Literal["POST", "GET"] = "POST"
    
    # Where to put the prompt in the request body
    # Uses dot notation for nested paths: "messages.0.content" or "prompt"
    prompt_field: str = "prompt"
    
    # Static fields to include in every request
    # Example: {"model": "gpt-4", "max_tokens": 1000}
    static_fields: dict = field(default_factory=dict)
    
    # Content-Type header (almost always JSON for AI APIs)
    content_type: str = "application/json"
    
    # Extra headers required by some APIs (e.g., anthropic-version)
    extra_headers: dict = field(default_factory=dict)


@dataclass
class ResponseMapping:
    """Maps the API's response format to our unified output."""
    # Path to extract the response text (dot notation)
    # Example: "choices.0.message.content" for OpenAI
    response_field: str = "response"
    
    # Optional: field containing error messages
    error_field: Optional[str] = None


@dataclass
class ConnectorConfig:
    """
    Complete configuration for connecting to an AI API.
    
    This is the core abstraction - the runtime only needs this to
    talk to ANY AI chatbot/agent API.
    """
    # Identity (required)
    name: str  # Human-readable name (e.g., "OpenAI GPT-4")
    provider: str  # Provider identifier (e.g., "openai", "anthropic")
    base_url: str  # API base URL (e.g., "https://api.openai.com")
    
    # Auth (optional, but almost always needed)
    auth: Optional[AuthConfig] = None
    
    # Request/Response mapping (optional)
    request: Optional[RequestMapping] = None
    response: Optional[ResponseMapping] = None
    
    # Metadata with defaults
    version: str = "1.0"  # Config schema version for future compatibility
    
    # Future extensibility (unused in Phase 1)
    streaming: bool = False  # Whether to use streaming mode
    timeout_seconds: int = 30
    
    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "name": self.name,
            "provider": self.provider,
            "version": self.version,
            "base_url": self.base_url,
            "auth": {
                "type": self.auth.type,
                "key_name": self.auth.key_name,
                "value_template": self.auth.value_template,
            } if self.auth else None,
            "request": {
                "endpoint": self.request.endpoint,
                "method": self.request.method,
                "prompt_field": self.request.prompt_field,
                "static_fields": self.request.static_fields,
                "content_type": self.request.content_type,
                "extra_headers": self.request.extra_headers,
            } if self.request else None,
            "response": {
                "response_field": self.response.response_field,
                "error_field": self.response.error_field,
            } if self.response else None,
            "streaming": self.streaming,
            "timeout_seconds": self.timeout_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ConnectorConfig":
        """Deserialize from JSON-compatible dict."""
        auth = None
        if data.get("auth"):
            auth = AuthConfig(
                type=data["auth"]["type"],
                key_name=data["auth"]["key_name"],
                value_template=data["auth"]["value_template"],
            )
        
        request = None
        if data.get("request"):
            request = RequestMapping(
                endpoint=data["request"]["endpoint"],
                method=data["request"].get("method", "POST"),
                prompt_field=data["request"]["prompt_field"],
                static_fields=data["request"].get("static_fields", {}),
                content_type=data["request"].get("content_type", "application/json"),
                extra_headers=data["request"].get("extra_headers", {}),
            )
        
        response = None
        if data.get("response"):
            response = ResponseMapping(
                response_field=data["response"]["response_field"],
                error_field=data["response"].get("error_field"),
            )
        
        return cls(
            name=data["name"],
            provider=data["provider"],
            version=data.get("version", "1.0"),
            base_url=data["base_url"],
            auth=auth,
            request=request,
            response=response,
            streaming=data.get("streaming", False),
            timeout_seconds=data.get("timeout_seconds", 30),
        )
    
    @classmethod
    def from_json_file(cls, path: str) -> "ConnectorConfig":
        """Load config from JSON file."""
        with open(path, "r") as f:
            return cls.from_dict(json.load(f))
    
    def to_json_file(self, path: str) -> None:
        """Save config to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
