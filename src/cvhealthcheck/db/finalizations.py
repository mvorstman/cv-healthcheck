"""Finalize and reload operations for ADR 0002 phase 5.

Finalize copies a project's working artifacts to an immutable snapshot
under `finalized/<n>/`. Reload copies the latest finalization back to
working. Both are application-layer operations — there is no filesystem-
level immutability; the contract is that no code path other than
`finalize_project` writes under `finalized/`.

Module layout matches ADR 0002's storage spec:

    data/catalog/artifacts/<customer>/<project>/working/<subject>/
        latest.json
        <timestamp>.json

    data/catalog/artifacts/<customer>/<project>/finalized/<n>/<subject>/
        latest.json
        <timestamp>.json

Each subject's `latest.json` is the authoritative "current state" file;
timestamped files are append-only history. Diffing only compares
`latest.json` per subject — a touched-but-identical save doesn't trigger
a false "modified" signal.
"""
from __future__ import annotations

import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cvhealthcheck.artifacts.store as _store_module


_WORKING = "working"
_FINALIZED = "finalized"
_LATEST_FILE = "latest.json"


class FinalizationError(RuntimeError):
    """Raised when finalize or reload preconditions aren't met.

    Examples:
      - Finalize called on a project with no working artifacts.
      - Reload called on a project with no finalizations.
    """


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _project_root(customer_id: str, project_id: str) -> Path:
    """Return the on-disk root directory for a project's artifacts.

    Reads _DEFAULT_BASE_DIR via attribute access so that the test
    fixture's monkeypatch on the store module is picked up.
    """
    return _store_module._DEFAULT_BASE_DIR / customer_id / project_id


def _working_root(customer_id: str, project_id: str) -> Path:
    return _project_root(customer_id, project_id) / _WORKING


def _finalized_root(customer_id: str, project_id: str, number: int) -> Path:
    return _project_root(customer_id, project_id) / _FINALIZED / str(number)


def _list_subject_dirs(root: Path) -> list[str]:
    """Return sorted subject_id names directly under `root`.

    Subjects are the immediate subdirectories. Missing root or empty root
    returns [].
    """
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def _max_finalization_number(
    db: sqlite3.Connection, project_id: str,
) -> int:
    row = db.execute(
        "SELECT MAX(finalization_number) FROM finalizations WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def finalize_project(
    db: sqlite3.Connection,
    customer_id: str,
    project_id: str,
) -> int:
    """Snapshot working state into a new finalization. Returns the new
    finalization_number.

    Raises FinalizationError if no project row, no customer row, or no
    working artifacts exist.
    """
    project = db.execute(
        "SELECT project_id, customer_id, ticket_reference, assigned_consultant"
        " FROM projects WHERE customer_id = ? AND project_id = ?",
        (customer_id, project_id),
    ).fetchone()
    if project is None:
        raise FinalizationError(
            f"Project '{project_id}' not found under customer '{customer_id}'."
        )

    working_root = _working_root(customer_id, project_id)
    subjects = _list_subject_dirs(working_root)
    if not subjects:
        raise FinalizationError(
            "Cannot finalize: no artifacts collected in working state."
        )

    next_number = _max_finalization_number(db, project_id) + 1
    finalized_root = _finalized_root(customer_id, project_id, next_number)
    finalized_root.mkdir(parents=True, exist_ok=True)

    for subject_id in subjects:
        shutil.copytree(
            working_root / subject_id,
            finalized_root / subject_id,
            # dirs_exist_ok kept False: a finalized subject dir should
            # never already exist when we land here (next_number is new).
        )

    db.execute(
        "INSERT INTO finalizations"
        " (finalization_id, project_id, finalization_number,"
        "  finalized_at, finalized_by, ticket_reference)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            f"finz_{uuid.uuid4().hex[:12]}",
            project_id,
            next_number,
            _now(),
            project["assigned_consultant"] or None,
            project["ticket_reference"] or None,
        ),
    )
    db.commit()
    return next_number


def reload_latest_finalization(
    db: sqlite3.Connection,
    customer_id: str,
    project_id: str,
) -> int:
    """Copy the latest finalization's files into the working directory,
    overwriting whatever is there. Returns the finalization_number that
    was reloaded.

    Raises FinalizationError if no finalization exists for the project.
    """
    latest = _max_finalization_number(db, project_id)
    if latest == 0:
        raise FinalizationError(
            "Cannot reload: no finalizations exist for this project."
        )

    finalized_root = _finalized_root(customer_id, project_id, latest)
    if not finalized_root.is_dir():
        raise FinalizationError(
            f"Finalization #{latest} row exists in the database but its "
            f"directory is missing at {finalized_root}."
        )

    working_root = _working_root(customer_id, project_id)
    working_root.mkdir(parents=True, exist_ok=True)

    # Remove every subject currently in working — reload is "restore from
    # snapshot," not "merge into snapshot." A subject that was finalized
    # then deleted from working must reappear after reload; a subject
    # added to working since the finalization must disappear.
    for existing in working_root.iterdir():
        if existing.is_dir():
            shutil.rmtree(existing)
        else:
            existing.unlink()

    for subject_id in _list_subject_dirs(finalized_root):
        shutil.copytree(
            finalized_root / subject_id,
            working_root / subject_id,
        )

    # Bump the project's working_state_modified_at so the UI's "uncommitted
    # changes" signal resets (working now matches the just-reloaded
    # finalization).
    db.execute(
        "UPDATE projects SET working_state_modified_at = ?"
        " WHERE customer_id = ? AND project_id = ?",
        (_now(), customer_id, project_id),
    )
    db.commit()
    return latest


def diff_working_vs_latest(
    db: sqlite3.Connection,
    customer_id: str,
    project_id: str,
) -> list[str]:
    """Return the sorted list of subject_ids that differ between working
    and the latest finalization.

    Comparison is content-based on each subject's `latest.json`. Subjects
    present in one but not the other are also "differ".

    Returns [] when:
      - Working and latest match exactly.
      - No finalizations exist (caller should handle this distinct case
        before calling — but [] is the technically correct "no diff"
        answer when there's no baseline).
    """
    latest = _max_finalization_number(db, project_id)
    if latest == 0:
        return []

    working_root = _working_root(customer_id, project_id)
    finalized_root = _finalized_root(customer_id, project_id, latest)

    working_subjects = set(_list_subject_dirs(working_root))
    finalized_subjects = set(_list_subject_dirs(finalized_root))

    differing: set[str] = working_subjects.symmetric_difference(finalized_subjects)

    for subject_id in working_subjects & finalized_subjects:
        wf = working_root / subject_id / _LATEST_FILE
        ff = finalized_root / subject_id / _LATEST_FILE
        if not wf.exists() or not ff.exists():
            differing.add(subject_id)
            continue
        if wf.read_bytes() != ff.read_bytes():
            differing.add(subject_id)

    return sorted(differing)
