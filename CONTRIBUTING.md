# Contributing

Use Python 3.11 or newer and keep changes limited to AI Agent environment management.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install -e . --no-deps
ruff check src tests
mypy src/grayom_agent_guidance/models src/grayom_agent_guidance/runtime
bandit -q -r src
pip-audit
python scripts/release_check.py
pytest -q --cov=grayom_agent_guidance
python -m build
```

Never include credentials, real Agent configuration, backups, caches, or build output in a commit.
Changes that mutate Agent state need preservation, failure-injection, rollback, and idempotency tests.
