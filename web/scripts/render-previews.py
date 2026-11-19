#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "jsonschema>=4.23",
#     "pypdf>=6.0",
#     "typst>=0.15",
# ]
# ///
"""Write preview-modern.pdf, preview-classic.pdf, and preview-sidebar.pdf.

Leaves cv.pdf and cv.md as they are. The run's own template is compiled last so
build/ still matches that PDF.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude" / "skills" / "tailoring-cvs" / "scripts"))

from cvtlib.errors import CvtError  # noqa: E402
from cvtlib.render import TEMPLATES, render_run  # noqa: E402
from cvtlib import state  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("Name the run directory.", file=sys.stderr)
        return 2
    run = Path(sys.argv[1]).resolve()
    try:
        st = state.load(run)
        state.require_stage(st, "tailored")
    except CvtError as err:
        print(err.message, file=sys.stderr)
        return 1
    current = str((st.get("options") or {}).get("template") or "modern")
    if current not in TEMPLATES:
        current = "modern"
    order = [name for name in TEMPLATES if name != current] + [current]
    rows = []
    for template in order:
        try:
            result = render_run(run, template=template, out_pdf=run / f"preview-{template}.pdf")
        except CvtError as err:
            print(err.message, file=sys.stderr)
            return 1
        rows.append({"template": template, "file": f"preview-{template}.pdf", "pages": result.pages})
    json.dump({"template": current, "templates": rows}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
