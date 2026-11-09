# OpenQuantMaster

Service-oriented quant building blocks under `src/services/` (`OHLCV`, `Ticker`, `Indicator`, `NewsFetcher`, `BinancePerp`, `NotificationService`). Each service is a facade with semantically named methods: `await service.fetch_bars({...})` → `ServiceResult`. `Ticker.fetch_ticker()` provides latest A-share and crypto snapshots through the existing Tushare and Binance configurations, complementing historical OHLCV bars.

The code follows a layered architecture: `src/protocols/` (CLI) → `src/services/` (facade) → `src/use_cases/` (workflow) → `src/providers/` (third-party calls), with shared types in `src/models/`, generic helpers in `src/utils/`, the external configuration format in `src/config.py`, and the composition boundary in `src/composition.py`.

Layering and test style: [`docs/conventions/`](docs/conventions/). Service references: [`docs/services/`](docs/services/).

## Requirements

- Python **>= 3.12**
- **TA-Lib** C library (needed by the `ta-lib` Python wheel used by `Indicator`)

On Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y build-essential wget
# If your distro has no libta-lib-dev package, build the C library:
wget https://github.com/TA-Lib/ta-lib/releases/download/v0.6.4/ta-lib-0.6.4-src.tar.gz
tar xzf ta-lib-0.6.4-src.tar.gz
cd ta-lib-0.6.4 && ./configure --prefix=/usr && make && sudo make install
```

## Setup

```bash
git clone https://github.com/linjiaqin12138/OpenQuantMaster.git
cd OpenQuantMaster

python3.12 -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install -e ".[dev]"
```

Optional: copy `config.yaml.example` / `.env.example` when you wire live exchange credentials later. Unit tests do not need them (SDKs are faked).

## CLI

After the editable install, use `qm-cli` to inspect and run services:

```bash
qm-cli help
qm-cli list
qm-cli run ohlcv --symbol BTCUSDT --market crypto --interval 1h --limit 10
qm-cli run indicator --symbol BTCUSDT --indicators sma,rsi,macd --patterns DOJI
qm-cli run news-fetcher --mode recent --sources cls,em --keywords 降息,央行
qm-cli run notification --title "Order filled" --content "BTCUSDT filled" --format markdown
qm-cli run binance-perp balance
```

Use `qm-cli run ohlcv --help` for all OHLCV options. The default `rich` output uses a service-specific renderer; services without one fall back to JSON. Successful JSON output contains only the service `data`, while failures contain only the error and exit non-zero. Live OHLCV calls access external market-data providers.

Select JSON output or apply a JSONPath expression to the successful `data` value:

```bash
qm-cli run ohlcv --symbol BTCUSDT --market crypto --interval 1h --limit 10 -o json
qm-cli run ohlcv --symbol BTCUSDT --market crypto --interval 1h -o 'jsonpath={.bars}'
qm-cli run ohlcv ... -o json > result.json
```

Service commands load YAML configuration from `--config PATH`, `./config.yaml`, or `~/.qm/config.yaml`, in that order. For example:

```bash
qm-cli --config /path/to/config.yaml run ohlcv --symbol BTCUSDT --market crypto --interval 1h
```

See `config.yaml.example` for the provider configuration structure.

## Run tests

From the repo root with the venv activated:

```bash
# all tests
pytest

# one layer only
pytest tests/services -q
pytest tests/providers -q
pytest tests/protocols -q

# unit marker only
pytest -m unit

# one file / one test
pytest tests/services/test_ohlcv.py -q
pytest tests/services/test_indicator.py::test_compute_rejects_an_unknown_indicator -q
```

`pyproject.toml` sets `pythonpath = ["."]`, so imports like `src.services...` resolve without extra env vars.

## Quick service call

```python
import asyncio
from src.services.ohlcv import OHLCV, OHLCVServiceConfig

async def main():
    service = OHLCV(OHLCVServiceConfig())
    result = await service.fetch_bars(
        {"symbol": "BTCUSDT", "market": "crypto", "interval": "1h", "limit": 10}
    )
    print(result.success, result.error, result.data)

asyncio.run(main())
```

Live `OHLCV` / exchange calls hit the network; prefer the tests (mocked SDKs) for a no-network smoke check.
