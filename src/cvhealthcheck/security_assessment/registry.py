from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Any

from .models import ArtifactRecord, ImportRun


class SecurityAssessmentArtifactRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path

    def ensure_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS import_runs (
                    import_run_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    commcell_id TEXT NOT NULL,
                    engagement_id TEXT,
                    report_stream_id TEXT,
                    report_run_id TEXT,
                    imported_at TEXT NOT NULL,
                    executed_at TEXT,
                    run_sequence INTEGER,
                    imported_by TEXT,
                    import_method TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    import_run_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_file TEXT,
                    file_path TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT,
                    last_accessed_at TEXT,
                    retention_policy TEXT,
                    imported_by TEXT,
                    import_method TEXT,
                    source_metadata TEXT,
                    FOREIGN KEY (import_run_id) REFERENCES import_runs(import_run_id)
                )
                """
            )
            self._ensure_column(connection, "import_runs", "imported_by", "TEXT")
            self._ensure_column(connection, "import_runs", "import_method", "TEXT")
            self._ensure_column(connection, "artifacts", "created_at", "TEXT")
            self._ensure_column(connection, "artifacts", "last_accessed_at", "TEXT")
            self._ensure_column(connection, "artifacts", "retention_policy", "TEXT")
            self._ensure_column(connection, "artifacts", "imported_by", "TEXT")
            self._ensure_column(connection, "artifacts", "import_method", "TEXT")
            self._ensure_column(connection, "artifacts", "source_metadata", "TEXT")
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_artifacts_active
                ON artifacts (artifact_type, is_active)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_import_runs_stream_exec
                ON import_runs (report_stream_id, executed_at, run_sequence)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_import_runs_scope
                ON import_runs (customer_id, commcell_id, engagement_id, report_stream_id, imported_at)
                """
            )
            connection.commit()

    def register_artifact(self, import_run: ImportRun, artifact: ArtifactRecord) -> None:
        self.ensure_schema()
        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute(
                """
                INSERT OR REPLACE INTO import_runs (
                    import_run_id,
                    customer_id,
                    commcell_id,
                    engagement_id,
                    report_stream_id,
                    report_run_id,
                    imported_at,
                    executed_at,
                    run_sequence,
                    imported_by,
                    import_method
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    import_run.import_run_id,
                    import_run.customer_id,
                    import_run.commcell_id,
                    import_run.engagement_id,
                    import_run.report_stream_id,
                    import_run.report_run_id,
                    import_run.imported_at,
                    import_run.executed_at,
                    import_run.run_sequence,
                    import_run.imported_by,
                    import_run.import_method,
                ),
            )
            if artifact.is_active:
                self._deactivate_scope(
                    connection,
                    artifact_type=artifact.artifact_type,
                    customer_id=artifact.customer_id,
                    commcell_id=artifact.commcell_id,
                    source_type=artifact.source_type,
                    engagement_id=artifact.engagement_id,
                    report_stream_id=artifact.report_stream_id,
                )
            connection.execute(
                """
                INSERT OR REPLACE INTO artifacts (
                    artifact_id,
                    import_run_id,
                    artifact_type,
                    source_type,
                    source_file,
                    file_path,
                    is_active,
                    created_at,
                    last_accessed_at,
                    retention_policy,
                    imported_by,
                    import_method,
                    source_metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    artifact.import_run_id,
                    artifact.artifact_type,
                    artifact.source_type,
                    artifact.source_file,
                    artifact.file_path,
                    1 if artifact.is_active else 0,
                    artifact.created_at,
                    artifact.last_accessed_at,
                    artifact.retention_policy,
                    artifact.imported_by,
                    artifact.import_method,
                    json.dumps(artifact.source_metadata, sort_keys=True),
                ),
            )
            connection.commit()

    def get_latest_artifact(
        self,
        artifact_type: str,
        *,
        customer_id: str | None = None,
        commcell_id: str | None = None,
        source_type: str | None = None,
        engagement_id: str | None = None,
        report_stream_id: str | None = None,
    ) -> ArtifactRecord | None:
        records = self.list_artifacts_for_scope(
            artifact_type,
            customer_id=customer_id,
            commcell_id=commcell_id,
            source_type=source_type,
            engagement_id=engagement_id,
            report_stream_id=report_stream_id,
            descending=True,
        )
        return records[0] if records else None

    def get_active_artifact(
        self,
        artifact_type: str,
        *,
        customer_id: str | None = None,
        commcell_id: str | None = None,
        source_type: str | None = None,
        engagement_id: str | None = None,
        report_stream_id: str | None = None,
    ) -> ArtifactRecord | None:
        self.ensure_schema()
        where_sql, parameters = self._scope_where_clause(
            artifact_type=artifact_type,
            customer_id=customer_id,
            commcell_id=commcell_id,
            source_type=source_type,
            engagement_id=engagement_id,
            report_stream_id=report_stream_id,
        )
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                f"""
                SELECT
                    a.artifact_id,
                    a.import_run_id,
                    a.artifact_type,
                    a.source_type,
                    a.source_file,
                    a.file_path,
                    a.is_active,
                    i.customer_id,
                    i.commcell_id,
                    i.engagement_id,
                    i.report_stream_id,
                    i.report_run_id,
                    i.imported_at,
                    i.executed_at,
                    i.run_sequence,
                    a.created_at,
                    a.last_accessed_at,
                    a.retention_policy,
                    a.imported_by,
                    a.import_method,
                    a.source_metadata
                FROM artifacts a
                JOIN import_runs i ON i.import_run_id = a.import_run_id
                WHERE a.is_active = 1 AND {where_sql}
                ORDER BY i.imported_at DESC
                LIMIT 1
                """,
                parameters,
            ).fetchone()
        if row is None:
            return None
        return self._artifact_from_row(row)

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        self.ensure_schema()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT
                    a.artifact_id,
                    a.import_run_id,
                    a.artifact_type,
                    a.source_type,
                    a.source_file,
                    a.file_path,
                    a.is_active,
                    i.customer_id,
                    i.commcell_id,
                    i.engagement_id,
                    i.report_stream_id,
                    i.report_run_id,
                    i.imported_at,
                    i.executed_at,
                    i.run_sequence,
                    a.created_at,
                    a.last_accessed_at,
                    a.retention_policy,
                    a.imported_by,
                    a.import_method,
                    a.source_metadata
                FROM artifacts a
                JOIN import_runs i ON i.import_run_id = a.import_run_id
                WHERE a.artifact_id = ?
                LIMIT 1
                """,
                (artifact_id,),
            ).fetchone()
        if row is None:
            return None
        return self._artifact_from_row(row)

    def list_artifacts(self, artifact_type: str | None = None) -> list[ArtifactRecord]:
        self.ensure_schema()
        query = """
            SELECT
                a.artifact_id,
                a.import_run_id,
                a.artifact_type,
                a.source_type,
                a.source_file,
                a.file_path,
                a.is_active,
                i.customer_id,
                i.commcell_id,
                i.engagement_id,
                i.report_stream_id,
                i.report_run_id,
                i.imported_at,
                i.executed_at,
                i.run_sequence,
                a.created_at,
                a.last_accessed_at,
                a.retention_policy,
                a.imported_by,
                a.import_method,
                a.source_metadata
            FROM artifacts a
            JOIN import_runs i ON i.import_run_id = a.import_run_id
        """
        parameters: tuple[object, ...] = ()
        if artifact_type:
            query += " WHERE a.artifact_type = ?"
            parameters = (artifact_type,)
        query += " ORDER BY i.imported_at ASC, a.artifact_id ASC"
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, parameters).fetchall()
        return [self._artifact_from_row(row) for row in rows]

    def list_artifacts_for_scope(
        self,
        artifact_type: str,
        *,
        customer_id: str | None = None,
        commcell_id: str | None = None,
        source_type: str | None = None,
        engagement_id: str | None = None,
        report_stream_id: str | None = None,
        descending: bool = True,
    ) -> list[ArtifactRecord]:
        self.ensure_schema()
        where_sql, parameters = self._scope_where_clause(
            artifact_type=artifact_type,
            customer_id=customer_id,
            commcell_id=commcell_id,
            source_type=source_type,
            engagement_id=engagement_id,
            report_stream_id=report_stream_id,
        )
        direction = "DESC" if descending else "ASC"
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT
                    a.artifact_id,
                    a.import_run_id,
                    a.artifact_type,
                    a.source_type,
                    a.source_file,
                    a.file_path,
                    a.is_active,
                    i.customer_id,
                    i.commcell_id,
                    i.engagement_id,
                    i.report_stream_id,
                    i.report_run_id,
                    i.imported_at,
                    i.executed_at,
                    i.run_sequence,
                    a.created_at,
                    a.last_accessed_at,
                    a.retention_policy,
                    a.imported_by,
                    a.import_method,
                    a.source_metadata
                FROM artifacts a
                JOIN import_runs i ON i.import_run_id = a.import_run_id
                WHERE {where_sql}
                ORDER BY i.imported_at {direction}, a.artifact_id {direction}
                """,
                parameters,
            ).fetchall()
        return [self._artifact_from_row(row) for row in rows]

    def get_artifact_by_import_run_id(self, import_run_id: str) -> ArtifactRecord | None:
        self.ensure_schema()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT
                    a.artifact_id,
                    a.import_run_id,
                    a.artifact_type,
                    a.source_type,
                    a.source_file,
                    a.file_path,
                    a.is_active,
                    i.customer_id,
                    i.commcell_id,
                    i.engagement_id,
                    i.report_stream_id,
                    i.report_run_id,
                    i.imported_at,
                    i.executed_at,
                    i.run_sequence,
                    a.created_at,
                    a.last_accessed_at,
                    a.retention_policy,
                    a.imported_by,
                    a.import_method,
                    a.source_metadata
                FROM artifacts a
                JOIN import_runs i ON i.import_run_id = a.import_run_id
                WHERE a.import_run_id = ?
                ORDER BY i.imported_at DESC
                LIMIT 1
                """,
                (import_run_id,),
            ).fetchone()
        if row is None:
            return None
        return self._artifact_from_row(row)

    def get_artifact_by_report_run_id(
        self,
        report_run_id: str,
        *,
        artifact_type: str | None = None,
    ) -> ArtifactRecord | None:
        self.ensure_schema()
        query = """
            SELECT
                a.artifact_id,
                a.import_run_id,
                a.artifact_type,
                a.source_type,
                a.source_file,
                a.file_path,
                a.is_active,
                i.customer_id,
                i.commcell_id,
                i.engagement_id,
                i.report_stream_id,
                i.report_run_id,
                i.imported_at,
                i.executed_at,
                i.run_sequence,
                a.created_at,
                a.last_accessed_at,
                a.retention_policy,
                a.imported_by,
                a.import_method,
                a.source_metadata
            FROM artifacts a
            JOIN import_runs i ON i.import_run_id = a.import_run_id
            WHERE i.report_run_id = ?
        """
        parameters: list[object] = [report_run_id]
        if artifact_type is not None:
            query += " AND a.artifact_type = ?"
            parameters.append(artifact_type)
        query += " ORDER BY i.imported_at DESC LIMIT 1"
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(query, tuple(parameters)).fetchone()
        if row is None:
            return None
        return self._artifact_from_row(row)

    def list_import_runs(
        self,
        *,
        customer_id: str | None = None,
        commcell_id: str | None = None,
        engagement_id: str | None = None,
        report_stream_id: str | None = None,
        report_run_id: str | None = None,
    ) -> list[ImportRun]:
        self.ensure_schema()
        clauses = ["1 = 1"]
        parameters: list[object] = []
        if customer_id is not None:
            clauses.append("customer_id = ?")
            parameters.append(customer_id)
        if commcell_id is not None:
            clauses.append("commcell_id = ?")
            parameters.append(commcell_id)
        if engagement_id is not None:
            clauses.append("engagement_id = ?")
            parameters.append(engagement_id)
        if report_stream_id is not None:
            clauses.append("report_stream_id = ?")
            parameters.append(report_stream_id)
        if report_run_id is not None:
            clauses.append("report_run_id = ?")
            parameters.append(report_run_id)
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT
                    import_run_id,
                    customer_id,
                    commcell_id,
                    engagement_id,
                    report_stream_id,
                    report_run_id,
                    imported_at,
                    executed_at,
                    run_sequence,
                    imported_by,
                    import_method
                FROM import_runs
                WHERE {' AND '.join(clauses)}
                ORDER BY imported_at DESC, import_run_id DESC
                """,
                tuple(parameters),
            ).fetchall()
        return [
            ImportRun(
                import_run_id=str(row["import_run_id"]),
                customer_id=str(row["customer_id"]),
                commcell_id=str(row["commcell_id"]),
                engagement_id=row["engagement_id"],
                report_stream_id=row["report_stream_id"],
                report_run_id=row["report_run_id"],
                imported_at=str(row["imported_at"]),
                executed_at=row["executed_at"],
                run_sequence=row["run_sequence"],
                imported_by=row["imported_by"],
                import_method=row["import_method"],
            )
            for row in rows
        ]

    def list_report_runs(
        self,
        *,
        customer_id: str | None = None,
        commcell_id: str | None = None,
        report_stream_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        clauses = ["report_run_id IS NOT NULL"]
        parameters: list[object] = []
        if customer_id is not None:
            clauses.append("customer_id = ?")
            parameters.append(customer_id)
        if commcell_id is not None:
            clauses.append("commcell_id = ?")
            parameters.append(commcell_id)
        if report_stream_id is not None:
            clauses.append("report_stream_id = ?")
            parameters.append(report_stream_id)
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT
                    report_run_id,
                    report_stream_id,
                    customer_id,
                    commcell_id,
                    executed_at,
                    run_sequence,
                    imported_at,
                    COUNT(*) AS artifact_count
                FROM import_runs
                WHERE {' AND '.join(clauses)}
                GROUP BY report_run_id, report_stream_id, customer_id, commcell_id, executed_at, run_sequence, imported_at
                ORDER BY executed_at DESC, imported_at DESC
                """,
                tuple(parameters),
            ).fetchall()
        return [dict(row) for row in rows]

    def touch_artifact_access(self, artifact_id: str, accessed_at: str) -> None:
        self.ensure_schema()
        with self._connect() as connection:
            connection.execute(
                "UPDATE artifacts SET last_accessed_at = ? WHERE artifact_id = ?",
                (accessed_at, artifact_id),
            )
            connection.commit()

    def set_active_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        self.ensure_schema()
        record = self.get_artifact(artifact_id)
        if record is None:
            return None
        with self._connect() as connection:
            connection.execute("BEGIN")
            self._deactivate_scope(
                connection,
                artifact_type=record.artifact_type,
                customer_id=record.customer_id,
                commcell_id=record.commcell_id,
                source_type=record.source_type,
                engagement_id=record.engagement_id,
                report_stream_id=record.report_stream_id,
            )
            connection.execute(
                "UPDATE artifacts SET is_active = 1 WHERE artifact_id = ?",
                (artifact_id,),
            )
            connection.commit()
        return self.get_artifact(artifact_id)

    def export_registry(self, artifact_type: str | None = None) -> dict[str, Any]:
        records = self.list_artifacts(artifact_type=artifact_type)
        return {
            "registry_path": str(self.path),
            "artifact_type": artifact_type,
            "record_count": len(records),
            "records": [record.to_dict() for record in records],
            "import_runs": [run.to_dict() for run in self.list_import_runs()],
        }

    def write_export_json(
        self,
        export_path: Path,
        *,
        artifact_type: str | None = None,
    ) -> Path:
        payload = self.export_registry(artifact_type=artifact_type)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        import json

        export_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return export_path

    def find_recoverable_artifact(
        self,
        artifact_type: str,
        *,
        customer_id: str | None = None,
        commcell_id: str | None = None,
        source_type: str | None = None,
        engagement_id: str | None = None,
        report_stream_id: str | None = None,
    ) -> ArtifactRecord | None:
        records = self.list_artifacts_for_scope(
            artifact_type,
            customer_id=customer_id,
            commcell_id=commcell_id,
            source_type=source_type,
            engagement_id=engagement_id,
            report_stream_id=report_stream_id,
            descending=True,
        )
        for record in records:
            if Path(record.file_path).exists():
                return record
        return None

    @staticmethod
    def _artifact_from_row(row: sqlite3.Row) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=str(row["artifact_id"]),
            import_run_id=str(row["import_run_id"]),
            artifact_type=str(row["artifact_type"]),
            source_type=str(row["source_type"]),
            source_file=row["source_file"],
            file_path=str(row["file_path"]),
            customer_id=str(row["customer_id"]),
            commcell_id=str(row["commcell_id"]),
            engagement_id=row["engagement_id"],
            report_stream_id=row["report_stream_id"],
            report_run_id=row["report_run_id"],
            imported_at=str(row["imported_at"]),
            executed_at=row["executed_at"],
            run_sequence=row["run_sequence"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            last_accessed_at=row["last_accessed_at"],
            retention_policy=row["retention_policy"],
            imported_by=row["imported_by"],
            import_method=row["import_method"],
            source_metadata=json.loads(row["source_metadata"] or "{}"),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _deactivate_scope(
        self,
        connection: sqlite3.Connection,
        *,
        artifact_type: str,
        customer_id: str | None,
        commcell_id: str | None,
        source_type: str | None,
        engagement_id: str | None,
        report_stream_id: str | None,
    ) -> None:
        where_sql, parameters = self._scope_where_clause(
            artifact_type=artifact_type,
            customer_id=customer_id,
            commcell_id=commcell_id,
            source_type=source_type,
            engagement_id=engagement_id,
            report_stream_id=report_stream_id,
        )
        connection.execute(
            f"""
            UPDATE artifacts
            SET is_active = 0
            WHERE artifact_id IN (
                SELECT a.artifact_id
                FROM artifacts a
                JOIN import_runs i ON i.import_run_id = a.import_run_id
                WHERE {where_sql}
            )
            """,
            parameters,
        )

    @staticmethod
    def _scope_where_clause(
        *,
        artifact_type: str,
        customer_id: str | None = None,
        commcell_id: str | None = None,
        source_type: str | None = None,
        engagement_id: str | None = None,
        report_stream_id: str | None = None,
    ) -> tuple[str, tuple[object, ...]]:
        clauses = ["a.artifact_type = ?"]
        parameters: list[object] = [artifact_type]

        if customer_id is not None:
            clauses.append("i.customer_id = ?")
            parameters.append(customer_id)
        if commcell_id is not None:
            clauses.append("i.commcell_id = ?")
            parameters.append(commcell_id)
        if source_type is not None:
            clauses.append("a.source_type = ?")
            parameters.append(source_type)
        if engagement_id is None:
            clauses.append("i.engagement_id IS NULL")
        else:
            clauses.append("i.engagement_id = ?")
            parameters.append(engagement_id)
        if report_stream_id is None:
            clauses.append("i.report_stream_id IS NULL")
        else:
            clauses.append("i.report_stream_id = ?")
            parameters.append(report_stream_id)

        return " AND ".join(clauses), tuple(parameters)

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing_columns = {str(row[1]) for row in rows}
        if column_name in existing_columns:
            return
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )
