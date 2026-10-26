#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "jsonschema>=4.23",
#     "pypdf>=6.0",
#     "typst>=0.15",
# ]
# ///
"""cvt: deterministic helper commands for the tailoring-cvs skill.

Run from the workspace root:  uv run .claude/skills/tailoring-cvs/scripts/cvt.py <command> [args]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

EXIT_MISSING_DEPENDENCY = 3

try:
    import cvtlib.cli
    import cvtlib.schemas  # noqa: F401  (imports jsonschema)
except ModuleNotFoundError as exc:
    print(f"cvt: error[E_DEPENDENCY]: missing Python module '{exc.name}'", file=sys.stderr)
    print(f"  hint: run with: uv run {Path(__file__).as_posix()} ...", file=sys.stderr)
    raise SystemExit(EXIT_MISSING_DEPENDENCY)

raise SystemExit(cvtlib.cli.main())
