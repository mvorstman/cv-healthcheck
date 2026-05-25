"""
cvhealthcheck.extractors.recognition
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Identifies an uploaded file as a known subject + version + source_type by
testing recognition hints stored in the subject_sources table.

Recognition hints per source_type:

HTML:
  "title_contains"       : str  — <title> or <h1> text, case-insensitive
  "has_selector"         : str  — CSS selector must return ≥1 element
  "grid_present"         : bool — presence/absence of div.react-grid-layout
  "table_count"          : int  — exact count of <table> elements
  "first_table_headers"  : list[str] — <th> texts in first table (subset check)

CSV:
  "first_line_contains"  : str  — first line contains value, case-insensitive
  "section_label"        : str  — any line exactly equals value (case-insensitive)
  "section_index"        : int  — always True (not a filter criterion)

Scoring: each evaluated hint criterion that passes adds 1 to the score.
section_index is excluded from the score.  All criteria must pass for a match.
The most-specific match (highest score) is returned.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


@dataclass
class RecognitionResult:
    subject_id: str
    version: int
    source_type: str
    extractable: bool
    non_extractable_reason: str | None
    title: str


class RecognitionEngine:
    def __init__(self, db_conn: sqlite3.Connection) -> None:
        self._db = db_conn
        self._html_cache: dict[Path, BeautifulSoup] = {}

    def identify(self, file_path: Path) -> RecognitionResult | None:
        source_type = _detect_source_type(file_path)
        if source_type is None:
            return None

        candidates = self._load_candidates(source_type)

        matches: list[tuple[int, dict[str, Any]]] = []
        for row in candidates:
            hints = row["recognition_hints"]
            if not hints:
                continue
            score = self._evaluate(file_path, source_type, hints)
            if score is not None:
                matches.append((score, row))

        if not matches:
            return None

        matches.sort(key=lambda x: x[0], reverse=True)
        best = matches[0][1]
        return RecognitionResult(
            subject_id=best["subject_id"],
            version=best["subject_version"],
            source_type=best["source_type"],
            extractable=bool(best["extractable"]),
            non_extractable_reason=best["non_extractable_reason"],
            title=best["title"],
        )

    # ------------------------------------------------------------------
    # DB
    # ------------------------------------------------------------------

    def _load_candidates(self, source_type: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """
            SELECT src.subject_id, src.subject_version, src.source_type,
                   src.extractable, src.non_extractable_reason,
                   src.recognition_hints, s.title
            FROM subject_sources src
            JOIN subjects s
              ON s.subject_id = src.subject_id
             AND s.version    = src.subject_version
            WHERE src.source_type = ?
              AND src.recognition_hints IS NOT NULL
              AND s.status = 'active'
            """,
            (source_type,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            try:
                d["recognition_hints"] = json.loads(d["recognition_hints"])
            except (json.JSONDecodeError, TypeError):
                d["recognition_hints"] = None
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Hint evaluation
    # ------------------------------------------------------------------

    def _evaluate(
        self, file_path: Path, source_type: str, hints: dict
    ) -> int | None:
        """Return score (≥0) if all hints pass, None if any fails."""
        score = 0

        if source_type == "html":
            try:
                soup = self._parse_html(file_path)
            except OSError:
                return None

            if "title_contains" in hints:
                value = hints["title_contains"].lower()
                title_tag = soup.find("title")
                title_text = title_tag.get_text(" ", strip=True).lower() if title_tag else ""
                if value not in title_text:
                    h1 = soup.find("h1")
                    h1_text = h1.get_text(" ", strip=True).lower() if h1 else ""
                    if value not in h1_text:
                        return None
                score += 1

            if "has_selector" in hints:
                if not soup.select(hints["has_selector"]):
                    return None
                score += 1

            if "grid_present" in hints:
                expected = bool(hints["grid_present"])
                present = bool(soup.select("div.react-grid-layout"))
                if present != expected:
                    return None
                score += 1

            if "table_count" in hints:
                if len(soup.find_all("table")) != hints["table_count"]:
                    return None
                score += 1

            if "first_table_headers" in hints:
                expected = {h.lower() for h in hints["first_table_headers"]}
                first_table = soup.find("table")
                if first_table is None:
                    return None
                actual = {
                    th.get_text(" ", strip=True).lower()
                    for th in first_table.find_all("th")
                }
                if not expected.issubset(actual):
                    return None
                score += 1

        elif source_type == "csv":
            try:
                text = _read_csv_text(file_path)
            except OSError:
                return None
            lines = text.splitlines()

            if "first_line_contains" in hints:
                first_line = lines[0].strip().lower() if lines else ""
                if hints["first_line_contains"].lower() not in first_line:
                    return None
                score += 1

            if "section_label" in hints:
                label = hints["section_label"].strip().lower()
                if not any(line.strip().lower() == label for line in lines):
                    return None
                score += 1

            # section_index: always True, excluded from score

        return score

    # ------------------------------------------------------------------
    # HTML parsing cache
    # ------------------------------------------------------------------

    def _parse_html(self, file_path: Path) -> BeautifulSoup:
        if file_path not in self._html_cache:
            content = file_path.read_bytes()
            for enc in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    self._html_cache[file_path] = BeautifulSoup(
                        content.decode(enc), "html.parser"
                    )
                    break
                except UnicodeDecodeError:
                    continue
        return self._html_cache[file_path]


# ------------------------------------------------------------------
# Module-level helpers (also used by dispatcher)
# ------------------------------------------------------------------

def _detect_source_type(file_path: Path) -> str | None:
    """Return 'html', 'csv', or None."""
    ext = file_path.suffix.lower()
    if ext in (".html", ".htm"):
        return "html"
    if ext in (".csv",):
        return "csv"
    try:
        first = file_path.read_bytes()[:512]
        first_lower = first.lower()
        if b"<html" in first_lower or b"<!doctype" in first_lower:
            return "html"
        first_line = first.split(b"\n")[0].decode("utf-8-sig", errors="replace")
        if "," in first_line or '"' in first_line:
            return "csv"
    except Exception:
        pass
    return None


def _read_csv_text(file_path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise OSError(f"Could not read {file_path} with any supported encoding")
