#!/usr/bin/env python3
"""
OpenAPI Parser & Config Generator

This module parses OpenAPI/Swagger specifications and automatically
generates ConnectorConfig JSON files for the Universal AI API Connector.

Design decisions:
1. Heuristics-based endpoint detection (no LLM required)
2. Keyword scoring to identify "chat" endpoints
3. Schema traversal to find prompt/response fields
4. Support for multiple auth patterns
"""

import yaml
import json
import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path


@dataclass
class EndpointCandidate:
    """A potential chat endpoint with its confidence score."""
    path: str
    method: str
    operation_id: str
    summary: str
    description: str
    score: float
    request_schema: Optional[Dict] = None
    response_schema: Optional[Dict] = None
    required_headers: List[Dict] = None


@dataclass 
class FieldMapping:
    """Mapping of prompt/response fields."""
    prompt_field: str
    prompt_template: Dict[str, Any]
    response_field: str


class OpenAPIParser:
    """
    Parses OpenAPI specs and identifies chat/completion endpoints.
    
    Heuristics used for endpoint detection:
    - Path keywords: chat, completion, message, generate, inference
    - Method: POST (required for chat)
    - Request schema: contains messages array or prompt field
    - Response schema: contains text/content/choices
    """
    
    # Scoring weights for endpoint detection
    PATH_KEYWORDS = {
        'chat': 10,
        'completions': 8,
        'completion': 8,
        'messages': 9,
        'message': 7,
        'generate': 6,
        'inference': 5,
        'converse': 7,
        'ask': 4,
    }
    
    NEGATIVE_KEYWORDS = {
        'list': -5,
        'delete': -10,
        'get': -3,
        'models': -5,
        'files': -10,
        'embeddings': -8,
        'images': -8,
        'audio': -8,
        'fine-tune': -10,
        'batch': -8,
    }
    
    REQUEST_FIELD_KEYWORDS = {
        'messages': 10,
        'message': 8,
        'prompt': 9,
        'content': 6,
        'input': 5,
        'text': 5,
        'query': 4,
    }
    
    RESPONSE_FIELD_KEYWORDS = {
        'content': 10,
        'text': 9,
        'message': 8,
        'choices': 7,
        'response': 6,
        'output': 5,
        'completion': 6,
        'generations': 7,
    }
    
    def __init__(self, spec_path: str):
        """Load and parse the OpenAPI spec."""
        self.spec_path = spec_path
        with open(spec_path, 'r') as f:
            self.spec = yaml.safe_load(f)
        
        self.info = self.spec.get('info', {})
        self.servers = self.spec.get('servers', [])
        self.paths = self.spec.get('paths', {})
        self.components = self.spec.get('components', {})
        self.security = self.spec.get('security', [])
    
    def get_base_url(self) -> str:
        """Extract the base URL from servers."""
        if self.servers:
            url = self.servers[0].get('url', '')
            # Remove trailing /v1, /v2, etc. if present (we'll get it from paths)
            return url.rstrip('/')
        return ''
    
    def get_provider_name(self) -> str:
        """Infer provider name from spec."""
        title = self.info.get('title', '')
        # Extract first word as provider
        if 'openai' in title.lower():
            return 'openai'
        elif 'anthropic' in title.lower():
            return 'anthropic'
        elif 'cohere' in title.lower():
            return 'cohere'
        else:
            # Use first word of title
            words = title.split()
            return words[0].lower() if words else 'unknown'
    
    def resolve_ref(self, ref: str) -> Dict:
        """Resolve a $ref to its actual schema."""
        if not ref.startswith('#/'):
            return {}
        
        parts = ref[2:].split('/')
        current = self.spec
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part, {})
            else:
                return {}
        return current
    
    def get_schema(self, schema_or_ref: Dict) -> Dict:
        """Get the actual schema, resolving $ref if needed."""
        if '$ref' in schema_or_ref:
            return self.resolve_ref(schema_or_ref['$ref'])
        return schema_or_ref
    
    def score_path(self, path: str) -> float:
        """Score a path based on keywords."""
        score = 0.0
        path_lower = path.lower()
        
        for keyword, weight in self.PATH_KEYWORDS.items():
            if keyword in path_lower:
                score += weight
        
        for keyword, weight in self.NEGATIVE_KEYWORDS.items():
            if keyword in path_lower:
                score += weight  # weight is negative
        
        return score
    
    def find_chat_endpoints(self) -> List[EndpointCandidate]:
        """Find all potential chat/completion endpoints."""
        candidates = []
        
        for path, path_item in self.paths.items():
            # Only consider POST endpoints
            if 'post' not in path_item:
                continue
            
            operation = path_item['post']
            
            # Calculate score
            score = self.score_path(path)
            
            # Bonus for operation ID keywords
            op_id = operation.get('operationId', '').lower()
            for keyword, weight in self.PATH_KEYWORDS.items():
                if keyword in op_id:
                    score += weight * 0.5
            
            # Bonus for summary/description keywords
            summary = operation.get('summary', '').lower()
            description = operation.get('description', '').lower()
            for keyword, weight in self.PATH_KEYWORDS.items():
                if keyword in summary or keyword in description:
                    score += weight * 0.3
            
            # Get request/response schemas
            request_schema = self._get_request_schema(operation)
            response_schema = self._get_response_schema(operation)
            
            # Bonus for request schema with messages/prompt
            if request_schema:
                props = request_schema.get('properties', {})
                for field in props:
                    if field.lower() in self.REQUEST_FIELD_KEYWORDS:
                        score += self.REQUEST_FIELD_KEYWORDS[field.lower()] * 0.5
            
            # Get required headers
            required_headers = self._get_required_headers(operation)
            
            if score > 0:
                candidates.append(EndpointCandidate(
                    path=path,
                    method='POST',
                    operation_id=operation.get('operationId', ''),
                    summary=operation.get('summary', ''),
                    description=operation.get('description', ''),
                    score=score,
                    request_schema=request_schema,
                    response_schema=response_schema,
                    required_headers=required_headers,
                ))
        
        # Sort by score descending
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates
    
    def _get_request_schema(self, operation: Dict) -> Optional[Dict]:
        """Extract the request body schema."""
        request_body = operation.get('requestBody', {})
        content = request_body.get('content', {})
        
        for content_type in ['application/json', '*/*']:
            if content_type in content:
                schema = content[content_type].get('schema', {})
                return self.get_schema(schema)
        
        return None
    
    def _get_response_schema(self, operation: Dict) -> Optional[Dict]:
        """Extract the 200 response schema."""
        responses = operation.get('responses', {})
        success_response = responses.get('200', responses.get('201', {}))
        content = success_response.get('content', {})
        
        for content_type in ['application/json', '*/*']:
            if content_type in content:
                schema = content[content_type].get('schema', {})
                return self.get_schema(schema)
        
        return None
    
    def _get_required_headers(self, operation: Dict) -> List[Dict]:
        """Extract required headers from operation parameters."""
        headers = []
        for param in operation.get('parameters', []):
            if param.get('in') == 'header' and param.get('required', False):
                headers.append({
                    'name': param.get('name'),
                    'value': param.get('schema', {}).get('example', ''),
                    'description': param.get('description', ''),
                })
        return headers
    
    def detect_auth(self) -> Tuple[str, str, str]:
        """
        Detect authentication method.
        
        Returns: (auth_type, key_name, value_template)
        """
        security_schemes = self.components.get('securitySchemes', {})
        
        for name, scheme in security_schemes.items():
            scheme_type = scheme.get('type', '')
            
            if scheme_type == 'http' and scheme.get('scheme') == 'bearer':
                return ('header', 'Authorization', 'Bearer {credential}')
            
            elif scheme_type == 'apiKey':
                location = scheme.get('in', 'header')
                key_name = scheme.get('name', 'api-key')
                return (location, key_name, '{credential}')
        
        # Default to bearer auth
        return ('header', 'Authorization', 'Bearer {credential}')
    
    def find_field_mapping(self, endpoint: EndpointCandidate) -> FieldMapping:
        """Find the prompt and response field mappings for an endpoint."""
        # Find prompt field in request
        prompt_field, prompt_template = self._find_prompt_field(endpoint.request_schema)
        
        # Find response field
        response_field = self._find_response_field(endpoint.response_schema)
        
        return FieldMapping(
            prompt_field=prompt_field,
            prompt_template=prompt_template,
            response_field=response_field,
        )
    
    def _find_prompt_field(self, schema: Optional[Dict]) -> Tuple[str, Dict]:
        """Find the field where the prompt should be injected."""
        if not schema:
            return ('prompt', {'prompt': '{prompt}'})
        
        props = schema.get('properties', {})
        required = schema.get('required', [])
        
        # Check for messages array (OpenAI/Anthropic style)
        if 'messages' in props:
            messages_schema = self.get_schema(props['messages'])
            if messages_schema.get('type') == 'array':
                return ('messages', {
                    'messages': [{'role': 'user', 'content': '{prompt}'}]
                })
        
        # Check for message field (Cohere style)
        if 'message' in props:
            return ('message', {'message': '{prompt}'})
        
        # Check for prompt field
        if 'prompt' in props:
            return ('prompt', {'prompt': '{prompt}'})
        
        # Check for content/input/text
        for field in ['content', 'input', 'text', 'query']:
            if field in props:
                return (field, {field: '{prompt}'})
        
        # Default
        return ('prompt', {'prompt': '{prompt}'})
    
    def _find_response_field(self, schema: Optional[Dict]) -> str:
        """Find the field containing the response text."""
        if not schema:
            return 'response'
        
        props = schema.get('properties', {})
        
        # Check for choices array (OpenAI style)
        if 'choices' in props:
            return 'choices.0.message.content'
        
        # Check for content array (Anthropic style)
        if 'content' in props:
            content_schema = self.get_schema(props['content'])
            if content_schema.get('type') == 'array':
                return 'content.0.text'
            return 'content'
        
        # Check for text field (Cohere style)
        if 'text' in props:
            return 'text'
        
        # Check for generations array
        if 'generations' in props:
            return 'generations.0.text'
        
        # Check for message
        if 'message' in props:
            return 'message.content'
        
        # Check for response/output
        for field in ['response', 'output', 'completion', 'result']:
            if field in props:
                return field
        
        return 'response'


class ConfigGenerator:
    """
    Generates ConnectorConfig from parsed OpenAPI spec.
    """
    
    def __init__(self, parser: OpenAPIParser):
        self.parser = parser
    
    def generate(self, model_hint: str = None) -> Dict:
        """
        Generate a ConnectorConfig dictionary.
        
        Args:
            model_hint: Optional model name to use in static_fields
        """
        # Find best chat endpoint
        endpoints = self.parser.find_chat_endpoints()
        if not endpoints:
            raise ValueError("No suitable chat endpoint found in spec")
        
        best_endpoint = endpoints[0]
        
        # Detect auth
        auth_type, key_name, value_template = self.parser.detect_auth()
        
        # Find field mappings
        mapping = self.parser.find_field_mapping(best_endpoint)
        
        # Build static fields
        static_fields = dict(mapping.prompt_template)
        
        # Add model if we can find a default
        if model_hint:
            static_fields['model'] = model_hint
        else:
            # Try to find model from schema
            if best_endpoint.request_schema:
                props = best_endpoint.request_schema.get('properties', {})
                if 'model' in props:
                    model_schema = props['model']
                    if 'example' in model_schema:
                        static_fields['model'] = model_schema['example']
                    elif 'default' in model_schema:
                        static_fields['model'] = model_schema['default']
        
        # Add max_tokens if required
        if best_endpoint.request_schema:
            required = best_endpoint.request_schema.get('required', [])
            if 'max_tokens' in required:
                static_fields['max_tokens'] = 1024
        
        # Build extra headers
        extra_headers = {}
        for header in (best_endpoint.required_headers or []):
            if header['name'] and header['value']:
                extra_headers[header['name']] = header['value']
        
        # Find error field
        error_field = 'error.message'  # Common pattern
        
        # Generate config
        config = {
            'name': f"{self.parser.info.get('title', 'Unknown API')}",
            'provider': self.parser.get_provider_name(),
            'version': '1.0',
            'base_url': self.parser.get_base_url(),
            'auth': {
                'type': auth_type,
                'key_name': key_name,
                'value_template': value_template,
            },
            'request': {
                'endpoint': best_endpoint.path,
                'method': 'POST',
                'prompt_field': mapping.prompt_field,
                'static_fields': static_fields,
                'content_type': 'application/json',
                'extra_headers': extra_headers,
            },
            'response': {
                'response_field': mapping.response_field,
                'error_field': error_field,
            },
            'streaming': False,
            'timeout_seconds': 30,
        }
        
        return config
    
    def generate_to_file(self, output_path: str, model_hint: str = None) -> str:
        """Generate config and save to file."""
        config = self.generate(model_hint)
        
        with open(output_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        return output_path


def main():
    """CLI for config generation."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Generate ConnectorConfig from OpenAPI spec'
    )
    parser.add_argument(
        '--spec', '-s',
        required=True,
        help='Path to OpenAPI spec (YAML or JSON)'
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='Output path for generated config'
    )
    parser.add_argument(
        '--model', '-m',
        help='Model name to use in config'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed parsing info'
    )
    
    args = parser.parse_args()
    
    print(f"Parsing OpenAPI spec: {args.spec}")
    
    # Parse spec
    openapi_parser = OpenAPIParser(args.spec)
    
    if args.verbose:
        print(f"\nAPI: {openapi_parser.info.get('title', 'Unknown')}")
        print(f"Base URL: {openapi_parser.get_base_url()}")
        print(f"Provider: {openapi_parser.get_provider_name()}")
        
        # Show detected endpoints
        endpoints = openapi_parser.find_chat_endpoints()
        print(f"\nFound {len(endpoints)} potential chat endpoints:")
        for ep in endpoints[:5]:
            print(f"  [{ep.score:.1f}] {ep.method} {ep.path}")
            print(f"       {ep.summary}")
        
        # Show auth
        auth = openapi_parser.detect_auth()
        print(f"\nAuth: {auth[0]} - {auth[1]}")
    
    # Generate config
    generator = ConfigGenerator(openapi_parser)
    
    try:
        output_path = generator.generate_to_file(args.output, args.model)
        print(f"\n✅ Generated config: {output_path}")
        
        # Show generated config
        with open(output_path) as f:
            config = json.load(f)
        
        print(f"\nConfig summary:")
        print(f"  Name: {config['name']}")
        print(f"  Provider: {config['provider']}")
        print(f"  Endpoint: {config['request']['endpoint']}")
        print(f"  Prompt field: {config['request']['prompt_field']}")
        print(f"  Response field: {config['response']['response_field']}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
