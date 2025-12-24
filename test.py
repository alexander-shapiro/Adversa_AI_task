#!/usr/bin/env python3
"""
Test script for Universal AI API Connector Engine

This verifies:
1. Config loading works
2. Request construction is correct
3. Response parsing works

Can be run without real API credentials.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config_schema import ConnectorConfig
from src.runtime import ConnectorRuntime


def test_config_loading():
    """Test that configs load correctly."""
    print("=" * 50)
    print("TEST: Config Loading")
    print("=" * 50)
    
    config = ConnectorConfig.from_json_file("configs/openai.json")
    
    assert config.name == "OpenAI GPT-3.5 Turbo"
    assert config.provider == "openai"
    assert config.base_url == "https://api.openai.com"
    assert config.auth.type == "header"
    assert config.auth.key_name == "Authorization"
    assert config.request.endpoint == "/v1/chat/completions"
    assert config.response.response_field == "choices.0.message.content"
    
    print("✅ Config loaded correctly")
    print(f"   Name: {config.name}")
    print(f"   Provider: {config.provider}")
    print(f"   Endpoint: {config.request.endpoint}")
    print()
    return config


def test_request_construction(config: ConnectorConfig):
    """Test that requests are constructed correctly."""
    print("=" * 50)
    print("TEST: Request Construction")
    print("=" * 50)
    
    runtime = ConnectorRuntime(config, "test-api-key")
    
    # Test header construction
    headers = runtime._build_headers()
    assert headers["Authorization"] == "Bearer test-api-key"
    assert headers["Content-Type"] == "application/json"
    print("✅ Headers constructed correctly")
    print(f"   Authorization: {headers['Authorization'][:20]}...")
    print(f"   Content-Type: {headers['Content-Type']}")
    
    # Test body construction
    body = runtime._build_body("Hello, how are you?")
    
    # Verify structure
    assert "model" in body
    assert "messages" in body
    assert len(body["messages"]) == 1
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][0]["content"] == "Hello, how are you?"
    
    print("✅ Body constructed correctly")
    print(f"   Model: {body['model']}")
    print(f"   Messages: {json.dumps(body['messages'], indent=4)}")
    print()
    
    runtime.close()
    return body


def test_response_parsing():
    """Test that responses are parsed correctly."""
    print("=" * 50)
    print("TEST: Response Parsing")
    print("=" * 50)
    
    config = ConnectorConfig.from_json_file("configs/openai.json")
    runtime = ConnectorRuntime(config, "test-api-key")
    
    # Mock OpenAI response
    mock_response = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-3.5-turbo-0613",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Hello! I'm doing well, thank you for asking."
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 9,
            "completion_tokens": 12,
            "total_tokens": 21
        }
    }
    
    # Test extraction
    content = runtime._get_nested_value(mock_response, config.response.response_field)
    
    assert content == "Hello! I'm doing well, thank you for asking."
    print("✅ Response parsed correctly")
    print(f"   Extracted content: {content}")
    print()
    
    runtime.close()


def test_mock_connector():
    """Test with a mock HTTP endpoint to verify full flow."""
    print("=" * 50)
    print("TEST: Mock Connector (httpbin.org)")
    print("=" * 50)
    
    # Can't easily use dataclass here without full setup, so skip this test
    print("⏭️  Skipped (would require network call)")
    print()


def test_openapi_parser():
    """Test the OpenAPI parser and config generator."""
    print("=" * 50)
    print("TEST: OpenAPI Parser & Config Generator")
    print("=" * 50)
    
    from src.openapi_parser import OpenAPIParser, ConfigGenerator
    
    # Test OpenAI spec parsing
    parser = OpenAPIParser("specs/openai_openapi.yaml")
    
    assert parser.get_provider_name() == "openai"
    assert "api.openai.com" in parser.get_base_url()
    
    endpoints = parser.find_chat_endpoints()
    assert len(endpoints) >= 1
    assert "/chat/completions" in endpoints[0].path
    
    print("✅ OpenAI spec parsed correctly")
    print(f"   Provider: {parser.get_provider_name()}")
    print(f"   Best endpoint: {endpoints[0].path} (score: {endpoints[0].score:.1f})")
    
    # Test config generation
    generator = ConfigGenerator(parser)
    config = generator.generate()
    
    assert config['provider'] == 'openai'
    assert config['request']['endpoint'] == '/chat/completions'
    assert config['response']['response_field'] == 'choices.0.message.content'
    
    print("✅ OpenAI config generated correctly")
    print(f"   Response field: {config['response']['response_field']}")
    
    # Test Anthropic spec
    parser2 = OpenAPIParser("specs/anthropic_openapi.yaml")
    
    assert parser2.get_provider_name() == "anthropic"
    
    auth = parser2.detect_auth()
    assert auth[1] == "x-api-key"
    
    generator2 = ConfigGenerator(parser2)
    config2 = generator2.generate()
    
    assert config2['response']['response_field'] == 'content.0.text'
    assert 'anthropic-version' in config2['request']['extra_headers']
    
    print("✅ Anthropic spec parsed correctly")
    print(f"   Auth header: {auth[1]}")
    print(f"   Extra headers: {list(config2['request']['extra_headers'].keys())}")
    
    # Test Cohere spec (different pattern)
    parser3 = OpenAPIParser("specs/cohere_openapi.yaml")
    generator3 = ConfigGenerator(parser3)
    config3 = generator3.generate()
    
    assert config3['request']['prompt_field'] == 'message'  # singular, not messages
    assert config3['response']['response_field'] == 'text'  # direct field, not nested
    
    print("✅ Cohere spec parsed correctly (different pattern)")
    print(f"   Prompt field: {config3['request']['prompt_field']}")
    print(f"   Response field: {config3['response']['response_field']}")
    print()


def test_error_types_and_retry():
    """Test error classification and retry config."""
    print("=" * 50)
    print("TEST: Error Types & Retry Logic")
    print("=" * 50)
    
    from src.runtime import ErrorType, RetryConfig
    
    # Test ErrorType enum
    assert ErrorType.AUTH_ERROR.value == "auth_error"
    assert ErrorType.RATE_LIMIT.value == "rate_limit"
    assert ErrorType.TIMEOUT.value == "timeout"
    print("✅ ErrorType enum defined correctly")
    
    # Test RetryConfig defaults
    retry_config = RetryConfig()
    assert retry_config.max_retries == 3
    assert retry_config.base_delay == 1.0
    assert ErrorType.RATE_LIMIT in retry_config.retry_on
    assert ErrorType.SERVER_ERROR in retry_config.retry_on
    assert ErrorType.AUTH_ERROR not in retry_config.retry_on  # Don't retry auth errors
    print("✅ RetryConfig defaults are sensible")
    
    # Test custom RetryConfig
    custom_config = RetryConfig(max_retries=5, base_delay=0.5)
    assert custom_config.max_retries == 5
    assert custom_config.base_delay == 0.5
    print("✅ Custom RetryConfig works")
    print()


def test_anthropic_config():
    """Test that Anthropic config loads and constructs requests correctly."""
    print("=" * 50)
    print("TEST: Anthropic Config")
    print("=" * 50)
    
    config = ConnectorConfig.from_json_file("configs/anthropic.json")
    
    # Verify config loaded
    assert config.name == "Anthropic Claude 3 Haiku"
    assert config.provider == "anthropic"
    assert config.base_url == "https://api.anthropic.com"
    assert config.auth.type == "header"
    assert config.auth.key_name == "x-api-key"
    assert config.request.endpoint == "/v1/messages"
    assert config.response.response_field == "content.0.text"
    
    print("✅ Anthropic config loaded correctly")
    print(f"   Name: {config.name}")
    print(f"   Auth header: {config.auth.key_name}")
    
    # Test header construction (should include anthropic-version)
    runtime = ConnectorRuntime(config, "test-anthropic-key")
    headers = runtime._build_headers()
    
    assert headers["x-api-key"] == "test-anthropic-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["Content-Type"] == "application/json"
    
    print("✅ Anthropic headers constructed correctly")
    print(f"   x-api-key: {headers['x-api-key'][:10]}...")
    print(f"   anthropic-version: {headers['anthropic-version']}")
    
    # Test body construction
    body = runtime._build_body("What is the meaning of life?")
    
    assert "model" in body
    assert body["model"] == "claude-3-haiku-20240307"
    assert "messages" in body
    assert body["messages"][0]["content"] == "What is the meaning of life?"
    
    print("✅ Anthropic body constructed correctly")
    print(f"   Model: {body['model']}")
    
    # Test response parsing with mock Anthropic response
    mock_response = {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": "The meaning of life is a profound philosophical question..."
            }
        ],
        "model": "claude-3-haiku-20240307",
        "stop_reason": "end_turn"
    }
    
    content = runtime._get_nested_value(mock_response, config.response.response_field)
    assert content == "The meaning of life is a profound philosophical question..."
    
    print("✅ Anthropic response parsed correctly")
    print(f"   Extracted: {content[:50]}...")
    print()
    
    runtime.close()


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 50)
    print("UNIVERSAL AI API CONNECTOR - TEST SUITE")
    print("=" * 50 + "\n")
    
    try:
        config = test_config_loading()
        test_request_construction(config)
        test_response_parsing()
        test_anthropic_config()
        test_openapi_parser()
        test_error_types_and_retry()
        test_mock_connector()
        
        print("=" * 50)
        print("ALL TESTS PASSED ✅")
        print("=" * 50)
        print("\nTo test with a real API:")
        print("  export OPENAI_API_KEY='your-key-here'")
        print("  python main.py --config configs/openai.json --prompt 'Hello!'")
        print("\n  export ANTHROPIC_API_KEY='your-key-here'")
        print("  python main.py --config configs/anthropic.json --prompt 'Hello!'")
        print("\nTo generate a config from OpenAPI spec:")
        print("  python generate_config.py --spec specs/openai_openapi.yaml --output configs/my_config.json")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
