"""Benchmark voice pipeline latency components.

Measures the response latency of each service in the voice pipeline to verify
that the end-to-end voice-to-voice target of <1500ms is achievable:

- **Ollama LLM** (gpt-oss:20b-cloud): target ~300-600ms
- **FastAPI endpoints**: target <50ms per request
- **RAG query**: target ~200-500ms

Each benchmark runs multiple iterations and reports min / avg / max / p95
statistics in a formatted table.

Prerequisites:
    All three services must be running before executing this script:
    - ``make run-api``   (port 8000)
    - ``make run-agent`` (port 7860)

Usage::

    python scripts/benchmark_latency.py
"""

import asyncio
import statistics
import sys
import os
import time as time_module
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

try:
    import httpx
except ImportError:
    logger.error("httpx is required. Install with: pip install httpx")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gpt-oss:20b-cloud")

# Latency targets (milliseconds) from the spec
TARGETS: dict[str, float] = {
    "Ollama LLM": 600.0,
    "API Health": 50.0,
    "API Slots": 100.0,
    "API Doctors": 100.0,
    "RAG Query": 500.0,
}

# Test prompts for LLM benchmarking
LLM_TEST_PROMPTS: list[str] = [
    "What time does the clinic open?",
    "I want to book an appointment with a cardiologist.",
    "Do you accept BlueCross insurance?",
    "Can I cancel my appointment?",
    "What are the parking options at the clinic?",
]

# Test queries for RAG benchmarking
RAG_TEST_QUERIES: list[str] = [
    "What insurance plans do you accept?",
    "What are the clinic hours?",
    "Tell me about Dr. Sarah Patel",
    "What is the cancellation policy?",
    "Do you offer pediatric services?",
]


def _percentile(data: list[float], p: float) -> float:
    """Calculate the p-th percentile of a sorted list of values.

    Args:
        data: List of numeric values (will be sorted internally).
        p: Percentile to compute (0-100).

    Returns:
        The value at the given percentile.
    """
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    d0 = sorted_data[f] * (c - k)
    d1 = sorted_data[c] * (k - f)
    return d0 + d1


def _format_ms(value_ms: float) -> str:
    """Format a millisecond value to a string with 1 decimal place.

    Args:
        value_ms: Duration in milliseconds.

    Returns:
        Formatted string like "123.4ms".
    """
    return f"{value_ms:.1f}ms"


def _print_results(name: str, latencies_ms: list[float], target_ms: float) -> None:
    """Print a formatted results row for one benchmark.

    Args:
        name: Benchmark name.
        latencies_ms: List of measured latencies in milliseconds.
        target_ms: Target latency from the spec.
    """
    if not latencies_ms:
        print(f"  {name:<20} {'N/A':>10} {'N/A':>10} {'N/A':>10} {'N/A':>10} {'N/A':>10}")
        return

    min_val = min(latencies_ms)
    avg_val = statistics.mean(latencies_ms)
    max_val = max(latencies_ms)
    p95_val = _percentile(latencies_ms, 95)
    status = "PASS" if avg_val <= target_ms else "WARN"

    print(
        f"  {name:<20} "
        f"{_format_ms(min_val):>10} "
        f"{_format_ms(avg_val):>10} "
        f"{_format_ms(max_val):>10} "
        f"{_format_ms(p95_val):>10} "
        f"{'<=' + _format_ms(target_ms):>12} "
        f"[{status}]"
    )


async def benchmark_ollama_latency(num_runs: int = 5) -> list[float]:
    """Benchmark Ollama LLM response latency.

    Sends short conversational prompts to the Ollama ``/api/generate`` endpoint
    and measures time-to-first-response.  Uses ``stream=false`` for simplicity.

    Args:
        num_runs: Number of prompts to send.

    Returns:
        List of latency measurements in milliseconds.
    """
    latencies: list[float] = []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Warm-up request (not counted)
            logger.debug("Ollama warm-up request...")
            try:
                await client.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": "Hello",
                        "stream": False,
                    },
                )
            except Exception:
                pass

            for i in range(num_runs):
                prompt = LLM_TEST_PROMPTS[i % len(LLM_TEST_PROMPTS)]
                start = time_module.perf_counter()

                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_predict": 50},
                    },
                )
                resp.raise_for_status()

                elapsed_ms = (time_module.perf_counter() - start) * 1000
                latencies.append(elapsed_ms)
                logger.debug(
                    "  Ollama run {}/{}: {:.1f}ms", i + 1, num_runs, elapsed_ms
                )

    except httpx.ConnectError:
        logger.warning(
            "Cannot connect to Ollama at {}. Is it running? "
            "Start with: ollama serve",
            OLLAMA_BASE_URL,
        )
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Ollama returned HTTP {}: {}. Is the model '{}' pulled?",
            exc.response.status_code,
            exc.response.text[:200],
            OLLAMA_MODEL,
        )
    except Exception as exc:
        logger.warning("Ollama benchmark failed: {}", exc)

    return latencies


async def benchmark_api_latency(num_runs: int = 10) -> dict[str, list[float]]:
    """Benchmark FastAPI endpoint latencies.

    Tests the health check, doctor listing, and slot query endpoints
    to measure backend response times.

    Args:
        num_runs: Number of requests per endpoint.

    Returns:
        Dict mapping endpoint name to list of latencies in milliseconds.
    """
    results: dict[str, list[float]] = {
        "API Health": [],
        "API Doctors": [],
        "API Slots": [],
    }

    endpoints = [
        ("API Health", "GET", "/health", None),
        ("API Doctors", "GET", "/api/doctors/", None),
        ("API Slots", "GET", "/api/appointments/slots", {"doctor_name": "Wilson"}),
    ]

    try:
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=10.0
        ) as client:
            # Warm-up
            logger.debug("API warm-up request...")
            try:
                await client.get("/health")
            except Exception:
                pass

            for name, method, path, params in endpoints:
                for i in range(num_runs):
                    start = time_module.perf_counter()

                    if method == "GET":
                        resp = await client.get(path, params=params)
                    else:
                        resp = await client.post(path, json=params or {})

                    resp.raise_for_status()
                    elapsed_ms = (time_module.perf_counter() - start) * 1000
                    results[name].append(elapsed_ms)

                logger.debug(
                    "  {} ({} runs): avg {:.1f}ms",
                    name,
                    num_runs,
                    statistics.mean(results[name]) if results[name] else 0,
                )

    except httpx.ConnectError:
        logger.warning(
            "Cannot connect to API at {}. Is it running? Start with: make run-api",
            API_BASE_URL,
        )
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "API returned HTTP {}: {}",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except Exception as exc:
        logger.warning("API benchmark failed: {}", exc)

    return results


async def benchmark_rag_latency(num_runs: int = 5) -> list[float]:
    """Benchmark RAG query latency via the API endpoint.

    Sends natural-language questions to ``/api/rag/query`` and measures
    end-to-end retrieval + synthesis time.

    Args:
        num_runs: Number of queries to send.

    Returns:
        List of latency measurements in milliseconds.
    """
    latencies: list[float] = []

    try:
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=30.0
        ) as client:
            # Warm-up
            logger.debug("RAG warm-up request...")
            try:
                await client.get("/api/rag/query", params={"q": "hello"})
            except Exception:
                pass

            for i in range(num_runs):
                query = RAG_TEST_QUERIES[i % len(RAG_TEST_QUERIES)]
                start = time_module.perf_counter()

                resp = await client.get("/api/rag/query", params={"q": query})
                resp.raise_for_status()

                elapsed_ms = (time_module.perf_counter() - start) * 1000
                latencies.append(elapsed_ms)
                logger.debug(
                    "  RAG run {}/{}: {:.1f}ms (q={!r})",
                    i + 1,
                    num_runs,
                    elapsed_ms,
                    query[:40],
                )

    except httpx.ConnectError:
        logger.warning(
            "Cannot connect to API at {}. Is it running? Start with: make run-api",
            API_BASE_URL,
        )
    except Exception as exc:
        logger.warning("RAG benchmark failed: {}", exc)

    return latencies


async def main() -> None:
    """Run all benchmarks and print a formatted results table.

    Executes Ollama, API, and RAG benchmarks sequentially, then prints
    a summary table showing min/avg/max/p95 for each component alongside
    the target latency from the spec.
    """
    print()
    print("=" * 90)
    print("  VOICE HEALTH AGENT -- LATENCY BENCHMARK")
    print("=" * 90)
    print()
    print(f"  API Server:   {API_BASE_URL}")
    print(f"  Ollama:       {OLLAMA_BASE_URL}")
    print(f"  LLM Model:    {OLLAMA_MODEL}")
    print()

    # Run benchmarks
    logger.info("Starting Ollama LLM benchmark...")
    ollama_latencies = await benchmark_ollama_latency(num_runs=5)

    logger.info("Starting API endpoint benchmark...")
    api_results = await benchmark_api_latency(num_runs=10)

    logger.info("Starting RAG query benchmark...")
    rag_latencies = await benchmark_rag_latency(num_runs=5)

    # Print results table
    print("-" * 90)
    print(
        f"  {'Component':<20} {'Min':>10} {'Avg':>10} {'Max':>10} {'P95':>10} {'Target':>12} Status"
    )
    print("-" * 90)

    _print_results("Ollama LLM", ollama_latencies, TARGETS["Ollama LLM"])
    _print_results("API Health", api_results.get("API Health", []), TARGETS["API Health"])
    _print_results("API Doctors", api_results.get("API Doctors", []), TARGETS["API Doctors"])
    _print_results("API Slots", api_results.get("API Slots", []), TARGETS["API Slots"])
    _print_results("RAG Query", rag_latencies, TARGETS["RAG Query"])

    print("-" * 90)
    print()

    # Summary
    all_latencies = {
        "Ollama LLM": ollama_latencies,
        "RAG Query": rag_latencies,
        **api_results,
    }

    passed = 0
    failed = 0
    skipped = 0

    for name, lats in all_latencies.items():
        target = TARGETS.get(name, 100.0)
        if not lats:
            skipped += 1
        elif statistics.mean(lats) <= target:
            passed += 1
        else:
            failed += 1

    print(f"  Results: {passed} passed, {failed} above target, {skipped} skipped (service unavailable)")
    print()

    # Estimated total voice-to-voice latency
    if ollama_latencies and rag_latencies:
        # Pipeline: STT (~650ms est) + LLM + TTS first chunk (~300ms est)
        stt_estimate = 650.0
        tts_estimate = 300.0
        llm_avg = statistics.mean(ollama_latencies)
        total_estimate = stt_estimate + llm_avg + tts_estimate

        print(f"  Estimated voice-to-voice latency:")
        print(f"    STT (faster-whisper base.en, CPU):  ~{stt_estimate:.0f}ms (estimated)")
        print(f"    LLM (gpt-oss:20b-cloud):             {llm_avg:.0f}ms (measured)")
        print(f"    TTS (Kokoro-82M ONNX, CPU):         ~{tts_estimate:.0f}ms (estimated)")
        print(f"    -----------------------------------------------")
        print(f"    Total estimate:                      ~{total_estimate:.0f}ms", end="")
        if total_estimate <= 1500:
            print("  [WITHIN TARGET <1500ms]")
        else:
            print(f"  [ABOVE TARGET by {total_estimate - 1500:.0f}ms]")
    else:
        print("  Could not estimate total voice-to-voice latency (Ollama or RAG unavailable)")

    print()
    print("=" * 90)
    print(
        "  Note: STT and TTS estimates are based on typical CPU benchmarks."
    )
    print(
        "  For accurate end-to-end measurement, use the voice agent with browser mic."
    )
    print("=" * 90)
    print()


if __name__ == "__main__":
    asyncio.run(main())
