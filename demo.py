#!/usr/bin/env python3
"""
Demo Script - Universal AI API Connector Engine

This script demonstrates the full workflow:
1. Parse an OpenAPI spec
2. Generate a ConnectorConfig
3. Run the scanner with mock mode
4. Show results

Run with: python demo.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.openapi_parser import OpenAPIParser, ConfigGenerator
from src.config_schema import ConnectorConfig
from src.runtime import ConnectorRuntime, RetryConfig


def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def demo_config_generation():
    """Demonstrate automatic config generation from OpenAPI spec."""
    print_header("STEP 1: Parse OpenAPI Spec")
    
    specs = [
        ("specs/openai_openapi.yaml", "OpenAI"),
        ("specs/anthropic_openapi.yaml", "Anthropic"),
        ("specs/cohere_openapi.yaml", "Cohere"),
        ("specs/groq_openapi.yaml", "Groq"),
    ]
    
    for spec_path, name in specs:
        parser = OpenAPIParser(spec_path)
        endpoints = parser.find_chat_endpoints()
        
        print(f"\n{name}:")
        print(f"  Base URL: {parser.get_base_url()}")
        print(f"  Best endpoint: {endpoints[0].path} (score: {endpoints[0].score:.1f})")
        
        # Generate config
        generator = ConfigGenerator(parser)
        config = generator.generate()
        
        print(f"  Response field: {config['response']['response_field']}")


def demo_unified_interface():
    """Demonstrate that all APIs use the same interface."""
    print_header("STEP 2: Unified Interface Demo")
    
    configs = [
        "configs/openai_generated.json",
        "configs/anthropic_generated.json",
        "configs/cohere_generated.json",
        "configs/groq_generated.json",
    ]
    
    print("\nAll APIs use the SAME code:")
    print("```python")
    print("config = ConnectorConfig.from_json_file(config_path)")
    print("runtime = ConnectorRuntime(config, api_key)")
    print("response = runtime.send_prompt('Hello!')")
    print("print(response.content)")
    print("```")
    
    print("\nLoaded configs:")
    for config_path in configs:
        config = ConnectorConfig.from_json_file(config_path)
        print(f"  ✅ {config.name}")
        print(f"     Endpoint: {config.base_url}{config.request.endpoint}")


def demo_scanner():
    """Demonstrate the scanner workflow."""
    print_header("STEP 3: Scanner Demo (Mock Mode)")
    
    import subprocess
    result = subprocess.run(
        ["python", "scanner.py", "--config", "configs/openai_generated.json", 
         "--prompts", "prompts.txt", "--mock", "--quiet"],
        capture_output=True,
        text=True
    )
    
    # Parse and show summary
    output = result.stdout
    print(output)


def demo_retry_logic():
    """Demonstrate retry configuration."""
    print_header("STEP 4: Production Features")
    
    print("\nRetry Logic:")
    print("  • Exponential backoff (1s → 2s → 4s)")
    print("  • Retries on: RATE_LIMIT, SERVER_ERROR, TIMEOUT")
    print("  • No retry on: AUTH_ERROR, BAD_REQUEST")
    
    print("\nError Classification:")
    from src.runtime import ErrorType
    for error_type in ErrorType:
        print(f"  • {error_type.value}")


def demo_summary():
    """Show final summary."""
    print_header("SUMMARY")
    
    print("""
What This System Does:
  1. Takes an OpenAPI spec (YAML)
  2. Auto-detects the chat endpoint using heuristics
  3. Generates a ConnectorConfig (JSON)
  4. Runtime uses config to call ANY AI API uniformly

Validated APIs:
  ✅ OpenAI (GPT-3.5, GPT-4)
  ✅ Anthropic (Claude)
  ✅ Cohere (Command-R)
  ✅ Groq (Llama, Mixtral)

Key Commands:
  python test.py                    # Run tests
  python generate_config.py --spec specs/openai_openapi.yaml --output config.json
  python scanner.py --config config.json --prompts prompts.txt --mock
""")


def main():
    print("\n" + "=" * 60)
    print("   UNIVERSAL AI API CONNECTOR ENGINE - DEMO")
    print("=" * 60)
    
    demo_config_generation()
    demo_unified_interface()
    demo_scanner()
    demo_retry_logic()
    demo_summary()
    
    print("\n✅ Demo complete!\n")


if __name__ == "__main__":
    main()
