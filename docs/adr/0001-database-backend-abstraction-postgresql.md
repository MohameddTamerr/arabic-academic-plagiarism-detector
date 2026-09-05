# ADR 0001: Database Backend Abstraction & PostgreSQL Migration Strategy

## Context & Problem Statement
The Arabic Academic Plagiarism Detector was originally built as a single-node, air-gapped institutional pilot build (v1.0.0-rc2) backed by SQLite in WAL mode. While SQLite is suitable for standalone desktop/pilot usage (supporting up to 2,800+ research records and 100+ corpus versions with zero concurrency issues), the Ministry-Scale Roadmap requires preparing the architecture to eventually support:
- Multiple administrative departments
- High-concurrency simultaneous user scans and reviews
- Scaled metadata storage for hundreds of thousands of research papers
- Multi-node application server deployments on the internal ministry LAN

However, the solution must strictly preserve:
- 100% on-premises, air-gapped deployment (zero internet, zero cloud dependencies, zero external APIs).
- Full backwards compatibility with SQLite for development, automated CI testing, and standalone desktop operation.
- Complete data integrity (report hash validation, audit history preservation, corpus governance, and RBAC security).

## Decision
1. **Dual-Backend Capability**: Abstract the database connection layer through SQLAlchemy, controlled explicitly via `DB_BACKEND` (`sqlite` | `postgresql`).
2. **PostgreSQL as Ministry Production Standard**: PostgreSQL (v14+) running exclusively within the internal ministry LAN becomes the target backend for multi-department deployments.
3. **Explicit Configuration**: The application will never silently auto-switch backends. If PostgreSQL is configured but unreachable, the application fails closed safely.
4. **Separation of Metadata vs Raw Documents**: PostgreSQL stores structured relational metadata (researches, files, reports, audit logs, corpus versions, users, RBAC). Raw documents (PDF/DOCX) remain in secure filesystem storage and will transition to enterprise object storage in Prompt 2.
5. **Safe Offline Migration Tool**: A standalone CLI tool (`tools/migrate_sqlite_to_postgresql.py`) provides preflight validation, ordered schema migration, record count verification, and report hash validation, treating the source SQLite database as strictly read-only.

## Consequences
- **Positive**:
  - Unlocks concurrent write scalability via PostgreSQL MVCC and row-level locking.
  - Enables multiple application servers to share a single authoritative database over LAN.
  - Zero disruption to existing SQLite tests and development workflow.
  - Preserves offline security and compliance guarantees.
- **Negative / Operational Considerations**:
  - Requires database administrator provisioning of PostgreSQL on the local ministry network.
  - Requires local connection pool management and transaction discipline to prevent connection exhaustion.
