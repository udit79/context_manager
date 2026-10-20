import pytest
from pydantic import ValidationError

from pipeline_observability.monitor import PipelineMonitor


def fake_clock(*readings):
    values = iter(readings)
    return lambda: next(values)


def test_successful_stage_records_correct_data():
    monitor = PipelineMonitor(
        run_id="run-001",
        clock=fake_clock(10.0, 10.4),
    )

    with monitor.stage("retrieval"):
        pass

    assert len(monitor.records) == 1
    record = monitor.records[0]

    assert record["run_id"] == "run-001"
    assert record["stage_name"] == "retrieval"
    assert record["sequence"] == 1
    assert record["duration_seconds"] == pytest.approx(0.4)
    assert record["status"] == "success"
    assert record["exception_type"] is None


def test_failed_stage_records_and_propagates_same_exception():
    monitor = PipelineMonitor(
        run_id="run-001",
        clock=fake_clock(20.0, 20.5),
    )
    original_error = RuntimeError("retrieval failed")

    with pytest.raises(RuntimeError) as caught:
        with monitor.stage("retrieval"):
            raise original_error

    assert caught.value is original_error

    record = monitor.records[0]
    assert record["status"] == "failed"
    assert record["exception_type"] == "RuntimeError"
    assert record["duration_seconds"] == pytest.approx(0.5)


def test_sequence_increases_after_failure():
    monitor = PipelineMonitor(
        run_id="run-001",
        clock=fake_clock(1.0, 1.2, 2.0, 2.3),
    )

    with monitor.stage("document_loading"):
        pass

    with pytest.raises(ValueError):
        with monitor.stage("parsing"):
            raise ValueError("invalid document")

    assert [r["sequence"] for r in monitor.records] == [1, 2]
    assert [r["status"] for r in monitor.records] == [
        "success",
        "failed",
    ]


def test_repeated_stage_names_are_recorded_separately():
    monitor = PipelineMonitor(
        run_id="run-001",
        clock=fake_clock(1.0, 1.1, 2.0, 2.2),
    )

    with monitor.stage("retrieval"):
        pass

    with monitor.stage("retrieval"):
        pass

    assert len(monitor.records) == 2
    assert [r["stage_name"] for r in monitor.records] == [
        "retrieval",
        "retrieval",
    ]
    assert [r["sequence"] for r in monitor.records] == [1, 2]


def test_empty_run_summary():
    monitor = PipelineMonitor(run_id="run-001")

    assert monitor.records == ()

    summary = monitor.summary

    assert summary["run_id"] == "run-001"
    assert summary["total_stages"] == 0
    assert summary["total_success"] == 0
    assert summary["total_fail"] == 0
    assert summary["total_duration_seconds"] == 0
    assert summary["avg_time"] is None
    assert summary["stage_order"] == []
    assert summary["err_freq"] == {}


@pytest.mark.parametrize("run_id", ["", "   ", "invalid"])
def test_invalid_run_id_is_rejected(run_id):
    with pytest.raises((ValidationError, ValueError)):
        PipelineMonitor(run_id=run_id)


from typing import Any, cast

def test_invalid_stage_name_is_rejected_before_body_runs():
    monitor = PipelineMonitor(run_id="run-001")
    body_executed = False

    invalid_stage = cast(Any, "unknown_stage")

    with pytest.raises((ValidationError, ValueError)):
        with monitor.stage(invalid_stage):
            body_executed = True

    assert body_executed is False
    assert monitor.records == ()
    assert monitor.seq_counter == 0


def test_records_collection_is_read_only():
    monitor = PipelineMonitor(
        run_id="run-001",
        clock=fake_clock(1.0, 1.2),
    )

    with monitor.stage("retrieval"):
        pass

    with pytest.raises(AttributeError):
        getattr(monitor.records, "clear")()

    assert len(monitor.records) == 1


def test_record_cannot_be_mutated():
    monitor = PipelineMonitor(
        run_id="run-001",
        clock=fake_clock(1.0, 1.2),
    )

    with monitor.stage("retrieval"):
        pass

    with pytest.raises(TypeError):
        monitor.records[0]["status"] = "failed"


def test_clock_injection_controls_duration():
    monitor = PipelineMonitor(
        run_id="run-001",
        clock=fake_clock(10.0, 10.25),
    )

    with monitor.stage("retrieval"):
        pass

    assert monitor.records[0]["duration_seconds"] == pytest.approx(0.25)


def test_summary_aggregates_success_failure_and_duration():
    monitor = PipelineMonitor(
        run_id="run-001",
        clock=fake_clock(1.0, 1.4, 2.0, 2.3),
    )

    with monitor.stage("document_loading"):
        pass

    with pytest.raises(RuntimeError):
        with monitor.stage("retrieval"):
            raise RuntimeError("retrieval failed")

    summary = monitor.summary

    assert summary["total_stages"] == 2
    assert summary["total_success"] == 1
    assert summary["total_fail"] == 1
    assert summary["total_duration_seconds"] == pytest.approx(0.7)
    assert summary["avg_time"] == pytest.approx(0.35)
    assert summary["stage_order"] == [
        "document_loading",
        "retrieval",
    ]
    assert summary["err_freq"] == {"RuntimeError": 1}


def test_zero_duration_is_preserved():
    monitor = PipelineMonitor(
        run_id="run-001",
        clock=fake_clock(5.0, 5.0),
    )

    with monitor.stage("retrieval"):
        pass

    assert monitor.records[0]["duration_seconds"] == 0.0
    assert monitor.summary["avg_time"] == 0.0