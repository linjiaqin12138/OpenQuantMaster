from unittest.mock import AsyncMock

import pytest

from runtime.notifier.base import Notifier
from tools.notifier.notify_tool import NotifyTool


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notify_tool_success_with_pushplus():
    mock_notifier = AsyncMock(spec=Notifier)
    mock_notifier.send.return_value = {"pushplus": "ok"}

    tool = NotifyTool(notifier=mock_notifier)
    result = await tool.execute(
        {
            "subject": "Agent Demo Report",
            "body": "The demo signals are bullish.",
            "channels": ["pushplus"],
        }
    )

    assert result.success is True
    assert result.data["results"]["pushplus"] == "ok"
    mock_notifier.send.assert_awaited_once_with("Agent Demo Report", "The demo signals are bullish.")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notify_tool_unconfigured_channel_not_implemented():
    mock_notifier = AsyncMock(spec=Notifier)
    mock_notifier.send.return_value = {"pushplus": "ok"}

    tool = NotifyTool(notifier=mock_notifier)
    result = await tool.execute(
        {
            "subject": "Agent Demo Report",
            "body": "Summary",
            "channels": ["pushplus", "telegram"],
        }
    )

    assert result.success is True
    assert result.data["results"]["pushplus"] == "ok"
    assert result.data["results"]["telegram"] == "not_implemented"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notify_tool_missing_token_returns_failure():
    mock_notifier = AsyncMock(spec=Notifier)
    mock_notifier.send.return_value = {"pushplus": "missing token", "success": False}

    tool = NotifyTool(notifier=mock_notifier)
    result = await tool.execute(
        {
            "subject": "Agent Demo Report",
            "body": "Summary",
            "channels": ["pushplus"],
        }
    )

    assert result.success is False
    assert result.data["results"]["pushplus"] == "missing token"
