# Standard library imports
import os
import tempfile
import shutil

# Third-party imports for data processing
import pandas as pd  # Excel file handling and data manipulation

# Data persistence and utilities
import json
from pathlib import Path
from datetime import datetime

# Qt framework for signals/slots pattern
from PySide6.QtCore import QObject, Signal

# Type hints for better code documentation
from typing import List, Dict, Any, Tuple

# Local imports
from logger import get_logger
from json_cache import get_cached_json, invalidate_json_cache

# Initialize module-level logger
logger = get_logger(__name__)

# Required columns in the Excel packing list
# These columns are mandatory for the application to function correctly
# - Order_Number: Unique identifier for each order
# - SKU: Product stock keeping unit code
# - Product_Name: Human-readable product description
# - Quantity: Number of items to pack for this SKU in this order
# - Courier: Shipping courier name (e.g., "PostOne", "Speedy", "DHL")
REQUIRED_COLUMNS = ['Order_Number', 'SKU', 'Product_Name', 'Quantity', 'Courier']

# Filename for session state persistence
# This file stores packing progress and is saved after every scan
# to enable crash recovery and session restoration
STATE_FILE_NAME = "packing_state.json"

# Filename for session summary (created upon completion)
# This file contains aggregated statistics and performance metrics
# for the completed packing session
SUMMARY_FILE_NAME = "session_summary.json"

class PackerLogic(QObject):
    """
    Handles the core business logic of the Packer's Assistant application.

    This class is responsible for loading and processing packing lists,
    generating barcodes, managing the state of the packing process (what has
    been packed), and handling the logic for scanning items. It operates
    independently of the UI, communicating changes via Qt signals.

    Attributes:
        item_packed (Signal): A signal emitted when an item is packed, providing
                              real-time progress updates.
        client_id (str): Client identifier for this session
        profile_manager (ProfileManager): Manager for client profiles and SKU mappings
        work_dir (Path): Work directory for this packing list
                        (e.g., Sessions/CLIENT_M/2025-11-10_1/packing/DHL_Orders/)
        barcode_dir (Path): Subdirectory for generated barcodes (work_dir/barcodes/)
        reports_dir (Path): Subdirectory for packing reports (work_dir/reports/)
        packing_list_df (pd.DataFrame): The original, unprocessed DataFrame
                                        loaded from the Excel file.
        processed_df (pd.DataFrame): The DataFrame after column mapping and
                                     validation.
        orders_data (Dict): A dictionary containing details for each order,
                            including its barcode path and item list.
        current_order_number (str | None): The order number currently being packed.
        current_order_state (Dict): The detailed packing state for the current
                                    order (required vs. packed counts for each SKU).
        session_packing_state (Dict): The packing state for the entire session,
                                      including in-progress and completed orders.
        sku_map (Dict[str, str]): Normalized barcode-to-SKU mapping
    """
    item_packed = Signal(str, int, int)  # order_number, packed_count, required_count

    def __init__(self, client_id: str, profile_manager, work_dir: str):
        """
        Initialize PackerLogic instance for a specific client.

        Args:
            client_id: Client identifier (e.g., "M", "R")
            profile_manager: ProfileManager instance for loading/saving SKU mappings
            work_dir: Work directory for this packing list
                     (e.g., Sessions/CLIENT_M/2025-11-10_1/packing/DHL_Orders/)
                     For legacy Excel workflow, this will be the barcodes directory
        """
        super().__init__()

        self.client_id = client_id
        self.profile_manager = profile_manager
        self.work_dir = Path(work_dir)

        # Create subdirectories
        # work_dir is packing/{list_name}/ (from Shopify session)
        # Barcode directory exists in session root (created by Shopify Tool)
        self.barcode_dir = self.work_dir.parent.parent / "barcodes"  # ../../../barcodes
        self.reports_dir = self.work_dir / "reports"

        # Ensure reports directory exists (barcodes dir created by Shopify Tool)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.packing_list_df = None
        self.processed_df = None
        self.orders_data = {}
        self.current_order_number = None
        self.current_order_state = {}

        # Session metadata (for new state structure)
        self.session_id = None  # Will be set when loading packing list
        self.packing_list_name = None  # Name of the packing list being packed
        self.started_at = None  # Session start timestamp
        self.worker_pc = os.environ.get('COMPUTERNAME', 'Unknown')  # PC name

        # Initialize session packing state with new structure
        # This will be populated when loading an existing state or starting new
        self.session_packing_state = {
            'in_progress': {},
            'completed_orders': [],
            'skipped_orders': []
        }

        # Load SKU mapping from ProfileManager
        self.sku_map = self._load_sku_mapping()

        # Load session state if exists
        self._load_session_state()

        # Phase 2b: Order-level timing tracking
        self.current_order_start_time = None  # ISO timestamp when order scanning started
        self.current_order_items_scanned = []  # List of items with scan timestamps
        self.completed_orders_metadata = []  # List of completed orders with timing data

        logger.info(f"PackerLogic initialized for client {client_id}")
        logger.debug(f"Work directory: {self.work_dir}")
        logger.debug(f"Barcode directory: {self.barcode_dir}")
        logger.debug(f"Reports directory: {self.reports_dir}")
        logger.debug(f"Loaded {len(self.sku_map)} SKU mappings")
        logger.debug("Phase 2b timing variables initialized")

    def _load_sku_mapping(self) -> Dict[str, str]:
        """
        Load SKU mapping from ProfileManager for the current client.

        SKU mappings allow barcodes from products to be translated to internal SKU codes.
        This is useful when:
        - Products have multiple barcode standards (EAN-13, UPC, manufacturer codes)
        - Supplier barcodes differ from internal SKU system
        - Same product has different barcodes from different suppliers

        For small warehouses, this is critical because products often come from
        multiple suppliers with different barcode systems, but need to be tracked
        under a single internal SKU.

        The method normalizes all barcode keys (lowercase, alphanumeric only) to ensure
        consistent matching regardless of scanner input variations.

        Returns:
            Dictionary of normalized barcode -> SKU mappings
            Example: {"7290018664100": "SKU-CREAM-01", "8809765431234": "SKU-SERUM-02"}
            Returns empty dict if loading fails (graceful degradation)
        """
        try:
            # Load raw mappings from centralized storage (file server)
            mappings = self.profile_manager.load_sku_mapping(self.client_id)

            # Normalize all barcode keys for consistent matching
            # This handles variations in scanner output (spaces, dashes, mixed case)
            # Original SKU values are preserved as-is
            normalized = {self._normalize_sku(k): v for k, v in mappings.items()}

            logger.debug(f"Loaded {len(normalized)} SKU mappings for client {self.client_id}")
            return normalized
        except Exception as e:
            # Graceful degradation: if SKU mapping fails to load, continue without it
            # Scanned barcodes will be matched directly against order SKUs
            logger.error(f"Error loading SKU mappings: {e}")
            return {}

    def set_sku_map(self, sku_map: Dict[str, str]):
        """
        Set the SKU map and save to ProfileManager.

        The barcode (key) is normalized to ensure consistent matching with
        scanner input. The SKU (value) is left as is. Changes are persisted
        to the centralized file server.

        Args:
            sku_map: The Barcode-to-SKU mapping

        Note:
            This method now saves to ProfileManager for cross-PC synchronization.
        """
        logger.info(f"Updating SKU mapping: {len(sku_map)} entries")

        # Normalize for in-memory use
        self.sku_map = {self._normalize_sku(k): v for k, v in sku_map.items()}

        # Save to ProfileManager (original keys, not normalized)
        try:
            self.profile_manager.save_sku_mapping(self.client_id, sku_map)
            logger.info("SKU mapping saved successfully")
        except Exception as e:
            logger.error(f"Failed to save SKU mapping: {e}")

    def _get_state_file_path(self) -> str:
        """
        Return path to packing_state.json in work_dir root.

        For unified workflow: work_dir/packing_state.json
        For Excel workflow: barcodes/packing_state.json (backward compatible)
        """
        # For unified workflow, state file goes in work_dir root
        # For Excel workflow (work_dir == barcodes), state file is still in barcodes dir
        if self.work_dir.name == "barcodes":
            # Excel workflow: keep state in barcodes directory
            return str(self.work_dir / STATE_FILE_NAME)
        else:
            # Unified workflow: state in work_dir root
            return str(self.work_dir / STATE_FILE_NAME)

    def _get_summary_file_path(self) -> str:
        """
        Return path to session_summary.json in work_dir root.

        For unified workflow: work_dir/session_summary.json
        For Excel workflow: barcodes/session_summary.json (backward compatible)
        """
        if self.work_dir.name == "barcodes":
            # Excel workflow: keep summary in barcodes directory
            return str(self.work_dir / SUMMARY_FILE_NAME)
        else:
            # Unified workflow: summary in work_dir root
            return str(self.work_dir / SUMMARY_FILE_NAME)

    def _load_session_state(self):
        """
        Load the packing state for the session from JSON file with caching.

        This method supports both old and new state file formats for backward compatibility:
        - Old format: {'in_progress': {...}, 'completed_orders': [...]}
        - New format: Full state with metadata (session_id, timestamps, progress, etc.)

        Note: Uses JSON cache with short TTL (30s) for state files since they change frequently.
        Cache is invalidated after every write to ensure consistency.
        """
        state_file = self._get_state_file_path()

        if not os.path.exists(state_file):
            logger.debug("No existing session state found, starting fresh")
            self.session_packing_state = {'in_progress': {}, 'completed_orders': [], 'skipped_orders': []}
            return

        try:
            # OPTIMIZED: Use JSON cache for faster repeated reads
            # This helps when multiple workers/processes access the same state file
            # Note: Cache is invalidated after writes in _save_session_state()
            data = get_cached_json(state_file, default=None)

            if data is None:
                # File exists but couldn't be read (invalid JSON, etc.)
                logger.error("Could not load session state, starting fresh")
                self.session_packing_state = {'in_progress': {}, 'completed_orders': [], 'skipped_orders': []}
                return

            # Handle both old and new format (with version)
            if isinstance(data, dict) and 'data' in data:
                # Legacy format with version wrapper
                state_data = data['data']
            else:
                # Could be new format (with metadata) or old direct format
                state_data = data

            # Load core packing state with validation
            # CRITICAL FIX: Validate in_progress structure to prevent AttributeError on resume
            raw_in_progress = state_data.get('in_progress', {})
            validated_in_progress = {}

            if isinstance(raw_in_progress, dict):
                for order_num, order_state in raw_in_progress.items():
                    # Skip internal metadata keys (like _timing)
                    if order_num.startswith('_'):
                        continue

                    # Validate that order_state is a list
                    if not isinstance(order_state, list):
                        logger.error(
                            f"CRITICAL: Invalid order state for {order_num}: expected list, got {type(order_state).__name__}. "
                            f"Skipping this order to prevent crash."
                        )
                        continue

                    # Validate that each item in the list is a dict
                    validated_items = []
                    for idx, item_state in enumerate(order_state):
                        if not isinstance(item_state, dict):
                            logger.error(
                                f"CRITICAL: Invalid item state in order {order_num} at index {idx}: "
                                f"expected dict, got {type(item_state).__name__}. Skipping this item."
                            )
                            continue

                        # Ensure critical keys exist (be lenient for backward compatibility)
                        # Support multiple legacy formats for SKU identification:
                        # - New format: 'original_sku' and/or 'normalized_sku'
                        # - Legacy format: 'sku' (used by old tests and early versions)

                        # Check if item has any form of SKU identifier
                        has_sku = 'original_sku' in item_state or 'normalized_sku' in item_state or 'sku' in item_state

                        if has_sku:
                            # Migrate legacy 'sku' field to new format if needed
                            if 'sku' in item_state and 'original_sku' not in item_state:
                                item_state['original_sku'] = item_state['sku']
                                logger.debug(f"Migrated legacy 'sku' field to 'original_sku' in {order_num}")

                            if 'original_sku' in item_state and 'normalized_sku' not in item_state:
                                # Generate normalized_sku from original_sku if missing
                                item_state['normalized_sku'] = self._normalize_sku(item_state['original_sku'])
                                logger.debug(f"Generated normalized_sku from original_sku in {order_num}")
                            elif 'normalized_sku' in item_state and 'original_sku' not in item_state:
                                # Use normalized_sku as original_sku if original is missing
                                item_state['original_sku'] = item_state['normalized_sku']
                                logger.debug(f"Used normalized_sku as original_sku in {order_num}")

                            # Fill in missing optional fields with defaults
                            if 'packed' not in item_state:
                                item_state['packed'] = 0
                                logger.debug(f"Added default packed=0 for item in {order_num}")
                            if 'required' not in item_state:
                                item_state['required'] = 0
                                logger.debug(f"Added default required=0 for item in {order_num}")
                            if 'row' not in item_state:
                                item_state['row'] = idx
                                logger.debug(f"Added default row={idx} for item in {order_num}")

                            validated_items.append(item_state)
                        else:
                            logger.error(
                                f"CRITICAL: Item state in order {order_num} at index {idx} has no SKU identifier "
                                f"(missing 'original_sku', 'normalized_sku', and 'sku'). Skipping item."
                            )

                    # Only include orders with valid items
                    if validated_items:
                        validated_in_progress[order_num] = validated_items
                    else:
                        logger.warning(f"Order {order_num} has no valid items after validation, skipping")
            else:
                logger.error(f"in_progress is not a dict: {type(raw_in_progress).__name__}, using empty state")

            self.session_packing_state['in_progress'] = validated_in_progress
            logger.debug(f"Loaded and validated {len(validated_in_progress)} in-progress orders")

            # Handle both new format (completed: list of dicts) and old format (completed_orders: list of strings)
            if 'completed' in state_data:
                # New format: list of dicts with metadata
                completed_list = state_data.get('completed', [])
                if completed_list and isinstance(completed_list[0], dict):
                    # Extract order numbers from metadata dicts
                    self.session_packing_state['completed_orders'] = [
                        item['order_number'] for item in completed_list if 'order_number' in item
                    ]

                    # ✅ CRITICAL: Restore timing metadata for Phase 2b
                    self.completed_orders_metadata = []
                    for item in completed_list:
                        metadata = {
                            'order_number': item['order_number'],
                            'started_at': item.get('started_at'),
                            'completed_at': item.get('completed_at'),
                            'duration_seconds': item.get('duration_seconds', 0),
                            'items_count': item.get('items_count', 0),
                            'items': item.get('items', [])
                        }
                        self.completed_orders_metadata.append(metadata)

                    logger.info(f"Restored {len(self.completed_orders_metadata)} orders with timing metadata")
                else:
                    # Fallback if completed is just a list of strings
                    self.session_packing_state['completed_orders'] = completed_list
                    self.completed_orders_metadata = []
                    logger.debug("Loaded old format state (no timing metadata)")
            else:
                # Old format: simple list of order numbers
                self.session_packing_state['completed_orders'] = state_data.get('completed_orders', [])
                self.completed_orders_metadata = []
                logger.debug("Old format: no timing metadata available")

            # Restore skipped orders list
            self.session_packing_state['skipped_orders'] = state_data.get('skipped_orders', [])

            # Load metadata if present (new format)
            if 'session_id' in state_data:
                self.session_id = state_data.get('session_id')
                self.packing_list_name = state_data.get('packing_list_name')
                self.started_at = state_data.get('started_at')
                # worker_pc is set from environment in __init__, but can be overridden from state
                logger.debug(f"Loaded session metadata: {self.session_id}")

            # Phase 2b: Restore in-progress timing if present
            if 'in_progress' in state_data and '_timing' in state_data['in_progress']:
                timing_data = state_data['in_progress']['_timing']
                self.current_order_start_time = timing_data.get('current_order_start_time')
                self.current_order_items_scanned = timing_data.get('items_scanned', [])
                logger.debug(f"Restored in-progress timing: started_at={self.current_order_start_time}")
            else:
                self.current_order_start_time = None
                self.current_order_items_scanned = []

            in_progress_count = len(self.session_packing_state.get('in_progress', {}))
            completed_count = len(self.session_packing_state.get('completed_orders', []))

            logger.info(f"Session state loaded: {in_progress_count} in progress, {completed_count} completed")

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading session state: {e}, starting fresh")
            self.session_packing_state = {'in_progress': {}, 'completed_orders': [], 'skipped_orders': []}

    def _save_session_state(self):
        """
        Save the current session's packing state to JSON file with atomic write.

        New behavior (redesigned state management):
        - Saves complete state with metadata (session_id, timestamps, progress)
        - Does NOT create .backup files (deprecated)
        - State file is kept as permanent history after session completion
        - Uses atomic write pattern to prevent corruption during crashes

        State structure:
        {
            "session_id": "2025-11-10_1",
            "client_id": "M",
            "packing_list_name": "DHL_Orders",
            "started_at": "2025-11-10T14:30:00",
            "last_updated": "2025-11-10T15:45:23",
            "status": "in_progress",
            "pc_name": "WAREHOUSE-PC-01",
            "progress": {...},
            "in_progress": {...},
            "completed": [...]
        }
        """
        state_file = self._get_state_file_path()

        # Calculate progress metrics
        total_orders = len(self.orders_data) if self.orders_data else 0
        completed_orders_count = len(self.session_packing_state.get('completed_orders', []))
        in_progress_count = len(self.session_packing_state.get('in_progress', {}))

        # Calculate total and packed items
        total_items = 0
        packed_items = 0

        # Count items from processed_df if available
        if self.processed_df is not None:
            try:
                import pandas as pd
                total_items = int(pd.to_numeric(self.processed_df['Quantity'], errors='coerce').sum())
            except Exception as e:
                logger.warning(f"Could not calculate total_items: {e}")

        # Count packed items from completed orders
        if self.processed_df is not None and self.session_packing_state.get('completed_orders'):
            try:
                import pandas as pd
                completed_items = pd.to_numeric(
                    self.processed_df[
                        self.processed_df['Order_Number'].isin(self.session_packing_state['completed_orders'])
                    ]['Quantity'],
                    errors='coerce'
                ).sum()
                packed_items += int(completed_items)
            except Exception as e:
                logger.warning(f"Could not calculate packed items from completed orders: {e}")

        # Count packed items from in-progress orders
        for order_state in self.session_packing_state.get('in_progress', {}).values():
            if isinstance(order_state, list):
                # New format: list of item states
                for item in order_state:
                    if isinstance(item, dict):
                        packed_items += item.get('packed', 0)

        # Build complete state structure with metadata
        from shared.metadata_utils import get_current_timestamp

        state_data = {
            # Version
            "version": "1.3.0",

            # Metadata
            "session_id": self.session_id,
            "client_id": self.client_id,
            "packing_list_name": self.packing_list_name,
            "started_at": self.started_at,
            "last_updated": get_current_timestamp(),
            "status": "completed" if completed_orders_count == total_orders and total_orders > 0 else "in_progress",
            "pc_name": self.worker_pc,

            # Progress summary
            "progress": {
                "total_orders": total_orders,
                "completed_orders": completed_orders_count,
                "in_progress_order": self.current_order_number,
                "total_items": total_items,
                "packed_items": packed_items
            },

            # Skipped orders (preserved in in_progress, can be resumed)
            "skipped_orders": self.session_packing_state.get('skipped_orders', []),

            # Detailed packing state
            # Phase 2b: Add timing metadata for in-progress order
            "in_progress": {
                **self.session_packing_state.get('in_progress', {}),
                # Add timing data if there's a current order with timing info
                **({
                    "_timing": {
                        "current_order_start_time": self.current_order_start_time,
                        "items_scanned": self.current_order_items_scanned
                    }
                } if self.current_order_number and self.current_order_start_time else {})
            },
            # Phase 2b: Use completed_orders_metadata if available
            "completed": self.completed_orders_metadata if hasattr(self, 'completed_orders_metadata') and self.completed_orders_metadata else self._build_completed_list()
        }

        try:
            state_path = Path(state_file)
            state_dir = state_path.parent

            # Atomic write: write to temp file first
            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=state_dir,
                prefix='.tmp_state_',
                suffix='.json',
                delete=False,
                encoding='utf-8'
            ) as tmp_file:
                json.dump(state_data, tmp_file, indent=2, ensure_ascii=False)
                tmp_path = tmp_file.name

            # Atomic replace (works on Windows too)
            shutil.move(tmp_path, state_file)

            # OPTIMIZED: Invalidate JSON cache after write to ensure fresh data on next read
            # This prevents serving stale cached data after state changes
            invalidate_json_cache(state_file)

            logger.debug(f"Session state saved: {completed_orders_count}/{total_orders} orders, {packed_items}/{total_items} items")

        except Exception as e:
            logger.error(f"CRITICAL: Failed to save session state: {e}", exc_info=True)

    def _build_completed_list(self) -> List[Dict[str, Any]]:
        """
        Build list of completed orders with timestamps and durations.

        Returns:
            List of dicts with order metadata:
            [
                {
                    "order_number": "ORDER-001",
                    "completed_at": "2025-11-10T14:35:12",
                    "items_count": 3,
                    "duration_seconds": 45
                }
            ]

        Note: This is a basic implementation. Full timestamps tracking requires
        storing start time for each order (future enhancement).
        """
        completed_list = []

        for order_number in self.session_packing_state.get('completed_orders', []):
            # Get items count for this order
            items_count = 0
            if order_number in self.orders_data:
                items_count = len(self.orders_data[order_number].get('items', []))

            from shared.metadata_utils import get_current_timestamp

            completed_list.append({
                "order_number": order_number,
                "completed_at": get_current_timestamp(),  # Approximation
                "items_count": items_count
                # duration_seconds: Cannot calculate without start time (future enhancement)
            })

        return completed_list

    def _complete_current_order(self):
        """Complete current order with timing metadata

        Called when all items in order are scanned. Records completion time,
        calculates duration, and stores detailed timing data for analytics.

        Phase 2b: Enhanced timing tracking
        """
        from shared.metadata_utils import get_current_timestamp, calculate_duration

        if not self.current_order_number:
            logger.warning("_complete_current_order called but no current order")
            return

        # Record completion time
        completed_at = get_current_timestamp()

        # Calculate order duration
        if self.current_order_start_time:
            duration_seconds = calculate_duration(
                self.current_order_start_time,
                completed_at
            )
        else:
            duration_seconds = 0
            logger.warning(f"Order {self.current_order_number} has no start time")

        # Build order metadata record
        order_metadata = {
            "order_number": self.current_order_number,
            "started_at": self.current_order_start_time,
            "completed_at": completed_at,
            "duration_seconds": duration_seconds,
            "items_count": len(self.current_order_items_scanned),
            "items": self.current_order_items_scanned.copy()  # Full items with timestamps
        }

        # Add to completed orders metadata
        self.completed_orders_metadata.append(order_metadata)

        logger.info(
            f"Order {self.current_order_number} completed: "
            f"duration={duration_seconds}s, items={len(self.current_order_items_scanned)}"
        )

        # Note: We don't reset current_order_number here because it's still needed
        # for legacy state management. The reset happens in clear_current_order() or
        # when starting a new order.

    def _initialize_session_metadata(self, session_id: str = None, packing_list_name: str = None):
        """
        Initialize session metadata for state tracking.

        This should be called when starting a new packing session (loading packing list).
        Sets up timestamps and identifiers for the session.

        Args:
            session_id: Unique session identifier (e.g., "2025-11-10_1")
            packing_list_name: Name of the packing list being packed (e.g., "DHL_Orders")
        """
        if not self.started_at:
            # Only set started_at if not already set (for session restoration)
            from shared.metadata_utils import get_current_timestamp
            self.started_at = get_current_timestamp()

        if session_id:
            self.session_id = session_id
        elif not self.session_id:
            # Generate session_id from timestamp if not provided
            self.session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        if packing_list_name:
            self.packing_list_name = packing_list_name

        logger.info(f"Session metadata initialized: {self.session_id} / {self.packing_list_name}")

    def _normalize_sku(self, sku: Any) -> str:
        """
        Normalizes an SKU for consistent comparison across different input sources.

        This normalization is essential for small warehouse operations where SKUs/barcodes
        can come from multiple sources with inconsistent formatting:
        - Manual Excel entry: may include spaces, dashes, parentheses
        - Barcode scanners: may add prefixes/suffixes depending on configuration
        - Different suppliers: varying formatting conventions
        - Copy-paste from supplier websites: may include special characters

        The normalization algorithm:
        1. Convert to string (handles numeric SKUs like "12345")
        2. Remove all non-alphanumeric characters (spaces, dashes, dots, etc.)
        3. Convert to lowercase (handles case-insensitive matching)

        Examples:
            "SKU-123-A" -> "sku123a"
            "7290 0186 6410 0" -> "72900186641100"
            "Product (ABC)" -> "productabc"
            12345 -> "12345"

        Args:
            sku (Any): The SKU to normalize, typically a string or number.
                      Can be Excel cell value (str, int, float)

        Returns:
            str: The normalized SKU string (lowercase alphanumeric only)
        """
        return ''.join(filter(str.isalnum, str(sku))).lower()

    def normalize_sku(self, sku: Any) -> str:
        """Public API for SKU normalization. See _normalize_sku for details."""
        return self._normalize_sku(sku)

    def _normalize_order_number(self, order_number: str) -> str:
        """
        Normalize order number for barcode matching.

        Identical to Shopify Tool's sanitize_order_number().
        This ensures scanned barcodes match orders regardless of special characters.

        The normalization removes special characters but preserves structural elements:
        - Keeps: alphanumeric (a-z, A-Z, 0-9), hyphen (-), underscore (_)
        - Removes: #, !, spaces, quotes, and all other special chars
        - Preserves: Case sensitivity (unlike SKU normalization)

        This allows barcodes generated by Shopify Tool to match order numbers
        stored in analysis_data.json even if the original CSV had special characters.

        Examples:
            "#1001" -> "1001"
            "ORD-123!" -> "ORD-123"
            "Test Order" -> "TestOrder"
            "ABC_123-X" -> "ABC_123-X"

        Args:
            order_number: The order number to normalize

        Returns:
            Normalized order number (alphanumeric + dash + underscore only)

        Note:
            Empty strings or None return empty string.
            Order numbers with only special chars (e.g., "###") return empty string.
        """
        if not order_number:
            return ""

        # Same normalization as Shopify Tool's sanitize_order_number()
        normalized = ''.join(c for c in str(order_number) if c.isalnum() or c in ['-', '_'])

        # Log warning if order number becomes empty after normalization
        if not normalized:
            logger.warning(f"Order number '{order_number}' has no valid alphanumeric characters")

        return normalized

    def start_order_packing(self, scanned_text: str) -> Tuple[List[Dict] | None, str]:
        """
        Starts or resumes packing an order based on a scanned barcode.

        It looks up the order number, validates its status (e.g., not already
        completed), and loads its packing state into memory.

        Args:
            scanned_text (str): The content from the scanned order barcode.

        Returns:
            Tuple[List[Dict] | None, str]: A tuple containing the list of items
                                           for the order and a status string
                                           ("ORDER_LOADED", "ORDER_NOT_FOUND",
                                           "ORDER_ALREADY_COMPLETED").
        """
        # STEP 1: Find order using normalized comparison
        scanned_normalized = self._normalize_order_number(scanned_text)
        logger.debug(f"Scanned text: '{scanned_text}' -> Normalized: '{scanned_normalized}'")

        # Find matching order in orders_data
        matched_order_number = None
        for order_number in self.orders_data.keys():
            order_normalized = self._normalize_order_number(order_number)
            if scanned_normalized == order_normalized:
                matched_order_number = order_number
                logger.debug(f"Match found: '{scanned_text}' matches order '{order_number}'")
                break

        if not matched_order_number:
            logger.info(f"Order not found for scanned text: '{scanned_text}'")
            return None, "ORDER_NOT_FOUND"

        original_order_number = matched_order_number

        if original_order_number in self.session_packing_state['completed_orders']:
            return None, "ORDER_ALREADY_COMPLETED"

        # If order was previously skipped, remove from skipped list so it can be resumed
        skipped = self.session_packing_state.setdefault('skipped_orders', [])
        if original_order_number in skipped:
            skipped.remove(original_order_number)
            logger.info(f"Order {original_order_number} removed from skipped list (resuming)")

        self.current_order_number = original_order_number
        items = self.orders_data[original_order_number]['items']

        in_progress = self.session_packing_state.setdefault('in_progress', {})
        if original_order_number in in_progress:
            self.current_order_state = in_progress[original_order_number]
        else:
            self.current_order_state = []
            for i, item in enumerate(items):
                sku = item.get('SKU')
                if not sku: continue
                try:
                    quantity = int(float(item.get('Quantity', 0)))
                except (ValueError, TypeError):
                    quantity = 1

                normalized_sku = self._normalize_sku(sku)
                self.current_order_state.append({
                    'original_sku': sku,
                    'normalized_sku': normalized_sku,
                    'required': quantity,
                    'packed': 0,
                    'row': i
                })
            in_progress[original_order_number] = self.current_order_state
            self._save_session_state()

        # Phase 2b: Record order start time
        from shared.metadata_utils import get_current_timestamp
        self.current_order_start_time = get_current_timestamp()
        self.current_order_items_scanned = []

        logger.info(f"Order {original_order_number} started at {self.current_order_start_time}")

        return items, "ORDER_LOADED"

    def process_sku_scan(self, sku: str) -> Tuple[Dict | None, str]:
        """
        Processes a scanned SKU for the currently active order.

        This is the core method called every time a warehouse worker scans a product
        barcode. It handles:
        1. SKU normalization (to handle different barcode formats)
        2. SKU mapping translation (manufacturer barcode -> internal SKU)
        3. Matching against order requirements
        4. Updating packing progress
        5. Detecting order completion
        6. Persisting state after every scan (crash recovery)

        The method implements a sophisticated matching logic that:
        - Tries to find the SKU in the current order
        - Supports multi-quantity items (scan same SKU multiple times)
        - Detects when an item is fully packed
        - Detects when entire order is complete
        - Handles error cases (wrong SKU, already packed, etc.)

        Args:
            sku (str): The raw content from the scanned product SKU barcode.
                      Can be any format (EAN-13, UPC, manufacturer code, internal SKU)

        Returns:
            Tuple[Dict | None, str]: A tuple containing:
                - Result dictionary with packing details (if successful)
                  {"row": int, "packed": int, "is_complete": bool}
                - Status string indicating what happened:
                  * "SKU_OK" - Item packed successfully, order still in progress
                  * "ORDER_COMPLETE" - Item packed and order is now complete
                  * "SKU_NOT_FOUND" - Scanned SKU is not in this order
                  * "SKU_EXTRA" - All items with this SKU are already packed
                  * "NO_ACTIVE_ORDER" - No order currently selected
        """
        # Safety check: ensure an order is actually loaded
        # This prevents errors if user somehow scans before loading an order
        if not self.current_order_number:
            return None, "NO_ACTIVE_ORDER"

        # === STEP 1: Normalize scanned barcode ===
        # Remove spaces, dashes, convert to lowercase
        # This handles variations in scanner configuration and barcode formats
        normalized_scan = self._normalize_sku(sku)

        # === STEP 2: SKU Mapping Translation (if configured) ===
        # This is a critical feature for small warehouses where:
        # - Products come from multiple suppliers with different barcodes
        # - Manufacturer barcodes don't match internal SKU system
        # - Same product has different barcodes from different batches
        #
        # Example scenarios:
        #   Scan: "7290018664100" (EAN-13 barcode)
        #   Map:  "7290018664100" -> "SKU-CREAM-01" (internal SKU)
        #   Use:  "SKU-CREAM-01" for matching
        #
        # Fallback behavior:
        #   If no mapping exists, use the scanned barcode directly
        #   This ensures backward compatibility with orders that use
        #   manufacturer barcodes directly in the packing list
        final_sku = self.sku_map.get(normalized_scan, normalized_scan)

        # Normalize the final SKU (whether mapped or direct)
        # This ensures consistent matching even if mapping returns non-normalized value
        normalized_final_sku = self._normalize_sku(final_sku)

        # The rest of the logic uses the potentially translated SKU.
        normalized_final_sku = self._normalize_sku(final_sku)

        # === STEP 3: Find matching item in current order ===
        # Search through all items in the order for a match
        # Important: we look for the FIRST item that:
        # 1. Matches the SKU
        # 2. Is not yet fully packed (packed < required)
        #
        # This handles multi-quantity items correctly:
        # Example: Order requires 3x "SKU-CREAM-01"
        # - First scan: packed=0 -> packed=1
        # - Second scan: packed=1 -> packed=2
        # - Third scan: packed=2 -> packed=3 (complete!)
        found_item = None
        for item_state in self.current_order_state:
            if item_state['normalized_sku'] == normalized_final_sku and item_state['packed'] < item_state['required']:
                found_item = item_state
                break

        # === STEP 4: Process successful match ===
        if found_item:
            # Increment packed count for this item
            found_item['packed'] += 1

            # Check if this specific item is now complete
            # (all required quantity for this SKU has been packed)
            is_complete = found_item['packed'] == found_item['required']

            # Phase 2b: Record item scan with timestamp
            from shared.metadata_utils import get_current_timestamp, calculate_duration

            scan_timestamp = get_current_timestamp()

            # Calculate time from order start
            if self.current_order_start_time:
                time_from_order_start = calculate_duration(
                    self.current_order_start_time,
                    scan_timestamp
                )
            else:
                time_from_order_start = 0
                logger.warning("Order start time not set, cannot calculate timing")

            # Get item details from orders_data
            items_list = self.orders_data[self.current_order_number]['items']
            item_idx = found_item['row']

            # Build item scan record
            item_scan_record = {
                "sku": normalized_final_sku,
                "title": items_list[item_idx].get('Product_Name', normalized_final_sku),
                "quantity": found_item['required'],
                "scanned_at": scan_timestamp,
                "time_from_order_start_seconds": time_from_order_start
            }

            # Add to scanned items list
            self.current_order_items_scanned.append(item_scan_record)

            logger.debug(f"Item {normalized_final_sku} scanned at +{time_from_order_start}s from order start")

            # Update session state (in-memory)
            self.session_packing_state.setdefault('in_progress', {})[self.current_order_number] = self.current_order_state

            # === Check if ENTIRE order is complete ===
            # An order is complete when ALL items have been packed
            # (not just the current item)
            all_items_complete = all(s['packed'] == s['required'] for s in self.current_order_state)

            if all_items_complete:
                # Order is complete!
                status = "ORDER_COMPLETE"

                # Phase 2b: Complete order with timing metadata
                self._complete_current_order()

                # Move order from "in_progress" to "completed_orders"
                self.session_packing_state.get('in_progress', {}).pop(self.current_order_number, None)

                # Add to completed list (deduplicated)
                completed = self.session_packing_state.setdefault('completed_orders', [])
                if self.current_order_number not in completed:
                    completed.append(self.current_order_number)
            else:
                # Order still in progress
                status = "SKU_OK"

                # Calculate overall progress for this order
                # (total items packed vs total items required)
                total_packed = sum(s['packed'] for s in self.current_order_state)
                total_required = sum(s['required'] for s in self.current_order_state)

                # Emit Qt signal to update UI progress display
                # This allows the UI to show "5/8 items packed" in real-time
                self.item_packed.emit(self.current_order_number, total_packed, total_required)

            # === CRITICAL: Save state to disk ===
            # This is called after EVERY successful scan to ensure:
            # - No data loss if application crashes
            # - Session can be restored exactly where we left off
            # - Multi-PC environments see consistent state
            self._save_session_state()

            # Return success with detailed information
            return {"row": found_item['row'], "packed": found_item['packed'], "is_complete": is_complete}, status

        # === STEP 5: Handle error cases ===
        # If we reach here, the scanned SKU didn't match any unpacked item

        # Check if SKU exists in order but all items are already packed
        is_sku_in_order = any(s['normalized_sku'] == normalized_final_sku for s in self.current_order_state)

        if is_sku_in_order:
            # SKU is in order, but all required quantity already packed
            # Example: Order needs 2x "SKU-CREAM-01", but user scanned it 3 times
            return None, "SKU_EXTRA"  # All items with this SKU are already packed
        else:
            # SKU is not in this order at all
            # Example: User scanned wrong product, or product from different order
            return None, "SKU_NOT_FOUND"

    def clear_current_order(self):
        """Clears the currently active order from memory."""
        self.current_order_number = None
        self.current_order_state = {}

    def get_order_metadata(self, order_number: str) -> dict:
        """
        Returns the Shopify metadata dict for the given order.

        Contains: system_note, internal_tags, tags, created_at, status,
                  recommended_box, shipping_method, courier.

        Returns an empty dict if the order is not found or has no metadata.
        """
        if order_number and order_number in self.orders_data:
            return self.orders_data[order_number].get('metadata', {})
        return {}

    def skip_order(self) -> bool:
        """
        Marks the currently active order as skipped.

        The order's in-progress packing state is preserved so it can be resumed
        by scanning the order barcode again. The order is added to the
        'skipped_orders' list in the session state and cleared as the active order.

        Returns:
            True if an order was successfully skipped, False if no active order.
        """
        if not self.current_order_number:
            logger.warning("skip_order called but no active order")
            return False

        order_num = self.current_order_number
        skipped = self.session_packing_state.setdefault('skipped_orders', [])
        if order_num not in skipped:
            skipped.append(order_num)

        # Preserve in_progress state — do NOT remove from session_packing_state['in_progress']
        self.current_order_number = None
        self.current_order_state = []
        self.current_order_start_time = None
        self.current_order_items_scanned = []
        self._save_session_state()

        logger.info(f"Order {order_num} skipped (state preserved for resume)")
        return True

    def load_packing_list_json(self, packing_list_path: Path) -> Tuple[int, str]:
        """
        Завантажити конкретний пакінг лист з JSON файлу.

        This method loads a specific packing list JSON file generated by Shopify Tool.
        Packing list JSONs are pre-filtered collections of orders ready for packing,
        typically organized by courier or delivery method.

        Expected JSON format:
        {
          "list_name": "DHL_Orders",
          "created_at": "2025-11-11T10:00:00",
          "courier": "DHL",  # Optional, if list is courier-specific
          "total_orders": 25,
          "orders": [
            {
              "order_number": "ORDER-001",
              "courier": "DHL",
              "items": [
                {"sku": "SKU-123", "quantity": 2, "product_name": "Product A"}
              ]
            }
          ]
        }

        Args:
            packing_list_path: Повний шлях до JSON файлу пакінг листа
                              (e.g., .../packing_lists/DHL_Orders.json)

        Returns:
            Tuple[int, str]: (кількість замовлень, назва листа)

        Raises:
            ValueError: Якщо файл не існує або невалідний JSON
            RuntimeError: If barcode generation fails
        """
        logger.info(f"Loading packing list from: {packing_list_path}")

        # Validate file exists
        packing_list_path = Path(packing_list_path)
        if not packing_list_path.exists():
            error_msg = f"Packing list file not found: {packing_list_path}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Extract list name from filename (without .json extension)
        list_name = packing_list_path.stem

        # Load JSON data
        try:
            with open(packing_list_path, 'r', encoding='utf-8') as f:
                packing_data = json.load(f)

            logger.debug(f"Loaded packing list: {packing_data.get('list_name', list_name)}")

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in packing list file: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Error reading packing list file: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Extract orders list
        orders_list = packing_data.get('orders', [])
        if not orders_list:
            logger.warning(f"No orders found in packing list: {list_name}")
            return 0, packing_data.get('list_name', list_name)

        # Convert to DataFrame (packing list format)
        # Each order may have multiple items, need to flatten
        rows = []
        order_metadata_map = {}  # order_number -> metadata dict

        for order in orders_list:
            # Validate required order fields
            if 'order_number' not in order:
                error_msg = f"Missing required field 'order_number' in order data"
                logger.error(error_msg)
                raise ValueError(error_msg)

            order_number = order['order_number']
            # Normalize courier: handle missing, None, or non-string values
            courier = str(order.get('courier', '')).strip() or 'N/A'
            items = order.get('items', [])

            if not items:
                logger.warning(f"Order {order_number} has no items, skipping")
                continue

            # Extract Shopify metadata fields for this order
            # Handle field name variants between analysis_data.json and packing_lists
            internal_tags_raw = order.get('internal_tags', [])
            tags_raw = order.get('tags', [])
            tags_list = tags_raw if isinstance(tags_raw, list) else [tags_raw] if tags_raw else []
            tags_list = [str(t) for t in tags_list if t and str(t).lower() not in ('nan', 'none')]
            order_metadata_map[order_number] = {
                'system_note': order.get('system_note', ''),
                'status_note': order.get('status_note', ''),
                'internal_tags': internal_tags_raw if isinstance(internal_tags_raw, list) else [internal_tags_raw] if internal_tags_raw else [],
                'tags': tags_list,
                'created_at': order.get('created_at', ''),
                'status': order.get('status', '') or order.get('fulfillment_status', ''),
                'recommended_box': order.get('recommended_box', '') or order.get('min_box', ''),
                'shipping_method': order.get('shipping_method', ''),
                'destination': order.get('destination', '') or order.get('shipping_country', ''),
                'order_type': order.get('order_type', ''),
                'courier': courier,
            }

            for item in items:
                row = {
                    'Order_Number': order_number,
                    'SKU': item.get('sku', ''),
                    'Product_Name': item.get('product_name', ''),
                    'Quantity': str(item.get('quantity', 1)),  # Convert to string for consistency
                    'Courier': courier
                }

                # Add any extra fields from order
                # (e.g., customer name, address, tracking number, etc.)
                for key, value in order.items():
                    if key not in ['order_number', 'courier', 'items', 'system_note',
                                   'status_note', 'internal_tags', 'tags', 'created_at',
                                   'status', 'fulfillment_status', 'recommended_box',
                                   'min_box', 'shipping_method', 'destination',
                                   'shipping_country', 'order_type']:
                        # Capitalize key to match packing list style
                        formatted_key = key.replace('_', ' ').title().replace(' ', '_')
                        row[formatted_key] = str(value)

                rows.append(row)

        # Create DataFrame
        df = pd.DataFrame(rows)

        if df.empty:
            logger.warning("No order items to process")
            return 0, packing_data.get('list_name', list_name)

        # Validate required columns
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            error_msg = f"Missing required columns in packing list: {missing_cols}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Store as packing_list_df and processed_df
        self.packing_list_df = df
        self.processed_df = df.copy()

        logger.info(f"Converted {len(df)} items from {len(orders_list)} orders to DataFrame")

        # Group items by order and populate orders_data
        self.orders_data = {}
        for order_number in df['Order_Number'].unique():
            order_df = df[df['Order_Number'] == order_number]
            self.orders_data[order_number] = {
                'items': order_df.to_dict('records'),
                'metadata': order_metadata_map.get(order_number, {})
            }

        # Initialize session metadata
        # Extract session_id from path if available (e.g., .../Sessions/CLIENT_M/2025-11-10_1/...)
        session_id = None
        try:
            # Try to extract session_id from path (parent directory name)
            parent_path = packing_list_path.parent
            if parent_path.name == 'packing_lists':
                # Path is .../packing_lists/list.json, go up one more level
                session_dir = parent_path.parent
                session_id = session_dir.name
        except Exception as e:
            logger.debug(f"Could not extract session_id from path: {e}")

        self._initialize_session_metadata(
            session_id=session_id,
            packing_list_name=packing_data.get('list_name', list_name)
        )

        # Count orders (barcodes pre-generated by Shopify Tool)
        try:
            order_count = len(self.orders_data)
            logger.info(f"Successfully loaded packing list '{list_name}': {order_count} orders")

            return order_count, packing_data.get('list_name', list_name)

        except Exception as e:
            error_msg = f"Error generating barcodes from packing list: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)

    def load_from_shopify_analysis(self, session_path: Path) -> Tuple[int, str]:
        """
        Load orders data from Shopify Tool's analysis_data.json.

        This method enables integration with Shopify Tool (Phase 1.3.2).
        It reads analysis_data.json from a Shopify session and converts it
        into the packing_list format expected by PackerLogic.

        Workflow:
        1. Read analysis_data.json from session/analysis/
        2. Convert Shopify order format to packing list DataFrame
        3. Generate barcodes for all orders
        4. Initialize orders_data structure

        Analysis data format (from Shopify Tool):
        {
          "analyzed_at": "2025-11-04T11:00:00",
          "total_orders": 150,
          "fulfillable_orders": 142,
          "orders": [
            {
              "order_number": "ORDER-001",
              "courier": "DHL",
              "status": "Fulfillable",
              "items": [
                {"sku": "SKU-123", "quantity": 2, "product_name": "Product A"}
              ]
            }
          ]
        }

        Args:
            session_path: Path to Shopify session directory
                         (e.g., Sessions/CLIENT_M/2025-11-04_1/)

        Returns:
            Tuple of (order_count, analysis_timestamp)

        Raises:
            ValueError: If analysis_data.json not found or invalid format
            RuntimeError: If barcode generation fails
        """
        logger.info(f"Loading data from Shopify session: {session_path}")

        # Locate analysis_data.json
        analysis_file = Path(session_path) / "analysis" / "analysis_data.json"

        if not analysis_file.exists():
            error_msg = f"analysis_data.json not found in {session_path}/analysis/"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Load analysis data
        try:
            with open(analysis_file, 'r', encoding='utf-8') as f:
                analysis_data = json.load(f)

            logger.debug(f"Loaded analysis data: {analysis_data.get('total_orders', 0)} orders")

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in analysis_data.json: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Error reading analysis_data.json: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Extract orders list
        orders_list = analysis_data.get('orders', [])
        if not orders_list:
            logger.warning("No orders found in analysis_data.json")
            return 0, analysis_data.get('analyzed_at', 'Unknown')

        # Convert to DataFrame (packing list format)
        # Each order may have multiple items, need to flatten
        rows = []
        order_metadata_map = {}  # order_number -> metadata dict

        for order in orders_list:
            # Validate required order fields
            missing_fields = []
            if 'order_number' not in order:
                missing_fields.append('order_number')

            if missing_fields:
                error_msg = f"Missing required columns in order data: {missing_fields}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            order_number = order['order_number']
            # Courier is optional in analysis_data.json (contains all orders before filtering)
            # Use default value if not present
            courier = order.get('courier', 'N/A')
            items = order.get('items', [])

            # Extract Shopify metadata fields for this order
            # Handle field name variants between analysis_data.json and packing_lists
            internal_tags_raw = order.get('internal_tags', [])
            tags_raw = order.get('tags', [])
            tags_list = tags_raw if isinstance(tags_raw, list) else [tags_raw] if tags_raw else []
            tags_list = [str(t) for t in tags_list if t and str(t).lower() not in ('nan', 'none')]
            order_metadata_map[order_number] = {
                'system_note': order.get('system_note', ''),
                'status_note': order.get('status_note', ''),
                'internal_tags': internal_tags_raw if isinstance(internal_tags_raw, list) else [internal_tags_raw] if internal_tags_raw else [],
                'tags': tags_list,
                'created_at': order.get('created_at', ''),
                'status': order.get('status', '') or order.get('fulfillment_status', ''),
                'recommended_box': order.get('recommended_box', '') or order.get('min_box', ''),
                'shipping_method': order.get('shipping_method', ''),
                'destination': order.get('destination', '') or order.get('shipping_country', ''),
                'order_type': order.get('order_type', ''),
                'courier': courier,
            }

            for item in items:
                row = {
                    'Order_Number': order_number,
                    'SKU': item.get('sku', ''),
                    'Product_Name': item.get('product_name', ''),
                    'Quantity': str(item.get('quantity', 1)),  # Convert to string for consistency
                    'Courier': courier
                }

                # Add any extra fields from Shopify analysis
                # (e.g., customer name, address, etc.)
                for key, value in order.items():
                    if key not in ['order_number', 'courier', 'items', 'status',
                                   'system_note', 'internal_tags', 'tags', 'created_at',
                                   'recommended_box', 'shipping_method']:
                        # Capitalize key to match packing list style
                        formatted_key = key.replace('_', ' ').title().replace(' ', '_')
                        row[formatted_key] = str(value)

                rows.append(row)

        # Create DataFrame
        df = pd.DataFrame(rows)

        if df.empty:
            logger.warning("No order items to process")
            return 0, analysis_data.get('analyzed_at', 'Unknown')

        # Validate required columns
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            error_msg = f"Missing required columns in analysis data: {missing_cols}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Store as packing_list_df and processed_df
        self.packing_list_df = df
        self.processed_df = df.copy()

        logger.info(f"Converted {len(df)} items from {len(orders_list)} orders to DataFrame")

        # Group items by order and populate orders_data
        self.orders_data = {}
        for order_number in df['Order_Number'].unique():
            order_df = df[df['Order_Number'] == order_number]
            self.orders_data[order_number] = {
                'items': order_df.to_dict('records'),
                'metadata': order_metadata_map.get(order_number, {})
            }

        # Initialize session metadata
        # Extract session_id from session_path (e.g., .../Sessions/CLIENT_M/2025-11-10_1)
        session_id = Path(session_path).name
        packing_list_name = "Shopify_Full_Session"

        self._initialize_session_metadata(
            session_id=session_id,
            packing_list_name=packing_list_name
        )

        # Count orders (barcodes pre-generated by Shopify Tool)
        try:
            order_count = len(self.orders_data)
            logger.info(f"Successfully loaded Shopify session: {order_count} orders")

            return order_count, analysis_data.get('analyzed_at', 'Unknown')

        except Exception as e:
            error_msg = f"Error loading Shopify data: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)

    def generate_session_summary(
        self,
        worker_id: str = None,
        worker_name: str = None,
        session_type: str = "shopify"
    ) -> dict:
        """
        Generate comprehensive session summary upon completion.

        Creates a unified v1.3.0 format session summary with:
        - Session metadata (ID, client, packing list, timestamps, worker info)
        - Counts (total orders, completed orders, items, unique SKUs)
        - Performance metrics (orders/hour, items/hour, average times)

        Args:
            worker_id: Worker who completed session (e.g., "worker_001")
            worker_name: Worker display name (e.g., "Dolphin")
            session_type: "shopify" or "excel"

        Returns:
            dict: Unified session summary (v1.3.0 format, ready for JSON serialization)

        Example structure:
        {
            "version": "1.3.0",
            "session_id": "2025-11-10_1",
            "session_type": "shopify",
            "client_id": "M",
            "packing_list_name": "DHL_Orders",
            "worker_id": "worker_001",
            "worker_name": "Dolphin",
            "pc_name": "WAREHOUSE-PC-01",
            "started_at": "2025-11-10T14:30:00+02:00",
            "completed_at": "2025-11-10T16:20:45+02:00",
            "duration_seconds": 6645,
            "total_orders": 45,
            "completed_orders": 45,
            "total_items": 156,
            "unique_skus": 42,
            "metrics": {
                "avg_time_per_order": 147.6,
                "avg_time_per_item": 42.6,
                "fastest_order_seconds": 0,
                "slowest_order_seconds": 0,
                "orders_per_hour": 24.3,
                "items_per_hour": 84.2
            },
            "orders": []
        }
        """
        from shared.metadata_utils import get_current_timestamp, calculate_duration

        logger.info("Generating session summary (v1.3.0 format)")

        # Calculate timestamps and duration
        completed_at = get_current_timestamp()
        duration_seconds = 0

        if self.started_at:
            duration_seconds = calculate_duration(self.started_at, completed_at)
            if duration_seconds == 0:
                # Fallback to old method if calculate_duration fails
                try:
                    started_dt = datetime.fromisoformat(self.started_at)
                    completed_dt = datetime.now()
                    duration_seconds = int((completed_dt - started_dt).total_seconds())
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse started_at for duration calculation: {e}")

        # Calculate order and item counts
        total_orders = len(self.orders_data) if self.orders_data else 0
        completed_orders = len(self.session_packing_state.get('completed_orders', []))

        # Calculate total items
        total_items = 0
        if self.processed_df is not None:
            try:
                import pandas as pd
                total_items = int(pd.to_numeric(self.processed_df['Quantity'], errors='coerce').sum())
            except Exception as e:
                logger.warning(f"Could not calculate total_items: {e}")

        # Count unique SKUs
        unique_skus = self._count_unique_skus()

        # Phase 2b: Calculate metrics from completed_orders_metadata
        if hasattr(self, 'completed_orders_metadata') and self.completed_orders_metadata:
            orders_with_timing = self.completed_orders_metadata

            # Extract durations
            durations = [
                order['duration_seconds']
                for order in orders_with_timing
                if order.get('duration_seconds')
            ]

            # Calculate order-level metrics
            if durations:
                avg_time_per_order = round(sum(durations) / len(durations), 1)
                fastest_order_seconds = min(durations)
                slowest_order_seconds = max(durations)
            else:
                avg_time_per_order = 0
                fastest_order_seconds = 0
                slowest_order_seconds = 0

            # Calculate item-level metrics
            all_items = []
            for order in orders_with_timing:
                all_items.extend(order.get('items', []))

            if all_items:
                item_times = [
                    item['time_from_order_start_seconds']
                    for item in all_items
                    if 'time_from_order_start_seconds' in item
                ]
                avg_time_per_item = round(sum(item_times) / len(item_times), 1) if item_times else 0
            else:
                avg_time_per_item = 0

            # Total items from metadata
            total_items_from_metadata = sum(order.get('items_count', 0) for order in orders_with_timing)

        else:
            # Fallback for old sessions without timing
            logger.warning("No timing metadata available, using fallback calculations")
            avg_time_per_order = 0
            avg_time_per_item = 0
            fastest_order_seconds = 0
            slowest_order_seconds = 0
            total_items_from_metadata = 0

        # Session-level performance (orders_per_hour, items_per_hour)
        orders_per_hour = 0
        items_per_hour = 0

        if duration_seconds and duration_seconds > 0:
            hours = duration_seconds / 3600.0

            if completed_orders > 0:
                orders_per_hour = round(completed_orders / hours, 1)

            # Use metadata total_items if available, otherwise fallback to processed_df total
            items_for_rate = total_items_from_metadata if total_items_from_metadata > 0 else total_items
            if items_for_rate > 0:
                items_per_hour = round(items_for_rate / hours, 1)

        # Build unified v1.3.0 session summary
        summary = {
            # Metadata
            "version": "1.3.0",
            "session_id": self.session_id,
            "session_type": session_type,
            "client_id": self.client_id,
            "packing_list_name": self.packing_list_name,

            # Ownership
            "worker_id": worker_id,
            "worker_name": worker_name if worker_name else "Unknown",
            "pc_name": self.worker_pc,

            # Timing
            "started_at": self.started_at,
            "completed_at": completed_at,
            "duration_seconds": duration_seconds,

            # Counts
            "total_orders": total_orders,
            "completed_orders": completed_orders,
            "total_items": total_items,
            "unique_skus": unique_skus,

            # Metrics
            "metrics": {
                "avg_time_per_order": avg_time_per_order,
                "avg_time_per_item": avg_time_per_item,
                "fastest_order_seconds": fastest_order_seconds,  # Phase 2b: Real data from timing
                "slowest_order_seconds": slowest_order_seconds,   # Phase 2b: Real data from timing
                "orders_per_hour": orders_per_hour,
                "items_per_hour": items_per_hour
            },

            # Phase 2b: Populate orders array with timing data
            "orders": self.completed_orders_metadata if hasattr(self, 'completed_orders_metadata') else []
        }

        logger.info(
            f"Session summary generated (v1.3.0): {completed_orders}/{total_orders} orders, "
            f"{total_items} items, {unique_skus} unique SKUs, "
            f"{duration_seconds}s duration, {orders_per_hour} orders/hour"
        )

        return summary

    def _count_unique_skus(self) -> int:
        """Count unique SKUs across all orders

        Returns:
            int: Number of unique SKUs in the packing list
        """
        if self.processed_df is None:
            return 0

        try:
            unique_skus = self.processed_df['SKU'].nunique()
            return int(unique_skus)
        except Exception as e:
            logger.warning(f"Could not count unique SKUs: {e}")
            return 0

    def save_session_summary(
        self,
        summary_path: str = None,
        worker_id: str = None,
        worker_name: str = None,
        session_type: str = "shopify"
    ) -> str:
        """
        Generate and save session summary to JSON file.

        Args:
            summary_path: Optional path to save summary. If None, saves to work_dir/session_summary.json
            worker_id: Worker who completed session (e.g., "worker_001")
            worker_name: Worker display name (e.g., "Dolphin")
            session_type: "shopify" or "excel"

        Returns:
            Path to saved summary file

        Raises:
            IOError: If summary cannot be written to disk
        """
        # Generate summary with worker info
        summary = self.generate_session_summary(
            worker_id=worker_id,
            worker_name=worker_name,
            session_type=session_type
        )

        # Determine output path
        if not summary_path:
            summary_path = self._get_summary_file_path()

        # Save to file
        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

            logger.info(f"Session summary (v1.3.0) saved to: {summary_path}")
            return summary_path

        except Exception as e:
            logger.error(f"Failed to save session summary: {e}", exc_info=True)
            raise IOError(f"Failed to save session summary: {e}")

    def end_session_cleanup(self):
        """
        Perform cleanup when ending a session.

        New behavior (redesigned state management):
        - Does NOT remove packing_state.json (kept as history)
        - State files are permanent historical records
        - session_summary.json should be created separately via save_session_summary()

        This method is now essentially a no-op, kept for backward compatibility.
        In the new design, state files are NEVER deleted - they form the historical record.
        """
        logger.info("Session cleanup called (state files preserved as history)")
        # No longer removing state files - they are permanent history
        # This method kept for backward compatibility but does nothing
