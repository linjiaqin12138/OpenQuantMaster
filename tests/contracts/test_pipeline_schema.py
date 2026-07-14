import json
from pathlib import Path

import jsonschema
import yaml
import pytest

SCHEMAS_DIR = Path(__file__).parents[2] / "schemas"
PIPELINES_DIR = Path(__file__).parents[2] / "pipelines"


@pytest.mark.unit
def test_hello_pipeline_validates():
    schema = json.loads((SCHEMAS_DIR / "pipeline_manifest.schema.json").read_text())
    instance = yaml.safe_load((PIPELINES_DIR / "hello_pipeline.yaml").read_text())
    jsonschema.validate(instance=instance, schema=schema)
    assert instance["name"] == "hello_pipeline"
    assert len(instance["stages"]) >= 1
    assert instance["stages"][0]["tool"] == "echo_tool"
