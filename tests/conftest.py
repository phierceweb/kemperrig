import pytest


@pytest.fixture(autouse=True)
def _no_installed_stomps(monkeypatch):
    """Tests see the fallback effect names whether or not Rig Manager is installed."""
    monkeypatch.setenv("KEMPERRIG_STOMPS_XML", "/nonexistent/Stomps.xml")
