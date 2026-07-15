import pytest

from runtime.state_store.models import PipelineRun, RunStatus, TriggerType


@pytest.mark.unit
def test_pipeline_run_defaults():
    run = PipelineRun(pipeline_name="hello_pipeline")
    assert run.pipeline_name == "hello_pipeline"
    assert run.status == RunStatus.running
    assert run.trigger_type == TriggerType.manual
    assert run.artifacts_index == {}
