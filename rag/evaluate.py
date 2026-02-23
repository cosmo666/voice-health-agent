"""RAG evaluation script — measures retrieval and answer quality.

Defines 20 test question-answer pairs covering insurance, services, doctors,
policies, and FAQs.  Runs each question through the RAG query engine, computes
basic quality metrics (retrieval hit rate, answer similarity, source coverage),
and optionally logs results to MLflow.

Usage::

    python -m rag.evaluate          # run from project root
    python rag/evaluate.py          # or directly
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from rag.query_engine import query_knowledge_base, retrieve_chunks

# ---------------------------------------------------------------------------
# Test dataset: 20 question-answer pairs with expected source files
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    """A single RAG evaluation test case.

    Attributes:
        question: The patient question to evaluate.
        expected_keywords: Keywords that a correct answer MUST contain (at least
            one must appear, case-insensitive).
        expected_sources: Source filenames that should appear in the retrieved chunks.
        category: Topical category for grouping metrics.
    """

    question: str
    expected_keywords: list[str]
    expected_sources: list[str]
    category: str


TEST_CASES: list[TestCase] = [
    # ---- Insurance (4 questions) ----
    TestCase(
        question="What insurance plans does Sunrise Health Clinic accept?",
        expected_keywords=["BlueCross", "Aetna", "UnitedHealthcare", "Cigna", "Medicare"],
        expected_sources=["insurance_policies.md"],
        category="insurance",
    ),
    TestCase(
        question="What is the copay for a specialist visit with BlueCross BlueShield PPO?",
        expected_keywords=["40", "copay"],
        expected_sources=["insurance_policies.md"],
        category="insurance",
    ),
    TestCase(
        question="Does Aetna HMO require referrals to see a specialist?",
        expected_keywords=["referral", "required", "PCP"],
        expected_sources=["insurance_policies.md"],
        category="insurance",
    ),
    TestCase(
        question="What is the annual deductible for Medicare Advantage?",
        expected_keywords=["250", "deductible"],
        expected_sources=["insurance_policies.md"],
        category="insurance",
    ),
    # ---- Services (4 questions) ----
    TestCase(
        question="What services does Sunrise Health Clinic offer?",
        expected_keywords=["checkup", "cardiology", "dermatology", "pediatric"],
        expected_sources=["clinic_services.md"],
        category="services",
    ),
    TestCase(
        question="How much does an annual physical cost?",
        expected_keywords=["175", "275", "preventive"],
        expected_sources=["clinic_services.md"],
        category="services",
    ),
    TestCase(
        question="Do you offer allergy testing and how long does it take?",
        expected_keywords=["allergy", "45", "60", "skin prick"],
        expected_sources=["clinic_services.md"],
        category="services",
    ),
    TestCase(
        question="What imaging services are available on-site?",
        expected_keywords=["X-ray", "ultrasound", "MRI", "imaging"],
        expected_sources=["clinic_services.md"],
        category="services",
    ),
    # ---- Doctors (4 questions) ----
    TestCase(
        question="Tell me about Dr. Sarah Patel and her specialty.",
        expected_keywords=["cardiology", "Johns Hopkins", "15 years"],
        expected_sources=["doctor_profiles.md"],
        category="doctors",
    ),
    TestCase(
        question="Which doctor should I see for a skin condition?",
        expected_keywords=["Dr. Michael Chen", "dermatology"],
        expected_sources=["doctor_profiles.md"],
        category="doctors",
    ),
    TestCase(
        question="What days is Dr. David Kim available?",
        expected_keywords=["Monday", "Tuesday", "Thursday"],
        expected_sources=["doctor_profiles.md"],
        category="doctors",
    ),
    TestCase(
        question="Who is the ENT specialist and what is their consultation fee?",
        expected_keywords=["Dr. Robert Thompson", "ENT", "250"],
        expected_sources=["doctor_profiles.md"],
        category="doctors",
    ),
    # ---- Policies (4 questions) ----
    TestCase(
        question="What are the clinic's hours of operation?",
        expected_keywords=["Monday", "Friday", "8:00", "6:00", "Saturday"],
        expected_sources=["clinic_policies.md"],
        category="policies",
    ),
    TestCase(
        question="What is the cancellation policy and the no-show fee?",
        expected_keywords=["24 hours", "$50", "no-show"],
        expected_sources=["clinic_policies.md"],
        category="policies",
    ),
    TestCase(
        question="Do you offer telehealth appointments?",
        expected_keywords=["telehealth", "video", "available"],
        expected_sources=["clinic_policies.md", "patient_faq.md"],
        category="policies",
    ),
    TestCase(
        question="What is your prescription refill policy?",
        expected_keywords=["48 hours", "refill", "controlled"],
        expected_sources=["clinic_policies.md"],
        category="policies",
    ),
    # ---- FAQ (4 questions) ----
    TestCase(
        question="How do I book an appointment at the clinic?",
        expected_keywords=["call", "555", "portal", "Maya"],
        expected_sources=["patient_faq.md"],
        category="faq",
    ),
    TestCase(
        question="What should I bring to my first appointment as a new patient?",
        expected_keywords=["photo ID", "insurance card", "medications"],
        expected_sources=["patient_faq.md"],
        category="faq",
    ),
    TestCase(
        question="Do I need to fast before blood work?",
        expected_keywords=["fasting", "8", "12", "lipid", "water"],
        expected_sources=["patient_faq.md"],
        category="faq",
    ),
    TestCase(
        question="What are your COVID-19 protocols?",
        expected_keywords=["masking", "optional", "testing", "vaccine"],
        expected_sources=["patient_faq.md", "clinic_policies.md"],
        category="faq",
    ),
]


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    """Evaluation result for a single test case.

    Attributes:
        test_case: The original test case.
        answer: The generated answer string.
        sources_returned: Source filenames returned by the query engine.
        retrieval_hit: Whether at least one expected source was retrieved.
        keyword_hit_rate: Fraction of expected keywords found in the answer.
        latency_ms: End-to-end query time in milliseconds.
    """

    test_case: TestCase
    answer: str
    sources_returned: list[str]
    retrieval_hit: bool
    keyword_hit_rate: float
    latency_ms: float


def _compute_keyword_hit_rate(answer: str, expected_keywords: list[str]) -> float:
    """Compute the fraction of expected keywords present in the answer.

    Comparison is case-insensitive.

    Args:
        answer: The generated answer text.
        expected_keywords: Keywords to look for.

    Returns:
        A float between 0.0 and 1.0 representing the hit rate.
    """
    if not expected_keywords:
        return 1.0

    answer_lower = answer.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
    return hits / len(expected_keywords)


def _check_retrieval_hit(sources_returned: list[str], expected_sources: list[str]) -> bool:
    """Check whether at least one expected source file appears in the retrieved sources.

    Args:
        sources_returned: Filenames actually returned by the retriever.
        expected_sources: Filenames we expect to be retrieved.

    Returns:
        True if there is at least one overlap, False otherwise.
    """
    returned_set = set(sources_returned)
    expected_set = set(expected_sources)
    return bool(returned_set & expected_set)


# ---------------------------------------------------------------------------
# Main evaluation runner
# ---------------------------------------------------------------------------

async def run_evaluation(
    test_cases: list[TestCase] | None = None,
    log_to_mlflow: bool = True,
) -> list[EvalResult]:
    """Run the full RAG evaluation suite.

    Iterates over every test case, queries the knowledge base, computes metrics,
    optionally logs to MLflow, and prints a summary report.

    Args:
        test_cases: List of test cases to evaluate.  Defaults to :data:`TEST_CASES`.
        log_to_mlflow: Whether to attempt logging results to MLflow.  If MLflow
            is not available or the tracking server is unreachable, this is
            silently skipped.

    Returns:
        A list of :class:`EvalResult` objects (one per test case).
    """
    test_cases = test_cases or TEST_CASES
    results: list[EvalResult] = []

    logger.info("Starting RAG evaluation with {} test cases", len(test_cases))

    for i, tc in enumerate(test_cases, start=1):
        logger.info("[{}/{}] Evaluating: '{}'", i, len(test_cases), tc.question[:70])

        start = time.perf_counter()
        try:
            response = await query_knowledge_base(tc.question, top_k=5)
        except Exception as exc:
            logger.error("Query failed for '{}': {}", tc.question[:50], exc)
            results.append(
                EvalResult(
                    test_case=tc,
                    answer=f"ERROR: {exc}",
                    sources_returned=[],
                    retrieval_hit=False,
                    keyword_hit_rate=0.0,
                    latency_ms=0.0,
                )
            )
            continue

        latency_ms = (time.perf_counter() - start) * 1000

        answer = response.get("answer", "")
        sources = response.get("sources", [])

        retrieval_hit = _check_retrieval_hit(sources, tc.expected_sources)
        keyword_rate = _compute_keyword_hit_rate(answer, tc.expected_keywords)

        result = EvalResult(
            test_case=tc,
            answer=answer,
            sources_returned=sources,
            retrieval_hit=retrieval_hit,
            keyword_hit_rate=keyword_rate,
            latency_ms=latency_ms,
        )
        results.append(result)

        status = "PASS" if retrieval_hit and keyword_rate >= 0.5 else "FAIL"
        logger.info(
            "  [{}] retrieval={}, keywords={:.0%}, latency={:.0f}ms",
            status,
            "HIT" if retrieval_hit else "MISS",
            keyword_rate,
            latency_ms,
        )

    # ---- Print summary report ----
    _print_summary(results)

    # ---- Log to MLflow (optional) ----
    if log_to_mlflow:
        _log_to_mlflow(results)

    return results


def _print_summary(results: list[EvalResult]) -> None:
    """Print a formatted summary report of evaluation results.

    Args:
        results: List of evaluation results.
    """
    total = len(results)
    if total == 0:
        logger.warning("No results to summarize")
        return

    retrieval_hits = sum(1 for r in results if r.retrieval_hit)
    avg_keyword_rate = sum(r.keyword_hit_rate for r in results) / total
    avg_latency = sum(r.latency_ms for r in results) / total
    passed = sum(
        1 for r in results if r.retrieval_hit and r.keyword_hit_rate >= 0.5
    )

    # Per-category breakdown
    categories: dict[str, list[EvalResult]] = {}
    for r in results:
        cat = r.test_case.category
        categories.setdefault(cat, []).append(r)

    print("\n" + "=" * 70)
    print("  RAG EVALUATION REPORT — Sunrise Health Clinic")
    print("=" * 70)
    print(f"\n  Total test cases:        {total}")
    print(f"  Passed (hit + kw>=50%):  {passed}/{total} ({passed/total:.0%})")
    print(f"  Retrieval hit rate:      {retrieval_hits}/{total} ({retrieval_hits/total:.0%})")
    print(f"  Avg keyword hit rate:    {avg_keyword_rate:.0%}")
    print(f"  Avg latency:             {avg_latency:.0f}ms")

    print("\n  Per-Category Breakdown:")
    print("  " + "-" * 50)
    for cat, cat_results in sorted(categories.items()):
        cat_total = len(cat_results)
        cat_retrieval = sum(1 for r in cat_results if r.retrieval_hit)
        cat_keyword = sum(r.keyword_hit_rate for r in cat_results) / cat_total
        cat_passed = sum(
            1 for r in cat_results
            if r.retrieval_hit and r.keyword_hit_rate >= 0.5
        )
        print(
            f"  {cat:12s}  pass={cat_passed}/{cat_total}  "
            f"retrieval={cat_retrieval}/{cat_total}  "
            f"keyword={cat_keyword:.0%}"
        )

    print("\n  Detailed Results:")
    print("  " + "-" * 50)
    for i, r in enumerate(results, start=1):
        status = (
            "PASS" if r.retrieval_hit and r.keyword_hit_rate >= 0.5 else "FAIL"
        )
        print(f"  {i:2d}. [{status}] {r.test_case.question[:60]}")
        print(f"      retrieval={'HIT' if r.retrieval_hit else 'MISS'}  "
              f"keywords={r.keyword_hit_rate:.0%}  "
              f"latency={r.latency_ms:.0f}ms")
        print(f"      sources: {r.sources_returned}")
        # Truncate answer for readability
        answer_preview = r.answer[:120].replace("\n", " ")
        print(f"      answer:  {answer_preview}...")

    print("\n" + "=" * 70 + "\n")


def _log_to_mlflow(results: list[EvalResult]) -> None:
    """Log evaluation metrics to MLflow.

    If MLflow is not installed or the tracking server is unreachable, this
    function logs a warning and returns silently — it never raises.

    Args:
        results: List of evaluation results to log.
    """
    try:
        import mlflow
    except ImportError:
        logger.warning("MLflow not installed — skipping metric logging")
        return

    mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")

    try:
        mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment("rag-evaluation")
    except Exception as exc:
        logger.warning("Could not connect to MLflow at {}: {}", mlflow_uri, exc)
        return

    total = len(results)
    if total == 0:
        return

    retrieval_hits = sum(1 for r in results if r.retrieval_hit)
    avg_keyword_rate = sum(r.keyword_hit_rate for r in results) / total
    avg_latency = sum(r.latency_ms for r in results) / total
    passed = sum(
        1 for r in results if r.retrieval_hit and r.keyword_hit_rate >= 0.5
    )

    try:
        with mlflow.start_run(run_name="rag-eval"):
            mlflow.log_param("num_test_cases", total)
            mlflow.log_param("embedding_model", EMBEDDING_MODEL)
            mlflow.log_param("llm_model", os.getenv("OLLAMA_MODEL", "gpt-oss:20b-cloud"))
            mlflow.log_param("top_k", 5)

            mlflow.log_metric("overall_pass_rate", passed / total)
            mlflow.log_metric("retrieval_hit_rate", retrieval_hits / total)
            mlflow.log_metric("avg_keyword_hit_rate", avg_keyword_rate)
            mlflow.log_metric("avg_latency_ms", avg_latency)

            # Per-category metrics
            categories: dict[str, list[EvalResult]] = {}
            for r in results:
                categories.setdefault(r.test_case.category, []).append(r)

            for cat, cat_results in categories.items():
                cat_total = len(cat_results)
                cat_retrieval = sum(1 for r in cat_results if r.retrieval_hit)
                cat_keyword = sum(r.keyword_hit_rate for r in cat_results) / cat_total
                mlflow.log_metric(f"{cat}_retrieval_hit_rate", cat_retrieval / cat_total)
                mlflow.log_metric(f"{cat}_keyword_hit_rate", cat_keyword)

        logger.info("Evaluation metrics logged to MLflow at {}", mlflow_uri)
    except Exception as exc:
        logger.warning("Failed to log metrics to MLflow: {}", exc)


# ---------------------------------------------------------------------------
# Retrieval-only evaluation (no LLM required)
# ---------------------------------------------------------------------------

def evaluate_retrieval_only(
    test_cases: list[TestCase] | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Evaluate retrieval quality without calling the LLM.

    This is useful for quick iteration on chunking and embedding strategies
    without needing the Ollama server running.

    Args:
        test_cases: List of test cases.  Defaults to :data:`TEST_CASES`.
        top_k: Number of chunks to retrieve per query.

    Returns:
        A dictionary with aggregated retrieval metrics.
    """
    test_cases = test_cases or TEST_CASES

    logger.info("Running retrieval-only evaluation ({} cases, top_k={})", len(test_cases), top_k)

    hits = 0
    total = len(test_cases)
    latencies: list[float] = []

    for i, tc in enumerate(test_cases, start=1):
        start = time.perf_counter()
        try:
            documents, sources, distances = retrieve_chunks(tc.question, top_k=top_k)
        except Exception as exc:
            logger.error("[{}/{}] Retrieval error for '{}': {}", i, total, tc.question[:50], exc)
            continue

        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

        hit = _check_retrieval_hit(sources, tc.expected_sources)
        if hit:
            hits += 1

        status = "HIT" if hit else "MISS"
        logger.info(
            "[{}/{}] [{}] '{}' -> sources={} (expected={}) {:.0f}ms",
            i, total, status,
            tc.question[:50],
            sources[:3],
            tc.expected_sources,
            latency_ms,
        )

    hit_rate = hits / total if total > 0 else 0.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    print(f"\nRetrieval-Only Results: {hits}/{total} hits ({hit_rate:.0%}), avg latency {avg_latency:.0f}ms\n")

    return {
        "hit_rate": hit_rate,
        "hits": hits,
        "total": total,
        "avg_latency_ms": avg_latency,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for CLI invocation."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )

    mode = "full"
    if len(sys.argv) > 1 and sys.argv[1] == "--retrieval-only":
        mode = "retrieval"

    if mode == "retrieval":
        evaluate_retrieval_only()
    else:
        asyncio.run(run_evaluation())


if __name__ == "__main__":
    main()
