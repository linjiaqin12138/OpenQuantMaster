# Testing conventions

## Goals

Tests should survive internal refactors and each behavior should have one primary test location. Prefer stable public surfaces—semantically named Service methods, Provider functions, Protocol entrypoints, and external SDK APIs—over private helpers.

The standard application behavior test is:

```text
build the Service through the composition root
    → call its named method with real Service and UseCase code
    → patch only the concrete Provider at the external-call boundary
    → assert the public ServiceResult
```

Do not create a separate test layer for every code layer. In particular, Service-to-UseCase delegation is normally thin and does not justify a parallel set of UseCase tests, and Composition does not need a standalone test suite duplicating Service scenarios.

## Test ownership

| Test location | Owns these behaviors | Does not repeat |
|---|---|---|
| `tests/services/` | Complete application actions through real Service and UseCase code: Input/Output validation, workflows, retry/fallback, Provider-to-Service error mapping, and configuration propagation | Provider transport parsing and Protocol formatting |
| `tests/providers/` | Provider request construction, SDK/HTTP interaction, response parsing, provider-local normalization, and exception-to-Provider-error mapping | UseCase workflows and Service error mapping |
| `tests/protocols/` | Transport parsing, protocol response rendering, Service-to-Protocol error-code mapping, exit/status behavior, and final unknown-exception handling | Application workflows and Provider behavior |
| `tests/utils/` | Small, direct tests of reusable helpers and decorators | Application workflows and exhaustive implementation matrices |
| Repository integration tests | Real queries, constraints, commits, rollbacks, and fixtures against a real test database | Provider or Protocol behavior |

A Service test may verify configuration propagation because the Service was built from external configuration through Composition. That covers Composition as part of the public behavior test; do not repeat the same scenario in `tests/composition/`.

UseCases remain real components inside Service tests. Do not add routine `tests/use_cases/` suites that repeat Service tests merely to call `UseCase.run()` directly. Add a lower-level test only for a genuinely independent component whose behavior cannot be exercised clearly through its public Service, not as a default layer.

Do not add routine `tests/models/` suites. Validate models and shared Result behavior through the public Service, Provider, or utility boundary that uses them rather than testing data structures in isolation for coverage.

## Utility tests

Keep `tests/utils/` simple. Call public utility functions or decorators directly with representative inputs and assert their outputs or effects. Cover the normal case and only meaningful boundaries such as empty input, invalid values, retry exhaustion, or backoff policy. Utilities should not require Service, Provider, network, database, global configuration, or complex fixtures. Do not mock their internals or reproduce the same cases through multiple application layers.

## Avoid duplicate coverage

Assign each assertion to one owning boundary:

- A Provider test proves that an SDK timeout becomes `provider_timeout`.
- A Service test proves that `provider_timeout` becomes the documented application error and triggers any application retry/fallback.
- A Protocol test proves that the application error becomes the external code required by that Protocol's spec.

These are different contracts and are not duplicates. By contrast, testing the same workflow, validation rule, or error mapping once through Service and again directly through UseCase is duplicate coverage.

Keep one representative end-to-end Service scenario when it demonstrates wiring. Do not copy the full UseCase scenario matrix into Service, Composition, and Protocol tests.

## Composition-based Service construction

Build Services under test through the composition root from external configuration whenever a composition path exists:

```python
app_config = AppConfig.model_validate(external_config_values)
service = build_application_service(app_config)
result = await service.execute(valid_request_values)
```

This exercises the same construction path used by Protocols and proves that external fields reach the correct Service/UseCase Config without testing Composition as an additional behavior layer.

Direct Service construction is acceptable only when no composition path exists or the test specifically concerns a manually assembled variant. Do not bypass Composition merely to simplify test setup.

## Patch strategy

### Service and UseCase code: do not patch

Keep the real Service, its concrete UseCases, composed UseCases, validation, workflows, and error mapping. Do not inject or mock a UseCase merely to test a Service. The standard `UseCase.run()` boundary is exercised through the Service's named methods.

### Concrete Providers: patch when testing application behavior

Service tests may monkeypatch the concrete Provider functions called by their UseCases. Providers are deliberate, thin, stable external-call boundaries with documented parameters and normalized results, so no Provider interface or dependency injection is required for testing.

Patch the Provider at its point of use so the real workflow receives the fake:

```python
monkeypatch.setattr(
    "src.use_cases.example.call_remote_api_result",
    fake_call_remote_api_result,
)
```

A fake Provider returns the Provider's documented `Result` and provider-level data, including provider-local normalization. It must not return a Service Output model or a Protocol response.

Use Provider fakes for success values and classified Provider failures, including `unknown`, to exercise application retry, fallback, default branches, and error mapping.

### SDK and transport: patch when testing Providers

Provider tests call the real Provider and patch its external SDK, HTTP client, network, or process boundary. Verify request arguments, raw response parsing, normalization, and exception mapping there rather than repeating those assertions in Service tests.

### Internal helpers: do not patch

Do not patch private Service/UseCase methods, internal validators, response shapers, or other implementation helpers. Reach them through the public Service or Provider boundary so internal refactors do not break tests unnecessarily.

### Repositories and persistence: use a real test database

Do not mock Repositories, database sessions, or their results in application workflow tests. Use a real test database with fixtures or factories and exercise actual queries, constraints, commits, and rollbacks. Isolate each test with its own database/schema or reliable cleanup. Use the production database engine for engine-specific transaction, locking, and concurrency behavior.

Pure computation needs no patch; call it through its public boundary and assert outputs.

## Example: Service behavior with a patched Provider

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_maps_provider_failure(app_config, monkeypatch):
    async def fail_call(**kwargs):
        return Result(
            success=False,
            error=Error(code="provider_unavailable", message="down"),
        )

    monkeypatch.setattr(
        "src.use_cases.example.call_remote_api_result",
        fail_call,
    )
    service = build_application_service(app_config)

    result = await service.execute({"value": "example"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "action_unavailable"
```

The same suite may place a successful fake Provider at that boundary and assert normalized `ServiceResult.data`. Provider-specific HTTP request and response details belong in `tests/providers/`, not here.

## Markers

- `@pytest.mark.unit` — fast, no real network; Providers or SDKs may be faked.
- `@pytest.mark.integration` — broader wiring or real test persistence; avoid live external services unless explicitly intended.
