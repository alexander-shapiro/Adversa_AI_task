#!/usr/bin/env python3
"""
Main entry point for Universal AI API Connector Engine

Usage:
    python main.py --config configs/openai.json --prompt "Hello, how are you?"
    
    # Or with credential from environment:
    export OPENAI_API_KEY="sk-..."
    python main.py --config configs/openai.json --prompt "Hello"
    
    # Or pass credential directly:
    python main.py --config configs/openai.json --prompt "Hello" --credential "sk-..."
"""

import argparse
import os
import sys
import json

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config_schema import ConnectorConfig
from src.runtime import ConnectorRuntime


def get_credential(args, config: ConnectorConfig) -> str:
    """
    Get API credential from args or environment.
    
    Looks for credential in this order:
    1. --credential argument
    2. Environment variable: {PROVIDER}_API_KEY (e.g., OPENAI_API_KEY)
    3. Generic API_KEY environment variable
    """
    if args.credential:
        return args.credential
    
    # Try provider-specific env var
    provider_env = f"{config.provider.upper()}_API_KEY"
    if provider_env in os.environ:
        return os.environ[provider_env]
    
    # Try generic env var
    if "API_KEY" in os.environ:
        return os.environ["API_KEY"]
    
    print(f"Error: No credential provided.")
    print(f"Either:")
    print(f"  1. Pass --credential 'your-api-key'")
    print(f"  2. Set {provider_env} environment variable")
    print(f"  3. Set API_KEY environment variable")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Universal AI API Connector - Send prompts to any AI API"
    )
    parser.add_argument(
        "--config", "-c",
        required=True,
        help="Path to connector config JSON file"
    )
    parser.add_argument(
        "--prompt", "-p",
        required=True,
        help="Prompt to send to the API"
    )
    parser.add_argument(
        "--credential", "-k",
        help="API credential (or set via environment variable)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output including raw response"
    )
    
    args = parser.parse_args()
    
    # Load config
    try:
        config = ConnectorConfig.from_json_file(args.config)
    except FileNotFoundError:
        print(f"Error: Config file not found: {args.config}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)
    
    # Get credential
    credential = get_credential(args, config)
    
    # Create runtime and send prompt
    print(f"Connecting to: {config.name}")
    print(f"Prompt: {args.prompt[:50]}{'...' if len(args.prompt) > 50 else ''}")
    print("-" * 40)
    
    with ConnectorRuntime(config, credential) as runtime:
        response = runtime.send_prompt(args.prompt)
    
    if response.success:
        print(f"Response:\n{response.content}")
        if args.verbose:
            print("-" * 40)
            print("Raw response:")
            print(json.dumps(response.raw_response, indent=2))
    else:
        print(f"Error: {response.error}")
        if response.status_code:
            print(f"Status code: {response.status_code}")
        if args.verbose and response.raw_response:
            print("-" * 40)
            print("Raw response:")
            print(json.dumps(response.raw_response, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
