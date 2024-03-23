import fnmatch
import warnings
from pathlib import Path

import pytest
from pytest import PytestWarning, UsageError


class PytestSelectWarning(PytestWarning):
    pass


def pytest_addoption(parser):
    select_group = parser.getgroup(
        "select",
        "Modify the list of collected tests.",  # pragma: no mutate  # pragma: no mutate
    )
    select_group.addoption(
        "--select-from-file",
        action="store",
        dest="selectfromfile",
        default=None,
        help="Select tests given in file. One line per test name.",  # pragma: no mutate
    )
    select_group.addoption(
        "--deselect-from-file",
        action="store",
        dest="deselectfromfile",
        default=None,
        help="Deselect tests given in file. One line per test name.",  # pragma: no mutate
    )
    select_group.addoption(
        "--select-fail-on-missing",
        action="store_true",
        dest="selectfailonmissing",
        default=False,
        help=(
            "Fail instead of warn when not all "  # pragma: no mutate
            "(de-)selected tests could be found."  # pragma: no mutate
        ),
    )


@pytest.hookimpl(trylast=True)  # pragma: no mutate
def pytest_report_header(config):
    _validate_option_values(config)

    fail_on_missing = config.getoption("selectfailonmissing")

    for option_name, selecting in [
        ("selectfromfile", True),
        ("deselectfromfile", False),
    ]:
        option_value = config.getoption(option_name)
        if option_value is not None:
            return [
                "select: {}selecting tests from '{}'{}".format(
                    "de" if not selecting else "",
                    option_value,
                    ", failing on missing selection items" if fail_on_missing else "",
                )
            ]


def pytest_collection_modifyitems(session, config, items):
    _validate_option_values(config)

    for option_name, should_select in [
        ("selectfromfile", True),
        ("deselectfromfile", False),
    ]:
        selection_file_name = config.getoption(option_name)
        if selection_file_name is None:
            continue

        selection_file_path = Path(selection_file_name)
        with selection_file_path.open("rt", encoding="UTF-8") as selection_file:
            test_patterns = {
                test_pattern.strip()
                for test_pattern in selection_file
                if not test_pattern.startswith("#")
            }

        test_patterns_that_matched = set()
        selected_items = []
        deselected_items = []

        for item in items:
            has_match = False
            for test_pattern in test_patterns:
                if fnmatch.fnmatch(item.nodeid, test_pattern) or item.name == test_pattern:
                    test_patterns_that_matched.add(test_pattern)
                    has_match = True

            if has_match:
                selected_items.append(item)
            else:
                deselected_items.append(item)

        if not should_select:
            # We are *de*selecting, flip collections
            selected_items, deselected_items = deselected_items, selected_items

        test_patterns_that_did_not_match = test_patterns - test_patterns_that_matched
        if test_patterns_that_did_not_match:
            # If any items remain in `test_patterns` those tests either don't exist or
            # have been deselected by another way - warn user

            message = (
                f"pytest-select: Not all test patterns matched an actual test. "
                f"The patterns without matching tests are:\n  - "
            )
            message += "\n  - ".join(test_patterns_that_did_not_match)
            if config.getoption("selectfailonmissing"):
                raise UsageError(message)
            warnings.warn(message, PytestSelectWarning)

        # Slice assignment is required since `items` needs to be modified in place
        items[:] = selected_items
        config.hook.pytest_deselected(items=deselected_items)


def _validate_option_values(config):
    is_option_conflict = (
        config.getoption("selectfromfile") is not None
        and config.getoption("deselectfromfile") is not None
    )
    if is_option_conflict:
        raise UsageError(
            "'--select-from-file' and '--deselect-from-file' can not be used together."
        )

    for option_name in ["selectfromfile", "deselectfromfile"]:
        option_value = config.getoption(option_name)
        if option_value is None:
            continue

        selection_file_path = Path(option_value)
        if not selection_file_path.exists():
            raise UsageError(f"Given selection file '{selection_file_path}' doesn't exist.")
