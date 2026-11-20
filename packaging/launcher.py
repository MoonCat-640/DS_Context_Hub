"""Frozen desktop application entry point."""

import sys
from pathlib import Path


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from smoke_test import run

        return run(Path(sys.argv[2]))

    from ds_context_hub.ui import main as run_app

    run_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
