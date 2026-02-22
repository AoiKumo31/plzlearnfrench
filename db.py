import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "french_coach.db")

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()

def init_db():
    with get_db() as db:
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                streak INTEGER DEFAULT 0,
                difficulty_level INTEGER DEFAULT 1,
                state TEXT DEFAULT '🟢',
                timezone TEXT DEFAULT 'UTC',
                learning_focus TEXT DEFAULT 'general',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        db.execute('''
            CREATE TABLE IF NOT EXISTS daily_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                date DATE,
                task_assigned TEXT,
                user_response TEXT,
                feedback_given TEXT,
                score INTEGER,
                adaptation_decision TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES users(chat_id)
            )
        ''')

def register_user(chat_id: int, username: str) -> bool:
    """Register a new user if they don't exist. Returns True if new user created."""
    with get_db() as db:
        user = db.execute('SELECT * FROM users WHERE chat_id = ?', (chat_id,)).fetchone()
        if not user:
            db.execute(
                'INSERT INTO users (chat_id, username, state) VALUES (?, ?, ?)',
                (chat_id, username, '🟢')
            )
            return True
        return False

def get_user(chat_id: int) -> dict:
    """Get user data by chat ID."""
    with get_db() as db:
        user = db.execute('SELECT * FROM users WHERE chat_id = ?', (chat_id,)).fetchone()
        return dict(user) if user else None

def update_user_state(chat_id: int, streak: int, difficulty_level: int, state: str):
    """Update user progress counters."""
    with get_db() as db:
        db.execute(
            'UPDATE users SET streak = ?, difficulty_level = ?, state = ? WHERE chat_id = ?',
            (streak, difficulty_level, state, chat_id)
        )

def log_daily_task(chat_id: int, task: str):
    """Log that a task was assigned today."""
    today = datetime.now().date().isoformat()
    with get_db() as db:
        db.execute(
            'INSERT INTO daily_logs (chat_id, date, task_assigned) VALUES (?, ?, ?)',
            (chat_id, today, task)
        )

def update_daily_log_response(chat_id: int, response: str, feedback: str, score: int, decision: str):
    """Update today's task log with the user's response and evaluation."""
    today = datetime.now().date().isoformat()
    with get_db() as db:
        # Update the most recent log for today
        db.execute('''
            UPDATE daily_logs 
            SET user_response = ?, feedback_given = ?, score = ?, adaptation_decision = ?
            WHERE chat_id = ? AND date = ? 
            ORDER BY id DESC LIMIT 1
        ''', (response, feedback, score, decision, chat_id, today))

def get_all_users() -> list:
    """Get a list of all chat_ids configured."""
    with get_db() as db:
        users = db.execute('SELECT chat_id FROM users').fetchall()
        return [usr['chat_id'] for usr in users]

if __name__ == '__main__':
    init_db()
    print("Database initialized.")
