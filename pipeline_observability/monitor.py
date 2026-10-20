from pipeline_observability.models import contract
from contextlib import contextmanager
from collections.abc import Callable
from pydantic import validate_call,Field
from typing import Annotated,Literal
from frozendict import frozendict
lazy import time
class PipelineMonitor:
    @validate_call
    def __init__(self,run_id:Annotated[str,Field(pattern=r"^run-\d{3}$")],clock:Callable[[],float]|None=None):
        self.run_id=run_id
        self.seq_counter=0
        self._record_contract=[]
        self._clock = clock if clock is not None else time.perf_counter
    @contextmanager
    @validate_call
    def stage(self,stage_name:Literal["document_loading","parsing","retrieval","model_inference","output_validation"]):
        self.seq_counter+=1
        current_sequence=self.seq_counter
        start_time=self._clock()
        status="success"
        exception_name=None
        try:
            yield
        except Exception as e:
            status="failed"
            exception_name=type(e).__name__
            raise 
        finally:
            end_time=self._clock()
            duration=end_time-start_time
            stage_contract = contract(
                run_id=self.run_id,
                stage_name=stage_name,
                sequence=current_sequence,
                duration_seconds=duration,
                status=status,
                exception_type=exception_name
                )
            self._record_contract.append(frozendict(stage_contract.model_dump()))
    @property
    def records(self):
        return tuple(self._record_contract)
    @property
    def summary(self)->dict:
        contracts=self._record_contract
        final_summary={"run_id":self.run_id,"avg_time":0,"stage_order":[],"total_success":0,"total_fail":0,"err_freq":{},"total_duration_seconds":0,"total_stages":0}
        for contract in contracts:
            final_summary["avg_time"]=final_summary["avg_time"]+contract["duration_seconds"]/len(contracts)
            final_summary["total_duration_seconds"]=final_summary["total_duration_seconds"]+contract["duration_seconds"]
            final_summary["stage_order"].append(contract["stage_name"])
            if contract["status"]=="success":
                final_summary["total_success"]=final_summary["total_success"]+1
            else:
                final_summary["total_fail"]=final_summary["total_fail"]+1
            if contract["exception_type"] !=None:
                final_summary["err_freq"][contract["exception_type"]]=final_summary["err_freq"].get(contract["exception_type"],0)+1
        final_summary["total_stages"]=len(final_summary["stage_order"])
        if final_summary["total_stages"]==0:
            final_summary["avg_time"]=None
        return final_summary