"""
AI Agent Evaluation Framework.

Evaluates AI agent responses across multiple quality dimensions:
- Relevance: Does the answer address the user's question?
- Groundedness: Is the answer grounded in the provided context/data?
- Coherence: Is the answer logically structured and readable?
- Latency: Does the agent respond within acceptable time bounds?

Built on Azure AI Evaluation SDK patterns with extensible metric plugins.

Usage:
    from ai.evaluation.eval_framework import EvaluationFramework, EvalConfig
    framework = EvaluationFramework(config)
    results = await framework.evaluate_agent("demand-forecast-agent", test_dataset)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import statistics
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from openai import AsyncAzureOpenAI

logger = logging.getLogger("ai_evaluation")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class MetricName(str, Enum):
    """Standard evaluation metrics."""
    RELEVANCE = "relevance"
    GROUNDEDNESS = "groundedness"
    COHERENCE = "coherence"
    FLUENCY = "fluency"
    LATENCY = "latency"
    DATA_ACCURACY = "data_accuracy"
    CITATION_QUALITY = "citation_quality"
    FORECAST_ACCURACY = "forecast_accuracy_mape"


@dataclass
class EvalConfig:
    """Configuration for the evaluation framework."""
    # Azure OpenAI (for LLM-as-judge evaluations)
    aoai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    aoai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    aoai_api_version: str = "2025-04-01-preview"
    judge_deployment: str = os.getenv("AZURE_OPENAI_JUDGE_DEPLOYMENT", "gpt-4.1")

    # Evaluation settings
    metrics: list[MetricName] = field(
        default_factory=lambda: [
            MetricName.RELEVANCE,
            MetricName.GROUNDEDNESS,
            MetricName.COHERENCE,
            MetricName.LATENCY,
        ]
    )
    passing_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            MetricName.RELEVANCE: 3.0,       # Score 1-5, pass >= 3
            MetricName.GROUNDEDNESS: 3.0,
            MetricName.COHERENCE: 3.0,
            MetricName.FLUENCY: 3.0,
            MetricName.LATENCY: 5000.0,       # Max ms
            MetricName.DATA_ACCURACY: 3.0,
            MetricName.CITATION_QUALITY: 3.0,
            MetricName.FORECAST_ACCURACY: 20.0,  # Max MAPE %
        }
    )
    max_concurrent_evaluations: int = 5
    output_directory: str = "ai/evaluation/results"


@dataclass
class TestCase:
    """A single test case for evaluation."""
    test_id: str
    query: str
    context: str = ""                    # Ground truth context
    expected_answer: str = ""            # Reference answer (optional)
    expected_data_points: dict = field(default_factory=dict)  # For data accuracy
    metadata: dict = field(default_factory=dict)
    agent_name: str = ""


@dataclass
class AgentResponse:
    """Captured response from an agent for evaluation."""
    test_id: str
    query: str
    response: str
    context_used: str = ""
    sources: list[dict] = field(default_factory=list)
    latency_ms: float = 0.0
    token_usage: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class MetricResult:
    """Result of a single metric evaluation."""
    metric_name: str
    score: float
    max_score: float
    passed: bool
    reasoning: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class TestCaseResult:
    """Complete evaluation result for a single test case."""
    test_id: str
    query: str
    agent_response: str
    metrics: list[MetricResult]
    overall_passed: bool
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def metric_scores(self) -> dict[str, float]:
        return {m.metric_name: m.score for m in self.metrics}


@dataclass
class EvaluationReport:
    """Aggregated evaluation report across all test cases."""
    agent_name: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    pass_rate: float
    metric_averages: dict[str, float]
    metric_distributions: dict[str, dict[str, float]]  # mean, std, min, max, p50, p95
    test_results: list[TestCaseResult]
    run_id: str
    timestamp: str = ""
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Metric Evaluators
# ---------------------------------------------------------------------------

class BaseMetricEvaluator(ABC):
    """Abstract base class for metric evaluators."""

    @property
    @abstractmethod
    def metric_name(self) -> MetricName:
        """Return the metric name."""
        ...

    @abstractmethod
    async def evaluate(
        self,
        test_case: TestCase,
        response: AgentResponse,
        config: EvalConfig,
    ) -> MetricResult:
        """Evaluate a single test case and return metric result."""
        ...


class LLMJudgeEvaluator(BaseMetricEvaluator):
    """
    Base class for LLM-as-judge evaluators.
    Uses a strong LLM (GPT-4.1) to evaluate agent responses on a 1-5 scale.
    """

    def __init__(self, client: AsyncAzureOpenAI, deployment: str):
        self.client = client
        self.deployment = deployment

    @property
    @abstractmethod
    def evaluation_prompt_template(self) -> str:
        """Return the evaluation prompt template."""
        ...

    async def _judge(
        self,
        prompt: str,
    ) -> tuple[int, str]:
        """Call the judge LLM and extract score and reasoning."""
        response = await self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert evaluator for AI agent responses. "
                        "Score the response on a scale of 1-5 and provide brief reasoning. "
                        "Respond in JSON format: {\"score\": <1-5>, \"reasoning\": \"<text>\"}"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=500,
            response_format={"type": "json_object"},
        )

        result_text = response.choices[0].message.content or "{}"
        try:
            result = json.loads(result_text)
            score = int(result.get("score", 1))
            score = max(1, min(5, score))  # Clamp to 1-5
            reasoning = result.get("reasoning", "No reasoning provided.")
        except (json.JSONDecodeError, ValueError):
            score = 1
            reasoning = f"Failed to parse judge response: {result_text[:200]}"

        return score, reasoning

    async def evaluate(
        self,
        test_case: TestCase,
        response: AgentResponse,
        config: EvalConfig,
    ) -> MetricResult:
        """Evaluate using LLM judge."""
        prompt = self.evaluation_prompt_template.format(
            query=test_case.query,
            context=test_case.context or response.context_used,
            response=response.response,
            expected_answer=test_case.expected_answer,
        )

        score, reasoning = await self._judge(prompt)
        threshold = config.passing_thresholds.get(self.metric_name, 3.0)

        return MetricResult(
            metric_name=self.metric_name.value,
            score=float(score),
            max_score=5.0,
            passed=score >= threshold,
            reasoning=reasoning,
        )


class RelevanceEvaluator(LLMJudgeEvaluator):
    """Evaluates whether the response is relevant to the user's query."""

    @property
    def metric_name(self) -> MetricName:
        return MetricName.RELEVANCE

    @property
    def evaluation_prompt_template(self) -> str:
        return """Evaluate the RELEVANCE of the AI assistant's response to the user's query.

User Query: {query}

AI Response: {response}

Expected Answer (reference): {expected_answer}

Score on a scale of 1-5:
1 = Completely irrelevant, does not address the query at all
2 = Partially relevant, addresses some aspect but misses the main point
3 = Moderately relevant, addresses the main point but misses key details
4 = Highly relevant, addresses the query well with most important details
5 = Perfectly relevant, directly and completely addresses the query

Consider:
- Does the response answer what was asked?
- Are the key points from the expected answer covered?
- Is there unnecessary information that distracts from the answer?"""


class GroundednessEvaluator(LLMJudgeEvaluator):
    """Evaluates whether the response is grounded in the provided context/data."""

    @property
    def metric_name(self) -> MetricName:
        return MetricName.GROUNDEDNESS

    @property
    def evaluation_prompt_template(self) -> str:
        return """Evaluate the GROUNDEDNESS of the AI assistant's response.
Groundedness measures whether claims in the response are supported by the provided context.

Context/Data Provided: {context}

AI Response: {response}

Score on a scale of 1-5:
1 = Completely ungrounded, all claims are fabricated or unsupported
2 = Mostly ungrounded, majority of claims lack support in the context
3 = Partially grounded, some claims are supported but others are not
4 = Mostly grounded, most claims are supported with minor unsupported statements
5 = Fully grounded, all claims are directly supported by the context

Consider:
- Are numbers, facts, and data points traceable to the provided context?
- Does the response cite sources appropriately?
- Are there any hallucinated facts or made-up statistics?
- Does the response distinguish between data-supported claims and inferences?"""


class CoherenceEvaluator(LLMJudgeEvaluator):
    """Evaluates the logical structure and readability of the response."""

    @property
    def metric_name(self) -> MetricName:
        return MetricName.COHERENCE

    @property
    def evaluation_prompt_template(self) -> str:
        return """Evaluate the COHERENCE of the AI assistant's response.

User Query: {query}

AI Response: {response}

Score on a scale of 1-5:
1 = Incoherent, difficult to follow, contradictory statements
2 = Poorly organized, some logical flow but significant gaps
3 = Moderately coherent, generally logical but could be better structured
4 = Well-structured, clear logical flow with good organization
5 = Excellent coherence, perfectly organized, easy to follow, professional quality

Consider:
- Is the response logically structured?
- Does it flow naturally from one point to the next?
- Are there any contradictions within the response?
- Is the formatting appropriate (tables, bullets, sections)?
- Is the language clear and professional?"""


class FluencyEvaluator(LLMJudgeEvaluator):
    """Evaluates language quality and naturalness."""

    @property
    def metric_name(self) -> MetricName:
        return MetricName.FLUENCY

    @property
    def evaluation_prompt_template(self) -> str:
        return """Evaluate the FLUENCY of the AI assistant's response.

AI Response: {response}

Score on a scale of 1-5:
1 = Incomprehensible, major grammar/language issues
2 = Poor fluency, frequent grammar errors, awkward phrasing
3 = Acceptable fluency, occasional issues but generally understandable
4 = Good fluency, natural language with minor imperfections
5 = Excellent fluency, perfectly natural, professional-quality writing

Consider:
- Grammar and spelling correctness
- Natural sentence construction
- Appropriate vocabulary for business context
- Number and data formatting consistency"""


class DataAccuracyEvaluator(LLMJudgeEvaluator):
    """Evaluates whether numerical data and calculations are accurate."""

    @property
    def metric_name(self) -> MetricName:
        return MetricName.DATA_ACCURACY

    @property
    def evaluation_prompt_template(self) -> str:
        return """Evaluate the DATA ACCURACY of the AI assistant's response.

Context/Source Data: {context}

AI Response: {response}

Expected Answer (with correct data): {expected_answer}

Score on a scale of 1-5:
1 = Completely inaccurate, all numbers and calculations are wrong
2 = Mostly inaccurate, significant numerical errors
3 = Partially accurate, some numbers correct but key figures are wrong
4 = Mostly accurate, minor discrepancies in less critical figures
5 = Fully accurate, all numbers, calculations, and data points are correct

Consider:
- Are revenue/quantity figures correct?
- Are percentages and growth rates calculated correctly?
- Are comparisons (YoY, period-over-period) accurate?
- Are rankings (top N) correct?
- Is the currency and unit handling consistent?"""


class CitationQualityEvaluator(LLMJudgeEvaluator):
    """Evaluates whether sources are properly cited."""

    @property
    def metric_name(self) -> MetricName:
        return MetricName.CITATION_QUALITY

    @property
    def evaluation_prompt_template(self) -> str:
        return """Evaluate the CITATION QUALITY of the AI assistant's response.

Context Sources Provided: {context}

AI Response: {response}

Score on a scale of 1-5:
1 = No citations at all despite making data claims
2 = Minimal citations, most claims uncited
3 = Some citations but inconsistent, key claims lack attribution
4 = Good citations, most claims properly attributed to sources
5 = Excellent citations, every claim is properly cited with clear source references

Consider:
- Are data-backed claims properly cited with source references?
- Are the citation references accurate (pointing to the correct source)?
- Is the citation format consistent throughout?
- Are inferences clearly distinguished from cited facts?"""


class LatencyEvaluator(BaseMetricEvaluator):
    """Evaluates response latency against configured thresholds."""

    @property
    def metric_name(self) -> MetricName:
        return MetricName.LATENCY

    async def evaluate(
        self,
        test_case: TestCase,
        response: AgentResponse,
        config: EvalConfig,
    ) -> MetricResult:
        """Evaluate response latency."""
        threshold = config.passing_thresholds.get(MetricName.LATENCY, 5000.0)
        latency = response.latency_ms
        passed = latency <= threshold

        # Convert to a 1-5 score based on latency brackets
        if latency <= 1000:
            score = 5.0
        elif latency <= 2000:
            score = 4.0
        elif latency <= 3000:
            score = 3.0
        elif latency <= 5000:
            score = 2.0
        else:
            score = 1.0

        return MetricResult(
            metric_name=self.metric_name.value,
            score=score,
            max_score=5.0,
            passed=passed,
            reasoning=f"Response latency: {latency:.0f}ms (threshold: {threshold:.0f}ms)",
            details={"latency_ms": latency, "threshold_ms": threshold},
        )


class ForecastAccuracyEvaluator(BaseMetricEvaluator):
    """
    Evaluates demand forecast accuracy using MAPE (Mean Absolute Percentage Error).
    Requires expected_data_points in the test case.
    """

    @property
    def metric_name(self) -> MetricName:
        return MetricName.FORECAST_ACCURACY

    async def evaluate(
        self,
        test_case: TestCase,
        response: AgentResponse,
        config: EvalConfig,
    ) -> MetricResult:
        """Evaluate forecast accuracy via MAPE."""
        expected = test_case.expected_data_points
        if not expected:
            return MetricResult(
                metric_name=self.metric_name.value,
                score=0.0,
                max_score=100.0,
                passed=False,
                reasoning="No expected data points provided for forecast accuracy evaluation.",
            )

        # Extract predicted values from agent response
        # This is a simplified extraction; in production, use structured output parsing
        predicted = response.metadata.get("predicted_values", {})

        if not predicted:
            return MetricResult(
                metric_name=self.metric_name.value,
                score=0.0,
                max_score=100.0,
                passed=False,
                reasoning="Could not extract predicted values from agent response.",
            )

        # Calculate MAPE
        ape_values = []
        for key, actual_value in expected.items():
            if key in predicted and actual_value != 0:
                pred_value = float(predicted[key])
                actual = float(actual_value)
                ape = abs(actual - pred_value) / abs(actual) * 100
                ape_values.append(ape)

        if not ape_values:
            return MetricResult(
                metric_name=self.metric_name.value,
                score=0.0,
                max_score=100.0,
                passed=False,
                reasoning="No matching data points between expected and predicted values.",
            )

        mape = statistics.mean(ape_values)
        threshold = config.passing_thresholds.get(MetricName.FORECAST_ACCURACY, 20.0)
        passed = mape <= threshold

        # Convert MAPE to a 1-5 score (lower MAPE = higher score)
        if mape <= 5:
            score = 5.0
        elif mape <= 10:
            score = 4.0
        elif mape <= 15:
            score = 3.0
        elif mape <= 25:
            score = 2.0
        else:
            score = 1.0

        return MetricResult(
            metric_name=self.metric_name.value,
            score=score,
            max_score=5.0,
            passed=passed,
            reasoning=f"MAPE: {mape:.1f}% (threshold: {threshold:.1f}%)",
            details={
                "mape": round(mape, 2),
                "threshold": threshold,
                "num_data_points": len(ape_values),
            },
        )


# ---------------------------------------------------------------------------
# Evaluation Framework
# ---------------------------------------------------------------------------

class EvaluationFramework:
    """
    Main evaluation framework that orchestrates metric evaluation across
    test datasets for AI agents.
    """

    def __init__(self, config: Optional[EvalConfig] = None):
        self.config = config or EvalConfig()
        self.openai_client: Optional[AsyncAzureOpenAI] = None
        self.evaluators: dict[MetricName, BaseMetricEvaluator] = {}

    async def initialize(self) -> None:
        """Initialize the OpenAI client and register evaluators."""
        self.openai_client = AsyncAzureOpenAI(
            azure_endpoint=self.config.aoai_endpoint,
            api_key=self.config.aoai_api_key,
            api_version=self.config.aoai_api_version,
        )

        # Register LLM-judge evaluators
        judge_evaluators = {
            MetricName.RELEVANCE: RelevanceEvaluator,
            MetricName.GROUNDEDNESS: GroundednessEvaluator,
            MetricName.COHERENCE: CoherenceEvaluator,
            MetricName.FLUENCY: FluencyEvaluator,
            MetricName.DATA_ACCURACY: DataAccuracyEvaluator,
            MetricName.CITATION_QUALITY: CitationQualityEvaluator,
        }

        for metric_name in self.config.metrics:
            if metric_name in judge_evaluators:
                self.evaluators[metric_name] = judge_evaluators[metric_name](
                    self.openai_client, self.config.judge_deployment
                )
            elif metric_name == MetricName.LATENCY:
                self.evaluators[metric_name] = LatencyEvaluator()
            elif metric_name == MetricName.FORECAST_ACCURACY:
                self.evaluators[metric_name] = ForecastAccuracyEvaluator()

        logger.info(
            f"Evaluation framework initialized with metrics: "
            f"{[m.value for m in self.evaluators.keys()]}"
        )

    async def evaluate_single(
        self,
        test_case: TestCase,
        response: AgentResponse,
    ) -> TestCaseResult:
        """Evaluate a single agent response against all configured metrics."""
        metric_results: list[MetricResult] = []

        # Run all metric evaluations concurrently
        tasks = []
        for metric_name, evaluator in self.evaluators.items():
            tasks.append(evaluator.evaluate(test_case, response, self.config))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Metric evaluation failed: {result}")
                metric_results.append(
                    MetricResult(
                        metric_name="error",
                        score=0.0,
                        max_score=5.0,
                        passed=False,
                        reasoning=f"Evaluation error: {str(result)}",
                    )
                )
            else:
                metric_results.append(result)

        overall_passed = all(m.passed for m in metric_results)

        return TestCaseResult(
            test_id=test_case.test_id,
            query=test_case.query,
            agent_response=response.response,
            metrics=metric_results,
            overall_passed=overall_passed,
        )

    async def evaluate_dataset(
        self,
        agent_name: str,
        test_cases: list[TestCase],
        agent_fn: Callable[[str], Any],
        run_id: Optional[str] = None,
    ) -> EvaluationReport:
        """
        Evaluate an agent across an entire test dataset.

        Args:
            agent_name: Name of the agent being evaluated.
            test_cases: List of test cases to evaluate.
            agent_fn: Async callable that takes a query string and returns an AgentResponse.
            run_id: Optional unique run identifier.

        Returns:
            EvaluationReport with aggregated results.
        """
        start_time = time.time()
        run_id = run_id or f"eval_{agent_name}_{int(time.time())}"

        logger.info(
            f"Starting evaluation run '{run_id}' for agent '{agent_name}' "
            f"with {len(test_cases)} test cases"
        )

        test_results: list[TestCaseResult] = []
        semaphore = asyncio.Semaphore(self.config.max_concurrent_evaluations)

        async def evaluate_one(test_case: TestCase) -> TestCaseResult:
            async with semaphore:
                # Get agent response
                try:
                    start = time.time()
                    response = await agent_fn(test_case.query)
                    if not isinstance(response, AgentResponse):
                        response = AgentResponse(
                            test_id=test_case.test_id,
                            query=test_case.query,
                            response=str(response),
                            latency_ms=(time.time() - start) * 1000,
                        )
                    response.test_id = test_case.test_id
                except Exception as e:
                    response = AgentResponse(
                        test_id=test_case.test_id,
                        query=test_case.query,
                        response=f"Agent error: {str(e)}",
                        latency_ms=0.0,
                    )

                # Evaluate the response
                return await self.evaluate_single(test_case, response)

        # Run evaluations concurrently with bounded parallelism
        tasks = [evaluate_one(tc) for tc in test_cases]
        test_results = await asyncio.gather(*tasks)

        # Aggregate results
        passed_count = sum(1 for r in test_results if r.overall_passed)
        failed_count = len(test_results) - passed_count

        # Compute metric statistics
        metric_scores: dict[str, list[float]] = {}
        for result in test_results:
            for metric in result.metrics:
                if metric.metric_name not in metric_scores:
                    metric_scores[metric.metric_name] = []
                metric_scores[metric.metric_name].append(metric.score)

        metric_averages = {
            name: statistics.mean(scores) for name, scores in metric_scores.items()
        }

        metric_distributions = {}
        for name, scores in metric_scores.items():
            sorted_scores = sorted(scores)
            p50_idx = len(sorted_scores) // 2
            p95_idx = int(len(sorted_scores) * 0.95)
            metric_distributions[name] = {
                "mean": round(statistics.mean(scores), 3),
                "std": round(statistics.stdev(scores), 3) if len(scores) > 1 else 0.0,
                "min": round(min(scores), 3),
                "max": round(max(scores), 3),
                "p50": round(sorted_scores[p50_idx], 3),
                "p95": round(sorted_scores[min(p95_idx, len(sorted_scores) - 1)], 3),
            }

        duration = time.time() - start_time

        report = EvaluationReport(
            agent_name=agent_name,
            total_tests=len(test_results),
            passed_tests=passed_count,
            failed_tests=failed_count,
            pass_rate=round(passed_count / len(test_results) * 100, 1) if test_results else 0.0,
            metric_averages={k: round(v, 3) for k, v in metric_averages.items()},
            metric_distributions=metric_distributions,
            test_results=test_results,
            run_id=run_id,
            duration_seconds=round(duration, 2),
        )

        logger.info(
            f"Evaluation complete: {passed_count}/{len(test_results)} passed "
            f"({report.pass_rate}%) in {duration:.1f}s"
        )

        return report

    def print_report(self, report: EvaluationReport) -> None:
        """Print a formatted evaluation report to stdout."""
        print(f"\n{'='*80}")
        print(f"EVALUATION REPORT: {report.agent_name}")
        print(f"{'='*80}")
        print(f"Run ID      : {report.run_id}")
        print(f"Timestamp   : {report.timestamp}")
        print(f"Duration    : {report.duration_seconds}s")
        print(f"Total Tests : {report.total_tests}")
        print(f"Passed      : {report.passed_tests}")
        print(f"Failed      : {report.failed_tests}")
        print(f"Pass Rate   : {report.pass_rate}%")

        print(f"\n{'--- Metric Averages ---':^80}")
        print(f"{'Metric':<25} {'Avg Score':>10} {'Min':>8} {'Max':>8} {'P50':>8} {'P95':>8}")
        print("-" * 80)
        for metric_name, dist in report.metric_distributions.items():
            avg = report.metric_averages.get(metric_name, 0)
            print(
                f"{metric_name:<25} {avg:>10.2f} "
                f"{dist['min']:>8.2f} {dist['max']:>8.2f} "
                f"{dist['p50']:>8.2f} {dist['p95']:>8.2f}"
            )

        # Show failed test cases
        failed_tests = [t for t in report.test_results if not t.overall_passed]
        if failed_tests:
            print(f"\n{'--- Failed Test Cases ---':^80}")
            for test in failed_tests[:10]:  # Show first 10 failures
                print(f"\n  Test: {test.test_id}")
                print(f"  Query: {test.query[:80]}...")
                for metric in test.metrics:
                    if not metric.passed:
                        print(
                            f"    FAIL [{metric.metric_name}] "
                            f"Score: {metric.score}/{metric.max_score} "
                            f"- {metric.reasoning[:100]}"
                        )

        print(f"\n{'='*80}")

    async def save_report(self, report: EvaluationReport) -> str:
        """Save evaluation report to JSON file."""
        output_dir = Path(self.config.output_directory)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{report.agent_name}_{report.run_id}.json"
        filepath = output_dir / filename

        # Convert report to serializable dict
        report_dict = {
            "agent_name": report.agent_name,
            "run_id": report.run_id,
            "timestamp": report.timestamp,
            "duration_seconds": report.duration_seconds,
            "summary": {
                "total_tests": report.total_tests,
                "passed_tests": report.passed_tests,
                "failed_tests": report.failed_tests,
                "pass_rate": report.pass_rate,
            },
            "metric_averages": report.metric_averages,
            "metric_distributions": report.metric_distributions,
            "test_results": [
                {
                    "test_id": r.test_id,
                    "query": r.query,
                    "overall_passed": r.overall_passed,
                    "metrics": [
                        {
                            "metric_name": m.metric_name,
                            "score": m.score,
                            "max_score": m.max_score,
                            "passed": m.passed,
                            "reasoning": m.reasoning,
                            "details": m.details,
                        }
                        for m in r.metrics
                    ],
                }
                for r in report.test_results
            ],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2)

        logger.info(f"Report saved to: {filepath}")
        return str(filepath)


# ---------------------------------------------------------------------------
# Test Dataset Loader
# ---------------------------------------------------------------------------

def load_test_dataset(file_path: str) -> list[TestCase]:
    """
    Load test cases from a JSONL file.

    Expected format per line:
    {
        "test_id": "tc_001",
        "query": "What were Q4 revenue figures?",
        "context": "Revenue data...",
        "expected_answer": "Q4 revenue was $2.4M...",
        "metadata": {"category": "revenue"}
    }
    """
    test_cases = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                test_cases.append(
                    TestCase(
                        test_id=data.get("test_id", f"tc_{line_num:04d}"),
                        query=data["query"],
                        context=data.get("context", ""),
                        expected_answer=data.get("expected_answer", ""),
                        expected_data_points=data.get("expected_data_points", {}),
                        metadata=data.get("metadata", {}),
                    )
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Skipping invalid test case at line {line_num}: {e}")

    logger.info(f"Loaded {len(test_cases)} test cases from {file_path}")
    return test_cases


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

async def main() -> None:
    """CLI entry point for running evaluations."""
    import argparse

    parser = argparse.ArgumentParser(description="AI Agent Evaluation Framework")
    parser.add_argument(
        "--agent",
        type=str,
        required=True,
        help="Agent name to evaluate",
    )
    parser.add_argument(
        "--test-file",
        type=str,
        required=True,
        help="Path to JSONL test dataset",
    )
    parser.add_argument(
        "--metrics",
        type=str,
        nargs="+",
        default=["relevance", "groundedness", "coherence", "latency"],
        help="Metrics to evaluate",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="ai/evaluation/results",
        help="Output directory for reports",
    )
    args = parser.parse_args()

    config = EvalConfig(
        metrics=[MetricName(m) for m in args.metrics],
        output_directory=args.output_dir,
    )

    framework = EvaluationFramework(config)
    await framework.initialize()

    test_cases = load_test_dataset(args.test_file)

    # In a real scenario, agent_fn would call the actual agent API
    async def mock_agent_fn(query: str) -> AgentResponse:
        """Mock agent function for demonstration. Replace with actual agent call."""
        return AgentResponse(
            test_id="",
            query=query,
            response="This is a mock response. Replace with actual agent integration.",
            latency_ms=1500.0,
        )

    report = await framework.evaluate_dataset(
        agent_name=args.agent,
        test_cases=test_cases,
        agent_fn=mock_agent_fn,
    )

    framework.print_report(report)
    report_path = await framework.save_report(report)
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
