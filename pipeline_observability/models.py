from pydantic import BaseModel,ConfigDict,Field,StrictInt,StrictFloat,BeforeValidator
from typing import Annotated,Literal,Any
def extract_exception_name(v: Any) -> str|None:
    if isinstance(v, BaseException):
        return v.__class__.__name__
    if isinstance(v, type) and issubclass(v, BaseException):
        return v.__name__
    if isinstance(v, str):
        return v
    return 
ExceptionName = Annotated[str|None, BeforeValidator(extract_exception_name)]
class contract(BaseModel):
    model_config=ConfigDict(frozen=True)
    run_id:Annotated[str,Field(pattern=r"^run-\d{3}$")]
    stage_name:Literal["document_loading","parsing","retrieval","model_inference","output_validation"]
    sequence:Annotated[StrictInt,Field(gt=0)]
    duration_seconds:Annotated[StrictFloat,Field(ge=0.0000)]
    status:Literal["success","failed"]
    exception_type:ExceptionName
