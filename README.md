# OpenQuantMaster

Agent-first quantitative trading daemon.

## Development setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
quantmaster-daemon --run hello_pipeline
```
