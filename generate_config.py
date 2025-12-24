#!/usr/bin/env python3
"""
Config Generator CLI

Generates ConnectorConfig from OpenAPI specifications.

Usage:
    python generate_config.py --spec specs/openai_openapi.yaml --output configs/openai_generated.json
    python generate_config.py --spec specs/anthropic_openapi.yaml --output configs/anthropic_generated.json --model claude-3-haiku-20240307
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.openapi_parser import main

if __name__ == '__main__':
    exit(main())
