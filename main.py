from document_pipeline import (
    ContextAnswerGenerator,
    DocumentPipeline,
    InMemoryDocumentLoader,
    KeywordContextRetriever,
    NonEmptyAnswerValidator,
    ParagraphParser,
)
from pipeline_observability.monitor import PipelineMonitor


def main() -> None:
    pipeline = DocumentPipeline(
        monitor=PipelineMonitor(run_id="run-013"),
        loader=InMemoryDocumentLoader(
            {
                "observability": (
                    "Pipeline monitoring records the duration and status of each stage.\n"
                    "Structured telemetry makes failures easier to diagnose."
                )
            }
        ),
        parser=ParagraphParser(),
        retriever=KeywordContextRetriever(),
        generator=ContextAnswerGenerator(),
        validator=NonEmptyAnswerValidator(),
    )
    answer = pipeline.run("observability", "How does monitoring help?")
    print(answer)
    print(pipeline.summary)


if __name__ == "__main__":
    main()
