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
        packing_list_name: Name of packing list (for JSON-based sessions)
        is_legacy: True if old Excel-based structure, False if new JSON-based
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
    packing_list_name: Optional[str] = None
    is_legacy: bool = False

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
                    # Check if NEW structure (has packing/ directory)
                    packing_dir = session_dir / "packing"
                    if packing_dir.exists() and packing_dir.is_dir():
                        # NEW STRUCTURE: Scan each packing list subdirectory
                        logger.debug(f"Session {session_dir.name} uses NEW structure, scanning packing lists...")
                        for packing_list_dir in packing_dir.iterdir():
                            if not packing_list_dir.is_dir():
                                continue

                            packing_list_record = self._parse_packing_list_session(
                                client_id=client_id,
                                session_dir=session_dir,
                                packing_list_dir=packing_list_dir
                            )

                            if packing_list_record is None:
                                continue

                            # Apply filters
                            if not include_incomplete and packing_list_record.in_progress_orders > 0:
                                logger.debug(f"Skipping incomplete packing list: {packing_list_dir.name}")
                                continue

                            if start_date and packing_list_record.start_time and packing_list_record.start_time < start_date:
                                continue

                            if end_date and packing_list_record.start_time and packing_list_record.start_time > end_date:
                                continue

                            sessions.append(packing_list_record)

                    else:
                        # LEGACY STRUCTURE: Parse as before
                        record = self._parse_session_directory(client_id, session_dir)

                        if record is None:
                            logger.debug(f"Skipping session {session_dir.name}: _parse_session_directory returned None")
                            continue

                        # Apply filters
                        if not include_incomplete and record.in_progress_orders > 0:
                            logger.debug(f"Skipping incomplete session: {session_dir.name}")
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
            sessions.sort(key=lambda s: s.start_time or datetime.min, reverse=True)

            logger.info(f"Found {len(sessions)} sessions for client {client_id}")
            return sessions

        except Exception as e:
            logger.error(f"Error retrieving sessions for client {client_id}: {e}", exc_info=True)
            return []

    def _parse_session_directory(
        self,
        client_id: str,
        session_dir: Path
    ) -> Optional[SessionHistoryRecord]:
        """
        Parse a session directory and extract metrics.

        This method now supports BOTH old and new session structures:
        - OLD (legacy Excel): session_dir/barcodes/packing_state.json
        - NEW (Shopify JSON): session_dir/packing/{list_name}/barcodes/packing_state.json

        For new structure, this will be called multiple times (once per packing list).

        Args:
            client_id: Client identifier
            session_dir: Path to session directory OR packing list directory

        Returns:
            SessionHistoryRecord or None if parsing fails
        """
        session_id = session_dir.name

        # Check if this is a NEW structure session (has packing/ directory)
        packing_dir = session_dir / "packing"
        if packing_dir.exists() and packing_dir.is_dir():
            # NEW STRUCTURE: Scan each packing list subdirectory
            logger.debug(f"Session {session_id} uses NEW structure (packing/ directory found)")
            # This session will be handled by get_client_sessions which calls
            # _parse_packing_list_session for each packing list
            return None

        # LEGACY STRUCTURE: Old Excel-based sessions
        # Try to load session_summary.json first (completed sessions)
        summary_file = session_dir / "session_summary.json"
        if summary_file.exists():
            logger.debug(f"Found session_summary.json for LEGACY session {session_id}, parsing...")
            return self._parse_session_summary(client_id, session_dir, summary_file, is_legacy=True)

        # Fallback: Try packing_state.json (incomplete/active sessions)
        state_file = session_dir / "barcodes" / "packing_state.json"

        if not state_file.exists():
            logger.debug(f"No session data found for session {session_id} (legacy structure)")
            return None

        logger.debug(f"Found packing_state.json for LEGACY session {session_id}, parsing incomplete session...")
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
                    end_time = datetime.fromisoformat(state_timestamp)
                    if start_time and end_time:
                        duration_seconds = (end_time - start_time).total_seconds()
                except ValueError:
                    pass

            # If no end time from state, use file modification time
            if not end_time:
                try:
                    mtime = state_file.stat().st_mtime
                    end_time = datetime.fromtimestamp(mtime)
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
                session_path=str(session_dir),
                packing_list_name=None,
                is_legacy=True
            )

        except Exception as e:
            logger.error(f"Error parsing LEGACY session directory {session_id}: {e}")
            return None

    def _parse_packing_list_session(
        self,
        client_id: str,
        session_dir: Path,
        packing_list_dir: Path
    ) -> Optional[SessionHistoryRecord]:
        """
        Parse a single packing list session from NEW structure.

        NEW structure: Sessions/CLIENT_M/2025-11-10_1/packing/DHL_Orders/
        This function parses one packing list directory.

        Args:
            client_id: Client identifier
            session_dir: Parent session directory
            packing_list_dir: Packing list directory (e.g., packing/DHL_Orders/)

        Returns:
            SessionHistoryRecord or None if parsing fails
        """
        session_id = session_dir.name
        packing_list_name = packing_list_dir.name

        logger.debug(f"Parsing packing list session: {session_id}/{packing_list_name}")

        # Check for session_summary.json (completed)
        summary_file = packing_list_dir / "session_summary.json"
        if summary_file.exists():
            logger.debug(f"Found session_summary.json for {session_id}/{packing_list_name}")
            return self._parse_session_summary(
                client_id=client_id,
                session_dir=session_dir,
                summary_file=summary_file,
                packing_list_name=packing_list_name,
                is_legacy=False
            )

        # Check for packing_state.json (incomplete/in-progress)
        state_file = packing_list_dir / "barcodes" / "packing_state.json"
        if not state_file.exists():
            logger.debug(f"No session data found for {session_id}/{packing_list_name}")
            return None

        logger.debug(f"Found packing_state.json for {session_id}/{packing_list_name}, parsing...")

        try:
            # Load packing state
            with open(state_file, 'r', encoding='utf-8') as f:
                packing_state = json.load(f)

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
                    end_time = datetime.fromisoformat(state_timestamp)
                    if start_time and end_time:
                        duration_seconds = (end_time - start_time).total_seconds()
                except ValueError:
                    pass

            # If no end time from state, use file modification time
            if not end_time:
                try:
                    mtime = state_file.stat().st_mtime
                    end_time = datetime.fromtimestamp(mtime)
                    if start_time:
                        duration_seconds = (end_time - start_time).total_seconds()
                except Exception:
                    pass

            # Try to get PC name from lock file or state
            pc_name = packing_state.get('pc_name')
            if not pc_name:
                # Try to get from lock file
                lock_file = packing_list_dir / ".session.lock"
                if lock_file.exists():
                    try:
                        with open(lock_file, 'r', encoding='utf-8') as f:
                            lock_data = json.load(f)
                            pc_name = lock_data.get('locked_by')
                    except Exception:
                        pass

            # Construct packing list path
            packing_list_path = str(session_dir / "packing_lists" / f"{packing_list_name}.json")

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
                session_path=str(packing_list_dir),
                packing_list_name=packing_list_name,
                is_legacy=False
            )

        except Exception as e:
            logger.error(f"Error parsing packing list session {session_id}/{packing_list_name}: {e}")
            return None

    def _parse_session_summary(
        self,
        client_id: str,
        session_dir: Path,
        summary_file: Path,
        packing_list_name: Optional[str] = None,
        is_legacy: bool = False
    ) -> Optional[SessionHistoryRecord]:
        """
        Parse session_summary.json for completed sessions.

        Args:
            client_id: Client identifier
            session_dir: Path to session directory (parent for new structure)
            summary_file: Path to session_summary.json file
            packing_list_name: Optional packing list name (for new structure)
            is_legacy: True if old structure, False if new structure

        Returns:
            SessionHistoryRecord or None if parsing fails
        """
        session_id = session_dir.name

        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                summary = json.load(f)

            # Parse timestamps
            start_time = None
            end_time = None
            duration_seconds = None

            if 'started_at' in summary and summary['started_at']:
                try:
                    start_time = datetime.fromisoformat(summary['started_at'])
                except (ValueError, TypeError):
                    pass

            if 'completed_at' in summary and summary['completed_at']:
                try:
                    end_time = datetime.fromisoformat(summary['completed_at'])
                except (ValueError, TypeError):
                    pass

            if 'duration_seconds' in summary:
                duration_seconds = summary['duration_seconds']
            elif start_time and end_time:
                duration_seconds = (end_time - start_time).total_seconds()

            # Determine session_path based on structure
            if is_legacy:
                session_path = str(session_dir)
            else:
                # For new structure, session_path points to packing list directory
                session_path = str(summary_file.parent)

            return SessionHistoryRecord(
                session_id=session_id,
                client_id=client_id,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                total_orders=summary.get('total_orders', 0),
                completed_orders=summary.get('completed_orders', 0),
                in_progress_orders=summary.get('in_progress_orders', 0),
                total_items_packed=summary.get('items_packed', 0),
                pc_name=summary.get('pc_name'),
                packing_list_path=summary.get('packing_list_path'),
                session_path=session_path,
                packing_list_name=packing_list_name,
                is_legacy=is_legacy
            )

        except Exception as e:
            logger.error(f"Error parsing session summary {session_id}: {e}", exc_info=True)
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
        """
        try:
            # Try standard format: YYYYMMDD_HHMMSS
            return datetime.strptime(session_id, "%Y%m%d_%H%M%S")
        except ValueError:
            try:
                # Try alternative formats
                return datetime.strptime(session_id, "%Y%m%d-%H%M%S")
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

            # Load packing state
            state_file = session_dir / "packing_state.json"
            if not state_file.exists():
                return None

            with open(state_file, 'r', encoding='utf-8') as f:
                packing_state = json.load(f)

            # Load session info
            session_info = self._load_session_info(session_dir)

            # Get session record
            record = self._parse_session_directory(client_id, session_dir)

            return {
                'record': record.to_dict() if record else None,
                'packing_state': packing_state,
                'session_info': session_info
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
                'Packing List': s.packing_list_name or 'Legacy',
                'Start Time': s.start_time.strftime('%Y-%m-%d %H:%M:%S') if s.start_time else '',
                'End Time': s.end_time.strftime('%Y-%m-%d %H:%M:%S') if s.end_time else '',
                'Duration (minutes)': round(s.duration_seconds / 60, 2) if s.duration_seconds else 0,
                'Total Orders': s.total_orders,
                'Completed Orders': s.completed_orders,
                'In Progress': s.in_progress_orders,
                'Items Packed': s.total_items_packed,
                'PC Name': s.pc_name or '',
                'Packing List Path': s.packing_list_path or ''
            }
            for s in sessions
        ]
