#!/usr/bin/env python3
"""
Mock Scanner - Simulates the AI scanning tool workflow

This demonstrates how the Universal Connector integrates with a scanning workflow:
1. Load prompts from a database/file
2. Send prompts to an AI chatbot API (via connector)
3. Receive responses
4. Analyze whether response is "good" or "bad" (mocked)

Usage:
    python scanner.py --config configs/openai.json --prompts prompts.txt
    python scanner.py --config configs/anthropic.json --prompts prompts.txt --credential "sk-..."
    
    # Mock mode (no real API calls):
    python scanner.py --config configs/openai.json --prompts prompts.txt --mock
"""

import argparse
import os
import sys
import json
import random
import time
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config_schema import ConnectorConfig
from src.runtime import ConnectorRuntime, ConnectorResponse, ErrorType


@dataclass
class ScanResult:
    """Result of scanning a single prompt."""
    prompt: str
    response: Optional[str]
    verdict: str  # "good", "bad", "error"
    confidence: float  # 0.0 - 1.0
    latency_ms: int
    error: Optional[str] = None
    error_type: Optional[str] = None  # ErrorType value
    retries: int = 0


class MockAnalyzer:
    """
    Mock analyzer that randomly classifies responses as good/bad.
    
    In production, this would be replaced with actual analysis logic
    (e.g., checking for harmful content, policy violations, etc.)
    """
    
    def analyze(self, prompt: str, response: str) -> tuple[str, float]:
        """
        Analyze a response and return (verdict, confidence).
        
        This is intentionally simple - real analysis would be much more sophisticated.
        """
        # Mock logic: 70% good, 25% bad, 5% uncertain
        roll = random.random()
        
        if roll < 0.70:
            return ("good", random.uniform(0.7, 0.99))
        elif roll < 0.95:
            return ("bad", random.uniform(0.6, 0.95))
        else:
            # Uncertain - classify as good with low confidence
            return ("good", random.uniform(0.4, 0.6))


class Scanner:
    """
    Orchestrates the scanning workflow.
    
    Connects to an AI API via the universal connector and runs
    analysis on responses.
    """
    
    def __init__(
        self, 
        config: ConnectorConfig, 
        credential: str,
        analyzer: MockAnalyzer = None,
        mock_mode: bool = False
    ):
        self.config = config
        self.credential = credential
        self.analyzer = analyzer or MockAnalyzer()
        self.mock_mode = mock_mode
        self.runtime = None if mock_mode else ConnectorRuntime(config, credential)
    
    def load_prompts(self, path: str) -> List[str]:
        """Load prompts from a file (one per line)."""
        with open(path, "r") as f:
            prompts = [line.strip() for line in f if line.strip()]
        return prompts
    
    def _mock_response(self, prompt: str) -> ConnectorResponse:
        """Generate a mock response for testing without real API calls."""
        mock_responses = [
            "I'd be happy to help with that!",
            "That's an interesting question. Let me explain...",
            "Here's what I think about that topic.",
            "I understand your query. The answer is...",
            "Great question! Based on my knowledge...",
        ]
        
        # Simulate some latency
        time.sleep(random.uniform(0.1, 0.3))
        
        return ConnectorResponse(
            success=True,
            content=random.choice(mock_responses) + f" (Re: {prompt[:30]}...)",
            raw_response={"mock": True},
            status_code=200,
        )
    
    def scan_prompt(self, prompt: str) -> ScanResult:
        """Scan a single prompt and return the result."""
        start_time = time.time()
        
        # Get response from API (or mock)
        if self.mock_mode:
            response = self._mock_response(prompt)
        else:
            response = self.runtime.send_prompt(prompt)
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Use latency from response if available (more accurate)
        if response.latency_ms:
            latency_ms = response.latency_ms
        
        if not response.success:
            return ScanResult(
                prompt=prompt,
                response=None,
                verdict="error",
                confidence=0.0,
                latency_ms=latency_ms,
                error=response.error,
                error_type=response.error_type.value if hasattr(response, 'error_type') and response.error_type else None,
                retries=response.retries if hasattr(response, 'retries') else 0,
            )
        
        # Analyze the response
        verdict, confidence = self.analyzer.analyze(prompt, response.content)
        
        return ScanResult(
            prompt=prompt,
            response=response.content,
            verdict=verdict,
            confidence=confidence,
            latency_ms=latency_ms,
            retries=response.retries if hasattr(response, 'retries') else 0,
        )
    
    def scan_all(self, prompts: List[str], progress: bool = True) -> List[ScanResult]:
        """Scan all prompts and return results."""
        results = []
        
        for i, prompt in enumerate(prompts):
            if progress:
                print(f"[{i+1}/{len(prompts)}] Scanning: {prompt[:40]}...")
            
            result = self.scan_prompt(prompt)
            results.append(result)
            
            if progress:
                status = "✅" if result.verdict == "good" else "❌" if result.verdict == "bad" else "⚠️"
                print(f"         {status} {result.verdict} (confidence: {result.confidence:.2f}, latency: {result.latency_ms}ms)")
        
        return results
    
    def close(self):
        """Clean up resources."""
        if self.runtime:
            self.runtime.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


def print_summary(results: List[ScanResult], config_name: str):
    """Print a summary of scan results."""
    print("\n" + "=" * 60)
    print(f"SCAN SUMMARY - {config_name}")
    print("=" * 60)
    
    total = len(results)
    
    if total == 0:
        print("No prompts scanned.")
        print("=" * 60)
        return
    
    good = sum(1 for r in results if r.verdict == "good")
    bad = sum(1 for r in results if r.verdict == "bad")
    errors = sum(1 for r in results if r.verdict == "error")
    total_retries = sum(r.retries for r in results)
    
    avg_latency = sum(r.latency_ms for r in results) / total
    non_error_count = total - errors
    avg_confidence = sum(r.confidence for r in results if r.verdict != "error") / non_error_count if non_error_count > 0 else 0
    
    print(f"Total prompts:     {total}")
    print(f"Good responses:    {good} ({100*good/total:.1f}%)")
    print(f"Bad responses:     {bad} ({100*bad/total:.1f}%)")
    print(f"Errors:            {errors} ({100*errors/total:.1f}%)")
    print(f"Avg latency:       {avg_latency:.0f}ms")
    print(f"Avg confidence:    {avg_confidence:.2f}")
    if total_retries > 0:
        print(f"Total retries:     {total_retries}")
    print("=" * 60)
    
    # Show error breakdown if any
    if errors > 0:
        print("\n❌ ERRORS:")
        error_types = {}
        for r in results:
            if r.verdict == "error":
                et = r.error_type or "unknown"
                error_types[et] = error_types.get(et, 0) + 1
        for et, count in sorted(error_types.items(), key=lambda x: -x[1]):
            print(f"  {et}: {count}")
        print()
    
    # Show bad responses if any
    if bad > 0:
        print("\n⚠️  BAD RESPONSES:")
        for r in results:
            if r.verdict == "bad":
                print(f"  Prompt: {r.prompt[:50]}...")
                print(f"  Response: {r.response[:100] if r.response else 'N/A'}...")
                print()


def export_results(results: List[ScanResult], output_path: str):
    """Export results to JSON."""
    total_retries = sum(r.retries for r in results)
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "total": len(results),
        "summary": {
            "good": sum(1 for r in results if r.verdict == "good"),
            "bad": sum(1 for r in results if r.verdict == "bad"),
            "errors": sum(1 for r in results if r.verdict == "error"),
            "total_retries": total_retries,
        },
        "results": [
            {
                "prompt": r.prompt,
                "response": r.response,
                "verdict": r.verdict,
                "confidence": r.confidence,
                "latency_ms": r.latency_ms,
                "error": r.error,
                "error_type": r.error_type,
                "retries": r.retries,
            }
            for r in results
        ]
    }
    
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    
    print(f"\nResults exported to: {output_path}")


def get_credential(args, config: ConnectorConfig) -> str:
    """Get API credential from args or environment."""
    if args.mock:
        return "mock-credential"
    
    if args.credential:
        return args.credential
    
    provider_env = f"{config.provider.upper()}_API_KEY"
    if provider_env in os.environ:
        return os.environ[provider_env]
    
    if "API_KEY" in os.environ:
        return os.environ["API_KEY"]
    
    print(f"Error: No credential provided. Use --credential or set {provider_env}")
    print("       Or use --mock for testing without real API calls.")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="AI Response Scanner - Tests AI APIs with prompts and analyzes responses"
    )
    parser.add_argument(
        "--config", "-c",
        required=True,
        help="Path to connector config JSON file"
    )
    parser.add_argument(
        "--prompts", "-p",
        required=True,
        help="Path to prompts file (one prompt per line)"
    )
    parser.add_argument(
        "--credential", "-k",
        help="API credential (or set via environment variable)"
    )
    parser.add_argument(
        "--mock", "-m",
        action="store_true",
        help="Use mock mode (no real API calls)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Export results to JSON file"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output"
    )
    
    args = parser.parse_args()
    
    # Load config
    try:
        config = ConnectorConfig.from_json_file(args.config)
    except FileNotFoundError:
        print(f"Error: Config file not found: {args.config}")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)
    
    # Get credential
    credential = get_credential(args, config)
    
    # Print header
    mode = "MOCK MODE" if args.mock else "LIVE MODE"
    print(f"\n{'=' * 60}")
    print(f"AI RESPONSE SCANNER - {mode}")
    print(f"{'=' * 60}")
    print(f"Config:    {config.name}")
    print(f"Provider:  {config.provider}")
    print(f"Endpoint:  {config.base_url}{config.request.endpoint}")
    print(f"Prompts:   {args.prompts}")
    print(f"{'=' * 60}\n")
    
    # Run scanner
    with Scanner(config, credential, mock_mode=args.mock) as scanner:
        prompts = scanner.load_prompts(args.prompts)
        print(f"Loaded {len(prompts)} prompts\n")
        
        results = scanner.scan_all(prompts, progress=not args.quiet)
    
    # Print summary
    print_summary(results, config.name)
    
    # Export if requested
    if args.output:
        export_results(results, args.output)


if __name__ == "__main__":
    main()
