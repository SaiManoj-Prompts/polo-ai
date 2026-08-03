"""Deterministic tests for db_manager.py — schema creation, save/retrieve,
clear history, and database integrity."""

import os
import sqlite3
import tempfile
import unittest

import db_manager


class TestDbManager(unittest.TestCase):
    """Every test uses a fresh temporary database, cleaned up afterwards."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._original_db_file = db_manager.DB_FILE
        db_manager.DB_FILE = self.db_path
        db_manager.init_db()

    def tearDown(self):
        db_manager.DB_FILE = self._original_db_file
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    # ── Schema initialization ────────────────────────────────────────────

    def test_init_creates_required_tables(self):
        """init_db must create the tasks and findings tables."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        conn.close()
        self.assertIn("tasks", tables)
        self.assertIn("findings", tables)

    def test_init_is_idempotent(self):
        """Calling init_db a second time must not raise."""
        db_manager.init_db()

    def test_tasks_table_has_queries_column(self):
        """The queries column must exist (ALTER TABLE migration)."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(tasks)")
        columns = {info[1] for info in cur.fetchall()}
        conn.close()
        self.assertIn("queries", columns)

    # ── Save and retrieve ────────────────────────────────────────────────

    def test_save_and_retrieve_roundtrip(self):
        """A saved task with findings must be retrievable with all fields."""
        findings = [{"title": "T1", "url": "http://a.com", "snippet": "s1"}]
        task_id = db_manager.save_task(
            "test query", "Completed", findings, queries=["q1"]
        )
        self.assertIsInstance(task_id, int)

        tasks = db_manager.get_all_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["query"], "test query")
        self.assertEqual(tasks[0]["status"], "Completed")
        self.assertEqual(len(tasks[0]["findings"]), 1)
        self.assertEqual(tasks[0]["findings"][0]["title"], "T1")

    def test_ordering_newest_first(self):
        """get_all_tasks must return tasks newest-first by created_at."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tasks (query, status, created_at) VALUES (?, ?, ?)",
            ("first", "Completed", "2024-01-01 10:00:00"),
        )
        cur.execute(
            "INSERT INTO tasks (query, status, created_at) VALUES (?, ?, ?)",
            ("second", "Completed", "2024-01-02 10:00:00"),
        )
        conn.commit()
        conn.close()

        tasks = db_manager.get_all_tasks()
        self.assertEqual(tasks[0]["query"], "second")
        self.assertEqual(tasks[1]["query"], "first")

    # ── Safe history clearing ────────────────────────────────────────────

    def test_clear_returns_deleted_count(self):
        """clear_task_history must return the number of deleted tasks."""
        db_manager.save_task("q1", "Completed", [])
        db_manager.save_task("q2", "Completed", [])
        self.assertEqual(db_manager.clear_task_history(), 2)

    def test_clear_removes_all_findings(self):
        """After clearing, both the tasks and findings tables must be empty."""
        db_manager.save_task("q", "Completed", [
            {"title": "T1", "url": "u1", "snippet": "s1"},
            {"title": "T2", "url": "u2", "snippet": "s2"},
        ])
        db_manager.clear_task_history()

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM findings")
        self.assertEqual(cur.fetchone()[0], 0)
        cur.execute("SELECT COUNT(*) FROM tasks")
        self.assertEqual(cur.fetchone()[0], 0)
        conn.close()

    def test_clear_empty_database_succeeds(self):
        """Clearing when history is already empty must not raise."""
        count = db_manager.clear_task_history()
        self.assertEqual(count, 0)

    def test_clear_preserves_schema_for_new_data(self):
        """After clearing, the database must still accept new saves."""
        db_manager.save_task(
            "q", "Completed", [{"title": "T", "url": "u", "snippet": "s"}]
        )
        db_manager.clear_task_history()

        task_id = db_manager.save_task("new query", "Completed", [])
        self.assertIsInstance(task_id, int)
        tasks = db_manager.get_all_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["query"], "new query")


if __name__ == "__main__":
    unittest.main()
