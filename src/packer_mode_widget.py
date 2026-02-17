import logging
from functools import partial
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QLineEdit, QHeaderView, QPushButton, QAbstractItemView, QFrame,
    QGroupBox, QGridLayout, QProgressBar, QMessageBox
)
from PySide6.QtGui import QFont, QColor, QPalette
from PySide6.QtCore import Qt, Signal
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class PackerModeWidget(QWidget):
    """
    The user interface for the main "Packer Mode" screen.

    This widget displays the items for the currently active order, provides
    visual feedback on scanning actions, and captures input from a barcode
    scanner. It is designed to be a dedicated, focused view for the packing
    process.

    Signals:
        barcode_scanned (str): Emitted when a barcode/order number is scanned.
        exit_packing_mode (): Emitted when the user clicks the exit button.
        skip_order_requested (): Emitted when the user confirms skipping the order.
        cancel_sku_scan (str): Emitted with the SKU to decrement packed count by 1.
        force_complete_sku (str): Emitted with the SKU to force-complete without scanning.
    """
    barcode_scanned = Signal(str)
    exit_packing_mode = Signal()
    skip_order_requested = Signal()
    cancel_sku_scan = Signal(str)
    force_complete_sku = Signal(str)

    FRAME_DEFAULT_STYLE = "QFrame#TableFrame { border: 1px solid palette(mid); border-radius: 3px; }"

    def __init__(self, parent: QWidget = None, sim_mode: bool = False):
        """
        Initializes the PackerModeWidget and its UI components.

        Args:
            parent: The parent widget. Defaults to None.
            sim_mode: When True, show a visible scan simulator panel for
                development/testing without a physical barcode scanner.
        """
        super().__init__(parent)
        self._sim_mode = sim_mode
        self._current_order_state: List[Dict] = []

        main_layout = QHBoxLayout(self)

        # ── Left side: items table ───────────────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        self.table_frame = QFrame()
        self.table_frame.setObjectName("TableFrame")
        self.table_frame.setFrameShape(QFrame.Shape.Box)
        self.table_frame.setFrameShadow(QFrame.Shadow.Plain)
        self.table_frame.setStyleSheet(self.FRAME_DEFAULT_STYLE)
        frame_layout = QVBoxLayout(self.table_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Product Name", "SKU", "Packed / Required", "Status", "Action"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)

        frame_layout.addWidget(self.table)
        left_layout.addWidget(self.table_frame)

        # ── Right side: controls & info ──────────────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setAlignment(Qt.AlignTop)

        # Dev mode: visible scan simulator panel
        if self._sim_mode:
            sim_group = QGroupBox("Scan Simulator (Dev Mode)")
            sim_group.setStyleSheet(
                "QGroupBox { border: 2px dashed #e67e22; border-radius: 6px; "
                "margin-top: 6px; padding: 4px; color: #e67e22; font-weight: bold; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
            )
            sim_layout = QHBoxLayout(sim_group)
            self.sim_input = QLineEdit()
            self.sim_input.setPlaceholderText("Type order number or SKU, press Enter to scan...")
            self.sim_input.returnPressed.connect(self._on_sim_scan)
            sim_btn = QPushButton("Scan")
            sim_btn.setFixedWidth(70)
            sim_btn.clicked.connect(self._on_sim_scan)
            sim_layout.addWidget(self.sim_input)
            sim_layout.addWidget(sim_btn)
            right_layout.addWidget(sim_group)

        # ── Order Info panel ─────────────────────────────────────────────────
        self._order_info_group = QGroupBox("Order Info")
        info_grid = QGridLayout(self._order_info_group)
        info_grid.setColumnStretch(1, 1)
        info_grid.setContentsMargins(6, 12, 6, 6)
        info_grid.setVerticalSpacing(3)

        self._info_labels: Dict[str, QLabel] = {}
        info_fields = [
            ("order",         "Order"),
            ("courier",       "Courier"),
            ("status",        "Status"),
            ("fulfillment",   "Fulfillment"),
            ("box",           "Box"),
            ("tags",          "Tags"),
            ("internal_tags", "Int. Tags"),
            ("shipping",      "Shipping"),
        ]
        for row_idx, (key, display) in enumerate(info_fields):
            title_lbl = QLabel(f"{display}:")
            title_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            small_font = title_lbl.font()
            small_font.setPointSize(9)
            title_lbl.setFont(small_font)

            val_lbl = QLabel("—")
            val_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            val_lbl.setWordWrap(True)
            val_font = val_lbl.font()
            val_font.setPointSize(9)
            val_lbl.setFont(val_font)

            info_grid.addWidget(title_lbl, row_idx, 0)
            info_grid.addWidget(val_lbl, row_idx, 1)
            self._info_labels[key] = val_lbl

        right_layout.addWidget(self._order_info_group)

        # ── Status & notification ────────────────────────────────────────────
        self.status_label = QLabel("Scan an order barcode")
        font = QFont(); font.setPointSize(16)
        self.status_label.setFont(font)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

        self.notification_label = QLabel("")
        notif_font = QFont(); notif_font.setPointSize(28); notif_font.setBold(True)
        self.notification_label.setFont(notif_font)
        self.notification_label.setAlignment(Qt.AlignCenter)
        self.notification_label.setWordWrap(True)
        right_layout.addWidget(self.notification_label)

        # ── Session progress bar ─────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("0 / 0 orders")
        self.progress_bar.setFixedHeight(20)
        right_layout.addWidget(self.progress_bar)

        # ── Skip Order button ────────────────────────────────────────────────
        self.skip_button = QPushButton("Skip Order →")
        self.skip_button.setFocusPolicy(Qt.NoFocus)
        self.skip_button.setEnabled(False)
        self.skip_button.clicked.connect(self._on_skip_order)
        right_layout.addWidget(self.skip_button)

        # ── SKU Summary panel ────────────────────────────────────────────────
        self._sku_summary_group = QGroupBox("SKU Summary")
        sku_layout = QVBoxLayout(self._sku_summary_group)
        sku_layout.setContentsMargins(4, 10, 4, 4)

        self.sku_summary_table = QTableWidget()
        self.sku_summary_table.setColumnCount(3)
        self.sku_summary_table.setHorizontalHeaderLabels(["SKU", "Required", "Packed"])
        self.sku_summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sku_summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sku_summary_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.sku_summary_table.setFocusPolicy(Qt.NoFocus)
        self.sku_summary_table.setMaximumHeight(150)
        sku_layout.addWidget(self.sku_summary_table)
        right_layout.addWidget(self._sku_summary_group)

        # ── Last Scan & history ──────────────────────────────────────────────
        raw_scan_title = QLabel("Last Scan:")
        raw_scan_title.setAlignment(Qt.AlignCenter)
        self.raw_scan_label = QLabel("-")
        self.raw_scan_label.setAlignment(Qt.AlignCenter)
        self.raw_scan_label.setObjectName("RawScanLabel")
        self.raw_scan_label.setWordWrap(True)

        history_title = QLabel("Scanned Orders History:")
        history_title.setAlignment(Qt.AlignCenter)
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(1)
        self.history_table.setHorizontalHeaderLabels(["Order #"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.history_table.setFocusPolicy(Qt.NoFocus)
        self.history_table.setMaximumHeight(120)

        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.addWidget(raw_scan_title)
        info_layout.addWidget(self.raw_scan_label)
        info_layout.addWidget(history_title)
        info_layout.addWidget(self.history_table)
        right_layout.addWidget(info_container)

        # ── Hidden scanner input ─────────────────────────────────────────────
        self.scanner_input = QLineEdit()
        self.scanner_input.setFixedSize(1, 1)
        self.scanner_input.returnPressed.connect(self._on_scan)
        right_layout.addWidget(self.scanner_input)

        right_layout.addStretch()

        # ── Exit button ──────────────────────────────────────────────────────
        self.exit_button = QPushButton("<< Back to Menu")
        font = self.exit_button.font(); font.setPointSize(14)
        self.exit_button.setFont(font)
        self.exit_button.clicked.connect(self.exit_packing_mode.emit)
        right_layout.addWidget(self.exit_button)

        main_layout.addWidget(left_widget, stretch=2)
        main_layout.addWidget(right_widget, stretch=1)

    # ── Private slots ────────────────────────────────────────────────────────

    def _on_scan(self):
        """Handle returnPressed on hidden scanner input."""
        text = self.scanner_input.text()
        self.scanner_input.clear()
        self.barcode_scanned.emit(text)

    def _on_sim_scan(self):
        """Handle scan simulator (dev mode only)."""
        text = self.sim_input.text().strip()
        if text:
            self.sim_input.clear()
            self.barcode_scanned.emit(text)

    def _on_manual_confirm(self, sku: str):
        """Emit barcode_scanned with the SKU for manual confirmation."""
        if sku:
            self.barcode_scanned.emit(sku)
        self.set_focus_to_scanner()

    def _on_cancel_scan(self, sku: str):
        """Emit cancel_sku_scan to decrement packed count by 1."""
        self.cancel_sku_scan.emit(sku)
        self.set_focus_to_scanner()

    def _on_force_complete(self, sku: str):
        """Ask for confirmation then emit force_complete_sku."""
        reply = QMessageBox.question(
            self,
            "Force Complete SKU",
            f"Force-complete '{sku}'?\n\n"
            "This marks the item as packed without scanning — use when the item "
            "is physically absent but the order should proceed.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.force_complete_sku.emit(sku)
        self.set_focus_to_scanner()

    def _on_skip_order(self):
        """Ask for confirmation then emit skip_order_requested."""
        reply = QMessageBox.question(
            self,
            "Skip Order",
            "Skip this order without completing it?\n"
            "Scan progress will be preserved — scan the order again to resume.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.skip_order_requested.emit()
        self.set_focus_to_scanner()

    # ── Public API ───────────────────────────────────────────────────────────

    def display_order(self, items: List[Dict[str, Any]], order_state: List[Dict[str, Any]],
                      metadata: Optional[Dict] = None):
        """
        Populates the items table with the details of the current order.

        Args:
            items: List of item dicts for the order.
            order_state: Current packing state showing packed counts per row.
            metadata: Optional order-level metadata dict (courier, tags, box, etc.).
        """
        self._current_order_state = order_state
        self.table.setRowCount(len(items))

        bold_font = QFont()
        bold_font.setBold(True)
        bold_font.setPointSize(10)

        for row, item in enumerate(items):
            sku = item.get('SKU', '')
            quantity = str(item.get('Quantity', ''))
            try:
                qty_int = int(float(quantity))
            except (ValueError, TypeError):
                qty_int = 1

            self.table.setItem(row, 0, QTableWidgetItem(item.get('Product_Name', '')))
            self.table.setItem(row, 1, QTableWidgetItem(sku))

            qty_item = QTableWidgetItem(f"0 / {quantity}")
            if qty_int > 1:
                qty_item.setForeground(QColor("#e67e22"))
                qty_item.setFont(bold_font)
            self.table.setItem(row, 2, qty_item)

            status_item = QTableWidgetItem("Pending")
            palette = self.table.palette()
            pending_bg = palette.color(QPalette.ColorRole.Highlight).lighter(180)
            pending_fg = palette.color(QPalette.ColorRole.HighlightedText)
            status_item.setBackground(pending_bg)
            status_item.setForeground(pending_fg)
            self.table.setItem(row, 3, status_item)

            # Action cell: [✓ Confirm] [−1] [✗ Force]
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 1, 2, 1)
            action_layout.setSpacing(3)

            confirm_btn = QPushButton("✓ Confirm")
            confirm_btn.setObjectName("ConfirmBtn")
            confirm_btn.setFocusPolicy(Qt.NoFocus)
            confirm_btn.setToolTip("Confirm manually (equivalent to scanning this SKU once)")

            cancel_btn = QPushButton("−1")
            cancel_btn.setObjectName("CancelBtn")
            cancel_btn.setFocusPolicy(Qt.NoFocus)
            cancel_btn.setToolTip("Undo one scan")
            cancel_btn.setFixedWidth(36)

            force_btn = QPushButton("✗ Force")
            force_btn.setObjectName("ForceBtn")
            force_btn.setFocusPolicy(Qt.NoFocus)
            force_btn.setToolTip(
                "Force-complete: mark this SKU as done without scanning.\n"
                "Use when item is physically absent but order should proceed."
            )
            force_btn.setStyleSheet("color: #e74c3c;")

            confirm_btn.clicked.connect(partial(self._on_manual_confirm, sku))
            cancel_btn.clicked.connect(partial(self._on_cancel_scan, sku))
            force_btn.clicked.connect(partial(self._on_force_complete, sku))

            action_layout.addWidget(confirm_btn)
            action_layout.addWidget(cancel_btn)
            action_layout.addWidget(force_btn)
            self.table.setCellWidget(row, 4, action_widget)

        # Apply existing scan progress from order_state (e.g. resuming a skipped order)
        for state_item in order_state:
            row_index = state_item.get('row')
            packed_count = state_item.get('packed', 0)
            if row_index is not None and packed_count > 0 and row_index < self.table.rowCount():
                required_count = state_item.get('required', 1)
                is_complete = packed_count >= required_count
                # Update the quantity text to show actual packed count
                qty_item = self.table.item(row_index, 2)
                if qty_item is not None:
                    required_text = qty_item.text().split(' / ')[1]
                    qty_item.setText(f"{packed_count} / {required_text}")
                self._apply_row_state(row_index, is_complete)

        order_number = items[0]['Order_Number'] if items else '?'
        self.status_label.setText(f"Order {order_number}\nIn Progress...")
        self.notification_label.setText("")
        self.skip_button.setEnabled(True)

        self.update_order_info(order_number, metadata or {})
        self.update_sku_summary(order_state)
        self.set_focus_to_scanner()

    def update_item_row(self, row: int, packed_count: int, is_complete: bool):
        """
        Updates a single row in the items table to reflect a new packed count.

        Handles both completing a row (Pending → Packed) and un-completing it
        (Packed → Pending) when packed_count drops below required via −1.

        Args:
            row: The table row index to update.
            packed_count: The new number of items packed for that SKU.
            is_complete: Whether this SKU is now fully packed.
        """
        if row < 0 or row >= self.table.rowCount():
            logger.warning(f"update_item_row: row {row} out of bounds (table has {self.table.rowCount()} rows)")
            return

        quantity_item = self.table.item(row, 2)
        if quantity_item is None:
            logger.warning(f"update_item_row: quantity item at row {row} is None")
            return

        required_quantity = quantity_item.text().split(' / ')[1]
        quantity_item.setText(f"{packed_count} / {required_quantity}")

        self._apply_row_state(row, is_complete)

        # Refresh summary (O(n) but orders are small; acceptable for now)
        self.update_sku_summary(self._current_order_state)

    def _apply_row_state(self, row: int, is_complete: bool):
        """
        Applies visual state (status cell + button enable/disable) to a table row.

        This is shared between display_order (initial population) and
        update_item_row (live updates), so the logic lives in one place.

        Args:
            row: Table row index.
            is_complete: True → mark Packed; False → mark/restore Pending.
        """
        palette = self.table.palette()

        if is_complete:
            status_item = QTableWidgetItem("Packed")
            status_item.setBackground(QColor("#1e4d2b"))
            status_item.setForeground(QColor("#43a047"))
            self.table.setItem(row, 3, status_item)

            action_widget = self.table.cellWidget(row, 4)
            if action_widget:
                for child in action_widget.findChildren(QPushButton):
                    # Keep −1 (CancelBtn) enabled so the operator can undo completion
                    if child.objectName() in ("ConfirmBtn", "ForceBtn"):
                        child.setEnabled(False)
                    else:
                        child.setEnabled(True)
        else:
            # Revert to Pending (handles both initial state and undo of completion)
            status_item = QTableWidgetItem("Pending")
            pending_bg = palette.color(QPalette.ColorRole.Highlight).lighter(180)
            pending_fg = palette.color(QPalette.ColorRole.HighlightedText)
            status_item.setBackground(pending_bg)
            status_item.setForeground(pending_fg)
            self.table.setItem(row, 3, status_item)

            # Re-enable all buttons
            action_widget = self.table.cellWidget(row, 4)
            if action_widget:
                for child in action_widget.findChildren(QPushButton):
                    child.setEnabled(True)

    def update_order_info(self, order_number: str, metadata: Dict):
        """
        Updates the Order Info panel with metadata for the current order.

        Handles None values and unexpected types gracefully (shows "—").

        Args:
            order_number: The current order number to display.
            metadata: Dict with optional keys: courier, status, fulfillment_status,
                      recommended_box, tags, internal_tags, shipping_method.
        """
        def _fmt(v) -> str:
            if v is None:
                return "—"
            if isinstance(v, list):
                return ", ".join(str(t) for t in v) or "—"
            return str(v) or "—"

        # Display order number without adding an extra # if one is already present
        display_num = order_number.lstrip('#')
        self._info_labels["order"].setText(f"#{display_num}")
        self._info_labels["courier"].setText(_fmt(metadata.get("courier")))
        self._info_labels["status"].setText(_fmt(metadata.get("status")))
        self._info_labels["fulfillment"].setText(_fmt(metadata.get("fulfillment_status")))
        self._info_labels["box"].setText(_fmt(metadata.get("recommended_box")))
        self._info_labels["tags"].setText(_fmt(metadata.get("tags")))
        self._info_labels["internal_tags"].setText(_fmt(metadata.get("internal_tags")))
        self._info_labels["shipping"].setText(_fmt(metadata.get("shipping_method")))

    def update_sku_summary(self, order_state: List[Dict]):
        """
        Rebuilds the SKU Summary table by aggregating duplicate SKU rows.

        Args:
            order_state: Current packing state list from PackerLogic.
        """
        # Aggregate by original_sku
        aggregated: Dict[str, Dict] = {}
        for item in order_state:
            sku = item.get('original_sku', '')
            if sku not in aggregated:
                aggregated[sku] = {'required': 0, 'packed': 0}
            aggregated[sku]['required'] += item.get('required', 0)
            aggregated[sku]['packed'] += item.get('packed', 0)

        self.sku_summary_table.setRowCount(len(aggregated))
        bold_font = QFont(); bold_font.setBold(True)

        for row_idx, (sku, counts) in enumerate(aggregated.items()):
            required = counts['required']
            packed = counts['packed']
            is_done = packed >= required

            sku_item = QTableWidgetItem(sku)
            req_item = QTableWidgetItem(str(required))
            packed_item = QTableWidgetItem(str(packed))

            req_item.setTextAlignment(Qt.AlignCenter)
            packed_item.setTextAlignment(Qt.AlignCenter)

            if required > 1:
                req_item.setForeground(QColor("#e67e22"))
                req_item.setFont(bold_font)

            if is_done:
                packed_item.setForeground(QColor("#43a047"))
            elif packed > 0:
                packed_item.setForeground(QColor("#3498db"))

            self.sku_summary_table.setItem(row_idx, 0, sku_item)
            self.sku_summary_table.setItem(row_idx, 1, req_item)
            self.sku_summary_table.setItem(row_idx, 2, packed_item)

    def update_session_progress(self, completed: int, total: int):
        """
        Updates the session-wide progress bar.

        Args:
            completed: Number of orders completed in this session.
            total: Total orders in this session.
        """
        if total <= 0:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("0 / 0 orders")
            return
        pct = int((completed / total) * 100)
        self.progress_bar.setValue(pct)
        self.progress_bar.setFormat(f"{completed}/{total} orders ({pct}%)")

    def show_notification(self, text: str, color_name: str):
        """
        Displays a large, colored notification message.

        Args:
            text: The message to display.
            color_name: Color name or hex (e.g., "red", "#43a047").
        """
        self.notification_label.setText(text)
        self.notification_label.setStyleSheet(f"color: {color_name};")

    def clear_screen(self):
        """Resets the widget to its initial state, ready for the next order."""
        self.table.clearContents()
        self.table.setRowCount(0)
        self.status_label.setText("Scan the next order's barcode")
        self.notification_label.setText("")
        self.scanner_input.clear()
        self.scanner_input.setEnabled(True)
        self.skip_button.setEnabled(False)
        self._current_order_state = []
        self.sku_summary_table.setRowCount(0)
        for key in self._info_labels:
            self._info_labels[key].setText("—")
        self.set_focus_to_scanner()

    def set_focus_to_scanner(self):
        """Sets keyboard focus to the hidden scanner input."""
        self.scanner_input.setFocus()

    def update_raw_scan_display(self, text: str):
        """
        Updates the label that shows the raw text from the last scan.

        Args:
            text: The text captured from the scanner.
        """
        self.raw_scan_label.setText(text)

    def add_order_to_history(self, order_number: str):
        """
        Adds an order number to the top of the scan history table.

        Args:
            order_number: The order number that was just scanned.
        """
        self.history_table.insertRow(0)
        self.history_table.setItem(0, 0, QTableWidgetItem(str(order_number)))
