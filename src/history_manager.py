"""
History Manager - Session analytics and history tracking.

This module provides comprehensive session history tracking, statistics,
and export functionality using SQLite for efficient querying.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import os

from logger import AppLogger


class HistoryManager:
    """
    Manages session history and analytics.

    Features:
    - Records completed sessions in SQLite database
    - Provides searchable session history
    - Calculates statistics per client and overall
    - Exports data to Excel and CSV
    """

    def __init__(self, profile_manager):
        """
        Initialize HistoryManager.

        Args:
            profile_manager: ProfileManager instance for accessing base paths
        """
        self.profile_manager = profile_manager
        self.logger = AppLogger.get_logger(self.__class__.__name__)

        # Database location
        analytics_dir = profile_manager.base_path / "analytics"
        analytics_dir.mkdir(exist_ok=True)

        self.db_path = analytics_dir / "analytics.db"

        # Initialize database
        self._init_database()

        self.logger.info(f"HistoryManager initialized with database: {self.db_path}")

    def _init_database(self):
        """Initialize SQLite database with schema."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    client_id TEXT NOT NULL,
                    client_name TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    pc_name TEXT,
                    user_name TEXT,
                    total_orders INTEGER DEFAULT 0,
                    completed_orders INTEGER DEFAULT 0,
                    total_items INTEGER DEFAULT 0,
                    unique_skus INTEGER DEFAULT 0,
                    errors_count INTEGER DEFAULT 0,
                    warnings_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # SKU statistics per session
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    sku TEXT NOT NULL,
                    product_name TEXT,
                    quantity INTEGER NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)

            # Create indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_client
                ON sessions(client_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_date
                ON sessions(completed_at)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_user
                ON sessions(user_name)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_skus_session
                ON session_skus(session_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_skus_sku
                ON session_skus(sku)
            """)

            conn.commit()
            conn.close()

            self.logger.info("Database initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}", exc_info=True)
            raise

    def record_completed_session(
        self,
        session_dir: Path,
        client_id: str,
        client_name: str,
        packing_state: Dict,
        start_time: datetime,
        end_time: datetime
    ) -> bool:
        """
        Record a completed session with full statistics.

        Args:
            session_dir: Path to session directory
            client_id: Client identifier
            client_name: Client display name
            packing_state: Dictionary of order packing state
            start_time: Session start datetime
            end_time: Session end datetime

        Returns:
            True if recorded successfully, False otherwise
        """
        try:
            session_id = session_dir.name

            # Calculate statistics from packing_state
            stats = self._calculate_statistics(packing_state)

            duration_seconds = int((end_time - start_time).total_seconds())

            # Prepare session metadata
            session_data = {
                'session_id': session_id,
                'client_id': client_id,
                'client_name': client_name,
                'started_at': start_time.isoformat(),
                'completed_at': end_time.isoformat(),
                'duration_seconds': duration_seconds,
                'duration_formatted': self._format_duration(duration_seconds),
                'pc_name': os.environ.get('COMPUTERNAME', 'Unknown'),
                'user_name': self._get_username(),
                'statistics': {
                    'total_orders': stats['total_orders'],
                    'completed_orders': stats['completed_orders'],
                    'total_items': stats['total_items'],
                    'unique_skus': stats['unique_skus'],
                    'avg_items_per_order': stats['avg_items_per_order']
                },
                'top_skus': stats['top_skus'][:10],  # Top 10
                'errors_count': 0,
                'warnings_count': 0
            }

            # Save to JSON file in session directory
            completed_json = session_dir / "session_completed.json"
            with open(completed_json, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)

            self.logger.debug(f"Saved session metadata to {completed_json}")

            # Insert into database
            self._insert_to_database(session_data, stats['sku_details'])

            self.logger.info(f"Recorded completed session: {session_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to record session: {e}", exc_info=True)
            return False

    def _calculate_statistics(self, packing_state: Dict) -> Dict:
        """
        Calculate statistics from packing state.

        Args:
            packing_state: Dictionary of order packing states

        Returns:
            Dictionary with calculated statistics
        """
        total_orders = len(packing_state)
        completed_orders = 0
        total_items = 0
        sku_quantities = {}  # sku -> {name, quantity}

        for order_number, order_data in packing_state.items():
            order_complete = True

            for sku, sku_data in order_data.items():
                packed = sku_data.get('packed', 0)
                required = sku_data.get('required', 0)
                product_name = sku_data.get('product_name', sku)

                total_items += packed

                # Track SKU quantities
                if sku not in sku_quantities:
                    sku_quantities[sku] = {
                        'name': product_name,
                        'quantity': 0
                    }
                sku_quantities[sku]['quantity'] += packed

                if packed < required:
                    order_complete = False

            if order_complete:
                completed_orders += 1

        # Sort SKUs by quantity
        top_skus = [
            {'sku': sku, 'name': data['name'], 'quantity': data['quantity']}
            for sku, data in sorted(
                sku_quantities.items(),
                key=lambda x: x[1]['quantity'],
                reverse=True
            )
        ]

        avg_items = total_items / total_orders if total_orders > 0 else 0

        return {
            'total_orders': total_orders,
            'completed_orders': completed_orders,
            'total_items': total_items,
            'unique_skus': len(sku_quantities),
            'avg_items_per_order': round(avg_items, 2),
            'top_skus': top_skus,
            'sku_details': list(sku_quantities.items())
        }

    def _insert_to_database(self, session_data: Dict, sku_details: List[Tuple]):
        """Insert session data into SQLite database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Insert session
            cursor.execute("""
                INSERT INTO sessions (
                    session_id, client_id, client_name, started_at, completed_at,
                    duration_seconds, pc_name, user_name, total_orders,
                    completed_orders, total_items, unique_skus,
                    errors_count, warnings_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_data['session_id'],
                session_data['client_id'],
                session_data['client_name'],
                session_data['started_at'],
                session_data['completed_at'],
                session_data['duration_seconds'],
                session_data['pc_name'],
                session_data['user_name'],
                session_data['statistics']['total_orders'],
                session_data['statistics']['completed_orders'],
                session_data['statistics']['total_items'],
                session_data['statistics']['unique_skus'],
                session_data.get('errors_count', 0),
                session_data.get('warnings_count', 0)
            ))

            # Insert SKU details
            for sku, data in sku_details:
                cursor.execute("""
                    INSERT INTO session_skus (session_id, sku, product_name, quantity)
                    VALUES (?, ?, ?, ?)
                """, (
                    session_data['session_id'],
                    sku,
                    data['name'],
                    data['quantity']
                ))

            conn.commit()
            conn.close()

            self.logger.debug(f"Inserted session {session_data['session_id']} to database")

        except sqlite3.IntegrityError as e:
            # Session already exists
            self.logger.warning(f"Session {session_data['session_id']} already in database: {e}")
        except Exception as e:
            self.logger.error(f"Database insertion error: {e}", exc_info=True)
            raise

    def get_session_history(
        self,
        client_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Query session history with filters.

        Args:
            client_id: Filter by client ID
            start_date: Filter by start date
            end_date: Filter by end date
            user_name: Filter by user name
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of session dictionaries sorted by completed_at descending
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Access by column name
            cursor = conn.cursor()

            # Build query with filters
            query = "SELECT * FROM sessions WHERE 1=1"
            params = []

            if client_id:
                query += " AND client_id = ?"
                params.append(client_id)

            if start_date:
                query += " AND completed_at >= ?"
                params.append(start_date.isoformat())

            if end_date:
                query += " AND completed_at <= ?"
                params.append(end_date.isoformat())

            if user_name:
                query += " AND user_name LIKE ?"
                params.append(f"%{user_name}%")

            query += " ORDER BY completed_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # Convert to dictionaries
            sessions = []
            for row in rows:
                session = dict(row)
                # Format duration
                session['duration_formatted'] = self._format_duration(session['duration_seconds'])
                sessions.append(session)

            conn.close()

            self.logger.debug(f"Retrieved {len(sessions)} sessions from history")
            return sessions

        except Exception as e:
            self.logger.error(f"Failed to get session history: {e}", exc_info=True)
            return []

    def search_sessions(
        self,
        query: str,
        search_fields: List[str] = ['client_id', 'user_name', 'pc_name']
    ) -> List[Dict]:
        """
        Full-text search across sessions.

        Args:
            query: Search query string
            search_fields: Fields to search in

        Returns:
            List of matching session dictionaries
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Build WHERE clause for search
            where_clauses = [f"{field} LIKE ?" for field in search_fields]
            where_sql = " OR ".join(where_clauses)
            params = [f"%{query}%"] * len(search_fields)

            sql = f"""
                SELECT * FROM sessions
                WHERE {where_sql}
                ORDER BY completed_at DESC
                LIMIT 100
            """

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            sessions = [dict(row) for row in rows]
            conn.close()

            self.logger.debug(f"Search '{query}' found {len(sessions)} sessions")
            return sessions

        except Exception as e:
            self.logger.error(f"Search failed: {e}", exc_info=True)
            return []

    def get_client_statistics(
        self,
        client_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get aggregated statistics for a client.

        Args:
            client_id: Client identifier
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with aggregated statistics
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Build date filters
            date_filter = ""
            params = [client_id]

            if start_date:
                date_filter += " AND completed_at >= ?"
                params.append(start_date.isoformat())

            if end_date:
                date_filter += " AND completed_at <= ?"
                params.append(end_date.isoformat())

            # Get aggregated stats
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total_sessions,
                    SUM(total_orders) as total_orders,
                    SUM(total_items) as total_items,
                    AVG(total_orders) as avg_orders_per_session,
                    AVG(duration_seconds / 60.0) as avg_duration_minutes
                FROM sessions
                WHERE client_id = ? {date_filter}
            """, params)

            row = cursor.fetchone()

            stats = {
                'total_sessions': row[0] or 0,
                'total_orders': row[1] or 0,
                'total_items': row[2] or 0,
                'avg_orders_per_session': round(row[3], 2) if row[3] else 0,
                'avg_duration_minutes': round(row[4], 2) if row[4] else 0
            }

            # Get top users
            cursor.execute(f"""
                SELECT user_name, COUNT(*) as session_count
                FROM sessions
                WHERE client_id = ? {date_filter}
                GROUP BY user_name
                ORDER BY session_count DESC
                LIMIT 5
            """, params)

            stats['top_users'] = [
                {'user_name': row[0], 'sessions': row[1]}
                for row in cursor.fetchall()
            ]

            # Get most packed SKUs
            cursor.execute(f"""
                SELECT ss.sku, ss.product_name, SUM(ss.quantity) as total_quantity
                FROM session_skus ss
                JOIN sessions s ON ss.session_id = s.session_id
                WHERE s.client_id = ? {date_filter}
                GROUP BY ss.sku, ss.product_name
                ORDER BY total_quantity DESC
                LIMIT 10
            """, params)

            stats['most_packed_skus'] = [
                {'sku': row[0], 'product_name': row[1], 'total_quantity': row[2]}
                for row in cursor.fetchall()
            ]

            conn.close()

            self.logger.debug(f"Retrieved statistics for client {client_id}")
            return stats

        except Exception as e:
            self.logger.error(f"Failed to get client statistics: {e}", exc_info=True)
            return {
                'total_sessions': 0,
                'total_orders': 0,
                'total_items': 0,
                'avg_orders_per_session': 0,
                'avg_duration_minutes': 0,
                'top_users': [],
                'most_packed_skus': []
            }

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Format duration in seconds to human-readable string."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    @staticmethod
    def _get_username() -> str:
        """Get current Windows username."""
        try:
            return os.getlogin()
        except Exception:
            return os.environ.get('USERNAME', 'Unknown')
