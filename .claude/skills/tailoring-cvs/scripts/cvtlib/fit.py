"""Page fit (interfaces.md section 9): density pass, then a monotone binary search over the drop order.

`drop_order` ranks every droppable unit (bullets, certifications, skill groups) so that dropping a longer prefix can only
shrink the document. `fit_run` uses that to find the smallest prefix that reaches the page target in O(log n) compiles,
never oscillating. Trial compiles go to `build/fit-try.pdf`; `cv.pdf` only ever holds the final fitted render.
"""

from __future__ import annotations

from pathlib import Path

from . import jsonio, render, schemas
from .errors import CvtError, ExitCode

MAX_RENDERS = 24  # safety cap on compiles per fit, including the final render
PINNED_PRIORITY = 1  # priority-1 units are never dropped
SEARCH_DENSITY = "compact"  # the densest preset: the drop search runs here
SCRATCH_PDF = f"{render.BUILD_DIR}/fit-try.pdf"
SCHEMA_VERSION = "1"
UNDATED_RANK = 1  # skill groups and certifications have no employer age; they drop after dated bullets of equal priority
DATED_RANK = 0
OVERFLOW_MESSAGE = "content with priority 1 exceeds {target} pages; lower some priorities or shorten bullets"
OVERFLOW_HINT = (
    "raise the priority number of low-value bullets in tailored.json (5 drops first), or shorten pinned bullets, "
    "then rerun: cvt check-tailored {run} && cvt fit {run}"
)


def _units(tailored: dict) -> list[tuple[str, int, str]]:
    """Every droppable unit in document order: (id, effective priority, employer start date or '')."""
    units: list[tuple[str, int, str]] = [(g["id"], g["priority"], "") for g in tailored["skills"]]
    for entry in tailored["experience"]:
        start = entry["start_date"]
        floor = entry["priority"]
        units += [(b["id"], max(b["priority"], floor), start) for b in entry["bullets"]]
        for eng in entry["engagements"]:
            eng_floor = max(floor, eng["priority"])
            units += [(b["id"], max(b["priority"], eng_floor), start) for b in eng["bullets"]]
    units += [(c["id"], c["priority"], "") for c in tailored["certifications"]]
    return units


def drop_order(tailored: dict) -> list[str]:
    """IDs to drop, first to last: priority descending, oldest employer first, last position first. Priority 1 excluded."""
    ranked = []
    for index, (unit_id, priority, start) in enumerate(_units(tailored)):
        if priority <= PINNED_PRIORITY:
            continue
        rank = DATED_RANK if start else UNDATED_RANK
        ranked.append(((-priority, rank, start, -index), unit_id))
    return [unit_id for _key, unit_id in sorted(ranked)]


def _trial_pages(run_dir: Path, density: str, dropped: set[str]) -> int:
    return render.render_run(run_dir, density=density, dropped_ids=dropped, out_pdf=run_dir / SCRATCH_PDF).pages


def _render_cap_error() -> CvtError:
    return CvtError(
        ExitCode.INTERNAL, "E_FIT_RENDER_CAP", f"fit needed more than {MAX_RENDERS} compiles",
        hint="this is a bug in the fit search; report out/<run>/fit.json (not written) and the tailored.json size",
    )


def fit_run(run_dir: Path, *, png: bool = False) -> dict:
    """Search density and drops, write `fit.json`, run the final render (PNGs only when `png`), return the fit object."""
    run_dir = Path(run_dir)
    tailored = jsonio.load_json(run_dir / render.TAILORED_FILE)
    target = int(tailored["target"]["page_target"])
    units = drop_order(tailored)
    log: list[str] = []
    measured: dict[int, int] = {}  # drop count k -> pages, for the search density
    renders = 0

    def attempt(density: str, k: int, label: str) -> int:
        nonlocal renders
        if renders >= MAX_RENDERS - 1:  # one compile stays reserved for the final render
            raise _render_cap_error()
        renders += 1
        pages = _trial_pages(run_dir, density, set(units[:k]))
        log.append(f"{label}: {pages} pages")
        if density == SEARCH_DENSITY:
            measured[k] = pages
        return pages

    def overflow() -> CvtError:
        return CvtError(
            ExitCode.CHECK_FAILED, "E_FIT_OVERFLOW", OVERFLOW_MESSAGE.format(target=target),
            hint=OVERFLOW_HINT.format(run=run_dir.name),
        )

    density, dropped_count, pages = SEARCH_DENSITY, 0, 0
    for candidate in render.DENSITIES:
        pages = attempt(candidate, 0, candidate)
        if pages <= target:
            density = candidate
            break
    else:
        if not units or attempt(SEARCH_DENSITY, len(units), f"k={len(units)}") > target:
            raise overflow()
        low, high = 1, len(units)  # k=0 overflows; k=len(units) fits
        while low < high:
            mid = (low + high) // 2
            if attempt(SEARCH_DENSITY, mid, f"k={mid}") <= target:
                high = mid
            else:
                low = mid + 1
        dropped_count = low
        pages = measured[dropped_count]
    dropped = units[:dropped_count]
    fit = {
        "schema_version": SCHEMA_VERSION, "run_id": run_dir.name, "tailored_version": int(tailored["version"]),
        "page_target": target, "pages": pages, "density": density, "dropped_ids": dropped, "renders": renders + 1,
        "underfilled": pages < target, "log": log,
    }
    schemas.require_valid(fit, "fit", render.FIT_FILE)
    jsonio.dump_json(fit, run_dir / render.FIT_FILE)
    final = render.render_run(run_dir, density=density, dropped_ids=set(dropped), png=png)
    if final.pages != pages:
        raise CvtError(
            ExitCode.INTERNAL, "E_FIT_NONDETERMINISTIC",
            f"final render has {final.pages} pages but the search measured {pages}",
            hint="rerun cvt fit; if it persists the template output is not deterministic",
        )
    return fit
