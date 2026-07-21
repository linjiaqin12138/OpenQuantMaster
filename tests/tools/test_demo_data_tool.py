import hashlib
import json

import pytest

from tools.demo.demo_data_tool import DemoDataTool


@pytest.mark.unit
@pytest.mark.asyncio
async def test_demo_data_tool_writes_artifact(tmp_path):
    tool = DemoDataTool(artifacts_path=tmp_path)
    result = await tool.execute({"topic": "BTC market outlook"})

    assert result.success is True
    assert result.data["topic"] == "BTC market outlook"
    assert result.data["rows"] == 3
    assert result.data["artifact"].endswith("demo_data.json")

    artifact = result.artifacts[0]
    assert artifact.name == "demo_data.json"
    assert artifact.mime_type == "application/json"

    expected_payload = {
        "topic": "BTC market outlook",
        "data": [
            {"signal": "momentum", "value": 0.65},
            {"signal": "volume", "value": 0.42},
            {"signal": "sentiment", "value": 0.71},
        ],
    }
    expected_content = json.dumps(expected_payload, indent=2)
    assert artifact.content == expected_content
    assert artifact.sha256 == hashlib.sha256(expected_content.encode("utf-8")).hexdigest()

    written_file = tmp_path / result.data["artifact"]
    assert json.loads(written_file.read_text(encoding="utf-8")) == expected_payload
