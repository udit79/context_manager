# Design notes

1. **Records versus summaries:** Individual records preserve stage order, status, timing, and failure details for diagnosing a run; summaries are useful aggregates but cannot explain which operation failed.
2. **Clock selection:** `time.perf_counter()` is a monotonic clock intended for elapsed-time measurements, unlike wall-clock `time.time()`, which may jump when the system clock changes. The monitor also accepts an injected clock so tests remain deterministic.
3. **Exception information:** The monitor records exception types, not messages, to retain failure categories without copying potentially sensitive document or application data into telemetry.
4. **Complexity:** The `summary` property traverses every recorded stage once, so its time complexity is O(n) for n records.
5. **Run scope:** A `PipelineMonitor` and its pipeline instance accumulate records across every `run()` call; summaries cover the entire lifetime of that monitor, not just the latest execution. Create a new monitor/pipeline per execution when isolated per-run telemetry is needed.
