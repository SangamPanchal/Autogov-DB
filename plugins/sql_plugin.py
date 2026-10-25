import logging
import re
import sqlite3
from typing import List, Tuple, Any
from tabulate import tabulate

logger = logging.getLogger("AutoGovDB.SQLPlugin")


class DatabasePlugin:
    FORBIDDEN_KEYWORDS_PATTERN = re.compile(
        r"\b(DROP|DELETE|UPDATE|ALTER|INSERT|TRUNCATE|REPLACE|GRANT|REVOKE|ATTACH|DETACH|PRAGMA)\b",
        re.IGNORECASE,
    )

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize_database()

    def _initialize_database(self) -> None:
        cursor = self._conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS infra_nodes (
                node_id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                role TEXT NOT NULL,
                region TEXT NOT NULL,
                status TEXT NOT NULL,
                cpu_utilization REAL NOT NULL,
                memory_utilization REAL NOT NULL,
                last_heartbeat_utc TEXT NOT NULL
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target_node_id TEXT,
                severity TEXT NOT NULL,
                details TEXT NOT NULL,
                FOREIGN KEY (target_node_id) REFERENCES infra_nodes (node_id)
            );
            """
        )

        cursor.execute("SELECT COUNT(*) FROM infra_nodes;")
        if cursor.fetchone()[0] == 0:
            infra_seed: List[Tuple[Any, ...]] = [
                ("node-us-east-01", "prd-k8s-wrk-01.corp", "worker", "us-east-1", "healthy", 42.5, 61.2, "2026-10-25T14:00:00Z"),
                ("node-us-east-02", "prd-k8s-wrk-02.corp", "worker", "us-east-1", "degraded", 94.8, 89.1, "2026-10-25T13:58:12Z"),
                ("node-eu-west-01", "prd-k8s-ctl-01.corp", "control-plane", "eu-west-1", "healthy", 31.0, 54.0, "2026-10-25T14:00:02Z"),
                ("node-eu-west-02", "prd-k8s-wrk-03.corp", "worker", "eu-west-1", "degraded", 88.3, 95.4, "2026-10-25T13:55:40Z"),
                ("node-ap-south-01", "prd-k8s-wrk-04.corp", "worker", "ap-south-1", "healthy", 50.2, 63.8, "2026-10-25T14:00:01Z"),
                ("node-ap-south-02", "prd-k8s-wrk-05.corp", "worker", "ap-south-1", "offline", 0.0, 0.0, "2026-10-25T11:20:00Z"),
                ("node-us-west-01", "prd-k8s-wrk-06.corp", "worker", "us-west-2", "degraded", 91.2, 84.7, "2026-10-25T13:59:10Z"),
            ]
            cursor.executemany(
                """
                INSERT INTO infra_nodes (
                    node_id, hostname, role, region, status,
                    cpu_utilization, memory_utilization, last_heartbeat_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                infra_seed,
            )

            audit_seed: List[Tuple[Any, ...]] = [
                ("2026-10-25T13:50:00Z", "sarah.dev@corp.internal", "DEPLOY_SERVICE", "node-us-east-02", "WARNING", "Deployed v2.1.0-unstable with runaway memory leak"),
                ("2026-10-25T13:45:00Z", "alex.infra@corp.internal", "APPLY_SYSCTL", "node-eu-west-02", "CRITICAL", "Applied vm.max_map_count misconfiguration"),
                ("2026-10-25T13:52:00Z", "ci-runner-bot@corp.internal", "RUN_BENCHMARK", "node-us-west-01", "HIGH", "Triggered high-concurrency load test without throttling"),
            ]
            cursor.executemany(
                """
                INSERT INTO audit_logs (
                    timestamp_utc, actor, action, target_node_id, severity, details
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                audit_seed,
            )
            self._conn.commit()

    def get_schema(self) -> str:
        """Retrieves SQLite database DDL CREATE TABLE statements for all tables."""
        print("\n>>> [TOOL CALL]: get_schema() invoked")
        cursor = self._conn.cursor()
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        rows = cursor.fetchall()
        return "\n\n".join([f"-- Table: {r['name']}\n{r['sql']};" for r in rows if r["sql"]])

    def execute_safe_query(self, query: str) -> str:
        """Executes a verified read-only SELECT query against the SQLite database."""
        print(f"\n>>> [TOOL CALL]: execute_safe_query({query})")
        if not query or not query.strip():
            return "Governance Error: Empty query provided."

        cleaned = query.strip()
        no_comments = re.sub(r"(--[^\r\n]*)|(/\*[\s\S]*?\*/)", " ", cleaned).strip()
        statements = [s.strip() for s in no_comments.split(";") if s.strip()]

        if len(statements) > 1:
            return "Governance Violation: Multi-statement queries are prohibited."

        stmt = statements[0]
        if not re.match(r"^(SELECT|WITH)\b", stmt, re.IGNORECASE):
            return "Governance Violation: Only read-only SELECT queries are permitted."

        forbidden = self.FORBIDDEN_KEYWORDS_PATTERN.search(stmt)
        if forbidden:
            return f"Governance Violation: Forbidden keyword detected: '{forbidden.group(1).upper()}'."

        try:
            cursor = self._conn.cursor()
            cursor.execute(stmt)
            rows = cursor.fetchall()
            if not rows:
                return "0 rows returned."
            return tabulate([tuple(r) for r in rows], headers=rows[0].keys(), tablefmt="github")
        except sqlite3.Error as e:
            return f"SQL Execution Error: {e}"

    def close(self) -> None:
        if self._conn:
            self._conn.close()
