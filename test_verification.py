"""Compatibility entry point for the offline retail regression tests."""


def main():
    from pathlib import Path

    import pytest

    root = Path(__file__).resolve().parent
    return pytest.main([str(root / "tests" / "offline" / "test_retail.py")])


if __name__ == "__main__":
    raise SystemExit(main())
