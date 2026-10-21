"""A small document-processing pipeline with injectable stages."""

from collections.abc import Mapping
from typing import Literal, Protocol, TypeAlias, TypedDict, cast

from pipeline_observability.monitor import PipelineMonitor

ParsedContent: TypeAlias = tuple[str, ...]


class StageRecord(TypedDict):
    run_id: str
    stage_name: str
    sequence: int
    duration_seconds: float
    status: Literal["success", "failed"]
    exception_type: str | None


class PipelineSummary(TypedDict):
    run_id: str
    avg_time: float | None
    stage_order: list[str]
    total_success: int
    total_fail: int
    err_freq: dict[str, int]
    total_duration_seconds: float
    total_stages: int


class DocumentLoader(Protocol):
    def load(self, document_id: str) -> str: ...


class DocumentParser(Protocol):
    def parse(self, document: str) -> ParsedContent: ...


class ContextRetriever(Protocol):
    def retrieve(self, document: ParsedContent, query: str) -> str: ...


class AnswerGenerator(Protocol):
    def generate(self, query: str, context: str) -> str: ...


class AnswerValidator(Protocol):
    def validate(self, candidate_answer: str) -> str: ...


class InMemoryDocumentLoader:
    """Load documents from a local mapping."""

    def __init__(self, documents: Mapping[str, str]) -> None:
        self._documents = documents

    def load(self, document_id: str) -> str:
        return self._documents[document_id]


class ParagraphParser:
    def parse(self, document: str) -> ParsedContent:
        return tuple(paragraph.strip() for paragraph in document.splitlines() if paragraph.strip())


class KeywordContextRetriever:
    def retrieve(self, document: ParsedContent, query: str) -> str:
        query_terms = {term.casefold().strip(".,!?;:") for term in query.split()}
        for paragraph in document:
            paragraph_terms = {
                term.casefold().strip(".,!?;:") for term in paragraph.split()
            }
            if query_terms & paragraph_terms:
                return paragraph
        return document[0] if document else ""


class ContextAnswerGenerator:
    def generate(self, query: str, context: str) -> str:
        return f"Answer to '{query}': {context}"


class NonEmptyAnswerValidator:
    def validate(self, candidate_answer: str) -> str:
        answer = candidate_answer.strip()
        if not answer:
            raise ValueError("The generated answer must not be empty.")
        return answer


class DocumentPipeline:
    def __init__(
        self,
        monitor: PipelineMonitor,
        loader: DocumentLoader,
        parser: DocumentParser,
        retriever: ContextRetriever,
        generator: AnswerGenerator,
        validator: AnswerValidator,
    ) -> None:
        self.monitor = monitor
        self._loader = loader
        self._parser = parser
        self._retriever = retriever
        self._generator = generator
        self._validator = validator

    @property
    def records(self) -> tuple[StageRecord, ...]:
        return cast(tuple[StageRecord, ...], self.monitor.records)

    @property
    def summary(self) -> PipelineSummary:
        return cast(PipelineSummary, self.monitor.summary)

    def run(self, document_id: str, query: str) -> str:
        with self.monitor.stage("document_loading"):
            raw_document = self._loader.load(document_id)

        with self.monitor.stage("parsing"):
            parsed_document = self._parser.parse(raw_document)

        with self.monitor.stage("retrieval"):
            context = self._retriever.retrieve(parsed_document, query)

        with self.monitor.stage("model_inference"):
            candidate_answer = self._generator.generate(query, context)

        with self.monitor.stage("output_validation"):
            return self._validator.validate(candidate_answer)
