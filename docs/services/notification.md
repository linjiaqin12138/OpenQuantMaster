# NotificationService

Sends notifications through a configured provider. PushPlus is currently supported and is the default provider.

## Configuration

```yaml
providers:
  pushplus:
    token: "your-pushplus-token"
    channel: wechat  # Optional; defaults to wechat.
    timeout: 10      # Optional; defaults to 10 seconds.
```

Only `providers.pushplus.token` must be configured. `channel` and `timeout` are optional. For direct construction, `NotificationConfig` contains `provider` (default `pushplus`) and `pushplus` provider settings. Construct from application configuration with `NotificationService.from_config(app_config)`, or pass `NotificationConfig` directly.

## Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | No | Notification title; defaults to an empty string |
| `content` | non-empty string | Yes | Notification body |
| `format` | `html`, `txt`, `markdown`, or `json` | No | Content format; defaults to `html` and maps to PushPlus `template` |

## Output

Successful `ServiceResult.data` contains:

- `provider`: provider used for delivery.
- `format`: content format sent.
- `message_id`: PushPlus response `data`, converted to a string when present.
- `response`: complete PushPlus JSON response.

Failures use `missing_provider_token` when no token is configured, `provider_rejected` for a PushPlus application error, `provider_request_failed` for HTTP transport errors, and `invalid_provider_response` for malformed response data. Input validation failures use the standard `unhandled_exception` error from `BaseService`.

## Example

```python
from src.config import NotificationConfig, PushPlusProviderConfig
from src.services.notification import NotificationService

service = NotificationService(
    NotificationConfig(pushplus=PushPlusProviderConfig(token="your-token"))
)
result = await service.run(
    {"title": "Order filled", "content": "BTCUSDT filled", "format": "markdown"}
)
```

The PushPlus operation uses the JSON POST endpoint `https://www.pushplus.plus/send`. Sending a notification is a live external side effect.
