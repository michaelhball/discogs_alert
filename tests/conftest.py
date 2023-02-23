from typing import List

import pytest


def pytest_addoption(parser: pytest.Parser):
    parser.addoption(
        "--online",
        action="store_true",
        default=False,
        help="Run all tests, including those that require internet access",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]):
    if config.getoption("--online"):
        return
    skip_online_test = pytest.mark.skip(reason="Need --online command-line flag in order to run")
    for item in items:
        if "online" in item.keywords:
            item.add_marker(skip_online_test)
