import asyncio
import uuid

import pytest

from runtime.event_bus.memory_bus import MemoryEventBus


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscriber_receives_event():
    bus = MemoryEventBus()
    await bus.start()
    received = []

    async def handler(envelope):
        received.append(envelope)

    bus.subscribe("test.event", handler)
    correlation_id = uuid.uuid4()
    await bus.publish("test.event", {"x": 1}, correlation_id=correlation_id)
    await asyncio.wait_for(bus._drain(), timeout=1.0)

    assert len(received) == 1
    assert received[0].event_type == "test.event"
    assert received[0].payload == {"x": 1}
    assert received[0].correlation_id == correlation_id
    await bus.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multiple_subscribers_receive_event():
    bus = MemoryEventBus()
    await bus.start()
    a, b = [], []

    async def handler_a(env):
        a.append(env)

    async def handler_b(env):
        b.append(env)

    bus.subscribe("multi.event", handler_a)
    bus.subscribe("multi.event", handler_b)
    await bus.publish("multi.event", {}, correlation_id=uuid.uuid4())
    await asyncio.wait_for(bus._drain(), timeout=1.0)

    assert len(a) == 1
    assert len(b) == 1
    await bus.stop()
