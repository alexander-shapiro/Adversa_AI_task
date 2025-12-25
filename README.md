# Universal AI API Connector Engine

A universal adapter for connecting to arbitrary AI chatbot APIs.

## Phases Completed

| Phase  | Goal                             | Status  |
|--------|----------------------------------|---------|
| 1      | Walking Skeleton - One API works | ✅      |
| 2      | Second API + Scanner Mock        | ✅      |
| 3      | Config Generator from OpenAPI    | ✅      |
| 4      | Hardening + 4th API              | ✅      |

### What's Built

```
ai-connector-engine/
├── configs/
│   ├── openai.json               # Manual config (reference)
│   ├── anthropic.json            # Manual config (reference)
│   ├── openai_generated.json     # Auto-generated
│   ├── anthropic_generated.json  # Auto-generated
│   ├── cohere_generated.json     # Auto-generated
│   └── groq_generated.json       # Auto-generated (4th API)
├── specs/
│   ├── openai_openapi.yaml       # OpenAPI specs
│   ├── anthropic_openapi.yaml
│   ├── cohere_openapi.yaml
│   └── groq_openapi.yaml
├── src/
│   ├── __init__.py
│   ├── config_schema.py          # ConnectorConfig dataclass
│   ├── runtime.py                # HTTP executor + retry logic
│   └── openapi_parser.py         # OpenAPI parser + generator
├── main.py                       # CLI entry point (single prompt)
├── scanner.py                    # Mock scanner (batch prompts)
├── generate_config.py            # Config generator CLI
├── test.py                       # Test suite
├── prompts.txt                   # Sample prompts
└── requirements.txt
```

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests (no API key needed)
python test.py

# Generate config from OpenAPI spec
python generate_config.py --spec specs/openai_openapi.yaml --output configs/my_openai.json --verbose

# Test scanner with generated config (mock mode)
python scanner.py --config configs/openai_generated.json --prompts prompts.txt --mock

# Test with real API
export OPENAI_API_KEY='sk-your-key-here'
python scanner.py --config configs/openai_generated.json --prompts prompts.txt
```

### Phase 4 Additions: Hardening

**Retry Logic with Exponential Backoff:**
```python
RetryConfig(
    max_retries=3,
    base_delay=1.0,      # Start with 1 second
    max_delay=30.0,      # Cap at 30 seconds
    exponential_base=2.0,
    retry_on=(ErrorType.RATE_LIMIT, ErrorType.SERVER_ERROR, ErrorType.TIMEOUT)
)
```

**Error Classification:**
- `AUTH_ERROR` (401, 403) — Invalid credentials, don't retry
- `RATE_LIMIT` (429) — Retry with backoff
- `SERVER_ERROR` (500+) — Retry with backoff
- `TIMEOUT` — Retry with backoff
- `BAD_REQUEST` (400) — Invalid request, don't retry
- `NETWORK_ERROR` — Connection issues
- `PARSE_ERROR` — Response parsing failed

**Latency Tracking:**
```
============================================================
SCAN SUMMARY - OpenAI API
============================================================
Total prompts:     5
Good responses:    4 (80.0%)
Bad responses:     1 (20.0%)
Errors:            0 (0.0%)
Avg latency:       191ms
Avg confidence:    0.83
Total retries:     2
============================================================
```

### Validated API Patterns (4 APIs)

| Provider | Endpoint | Prompt Field | Response Field | Auth |
|----------|----------|--------------|----------------|------|
| OpenAI | /chat/completions | messages[] | choices.0.message.content | Bearer |
| Anthropic | /messages | messages[] | content.0.text | x-api-key |
| Cohere | /chat | message | text | Bearer |
| Groq | /chat/completions | messages[] | choices.0.message.content | Bearer |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    OpenAPI Spec (YAML)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  OpenAPI Parser                             │
│  • Endpoint detection (keyword scoring)                     │
│  • Auth detection (Bearer, API key)                         │
│  • Field mapping (prompt, response)                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  ConnectorConfig (JSON)                     │
│  • Provider, base_url, auth                                 │
│  • Request mapping (endpoint, static_fields)                │
│  • Response mapping (response_field)                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  ConnectorRuntime                           │
│  • Build headers (auth, extra headers)                      │
│  • Build body (inject prompt)                               │
│  • Execute with retry logic                                 │
│  • Parse response (extract content)                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Scanner                                 │
│  • Load prompts from file                                   │
│  • Call connector for each prompt                           │
│  • Analyze responses (mock: random good/bad)                │
│  • Generate summary report                                  │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Heuristics-based parsing** — No LLM required, deterministic results
2. **`{prompt}` placeholder** — Handles complex nested structures
3. **Dot notation paths** — `choices.0.message.content` for nested extraction
4. **Retry with backoff** — Handles transient failures gracefully
5. **Error classification** — Smart retry decisions based on error type
6. **Config-driven** — All API specifics in JSON, runtime is generic
