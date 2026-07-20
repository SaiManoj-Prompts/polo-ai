import sqlite3
from datetime import datetime
import os

DB_FILE = "polo_ai.db"

def init_db():
    """Initialize the database and create tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            title TEXT,
            url TEXT,
            snippet TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def save_task(query: str, status: str, findings: list) -> int:
    """
    Save a task and its findings to the database.
    Returns the ID of the newly created task.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT INTO tasks (query, status, created_at)
        VALUES (?, ?, ?)
    ''', (query, status, created_at))
    
    task_id = cursor.lastrowid
    
    for finding in findings:
        cursor.execute('''
            INSERT INTO findings (task_id, title, url, snippet)
            VALUES (?, ?, ?, ?)
        ''', (task_id, finding.get('title', ''), finding.get('url', ''), finding.get('snippet', '')))
        
    conn.commit()
    conn.close()
    
    return task_id

def get_all_tasks():
    """
    Retrieve all tasks and their associated findings, ordered from newest to oldest.
    Returns a list of dicts.
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # To get dict-like rows
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, query, status, created_at
        FROM tasks
        ORDER BY created_at DESC
    ''')
    
    tasks_rows = cursor.fetchall()
    tasks_list = []
    
    for row in tasks_rows:
        task_dict = dict(row)
        
        # Get findings for this task
        cursor.execute('''
            SELECT title, url, snippet
            FROM findings
            WHERE task_id = ?
        ''', (task_dict['id'],))
        
        findings_rows = cursor.fetchall()
        task_dict['findings'] = [dict(f) for f in findings_rows]
        
        tasks_list.append(task_dict)
        
    conn.close()
    return tasks_list
