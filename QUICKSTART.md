# Quick Start Guide (5 minutes)

## What This Is

A universal adapter that lets you connect to **any AI chatbot API** using the same code. Just provide an OpenAPI spec, and the system generates the configuration automatically.

## Setup

```bash
cd ai-connector-engine
pip install -r requirements.txt
```

## Verify It Works

```bash
python test.py
# Should show: ALL TESTS PASSED ✅
```

## The Core Workflow

### 1. Generate Config from OpenAPI Spec

```bash
python generate_config.py \
  --spec specs/openai_openapi.yaml \
  --output configs/my_config.json \
  --verbose
```

Output:
```
Parsing OpenAPI spec: specs/openai_openapi.yaml
API: OpenAI API
Base URL: https://api.openai.com/v1
Found 2 potential chat endpoints:
  [49.6] POST /chat/completions  ← Selected (highest score)
  [26.9] POST /completions

✅ Generated config: configs/my_config.json
```

### 2. Run Scanner with Mock Mode

```bash
python scanner.py \
  --config configs/my_config.json \
  --prompts prompts.txt \
  --mock
```

Output:
```
[1/5] Scanning: Hello, how are you?...
         ✅ good (confidence: 0.74, latency: 295ms)
[2/5] Scanning: What is the capital of France?...
         ❌ bad (confidence: 0.85, latency: 205ms)
...

SCAN SUMMARY
Total prompts:     5
Good responses:    4 (80.0%)
Bad responses:     1 (20.0%)
```

### 3. Test with Real API (Optional)

```bash
export OPENAI_API_KEY='sk-your-key-here'
python main.py --config configs/my_config.json --prompt "Hello!"
```

## How It Works

```
OpenAPI Spec → Parser → ConnectorConfig → Runtime → Any AI API
    (YAML)              (JSON)         (Python)
```

1. **Parser** reads OpenAPI spec, finds the chat endpoint using keyword scoring
2. **Config** captures: base URL, auth method, request/response mapping
3. **Runtime** uses config to make HTTP calls to any provider uniformly

## Adding a New AI Provider

1. Get their OpenAPI spec (or create one from their docs)
2. Run: `python generate_config.py --spec their_spec.yaml --output configs/new_provider.json`
3. Test: `python scanner.py --config configs/new_provider.json --prompts prompts.txt --mock`
4. Done! Scanner now works with the new provider

## Key Files

| File | Purpose |
|------|---------|
| `generate_config.py` | Create config from OpenAPI spec |
| `scanner.py` | Run batch prompts through any API |
| `main.py` | Test single prompt |
| `test.py` | Verify everything works |
| `demo.py` | Full interactive demo |

## Run the Full Demo

```bash
python demo.py
```

This shows all 4 APIs being parsed and configured automatically.
