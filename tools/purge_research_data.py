# -*- coding: utf-8 -*-
"""Permanently remove all research-domain data while preserving accounts/configuration."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config


CONFIRMATION = "DELETE-ALL-RESEARCH"

DOMAIN_TABLES = (
    "matches",
    "document_pages",
    "document_segments",
    "reference_metadata_history",
    "documents",
    "review_decision_history",
    "report_snapshots",
    "reports",
    "thesis_parts",
    "theses",
    "scan_batch_items",
    "research_files",
    "research",
    "scan_batches",
    "scan_jobs",
    "queue_jobs",
    "job_records",
    "distributed_locks",
    "index_state_records",
    "corpus_changesets",
    "reference_corpus_versions",
)

DOMAIN_AUDIT_CATEGORIES = (
    "batch",
    "report",
    "reference",
    "research",
    "review",
    "scan",
    "thesis",
)


def _assert_child(path: Path, parent: Path) -> Path:
    resolved = path.resolve()
    parent_resolved = parent.resolve()
    if resolved == parent_resolved or parent_resolved not in resolved.parents:
        raise RuntimeError(f"Unsafe purge target: {resolved}")
    return resolved


def _clear_directory(path: Path, parent: Path) -> int:
    target = _assert_child(path, parent)
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)
        return 0

    removed = 0
    for child in target.iterdir():
        child_resolved = _assert_child(child, target)
        if child_resolved.is_dir():
            shutil.rmtree(child_resolved)
        else:
            child_resolved.unlink()
        removed += 1
    return removed


def purge_database(db_path: Path) -> dict[str, int]:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    deleted: dict[str, int] = {}
    connection = sqlite3.connect(str(db_path), timeout=60)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        connection.execute("BEGIN IMMEDIATE")
        for table in DOMAIN_TABLES:
            if table not in existing:
                continue
            before = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            connection.execute(f'DELETE FROM "{table}"')
            deleted[table] = int(before)

        if "audit_logs" in existing:
            placeholders = ",".join("?" for _ in DOMAIN_AUDIT_CATEGORIES)
            before = connection.execute(
                f"SELECT COUNT(*) FROM audit_logs WHERE category IN ({placeholders})",
                DOMAIN_AUDIT_CATEGORIES,
            ).fetchone()[0]
            connection.execute(
                f"DELETE FROM audit_logs WHERE category IN ({placeholders})",
                DOMAIN_AUDIT_CATEGORIES,
            )
            deleted["audit_logs(domain)"] = int(before)

        if "reference_sequences" in existing:
            before = connection.execute(
                "SELECT COUNT(*) FROM reference_sequences "
                "WHERE namespace IN ('research', 'reference_corpus', 'thesis')"
            ).fetchone()[0]
            connection.execute(
                "DELETE FROM reference_sequences "
                "WHERE namespace IN ('research', 'reference_corpus', 'thesis')"
            )
            deleted["reference_sequences(domain)"] = int(before)

        if "sqlite_sequence" in existing:
            placeholders = ",".join("?" for _ in DOMAIN_TABLES)
            connection.execute(
                f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})",
                DOMAIN_TABLES,
            )
        connection.commit()
        connection.execute("VACUUM")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db_path) + suffix)
        if sidecar.exists():
            sidecar.unlink()
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit("Refusing purge: confirmation phrase does not match")
    if not str(config.DATABASE_URL).startswith("sqlite"):
        raise SystemExit("This maintenance command only supports the local SQLite deployment")

    data_root = Path(config.DATA_ROOT).resolve()
    db_path = _assert_child(Path(config.DEFAULT_SQLITE_PATH), data_root)
    storage_root = _assert_child(Path(config.STORAGE_ROOT), data_root)
    backup_root = _assert_child(Path(config.BACKUP_DIR), data_root)

    deleted = purge_database(db_path)
    cleared = {
        "storage_items": _clear_directory(storage_root, data_root),
        "backup_items": _clear_directory(backup_root, data_root),
    }
    Path(config.TEMP_UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(config.SEMANTIC_CACHE_DIR).mkdir(parents=True, exist_ok=True)
    Path(config.OCR_CACHE_DIR).mkdir(parents=True, exist_ok=True)
    (storage_root / "document_previews").mkdir(parents=True, exist_ok=True)

    print("Database rows removed:")
    for table, count in deleted.items():
        print(f"  {table}: {count}")
    print("Filesystem items removed:")
    for name, count in cleared.items():
        print(f"  {name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
