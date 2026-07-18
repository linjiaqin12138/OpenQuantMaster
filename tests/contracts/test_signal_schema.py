import json
from pathlib import Path

import pytest

from runtime.state_store.models import Signal

SCHEMAS_DIR = Path(__file__).parents[2] / "schemas"


@pytest.mark.unit
def test_signal_schema_matches_pydantic_model():
    schema_path = SCHEMAS_DIR / "signal.schema.json"
    assert schema_path.exists()
    written_schema = json.loads(schema_path.read_text())
    generated_schema = Signal.model_json_schema()
    assert written_schema == generated_schema
