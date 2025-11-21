"""
Session History Manager - Manages historical session data and analytics.

This module provides functionality to retrieve, analyze, and search through
completed packing sessions, enabling historical reporting and analytics.
"""
import os
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class SessionHistoryRecord:
    """
    Represents a historical session record with all relevant metrics.

    Attributes:
        session_id: Unique session identifier (timestamp-based directory name)
        client_id: Client identifier
        start_time: Session start timestamp
        end_time: Session end timestamp (if available)
        duration_seconds: Total session duration in seconds
        total_orders: Total number of orders in the session
        completed_orders: Number of completed orders
        in_progress_orders: Number of in-progress orders
        total_items_packed: Total number of items packed
        pc_name: Computer name where session was executed
        packing_list_path: Original packing list file path
        session_path: Full path to session directory
    """
    session_id: str
    client_id: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    duration_seconds: Optional[float]
    total_orders: int
    completed_orders: int
    in_progress_orders: int
    total_items_packed: int
    pc_name: Optional[str]
    packing_list_path: Optional[str]
    session_path: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with datetime objects as ISO strings."""
        data = asdict(self)
        if self.start_time:
            data['start_time'] = self.start_time.isoformat()
        if self.end_time:
            data['end_time'] = self.end_time.isoformat()
        return data


@dataclass
class ClientAnalytics:
    """
    Aggregated analytics for a specific client.

    Attributes:
        client_id: Client identifier
        total_sessions: Total number of sessions
        total_orders_packed: Total orders packed across all sessions
        average_orders_per_session: Average orders per session
        average_session_duration_minutes: Average session duration in minutes
        total_items_packed: Total items packed
        last_session_date: Date of most recent session
    """
    client_id: str
    total_sessions: int
    total_orders_packed: int
    average_orders_per_session: float
    average_session_duration_minutes: float
    total_items_packed: int
    last_session_date: Optional[datetime]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with datetime objects as ISO strings."""
        data = asdict(self)
        if self.last_session_date:
            data['last_session_date'] = self.last_session_date.isoformat()
        return data


class SessionHistoryManager:
    """
    Manages historical session data retrieval and analytics.

    This class provides methods to scan session directories, extract metrics
    from completed sessions, and generate analytics reports for clients.
    """

    def __init__(self, profile_manager):
        """
        Initialize SessionHistoryManager.

        Args:
            profile_manager: ProfileManager instance for accessing session paths
        """
        self.profile_manager = profile_manager
        logger.info("SessionHistoryManager initialized")

    def get_client_sessions(
        self,
        client_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_incomplete: bool = True
    ) -> List[SessionHistoryRecord]:
        """
        Retrieve all sessions for a specific client.

        Args:
            client_id: Client identifier
            start_date: Filter sessions after this date (inclusive)
            end_date: Filter sessions before this date (inclusive)
            include_incomplete: Include sessions that are still in progress

        Returns:
            List of SessionHistoryRecord objects, sorted by start time (newest first)
        """
        # Ensure date filters are timezone-aware for comparison with session timestamps
        from datetime import timezone

        if start_date is not None and start_date.tzinfo is None:
            # Assume local timezone if naive
            start_date = start_date.replace(tzinfo=timezone.utc)
            logger.debug(f"Converted naive start_date to timezone-aware (UTC)")

        if end_date is not None and end_date.tzinfo is None:
            # Assume local timezone if naive
            end_date = end_date.replace(tzinfo=timezone.utc)
            logger.debug(f"Converted naive end_date to timezone-aware (UTC)")

        logger.info(f"Retrieving sessions for client {client_id}")

        try:
            sessions_root = self.profile_manager.get_sessions_root() / f"CLIENT_{client_id}"

            if not sessions_root.exists():
                logger.warning(f"Sessions directory not found for client {client_id}: {sessions_root}")
                return []

            logger.debug(f"Searching for sessions in: {sessions_root}")
            sessions = []
            session_dirs = list(sessions_root.iterdir())
            logger.info(f"Found {len(session_dirs)} directories/files in {sessions_root}")

            # Iterate through all session directories
            for session_dir in session_dirs:
                if not session_dir.is_dir():
                    logger.debug(f"Skipping non-directory: {session_dir.name}")
                    continue

                logger.debug(f"Parsing session directory: {session_dir.name}")
                try:
                    records = self._parse_session_directory(client_id, session_dir)

                    if not records:
                        logger.debug(f"Skipping session {session_dir.name}: _parse_session_directory returned empty list")
                        continue

                    # Apply filters to each record
                    for record in records:
                        if not include_incomplete and record.in_progress_orders > 0:
                            logger.debug(f"Skipping incomplete packing list in session: {session_dir.name}")
                            continue

                        if start_date and record.start_time and record.start_time < start_date:
                            logger.debug(f"Skipping session {session_dir.name}: before start_date")
                            continue

                        if end_date and record.start_time and record.start_time > end_date:
                            logger.debug(f"Skipping session {session_dir.name}: after end_date")
                            continue

                        logger.debug(f"Adding session {session_dir.name} to results")
                        sessions.append(record)

                except Exception as e:
                    logger.warning(f"Error parsing session {session_dir.name}: {e}", exc_info=True)
                    continue

            # Sort by start time, newest first
            # Use timezone-aware min for compatibility with new timestamps
            from datetime import timezone
            min_dt = datetime.min.replace(tzinfo=timezone.utc)
            sessions.sort(key=lambda s: s.start_time or min_dt, reverse=True)

            logger.info(f"Found {len(sessions)} sessions for client {client_id}")
            return sessions

        except Exception as e:
            logger.error(f"Error retrieving sessions for client {client_id}: {e}", exc_info=True)
            return []

    def _parse_session_directory(
        self,
        client_id: str,
        session_dir: Path
    ) -> List[SessionHistoryRecord]:
        """
        Parse a session directory and extract metrics for all packing lists.

        Supports both:
        - Phase 1 (Shopify): packing/*/packing_state.json (multiple lists)
        - Legacy (Excel): barcodes/packing_state.json (single list)

        Args:
            client_id: Client identifier
            session_dir: Path to session directory

        Returns:
            List of SessionHistoryRecord objects (one per packing list), or empty list if parsing fails
        """
        session_id = session_dir.name
        records = []

        # ========================================
        # PHASE 1 (Shopify) - Try first
        # ========================================
        packing_dir = session_dir / "packing"
        if packing_dir.exists() and packing_dir.is_dir():
            logger.debug(f"Found packing/ directory in {session_id}, checking for Phase 1 data")

            # Iterate through all packing list work directories
            for work_dir in packing_dir.iterdir():
                if not work_dir.is_dir():
                    continue

                logger.debug(f"Checking work directory: {work_dir.name}")

                # Check for session_summary.json (completed session)
                summary_file = work_dir / "session_summary.json"
                if summary_file.exists():
                    logger.info(f"Found session_summary.json in {session_id}/{work_dir.name}")
                    record = self._parse_session_summary(client_id, session_dir, summary_file)
                    if record:
                        records.append(record)
                    continue  # Continue to next work_dir instead of returning

                # Check for packing_state.json (in-progress or completed)
                state_file = work_dir / "packing_state.json"
                if state_file.exists():
                    logger.info(f"Found packing_state.json in {session_id}/{work_dir.name}")
                    record = self._parse_packing_state(client_id, session_dir, state_file)
                    if record:
                        records.append(record)
                    continue  # Continue to next work_dir instead of returning

            if records:
                logger.info(f"Found {len(records)} packing list(s) in Phase 1 structure for {session_id}")
                return records

            logger.debug(f"No packing data found in Phase 1 structure for {session_id}")

        # ========================================
        # LEGACY (Excel) - Fallback
        # ========================================
        # Check barcodes/packing_state.json
        state_file = session_dir / "barcodes" / "packing_state.json"
        if state_file.exists():
            logger.info(f"Found Legacy Excel packing_state.json in {session_id}")
            record = self._parse_packing_state(client_id, session_dir, state_file)
            if record:
                return [record]

        # Check barcodes/session_summary.json (if exists)
        summary_file = session_dir / "barcodes" / "session_summary.json"
        if summary_file.exists():
            logger.info(f"Found Legacy Excel session_summary.json in {session_id}")
            record = self._parse_session_summary(client_id, session_dir, summary_file)
            if record:
                return [record]

        # ========================================
        # NO PACKING DATA FOUND
        # ========================================
        logger.info(f"No packing data found for session {session_id} - session will be skipped")
        return []

    def _parse_session_summary(
        self,
        client_id: str,
        session_dir: Path,
        summary_file: Path
    ) -> Optional[SessionHistoryRecord]:
        """
        Parse session_summary.json for completed sessions (v1.3.0 format only).

        Args:
            client_id: Client identifier
            session_dir: Path to session directory
            summary_file: Path to session_summary.json file

        Returns:
            SessionHistoryRecord or None if parsing fails
        """
        from shared.metadata_utils import load_session_summary, parse_timestamp

        session_id = session_dir.name

        try:
            # Load v1.3.0 format
            summary = load_session_summary(summary_file)

            # Parse timestamps using utility function
            start_time = parse_timestamp(summary.get('started_at', ''))
            end_time = parse_timestamp(summary.get('completed_at', ''))

            # Get duration
            duration_seconds = summary.get('duration_seconds')
            if duration_seconds is None and start_time and end_time:
                duration_seconds = (end_time - start_time).total_seconds()

            # Map v1.3.0 format to SessionHistoryRecord
            return SessionHistoryRecord(
                session_id=session_id,
                client_id=client_id,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                total_orders=summary.get('total_orders', 0),
                completed_orders=summary.get('completed_orders', 0),
                in_progress_orders=0,  # No longer tracked in v1.3.0
                total_items_packed=summary.get('total_items', 0),
                pc_name=summary.get('pc_name', ''),
                packing_list_path=summary.get('packing_list_name', ''),
                session_path=str(session_dir)
            )

        except Exception as e:
            logger.error(f"Error parsing session summary {session_id}: {e}", exc_info=True)
            return None

    def _parse_packing_state(
        self,
        client_id: str,
        session_dir: Path,
        state_file: Path
    ) -> Optional[SessionHistoryRecord]:
        """
        Parse packing_state.json for in-progress or completed sessions.

        Args:
            client_id: Client identifier
            session_dir: Path to session directory
            state_file: Path to packing_state.json file

        Returns:
            SessionHistoryRecord or None if parsing fails
        """
        session_id = session_dir.name

        try:
            # Load packing state
            with open(state_file, 'r', encoding='utf-8') as f:
                packing_state = json.load(f)

            # Extract session info if available
            session_info = self._load_session_info(session_dir)

            # Parse session ID to extract timestamp
            start_time = self._parse_session_timestamp(session_id)

            # Calculate metrics from packing state
            data = packing_state.get('data', {})
            in_progress = data.get('in_progress', {})
            completed = data.get('completed_orders', [])

            total_orders = len(in_progress) + len(completed)
            completed_orders = len(completed)
            in_progress_orders = len(in_progress)

            # Count total items packed
            total_items_packed = self._count_packed_items(in_progress, completed)

            # Try to determine end time from state timestamp or file modification time
            end_time = None
            duration_seconds = None

            state_timestamp = packing_state.get('timestamp')
            if state_timestamp:
                try:
                    from shared.metadata_utils import parse_timestamp
                    end_time = parse_timestamp(state_timestamp)
                    if start_time and end_time:
                        duration_seconds = (end_time - start_time).total_seconds()
                except (ValueError, TypeError):
                    pass

            # If no end time from state, use file modification time
            if not end_time:
                try:
                    from datetime import timezone
                    mtime = state_file.stat().st_mtime
                    end_time = datetime.fromtimestamp(mtime, tz=timezone.utc)
                    if start_time:
                        duration_seconds = (end_time - start_time).total_seconds()
                except Exception:
                    pass

            # Extract session info details
            pc_name = session_info.get('pc_name') if session_info else None
            packing_list_path = session_info.get('packing_list_path') if session_info else None

            return SessionHistoryRecord(
                session_id=session_id,
                client_id=client_id,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                total_orders=total_orders,
                completed_orders=completed_orders,
                in_progress_orders=in_progress_orders,
                total_items_packed=total_items_packed,
                pc_name=pc_name,
                packing_list_path=packing_list_path,
                session_path=str(session_dir)
            )

        except Exception as e:
            logger.error(f"Error parsing packing_state.json for {session_id}: {e}", exc_info=True)
            return None

    def _load_session_info(self, session_dir: Path) -> Optional[Dict[str, Any]]:
        """Load session_info.json if it exists."""
        info_file = session_dir / "session_info.json"
        if info_file.exists():
            try:
                with open(info_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error reading session_info.json: {e}")
        return None

    def _parse_session_timestamp(self, session_id: str) -> Optional[datetime]:
        """
        Parse timestamp from session ID.

        Session IDs are typically in format: YYYYMMDD_HHMMSS
        Returns timezone-aware datetime (UTC).
        """
        from datetime import timezone
        try:
            # Try standard format: YYYYMMDD_HHMMSS
            dt = datetime.strptime(session_id, "%Y%m%d_%H%M%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                # Try alternative formats
                dt = datetime.strptime(session_id, "%Y%m%d-%H%M%S")
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                logger.debug(f"Could not parse timestamp from session ID: {session_id}")
                return None

    def _count_packed_items(
        self,
        in_progress: Dict[str, Any],
        completed: List[str]
    ) -> int:
        """
        Count total items packed across all orders.

        Args:
            in_progress: Dictionary of in-progress orders
            completed: List of completed order IDs

        Returns:
            Total count of packed items
        """
        total = 0

        # Count items in in-progress orders
        for order_data in in_progress.values():
            for sku_data in order_data.values():
                if isinstance(sku_data, dict) and 'packed' in sku_data:
                    total += sku_data['packed']

        # For completed orders, we assume all items are packed
        # This is an approximation since we don't store required counts separately
        # In a real scenario, you might want to store this differently

        return total

    def get_client_analytics(
        self,
        client_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> ClientAnalytics:
        """
        Generate analytics for a specific client.

        Args:
            client_id: Client identifier
            start_date: Include sessions after this date
            end_date: Include sessions before this date

        Returns:
            ClientAnalytics object with aggregated metrics
        """
        sessions = self.get_client_sessions(
            client_id,
            start_date=start_date,
            end_date=end_date,
            include_incomplete=False
        )

        if not sessions:
            return ClientAnalytics(
                client_id=client_id,
                total_sessions=0,
                total_orders_packed=0,
                average_orders_per_session=0.0,
                average_session_duration_minutes=0.0,
                total_items_packed=0,
                last_session_date=None
            )

        total_sessions = len(sessions)
        total_orders = sum(s.completed_orders for s in sessions)
        total_items = sum(s.total_items_packed for s in sessions)

        # Calculate average orders per session
        avg_orders = total_orders / total_sessions if total_sessions > 0 else 0.0

        # Calculate average session duration
        durations = [s.duration_seconds for s in sessions if s.duration_seconds is not None]
        avg_duration_seconds = sum(durations) / len(durations) if durations else 0.0
        avg_duration_minutes = avg_duration_seconds / 60.0

        # Get last session date
        last_session_date = sessions[0].start_time if sessions else None

        return ClientAnalytics(
            client_id=client_id,
            total_sessions=total_sessions,
            total_orders_packed=total_orders,
            average_orders_per_session=avg_orders,
            average_session_duration_minutes=avg_duration_minutes,
            total_items_packed=total_items,
            last_session_date=last_session_date
        )

    def search_sessions(
        self,
        client_id: str,
        search_term: str,
        search_fields: List[str] = None
    ) -> List[SessionHistoryRecord]:
        """
        Search sessions by various fields.

        Args:
            client_id: Client identifier
            search_term: Search term to match
            search_fields: List of fields to search in (session_id, pc_name, etc.)
                          If None, searches all text fields

        Returns:
            List of matching SessionHistoryRecord objects
        """
        if search_fields is None:
            search_fields = ['session_id', 'pc_name', 'packing_list_path']

        all_sessions = self.get_client_sessions(client_id)
        search_term_lower = search_term.lower()

        matching_sessions = []
        for session in all_sessions:
            for field in search_fields:
                value = getattr(session, field, None)
                if value and search_term_lower in str(value).lower():
                    matching_sessions.append(session)
                    break

        return matching_sessions

    def get_session_details(
        self,
        client_id: str,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific session.

        Supports both Phase 1 (Shopify) and Legacy (Excel) structures.

        Args:
            client_id: Client identifier
            session_id: Session identifier

        Returns:
            Dictionary with detailed session information including packing state
        """
        try:
            session_dir = self.profile_manager.get_sessions_root() / f"CLIENT_{client_id}" / session_id

            if not session_dir.exists():
                logger.warning(f"Session directory not found: {session_dir}")
                return None

            # Find packing state file (supports both Phase 1 and Legacy structures)
            state_file = None

            # Try Phase 1 structure first
            packing_dir = session_dir / "packing"
            if packing_dir.exists() and packing_dir.is_dir():
                for work_dir in packing_dir.iterdir():
                    if work_dir.is_dir():
                        candidate = work_dir / "packing_state.json"
                        if candidate.exists():
                            state_file = candidate
                            break

            # Fallback to Legacy structure
            if not state_file:
                candidate = session_dir / "barcodes" / "packing_state.json"
                if candidate.exists():
                    state_file = candidate

            if not state_file:
                logger.warning(f"No packing_state.json found for session {session_id}")
                return None

            with open(state_file, 'r', encoding='utf-8') as f:
                packing_state = json.load(f)

            # Load session info
            session_info = self._load_session_info(session_dir)

            # Load session summary if exists (Phase 2b data)
            session_summary = {}
            work_dir_path = state_file.parent  # work_dir containing packing_state.json
            summary_file = work_dir_path / "session_summary.json"
            if summary_file.exists():
                try:
                    from shared.metadata_utils import load_session_summary
                    session_summary = load_session_summary(summary_file)
                    logger.info(f"Loaded session_summary.json for session {session_id} with {len(session_summary.get('orders', []))} orders")
                except Exception as e:
                    logger.warning(f"Failed to load session_summary.json: {e}")

            # Get session records (may be multiple for multi-list sessions)
            records = self._parse_session_directory(client_id, session_dir)

            # For backward compatibility, return the first record
            # TODO: Future enhancement - support selecting specific packing list
            record = records[0] if records else None

            return {
                'record': record.to_dict() if record else None,
                'packing_state': packing_state,
                'session_info': session_info,
                'session_summary': session_summary
            }

        except Exception as e:
            logger.error(f"Error getting session details: {e}")
            return None

    def export_sessions_to_dict(
        self,
        sessions: List[SessionHistoryRecord]
    ) -> List[Dict[str, Any]]:
        """
        Export sessions to a list of dictionaries suitable for pandas DataFrame.

        Args:
            sessions: List of SessionHistoryRecord objects

        Returns:
            List of dictionaries with session data
        """
        return [
            {
                'Session ID': s.session_id,
                'Client ID': s.client_id,
                'Start Time': s.start_time.strftime('%Y-%m-%d %H:%M:%S') if s.start_time else '',
                'End Time': s.end_time.strftime('%Y-%m-%d %H:%M:%S') if s.end_time else '',
                'Duration (minutes)': round(s.duration_seconds / 60, 2) if s.duration_seconds else 0,
                'Total Orders': s.total_orders,
                'Completed Orders': s.completed_orders,
                'In Progress': s.in_progress_orders,
                'Items Packed': s.total_items_packed,
                'PC Name': s.pc_name or '',
                'Packing List': s.packing_list_path or ''
            }
            for s in sessions
        ]
