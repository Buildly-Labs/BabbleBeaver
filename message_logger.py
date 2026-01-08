import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any

"""
Log messages sent through the chatbot and allow for retrievening them later.
This is implemented in SQLListe for testing purposes.  Would be better to implement in 
a MongoDB or similar document-based database for scalability.

TODO: Create simple analytics for the chatbot, such as the number of messages sent, the most common messages, etc.
"""


class MessageLogger:
    def __init__(self, db_path="chatbot.db"):
        self.db_path = db_path
        self._create_table()

    def _create_table(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    provider TEXT DEFAULT NULL
                )
            """)
            # Add columns if they don't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE messages ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute("ALTER TABLE messages ADD COLUMN provider TEXT DEFAULT NULL")
            except sqlite3.OperationalError:
                pass  # Column already exists

    def log_message(self, message: str, type: str, provider: str = None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO messages (message, type, provider, timestamp) VALUES (?, ?, ?, ?)",
                (message, type, provider, datetime.now().isoformat())
            )
            conn.commit()

    def retrieve_messages(
        self,
        limit: int = 100,
        offset: int = 0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        provider: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve messages with optional filtering."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT id, type, message, timestamp, provider FROM messages WHERE 1=1"
            params = []
            
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)
            if provider:
                query += " AND provider = ?"
                params.append(provider)
            
            query += " ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_message_count(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        provider: Optional[str] = None
    ) -> int:
        """Get total count of messages with optional filtering."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = "SELECT COUNT(*) FROM messages WHERE 1=1"
            params = []
            
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)
            if provider:
                query += " AND provider = ?"
                params.append(provider)
            
            cursor.execute(query, params)
            return cursor.fetchone()[0]

    def export_for_fine_tuning(
        self,
        format: str = "jsonl",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        provider: Optional[str] = None
    ) -> str:
        """Export messages in format suitable for fine-tuning."""
        import json
        
        messages = self.retrieve_messages(
            limit=10000,  # Get all for export
            start_date=start_date,
            end_date=end_date,
            provider=provider
        )
        
        if format == "jsonl":
            lines = []
            for msg in messages:
                lines.append(json.dumps(msg))
            return "\n".join(lines)
        else:
            return json.dumps(messages, indent=2)

    def get_analytics(self) -> Dict[str, Any]:
        """Get analytics about logged messages."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Total messages
            cursor.execute("SELECT COUNT(*) FROM messages")
            total = cursor.fetchone()[0]
            
            # Messages by type
            cursor.execute("SELECT type, COUNT(*) FROM messages GROUP BY type")
            by_type = dict(cursor.fetchall())
            
            # Messages by provider
            cursor.execute("SELECT provider, COUNT(*) FROM messages WHERE provider IS NOT NULL GROUP BY provider")
            by_provider = dict(cursor.fetchall())
            
            # Recent activity (last 7 days)
            cursor.execute("""
                SELECT DATE(timestamp) as date, COUNT(*) as count 
                FROM messages 
                WHERE timestamp >= DATE('now', '-7 days')
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
            """)
            recent = [{'date': row[0], 'count': row[1]} for row in cursor.fetchall()]
            
            return {
                'total_messages': total,
                'by_type': by_type,
                'by_provider': by_provider,
                'recent_activity': recent
            }
