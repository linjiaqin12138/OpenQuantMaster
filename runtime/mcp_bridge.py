from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class McpConfig:
    mode: str
    mcp_command: str
    mcp_url: str


class McpError(RuntimeError):
    pass


class McpBridge:
    """Minimal stdio MCP client for Vibe-Trading."""

    _instances: dict[str, "McpBridge"] = {}
    _lock = asyncio.Lock()

    def __init__(self, cfg: McpConfig) -> None:
        self._cfg = cfg
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._next_id = 1
        self._init_lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls, cfg: McpConfig) -> "McpBridge":
        key = f"{cfg.mcp_command}:{cfg.mcp_url}"
        async with cls._lock:
            bridge = cls._instances.get(key)
            if bridge is None or not bridge.is_alive:
                bridge = cls(cfg)
                cls._instances[key] = bridge
            return bridge

    @property
    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def _ensure_started(self) -> None:
        async with self._init_lock:
            if self.is_alive:
                return

            command = self._cfg.mcp_command
            logger.info("mcp_bridge.starting", command=command)
            self._proc = await asyncio.create_subprocess_exec(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._reader = self._proc.stdout
            self._writer = self._proc.stdin
            if self._reader is None or self._writer is None:
                raise McpError("Failed to open stdio pipes for MCP server")

            await self._initialize()

    async def _initialize(self) -> None:
        result = await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "openquantmaster", "version": "0.1.0"},
            },
        )
        logger.debug("mcp_bridge.initialized", result=result)
        await self._notification("notifications/initialized")

    async def list_tools(self) -> list[dict[str, Any]]:
        await self._ensure_started()
        result = await self._request("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        await self._ensure_started()
        result = await self._request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            content = result.get("content", [])
            text = "\n".join(str(c.get("text", "")) for c in content)
            raise McpError(f"MCP tool '{name}' returned error: {text}")

        content = result.get("content", [])
        texts = [str(c.get("text", "")) for c in content if c.get("type") == "text"]
        if not texts:
            return result
        full_text = "".join(texts)
        try:
            return json.loads(full_text)
        except json.JSONDecodeError:
            return {"text": full_text}

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        await self._send(message)

        while True:
            line = await self._read_line()
            if line is None:
                raise McpError(f"MCP server closed stream while waiting for {method}")
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("mcp_bridge.invalid_json", line=line)
                continue

            # Ignore notifications / unsolicited responses
            if response.get("id") != request_id:
                logger.debug("mcp_bridge.unsolicited", response=response)
                continue
            if "error" in response:
                error = response["error"]
                raise McpError(f"MCP error {error.get('code')}: {error.get('message')}")
            return response.get("result", {})

    async def _notification(self, method: str) -> None:
        await self._send({"jsonrpc": "2.0", "method": method})

    async def _send(self, message: dict[str, Any]) -> None:
        if self._writer is None:
            raise McpError("MCP bridge not started")
        payload = json.dumps(message, ensure_ascii=False) + "\n"
        self._writer.write(payload.encode("utf-8"))
        await self._writer.drain()

    async def _read_line(self) -> str | None:
        if self._reader is None:
            raise McpError("MCP bridge not started")
        try:
            line = await asyncio.wait_for(self._reader.readline(), timeout=60.0)
        except asyncio.TimeoutError:
            raise McpError("Timeout reading from MCP server")
        if not line:
            return None
        return line.decode("utf-8").strip()

    async def stop(self) -> None:
        async with self._init_lock:
            if self._proc is not None and self._proc.returncode is None:
                self._proc.terminate()
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._proc.kill()
                    await self._proc.wait()
            self._proc = None
            self._reader = None
            self._writer = None
