"""Step 0 smoke tests for the isolated, non-executing project shell."""

from meridian import __version__


def test_package_version_is_present() -> None:
    assert __version__ == "0.0.0"
