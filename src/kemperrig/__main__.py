"""`python -m kemperrig` — the same entry point as the `kemperrig` console script."""

import sys

from kemperrig.cli import main

if __name__ == "__main__":
    sys.exit(main())
