"""Every name a package exports in `__all__` must exist (`from package import *` must not raise)."""
import importlib

import pytest

PACKAGES = ["core", "income", "pam", "region", "soil", "water"]


@pytest.mark.parametrize("name", PACKAGES)
def test_all_names_exist(name):
    module = importlib.import_module(f"field_shift.{name}")
    missing = [n for n in module.__all__ if not hasattr(module, n)]
    assert not missing, f"field_shift.{name}.__all__ lists missing names: {missing}"
