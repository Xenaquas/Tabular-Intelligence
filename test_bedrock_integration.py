"""Compatibility entry point; importing this module never contacts services."""


def main():
    import argparse
    from pathlib import Path

    import pytest

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-bedrock", action="store_true", help="Allow paid inference")
    parser.add_argument("--run-nomic", action="store_true", help="Allow local Nomic calls")
    args = parser.parse_args()
    if not (args.run_bedrock or args.run_nomic):
        parser.error("Specify --run-bedrock and/or --run-nomic to opt into live tests")
    root = Path(__file__).resolve().parent
    options = [str(root / "tests" / "integration")]
    options += [f"--run-{name}" for name in ("bedrock", "nomic") if getattr(args, f"run_{name}")]
    return pytest.main(options)


if __name__ == "__main__":
    raise SystemExit(main())
