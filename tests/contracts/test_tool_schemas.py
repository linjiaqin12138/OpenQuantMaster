import json
from pathlib import Path

import pytest

from tools.base.tool_result import ToolResult

SCHEMAS_DIR = Path(__file__).parents[2] / "schemas"


@pytest.mark.unit
def test_tool_result_schema_matches_pydantic_model():
    schema_path = SCHEMAS_DIR / "tool_result.schema.json"
    assert schema_path.exists()
    written_schema = json.loads(schema_path.read_text())
    generated_schema = ToolResult.model_json_schema()
    assert written_schema == generated_schema


@pytest.mark.unit
def test_tool_result_serializes_failed_result():
    result = ToolResult(
        success=False,
        data={},
        artifacts=[],
        error="something went wrong",
        cost_usd=0.0,
        duration_seconds=0.1,
    )
    dumped = result.model_dump()
    assert dumped["success"] is False
    assert dumped["error"] == "something went wrong"
    assert dumped["duration_seconds"] == pytest.approx(0.1)


@pytest.mark.unit
def test_tool_result_serializes_success_result_with_artifacts():
    from tools.base.tool_result import ArtifactRef

    result = ToolResult(
        success=True,
        data={"echoed": "hello"},
        artifacts=[
            ArtifactRef(name="echo.txt", mime_type="text/plain", relative_path="run/stage/echo.txt", sha256="a" * 64),
        ],
        error=None,
        cost_usd=0.0,
        duration_seconds=0.05,
    )
    dumped = result.model_dump()
    assert dumped["success"] is True
    assert len(dumped["artifacts"]) == 1
    assert dumped["artifacts"][0]["name"] == "echo.txt"
