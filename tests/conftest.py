import pytest


@pytest.fixture(autouse=True)
def _private_cache_home(tmp_path_factory, monkeypatch):
    """Keep the paper index cache that tests write out of the real ~/.cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
