import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "incidents.db"

FIELD_TABLES = [
    "impacted_region",
    "impact_type",
    "audience",
    "observation_method",
    "root_cause",
    "severity",
    "application",
    "team",
    "year",
    "quarter",
]


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Create field tables
    for table in FIELD_TABLES:
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """)

    # Create raw Jira data table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_jira_data (
            jira_ticket_id TEXT PRIMARY KEY,
            project TEXT,
            issue_type TEXT,
            summary TEXT,
            description TEXT,
            status TEXT,
            priority TEXT,
            assignee TEXT,
            reporter TEXT,
            created TEXT,
            updated TEXT,
            resolved TEXT,
            labels TEXT,
            components TEXT,
            raw_json TEXT,
            imported INTEGER DEFAULT 0
        )
    """)

    # Create incidents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jira_ticket TEXT,
            summary TEXT,
            downtime_mins INTEGER,
            impacted_region_id INTEGER,
            impact_type_id INTEGER,
            audience_id INTEGER,
            observation_method_id INTEGER,
            root_cause_id INTEGER,
            severity_id INTEGER,
            application_id INTEGER,
            team_id INTEGER,
            year_id INTEGER,
            quarter_id INTEGER,
            FOREIGN KEY (impacted_region_id) REFERENCES impacted_region(id),
            FOREIGN KEY (impact_type_id) REFERENCES impact_type(id),
            FOREIGN KEY (audience_id) REFERENCES audience(id),
            FOREIGN KEY (observation_method_id) REFERENCES observation_method(id),
            FOREIGN KEY (root_cause_id) REFERENCES root_cause(id),
            FOREIGN KEY (severity_id) REFERENCES severity(id),
            FOREIGN KEY (application_id) REFERENCES application(id),
            FOREIGN KEY (team_id) REFERENCES team(id),
            FOREIGN KEY (year_id) REFERENCES year(id),
            FOREIGN KEY (quarter_id) REFERENCES quarter(id)
        )
    """)

    # Migration: Add imported column if it doesn't exist
    cursor.execute("PRAGMA table_info(raw_jira_data)")
    columns = [col[1] for col in cursor.fetchall()]
    if "imported" not in columns:
        cursor.execute("ALTER TABLE raw_jira_data ADD COLUMN imported INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


def add_field_value(table: str, name: str) -> int | None:
    if table not in FIELD_TABLES:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_field_values(table: str) -> list[tuple[int, str]]:
    if table not in FIELD_TABLES:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT id, name FROM {table} ORDER BY name")
    results = cursor.fetchall()
    conn.close()
    return results


def delete_field_value(table: str, value_id: int) -> bool:
    if table not in FIELD_TABLES:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {table} WHERE id = ?", (value_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def add_incident(
    jira_ticket: str,
    summary: str,
    downtime_mins: int,
    field_values: dict[str, int | None],
) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO incidents (
            jira_ticket, summary, downtime_mins,
            impacted_region_id, impact_type_id, audience_id,
            observation_method_id, root_cause_id, severity_id,
            application_id, team_id, year_id, quarter_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            jira_ticket,
            summary,
            downtime_mins,
            field_values.get("impacted_region"),
            field_values.get("impact_type"),
            field_values.get("audience"),
            field_values.get("observation_method"),
            field_values.get("root_cause"),
            field_values.get("severity"),
            field_values.get("application"),
            field_values.get("team"),
            field_values.get("year"),
            field_values.get("quarter"),
        ),
    )
    conn.commit()
    incident_id = cursor.lastrowid
    conn.close()
    return incident_id


def get_incidents() -> list[dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            i.id, i.jira_ticket, i.summary, i.downtime_mins,
            ir.name as impacted_region,
            it.name as impact_type,
            a.name as audience,
            om.name as observation_method,
            rc.name as root_cause,
            s.name as severity,
            app.name as application,
            t.name as team,
            y.name as year,
            q.name as quarter
        FROM incidents i
        LEFT JOIN impacted_region ir ON i.impacted_region_id = ir.id
        LEFT JOIN impact_type it ON i.impact_type_id = it.id
        LEFT JOIN audience a ON i.audience_id = a.id
        LEFT JOIN observation_method om ON i.observation_method_id = om.id
        LEFT JOIN root_cause rc ON i.root_cause_id = rc.id
        LEFT JOIN severity s ON i.severity_id = s.id
        LEFT JOIN application app ON i.application_id = app.id
        LEFT JOIN team t ON i.team_id = t.id
        LEFT JOIN year y ON i.year_id = y.id
        LEFT JOIN quarter q ON i.quarter_id = q.id
        ORDER BY i.id DESC
        """
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def upsert_raw_jira_data(issues: list[dict]) -> int:
    """Insert or update raw Jira data. Returns count of upserted records."""
    conn = get_connection()
    cursor = conn.cursor()
    count = 0
    for issue in issues:
        cursor.execute(
            """
            INSERT INTO raw_jira_data (
                jira_ticket_id, project, issue_type, summary, description,
                status, priority, assignee, reporter, created, updated,
                resolved, labels, components, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(jira_ticket_id) DO UPDATE SET
                project = excluded.project,
                issue_type = excluded.issue_type,
                summary = excluded.summary,
                description = excluded.description,
                status = excluded.status,
                priority = excluded.priority,
                assignee = excluded.assignee,
                reporter = excluded.reporter,
                created = excluded.created,
                updated = excluded.updated,
                resolved = excluded.resolved,
                labels = excluded.labels,
                components = excluded.components,
                raw_json = excluded.raw_json
            """,
            (
                issue.get("jira_ticket_id"),
                issue.get("project"),
                issue.get("issue_type"),
                issue.get("summary"),
                issue.get("description"),
                issue.get("status"),
                issue.get("priority"),
                issue.get("assignee"),
                issue.get("reporter"),
                issue.get("created"),
                issue.get("updated"),
                issue.get("resolved"),
                issue.get("labels"),
                issue.get("components"),
                issue.get("raw_json"),
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def get_raw_jira_data() -> list[dict]:
    """Get all raw Jira data."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM raw_jira_data ORDER BY updated DESC"
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def delete_raw_jira_data(jira_ticket_id: str) -> bool:
    """Delete a raw Jira data record."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM raw_jira_data WHERE jira_ticket_id = ?", (jira_ticket_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def set_jira_imported(jira_ticket_id: str, imported: bool) -> bool:
    """Set the imported status of a raw Jira data record."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE raw_jira_data SET imported = ? WHERE jira_ticket_id = ?",
        (1 if imported else 0, jira_ticket_id),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def get_unimported_jira_data() -> list[dict]:
    """Get raw Jira data that hasn't been imported yet."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM raw_jira_data WHERE imported = 0 ORDER BY updated DESC"
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results
