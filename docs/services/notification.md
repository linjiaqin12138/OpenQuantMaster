# NotificationService

Sends notifications through a configured provider. PushPlus is currently supported and is the default provider.

## Method

`await service.send(request)` — one operation, one UseCase (`SendNotificationUseCase`).

## Configuration

```yaml
providers:
  pushplus:
    token: "your-pushplus-token"
    channel: wechat  # Optional; defaults to wechat.
    timeout: 10      # Optional; defaults to 10 seconds.
```

Only `providers.pushplus.token` must be configured. `channel` and `timeout` are optional. For direct construction, `NotificationServiceConfig` holds `provider` (default `pushplus`), `token`, `channel`, and `timeout_seconds`; the service converts it into the config of its UseCase (`SendNotificationUseCaseConfig`). The composition boundary builds the service config from the external configuration: `build_notification_service(app_config)`.

## Request (`SendNotificationInput`)

The request and response models belong to the UseCase that owns the action; the service re-exports them as part of its public facade.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | No | Notification title; defaults to an empty string |
| `content` | non-empty string | Yes | Notification body |
| `format` | `html`, `txt`, `markdown`, or `json` | No | Content format; defaults to `html` and maps to PushPlus `template` |

## Response (`SendNotificationOutput`)

Successful `ServiceResult.data` contains:

- `provider`: provider used for delivery.
- `format`: content format sent.
- `message_id`: PushPlus response `data`, converted to a string when present.
- `response`: complete PushPlus JSON response.

## Errors

| Code | Meaning |
|------|---------|
| `invalid_input` | The request does not satisfy `SendNotificationInput` |
| `missing_provider_token` | No PushPlus token is configured |
| `unsupported_provider` | The configured provider is not supported |
| `notification_rejected` | PushPlus rejected the message or the credentials |
| `notification_unavailable` | The provider timed out, is unreachable, or rate-limited |
| `notification_failed` | Any other provider failure |

## Example

```python
from src.services.notification import NotificationService, NotificationServiceConfig

service = NotificationService(NotificationServiceConfig(token="your-token"))
result = await service.send(
    {"title": "Order filled", "content": "BTCUSDT filled", "format": "markdown"}
)
```

The PushPlus operation uses the JSON POST endpoint `https://www.pushplus.plus/send`. Sending a notification is a live external side effect.
