"""Inbound adapters: CLI, REST API, MCP, and MQ consumers.

A protocol deserializes and validates external input, calls the matching
service, and serializes the result. It never implements business workflows.
"""
