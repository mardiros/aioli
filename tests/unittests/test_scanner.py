from typing import Any

import pytest

import blacksmith
from blacksmith.domain.registry import Registry


@pytest.mark.parametrize(
    "params",
    [
        {
            "mod": "tests.unittests.scanned_resources",
            "expected": {
                "fruits": ("fruits", "v1"),
                "vegetables": ("vegetables", "v1"),
            },
        },
        {
            "mod": "tests.unittests.scanned_resources2.potatoes",
            "expected": {"vegetables": ("vegetables", "v1")},
        },
    ],
)
def test_scan(params: dict[str, Any], registry: Registry):
    blacksmith.scan(params["mod"])
    assert registry.client_service == params["expected"]


@pytest.mark.parametrize(
    "params",
    [
        {
            "mod": "42",
            "expected_exception": ModuleNotFoundError,
            "expected_message": "No module named '42'",
        },
        {
            "mod": ".scanned_resources",
            "expected_exception": ValueError,
            "expected_message": ".scanned_resources: Relative package unsupported",
        },
    ],
)
def test_scan_errors(params: dict[str, Any], registry: Registry):
    with pytest.raises(params["expected_exception"]) as ctx:
        blacksmith.scan(params["mod"])
    assert str(ctx.value) == params["expected_message"]
