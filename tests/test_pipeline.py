from collections import Counter
from collections.abc import Callable
from typing import TypeVar

import pytest

from document_pipeline import (
    ContextAnswerGenerator,
    DocumentPipeline,
    InMemoryDocumentLoader,
    KeywordContextRetriever,
    NonEmptyAnswerValidator,
    ParagraphParser,
)
from pipeline_observability.monitor import PipelineMonitor

STAGE_ORDER = [
    "document_loading",
    "parsing",
    "retrieval",
    "model_inference",
    "output_validation",
]
Result = TypeVar("Result")


def fake_clock(*readings: float) -> Callable[[], float]:
    values = iter(readings)
    return lambda: next(values)


def assert_summary_matches_records(pipeline: DocumentPipeline) -> None:
    records = pipeline.records
    summary = pipeline.summary

    assert summary["total_stages"] == len(records)
    assert summary["total_success"] + summary["total_fail"] == len(records)
    assert summary["total_duration_seconds"] == pytest.approx(
        sum(record["duration_seconds"] for record in records)
    )
    assert summary["stage_order"] == [record["stage_name"] for record in records]
    assert summary["err_freq"] == dict(
        Counter(
            record["exception_type"]
            for record in records
            if record["status"] == "failed"
        )
    )


def make_pipeline(
    *,
    documents: dict[str, str] | None = None,
    clock: Callable[[], float] | None = None,
) -> DocumentPipeline:
    return DocumentPipeline(
        monitor=PipelineMonitor(run_id="run-013", clock=clock),
        loader=InMemoryDocumentLoader(
            documents
            or {
                "guide": (
                    "The observability guide explains stage-level monitoring.\n"
                    "Deterministic tests use injected clocks and local dependencies."
                )
            }
        ),
        parser=ParagraphParser(),
        retriever=KeywordContextRetriever(),
        generator=ContextAnswerGenerator(),
        validator=NonEmptyAnswerValidator(),
    )


def test_successful_execution_returns_validated_answer_and_records_all_stages():
    pipeline = make_pipeline(
        clock=fake_clock(
            1.0,
            1.125,
            2.0,
            2.125,
            3.0,
            3.125,
            4.0,
            4.125,
            5.0,
            5.125,
        )
    )

    answer = pipeline.run("guide", "What does observability explain?")

    assert answer == (
        "Answer to 'What does observability explain?': "
        "The observability guide explains stage-level monitoring."
    )
    assert [record["stage_name"] for record in pipeline.records] == STAGE_ORDER
    assert [record["status"] for record in pipeline.records] == ["success"] * 5
    assert [record["sequence"] for record in pipeline.records] == [1, 2, 3, 4, 5]
    assert [record["duration_seconds"] for record in pipeline.records] == pytest.approx(
        [0.125] * 5
    )
    assert pipeline.summary["total_success"] == 5
    assert pipeline.summary["total_fail"] == 0
    assert_summary_matches_records(pipeline)


class RecordingStages:
    def __init__(self, fail_at: str | None = None, error: Exception | None = None):
        self.executed: list[str] = []
        self.fail_at = fail_at
        self.error = error

    def _run(self, stage: str, result: Result) -> Result:
        self.executed.append(stage)
        if stage == self.fail_at and self.error is not None:
            raise self.error
        return result

    def load(self, document_id: str) -> str:
        return self._run("document_loading", f"raw:{document_id}")

    def parse(self, document: str) -> tuple[str, ...]:
        return self._run("parsing", (document,))

    def retrieve(self, document: tuple[str, ...], query: str) -> str:
        return self._run("retrieval", f"{query}:{document[0]}")

    def generate(self, query: str, context: str) -> str:
        return self._run("model_inference", f"{query}:{context}")

    def validate(self, candidate_answer: str) -> str:
        return self._run("output_validation", candidate_answer)


@pytest.mark.parametrize(
    ("failed_stage", "completed_stages"),
    [
        ("document_loading", ["document_loading"]),
        ("parsing", ["document_loading", "parsing"]),
        ("retrieval", ["document_loading", "parsing", "retrieval"]),
        (
            "model_inference",
            ["document_loading", "parsing", "retrieval", "model_inference"],
        ),
        ("output_validation", STAGE_ORDER),
    ],
)
def test_stage_failure_records_executed_stages_and_stops_pipeline(
    failed_stage: str, completed_stages: list[str]
):
    original_error = RuntimeError(f"{failed_stage} failed")
    stages = RecordingStages(fail_at=failed_stage, error=original_error)
    pipeline = DocumentPipeline(
        monitor=PipelineMonitor(
            run_id="run-013",
            clock=fake_clock(
                *[
                    reading
                    for sequence in range(5)
                    for reading in (sequence, sequence + 0.25)
                ]
            ),
        ),
        loader=stages,
        parser=stages,
        retriever=stages,
        generator=stages,
        validator=stages,
    )

    with pytest.raises(RuntimeError) as caught:
        pipeline.run("unused", "unused")

    assert caught.value is original_error
    assert stages.executed == completed_stages
    assert [record["stage_name"] for record in pipeline.records] == completed_stages
    assert [record["sequence"] for record in pipeline.records] == list(
        range(1, len(completed_stages) + 1)
    )
    assert [record["status"] for record in pipeline.records] == [
        "success"
    ] * (len(completed_stages) - 1) + ["failed"]
    assert pipeline.records[-1]["exception_type"] == "RuntimeError"
    assert [record["duration_seconds"] for record in pipeline.records] == pytest.approx(
        [0.25] * len(completed_stages)
    )
    assert_summary_matches_records(pipeline)


def test_telemetry_does_not_contain_document_or_answer_content():
    private_document = "PRIVATE_DOCUMENT_7d9c: confidential passage."
    pipeline = make_pipeline(
        documents={"private-id": private_document},
        clock=fake_clock(
            1.0,
            1.1,
            2.0,
            2.1,
            3.0,
            3.1,
            4.0,
            4.1,
            5.0,
            5.1,
        ),
    )

    answer = pipeline.run("private-id", "What is confidential?")
    telemetry = repr(pipeline.records) + repr(pipeline.summary)

    assert private_document in answer
    assert "PRIVATE_DOCUMENT_7d9c" not in telemetry
    assert "private-id" not in telemetry
    assert answer not in telemetry
    assert "confidential" not in telemetry
    assert_summary_matches_records(pipeline)