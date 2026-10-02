"""Keep the suite from reading whoever is running it.

A test that reaches the ambient environment passes or fails by accident. Two ways in:

- `GITHUB_TOKEN` / `GH_TOKEN` decide the discovery budget, so a machine with a token keeps
  12 candidates where CI keeps 2. That shipped a green local run to a red CI once already.
- `GRAYOM_HOME` is unset by default, so anything constructing a cache, config or state
  store without an explicit path reads and writes the developer's real `~/.grayom`.

Both are neutralised for every test. A test that wants either sets it with `monkeypatch`,
which applies inside the test body and so still wins.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path_factory):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GRAYOM_HOME", str(tmp_path_factory.mktemp("grayom-home")))
