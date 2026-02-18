import logging
from functools import partial
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QLineEdit, QHeaderView, QPushButton, QAbstractItemView, QFrame,
    QGroupBox, QProgressBar, QSplitter, QScrollArea, QSizePolicy
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, Signal
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Courier -> badge color mapping (background, foreground)
COURIER_COLORS = {
    'DHL':      ('#c8a800', '#1a1a00'),
    'PostOne':  ('#1565c0', '#e3f2fd'),
    'Speedy':   ('#2e7d32', '#e8f5e9'),
    'Nova':     ('#6a1b9a', '#f3e5f5'),
    'Econt':    ('#00695c', '#e0f2f1'),
}
DEFAULT_COURIER_COLOR = ('#555555', '#ffffff')

# Fulfillment status -> badge color
STATUS_COLORS = {
    'Fulfillable':   ('#1b5e20', '#a5d6a7'),
    'Unfulfillable': ('#b71c1c', '#ef9a9a'),
    'Fulfilled':     ('#0d47a1', '#90caf9'),
}
DEFAULT_STATUS_COLOR = ('#424242', '#bdbdbd')

_BADGE_STYLE = (
    "border-radius: 4px; padding: 2px 8px; font-weight: bold; font-size: 11px;"
)


def _make_badge(text: str, bg: str, fg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"background-color: {bg}; color: {fg}; {_BADGE_STYLE}")
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return lbl


class PackerModeWidget(QWidget):
    """
    Packer Mode UI — main screen for warehouse scanning.

    Layout:
      [TOP]    Session progress bar + label           (full width)
      [MAIN]   QSplitter horizontal:
                 Left (resizable): items-to-pack summary table
                 Center (stretch): SKU scan table
                 Right (resizable): status / notification / skip / history / controls
      [BOTTOM] Order metadata strip (hidden until order loaded):
                 courier badge | status badge | box | method | date | tags | note

    Signals:
        barcode_scanned(str): Emitted when scanner fires.
        exit_packing_mode():  Back to menu.
        skip_order_requested(): Skip button clicked.
        force_complete_sku(str): Force-complete a SKU row.
    """

    barcode_scanned = Signal(str)
    exit_packing_mode = Signal()
    skip_order_requested = Signal()
    force_complete_sku = Signal(str)

    FRAME_DEFAULT_STYLE = (
        "QFrame#TableFrame { border: 1px solid palette(mid); border-radius: 3px; }"
    )

    def __init__(self, parent: QWidget = None, sim_mode: bool = False):
        super().__init__(parent)
        self._sim_mode = sim_mode

        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(4)
        root_layout.setContentsMargins(6, 4, 6, 4)

        # ── TOP: SESSION PROGRESS STRIP ────────────────────────────────────────
        top_strip = QFrame()
        top_strip.setFrameShape(QFrame.Shape.StyledPanel)
        top_strip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_layout = QHBoxLayout(top_strip)
        top_layout.setContentsMargins(8, 4, 8, 4)
        top_layout.setSpacing(8)

        prog_lbl = QLabel("Session:")
        prog_lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        bold_font = QFont(); bold_font.setBold(True)
        prog_lbl.setFont(bold_font)

        self.session_progress_bar = QProgressBar()
        self.session_progress_bar.setRange(0, 1)
        self.session_progress_bar.setValue(0)
        self.session_progress_bar.setFormat("%v / %m orders")
        self.session_progress_bar.setAlignment(Qt.AlignCenter)
        self.session_progress_bar.setTextVisible(True)
        self.session_progress_bar.setFixedHeight(20)
        self.session_progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.session_progress_label = QLabel("0 of 0 completed")
        self.session_progress_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        top_layout.addWidget(prog_lbl)
        top_layout.addWidget(self.session_progress_bar)
        top_layout.addWidget(self.session_progress_label)
        root_layout.addWidget(top_strip)

        # ── MAIN: QSplitter (left summary | center table | right controls) ─────
        self._main_splitter = QSplitter(Qt.Horizontal)
        self._main_splitter.setChildrenCollapsible(False)

        # ── LEFT: Items-to-pack summary ────────────────────────────────────────
        left_widget = QWidget()
        left_widget.setMinimumWidth(160)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(4)

        summary_title = QLabel("Items to Pack")
        summary_title.setFont(bold_font)
        left_layout.addWidget(summary_title)

        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(3)
        self.summary_table.setHorizontalHeaderLabels(["SKU", "Product", "Qty"])
        self.summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.summary_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.summary_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.summary_table.setFocusPolicy(Qt.NoFocus)
        self.summary_table.verticalHeader().setVisible(False)
        left_layout.addWidget(self.summary_table, stretch=1)

        self._main_splitter.addWidget(left_widget)

        # ── CENTER: SKU scan table ─────────────────────────────────────────────
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)

        self.table_frame = QFrame()
        self.table_frame.setObjectName("TableFrame")
        self.table_frame.setFrameShape(QFrame.Shape.Box)
        self.table_frame.setFrameShadow(QFrame.Shadow.Plain)
        self.table_frame.setStyleSheet(self.FRAME_DEFAULT_STYLE)
        frame_layout = QVBoxLayout(self.table_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Product Name", "SKU", "Packed / Required", "Status", "Confirm", "Force"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.verticalHeader().setDefaultSectionSize(34)

        frame_layout.addWidget(self.table)
        center_layout.addWidget(self.table_frame)

        self._main_splitter.addWidget(center_widget)

        # ── RIGHT: Status / controls / history ────────────────────────────────
        right_widget = QWidget()
        right_widget.setMinimumWidth(160)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(6)

        if self._sim_mode:
            sim_group = QGroupBox("Scan Simulator")
            sim_group.setStyleSheet(
                "QGroupBox { border: 2px dashed #e67e22; border-radius: 6px; "
                "margin-top: 6px; padding: 4px; color: #e67e22; font-weight: bold; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
            )
            sim_layout = QHBoxLayout(sim_group)
            self.sim_input = QLineEdit()
            self.sim_input.setPlaceholderText("Order # or SKU…")
            self.sim_input.returnPressed.connect(self._on_sim_scan)
            sim_btn = QPushButton("Scan")
            sim_btn.setFixedWidth(50)
            sim_btn.clicked.connect(self._on_sim_scan)
            sim_layout.addWidget(self.sim_input)
            sim_layout.addWidget(sim_btn)
            right_layout.addWidget(sim_group)

        self.status_label = QLabel("Scan an order barcode")
        status_font = QFont(); status_font.setPointSize(14)
        self.status_label.setFont(status_font)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

        self.notification_label = QLabel("")
        notif_font = QFont(); notif_font.setPointSize(20); notif_font.setBold(True)
        self.notification_label.setFont(notif_font)
        self.notification_label.setAlignment(Qt.AlignCenter)
        self.notification_label.setWordWrap(True)
        right_layout.addWidget(self.notification_label)

        right_layout.addStretch()

        self.skip_button = QPushButton("⏭  Skip Order")
        self.skip_button.setFocusPolicy(Qt.NoFocus)
        self.skip_button.setEnabled(False)
        self.skip_button.setToolTip(
            "Skip current order. Progress is preserved — scan barcode to resume."
        )
        self.skip_button.clicked.connect(self.skip_order_requested.emit)
        right_layout.addWidget(self.skip_button)

        raw_scan_title = QLabel("Last Scan:")
        raw_scan_title.setAlignment(Qt.AlignCenter)
        self.raw_scan_label = QLabel("-")
        self.raw_scan_label.setAlignment(Qt.AlignCenter)
        self.raw_scan_label.setObjectName("RawScanLabel")
        self.raw_scan_label.setWordWrap(True)
        right_layout.addWidget(raw_scan_title)
        right_layout.addWidget(self.raw_scan_label)

        history_title = QLabel("Scanned Orders:")
        history_title.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(history_title)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(2)
        self.history_table.setHorizontalHeaderLabels(["Order #", "Items"])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.history_table.setFocusPolicy(Qt.NoFocus)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right_layout.addWidget(self.history_table, stretch=1)

        prev_title = QLabel("Previous Order Items:")
        prev_title.setAlignment(Qt.AlignCenter)
        prev_title_font = QFont(); prev_title_font.setPointSize(8)
        prev_title.setFont(prev_title_font)
        right_layout.addWidget(prev_title)

        self.prev_order_table = QTableWidget()
        self.prev_order_table.setColumnCount(2)
        self.prev_order_table.setHorizontalHeaderLabels(["SKU", "Product"])
        self.prev_order_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.prev_order_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.prev_order_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.prev_order_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.prev_order_table.setFocusPolicy(Qt.NoFocus)
        self.prev_order_table.verticalHeader().setVisible(False)
        self.prev_order_table.setVisible(False)
        self.prev_order_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right_layout.addWidget(self.prev_order_table, stretch=1)

        # Hidden scanner capture
        self.scanner_input = QLineEdit()
        self.scanner_input.setFixedSize(1, 1)
        self.scanner_input.returnPressed.connect(self._on_scan)
        right_layout.addWidget(self.scanner_input)

        self.exit_button = QPushButton("<< Back to Menu")
        exit_font = self.exit_button.font(); exit_font.setPointSize(12)
        self.exit_button.setFont(exit_font)
        self.exit_button.setFocusPolicy(Qt.NoFocus)
        self.exit_button.clicked.connect(self.exit_packing_mode.emit)
        right_layout.addWidget(self.exit_button)

        self._main_splitter.addWidget(right_widget)

        # Splitter initial proportions: 1 : 4 : 1.5
        self._main_splitter.setStretchFactor(0, 1)
        self._main_splitter.setStretchFactor(1, 4)
        self._main_splitter.setStretchFactor(2, 1)

        root_layout.addWidget(self._main_splitter, stretch=1)

        # ── BOTTOM: Order metadata strip (hidden until order loaded) ───────────
        self.metadata_frame = QFrame()
        self.metadata_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.metadata_frame.setVisible(False)
        self.metadata_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        meta_layout = QHBoxLayout(self.metadata_frame)
        meta_layout.setContentsMargins(8, 4, 8, 4)
        meta_layout.setSpacing(8)

        self.meta_status_label = QLabel()
        self.meta_status_label.setVisible(False)
        meta_layout.addWidget(self.meta_status_label)

        self.meta_courier_label = QLabel()
        self.meta_courier_label.setVisible(False)
        meta_layout.addWidget(self.meta_courier_label)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        meta_layout.addWidget(sep1)

        self.meta_box_label = QLabel()
        self.meta_box_label.setVisible(False)
        meta_layout.addWidget(self.meta_box_label)

        self.meta_method_label = QLabel()
        self.meta_method_label.setVisible(False)
        meta_layout.addWidget(self.meta_method_label)

        self.meta_created_label = QLabel()
        self.meta_created_label.setVisible(False)
        small_font = QFont(); small_font.setPointSize(8)
        self.meta_created_label.setFont(small_font)
        meta_layout.addWidget(self.meta_created_label)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        meta_layout.addWidget(sep2)

        self.meta_tags_label = QLabel()
        self.meta_tags_label.setVisible(False)
        self.meta_tags_label.setFont(small_font)
        meta_layout.addWidget(self.meta_tags_label)

        self.meta_internal_tags_label = QLabel()
        self.meta_internal_tags_label.setVisible(False)
        self.meta_internal_tags_label.setFont(small_font)
        meta_layout.addWidget(self.meta_internal_tags_label)

        sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.VLine)
        sep3.setFrameShadow(QFrame.Shadow.Sunken)
        meta_layout.addWidget(sep3)

        self.meta_note_label = QLabel()
        self.meta_note_label.setVisible(False)
        self.meta_note_label.setFont(small_font)
        self.meta_note_label.setWordWrap(False)
        meta_layout.addWidget(self.meta_note_label)

        self.meta_status_note_label = QLabel()
        self.meta_status_note_label.setVisible(False)
        self.meta_status_note_label.setFont(small_font)
        self.meta_status_note_label.setWordWrap(False)
        meta_layout.addWidget(self.meta_status_note_label)

        meta_layout.addStretch()

        root_layout.addWidget(self.metadata_frame)

    # ── SCANNER SLOTS ──────────────────────────────────────────────────────────

    def _on_scan(self):
        text = self.scanner_input.text()
        self.scanner_input.clear()
        self.barcode_scanned.emit(text)

    def _on_sim_scan(self):
        text = self.sim_input.text().strip()
        if text:
            self.sim_input.clear()
            self.barcode_scanned.emit(text)

    def _on_manual_confirm(self, sku: str):
        if sku:
            self.barcode_scanned.emit(sku)
        self.set_focus_to_scanner()

    def _on_force_complete(self, sku: str):
        if sku:
            self.force_complete_sku.emit(sku)
        self.set_focus_to_scanner()

    # ── SESSION PROGRESS ───────────────────────────────────────────────────────

    def update_session_progress(self, completed: int, total: int):
        """Updates the session-wide progress bar and label."""
        self.session_progress_bar.setRange(0, max(total, 1))
        self.session_progress_bar.setValue(completed)
        self.session_progress_label.setText(f"{completed} of {total} completed")

    # ── ORDER METADATA (BOTTOM STRIP) ─────────────────────────────────────────

    def display_order_metadata(self, metadata: dict, courier: str = ''):
        """Populates and shows the order metadata strip at the bottom."""
        # Status badge
        status = metadata.get('status', '')
        if status:
            bg, fg = STATUS_COLORS.get(status, DEFAULT_STATUS_COLOR)
            self.meta_status_label.setText(status)
            self.meta_status_label.setStyleSheet(
                f"background-color: {bg}; color: {fg}; {_BADGE_STYLE}"
            )
            self.meta_status_label.setVisible(True)
        else:
            self.meta_status_label.setVisible(False)

        # Courier badge
        courier_name = courier or metadata.get('courier', '')
        if courier_name:
            bg, fg = COURIER_COLORS.get(courier_name, DEFAULT_COURIER_COLOR)
            self.meta_courier_label.setText(courier_name)
            self.meta_courier_label.setStyleSheet(
                f"background-color: {bg}; color: {fg}; {_BADGE_STYLE}"
            )
            self.meta_courier_label.setVisible(True)
        else:
            self.meta_courier_label.setVisible(False)

        # Recommended box
        box = metadata.get('recommended_box', '')
        if box:
            self.meta_box_label.setText(f"📦 {box}")
            self.meta_box_label.setVisible(True)
        else:
            self.meta_box_label.setVisible(False)

        # Shipping method
        method = metadata.get('shipping_method', '')
        if method:
            self.meta_method_label.setText(f"🚚 {method}")
            self.meta_method_label.setVisible(True)
        else:
            self.meta_method_label.setVisible(False)

        # Created at (date only)
        created = metadata.get('created_at', '')
        if created:
            date_str = created[:10] if len(created) >= 10 else created
            self.meta_created_label.setText(f"Created: {date_str}")
            self.meta_created_label.setVisible(True)
        else:
            self.meta_created_label.setVisible(False)

        # Tags
        tags = metadata.get('tags', [])
        if tags:
            self.meta_tags_label.setText("Tags: " + ", ".join(str(t) for t in tags))
            self.meta_tags_label.setVisible(True)
        else:
            self.meta_tags_label.setVisible(False)

        # Internal tags
        internal_tags = metadata.get('internal_tags', [])
        if internal_tags:
            self.meta_internal_tags_label.setText(
                "⚙ " + ", ".join(str(t) for t in internal_tags)
            )
            self.meta_internal_tags_label.setVisible(True)
        else:
            self.meta_internal_tags_label.setVisible(False)

        # System note
        note = metadata.get('system_note', '')
        if note:
            # Truncate if too long for bottom strip
            display_note = note[:80] + "…" if len(note) > 80 else note
            self.meta_note_label.setText(f"⚠ {display_note}")
            self.meta_note_label.setToolTip(note)
            self.meta_note_label.setVisible(True)
        else:
            self.meta_note_label.setVisible(False)

        # Status note
        status_note = metadata.get('status_note', '')
        if status_note:
            display_sn = status_note[:80] + "…" if len(status_note) > 80 else status_note
            self.meta_status_note_label.setText(f"📋 {display_sn}")
            self.meta_status_note_label.setToolTip(status_note)
            self.meta_status_note_label.setVisible(True)
        else:
            self.meta_status_note_label.setVisible(False)

        self.metadata_frame.setVisible(True)

    def clear_order_info(self):
        """Hides the order metadata strip."""
        self.metadata_frame.setVisible(False)

    # ── ORDER SUMMARY TABLE (LEFT PANEL) ──────────────────────────────────────

    def update_order_summary(self, items: List[Dict[str, Any]]):
        """
        Aggregates items by SKU and populates the 'Items to Pack' summary table.
        Shows one row per unique SKU with total quantity.
        """
        aggregated: Dict[str, Dict] = {}
        for item in items:
            sku = item.get('SKU', '')
            if not sku:
                continue
            if sku not in aggregated:
                aggregated[sku] = {'product': item.get('Product_Name', ''), 'qty': 0}
            try:
                aggregated[sku]['qty'] += int(float(item.get('Quantity', 1)))
            except (ValueError, TypeError):
                aggregated[sku]['qty'] += 1

        self.summary_table.setRowCount(len(aggregated))
        for row, (sku, data) in enumerate(aggregated.items()):
            qty = data['qty']
            sku_item = QTableWidgetItem(sku)
            prod_item = QTableWidgetItem(data['product'])
            qty_item = QTableWidgetItem(str(qty))
            qty_item.setTextAlignment(Qt.AlignCenter)
            if qty > 1:
                bold = QFont(); bold.setBold(True)
                qty_item.setFont(bold)
                qty_item.setForeground(QColor("#ffc107"))
            self.summary_table.setItem(row, 0, sku_item)
            self.summary_table.setItem(row, 1, prod_item)
            self.summary_table.setItem(row, 2, qty_item)

    # ── MAIN SKU TABLE ─────────────────────────────────────────────────────────

    def display_order(self, items: List[Dict[str, Any]], order_state: List[Dict[str, Any]]):
        """
        Populates the items table with the details of the current order.

        Args:
            items: List of item dicts (Order_Number, SKU, Product_Name, Quantity).
            order_state: Current packing state per row.
        """
        self.table.setRowCount(len(items))
        # Explicit accessible colors, independent of system palette
        pending_bg = QColor("#1a3550")
        pending_fg = QColor("#90caf9")

        for row, item in enumerate(items):
            sku = item.get('SKU', '')
            quantity_str = str(item.get('Quantity', '1'))
            try:
                quantity_int = int(float(quantity_str))
            except (ValueError, TypeError):
                quantity_int = 1

            self.table.setItem(row, 0, QTableWidgetItem(item.get('Product_Name', '')))
            self.table.setItem(row, 1, QTableWidgetItem(sku))

            qty_item = QTableWidgetItem(f"0 / {quantity_int}")
            qty_item.setTextAlignment(Qt.AlignCenter)
            if quantity_int > 1:
                bold_font = qty_item.font(); bold_font.setBold(True)
                qty_item.setFont(bold_font)
                qty_item.setBackground(QColor("#5a4a00"))
                qty_item.setForeground(QColor("#ffc107"))
            self.table.setItem(row, 2, qty_item)

            status_item = QTableWidgetItem("Pending")
            status_item.setBackground(pending_bg)
            status_item.setForeground(pending_fg)
            self.table.setItem(row, 3, status_item)

            confirm_btn = QPushButton("Confirm")
            confirm_btn.setFocusPolicy(Qt.NoFocus)
            confirm_btn.setObjectName("ConfirmBtn")
            confirm_btn.clicked.connect(partial(self._on_manual_confirm, sku))
            self.table.setCellWidget(row, 4, confirm_btn)

            force_btn = QPushButton("Force")
            force_btn.setFocusPolicy(Qt.NoFocus)
            force_btn.setObjectName("ForceBtn")
            force_btn.setToolTip("Force-complete this SKU (mark all units as packed)")
            force_btn.clicked.connect(partial(self._on_force_complete, sku))
            self.table.setCellWidget(row, 5, force_btn)

        # Apply existing progress
        first_unpacked_row = None
        for state_item in order_state:
            row_index = state_item.get('row')
            packed_count = state_item.get('packed', 0)
            if row_index is not None and packed_count > 0 and row_index < self.table.rowCount():
                required_count = state_item.get('required', 1)
                is_complete = packed_count >= required_count
                self.update_item_row(row_index, packed_count, is_complete)
                if not is_complete and first_unpacked_row is None:
                    first_unpacked_row = row_index
            elif row_index is not None and first_unpacked_row is None:
                first_unpacked_row = row_index

        # Auto-scroll to first unpacked row when resuming
        if first_unpacked_row is not None:
            item_to_scroll = self.table.item(first_unpacked_row, 0)
            if item_to_scroll:
                self.table.scrollToItem(item_to_scroll, QAbstractItemView.ScrollHint.PositionAtTop)

        self.update_order_summary(items)

        order_number = items[0]['Order_Number'] if items else ''
        self.status_label.setText(f"Order {order_number}\nIn Progress…")
        self.skip_button.setEnabled(True)
        self.set_focus_to_scanner()

    def update_item_row(self, row: int, packed_count: int, is_complete: bool):
        """Updates a single row to reflect a new packed count."""
        if row < 0 or row >= self.table.rowCount():
            logger.warning(f"update_item_row: row {row} out of bounds (table has {self.table.rowCount()} rows)")
            return
        quantity_item = self.table.item(row, 2)
        if quantity_item is None:
            logger.warning(f"Cannot update row {row}: quantity item is None")
            return

        required_quantity = quantity_item.text().split(' / ')[1]
        try:
            required_int = int(required_quantity)
        except ValueError:
            required_int = 1

        quantity_item.setText(f"{packed_count} / {required_quantity}")

        if is_complete:
            status_item = QTableWidgetItem("Packed")
            status_item.setBackground(QColor("#1e4d2b"))
            status_item.setForeground(QColor("#43a047"))
            self.table.setItem(row, 3, status_item)
            confirm_btn = self.table.cellWidget(row, 4)
            if confirm_btn:
                confirm_btn.setEnabled(False)
        else:
            if required_int > 1:
                bold_font = quantity_item.font(); bold_font.setBold(True)
                quantity_item.setFont(bold_font)
                quantity_item.setBackground(QColor("#5a4a00"))
                quantity_item.setForeground(QColor("#ffc107"))

    # ── NOTIFICATIONS ──────────────────────────────────────────────────────────

    def show_notification(self, text: str, color_name: str):
        """Displays a large colored notification message."""
        self.notification_label.setText(text)
        self.notification_label.setStyleSheet(f"color: {color_name};")

    # ── HISTORY ────────────────────────────────────────────────────────────────

    def add_order_to_history(self, order_number: str, item_count: int = 0):
        """Adds an order to the top of the scan history table."""
        self.history_table.insertRow(0)
        self.history_table.setItem(0, 0, QTableWidgetItem(str(order_number)))
        count_item = QTableWidgetItem(str(item_count) if item_count else "")
        count_item.setTextAlignment(Qt.AlignCenter)
        self.history_table.setItem(0, 1, count_item)

    def show_previous_order_items(self, items: List[Dict[str, Any]]):
        """Shows items of the just-completed/skipped order in a dimmed reference table."""
        dim_color = QColor("#555555")
        self.prev_order_table.setRowCount(len(items))
        for i, item in enumerate(items):
            sku_cell = QTableWidgetItem(item.get('SKU', ''))
            name_cell = QTableWidgetItem(item.get('Product_Name', ''))
            sku_cell.setForeground(dim_color)
            name_cell.setForeground(dim_color)
            self.prev_order_table.setItem(i, 0, sku_cell)
            self.prev_order_table.setItem(i, 1, name_cell)
        self.prev_order_table.setVisible(True)

    # ── SCREEN MANAGEMENT ─────────────────────────────────────────────────────

    def clear_screen(self):
        """Resets the main table to initial state, ready for next order."""
        self.table.clearContents()
        self.table.setRowCount(0)
        self.summary_table.clearContents()
        self.summary_table.setRowCount(0)
        self.status_label.setText("Scan the next order's barcode")
        self.notification_label.setText("")
        self.scanner_input.clear()
        self.scanner_input.setEnabled(True)
        self.skip_button.setEnabled(False)
        self.clear_order_info()
        self.set_focus_to_scanner()

    def set_focus_to_scanner(self):
        """Sets keyboard focus to the hidden scanner input field."""
        self.scanner_input.setFocus()

    def update_raw_scan_display(self, text: str):
        """Updates the raw scan display label."""
        self.raw_scan_label.setText(text)

    def enable_skip_button(self, enabled: bool):
        """Enables or disables the Skip Order button."""
        self.skip_button.setEnabled(enabled)
