"""
Unit tests for src/packer_mode_widget.py — PackerModeWidget.

Requires: pytest-qt (qtbot fixture from conftest via pytest-qt plugin).

Tests cover:
- Widget initialization (UI elements created)
- display_order() — table populated, status label updated
- update_item_row() — quantity and status column updated
- show_notification() — label text and style set
- clear_screen() — table cleared, status/notification reset
- update_raw_scan_display() — raw scan label updated
- add_order_to_history() — row inserted at top of history table
- _on_scan() / barcode_scanned signal emitted
- _on_manual_confirm() / barcode_scanned signal emitted from button
"""

import pytest
from PySide6.QtCore import Qt

from packer_mode_widget import PackerModeWidget


# ---------------------------------------------------------------------------
# Sample test data
# ---------------------------------------------------------------------------

SAMPLE_ITEMS = [
    {"Order_Number": "ORD-001", "SKU": "SKU-A", "Product_Name": "Product Alpha", "Quantity": 2},
    {"Order_Number": "ORD-001", "SKU": "SKU-B", "Product_Name": "Product Beta", "Quantity": 1},
]

EMPTY_STATE = []

PARTIAL_STATE = [
    {"row": 0, "packed": 1, "required": 2},
]


# ============================================================================
# Initialization
# ============================================================================

class TestPackerModeWidgetInit:
    def test_widget_creates(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget is not None

    def test_table_has_five_columns(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget.table.columnCount() == 5

    def test_history_table_has_one_column(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget.history_table.columnCount() == 1

    def test_status_label_initial_text(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert "Scan" in widget.status_label.text()

    def test_notification_label_initially_empty(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget.notification_label.text() == ""

    def test_raw_scan_label_initial_value(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget.raw_scan_label.text() == "-"

    def test_scanner_input_is_tiny(self, qtbot):
        """Scanner input is intentionally hidden (1x1 px)."""
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget.scanner_input.width() == 1
        assert widget.scanner_input.height() == 1


# ============================================================================
# display_order
# ============================================================================

class TestDisplayOrder:
    def test_table_rows_match_items(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        assert widget.table.rowCount() == len(SAMPLE_ITEMS)

    def test_sku_populated_in_table(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        assert widget.table.item(0, 1).text() == "SKU-A"
        assert widget.table.item(1, 1).text() == "SKU-B"

    def test_product_name_populated(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        assert widget.table.item(0, 0).text() == "Product Alpha"

    def test_quantity_shows_zero_packed_initially(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        assert widget.table.item(0, 2).text() == "0 / 2"

    def test_status_column_initially_pending(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        assert widget.table.item(0, 3).text() == "Pending"

    def test_status_label_shows_order_number(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        assert "ORD-001" in widget.status_label.text()

    def test_partial_state_updates_row(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, PARTIAL_STATE)
        # Row 0 has 1 packed out of 2, so it's NOT complete — status stays Pending
        qty_text = widget.table.item(0, 2).text()
        assert qty_text == "1 / 2"

    def test_confirm_button_in_action_column(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        btn = widget.table.cellWidget(0, 4)
        assert btn is not None
        assert btn.text() == "Confirm Manually"


# ============================================================================
# update_item_row
# ============================================================================

class TestUpdateItemRow:
    def test_quantity_updated(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        widget.update_item_row(0, 1, False)
        assert widget.table.item(0, 2).text() == "1 / 2"

    def test_status_packed_when_complete(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        widget.update_item_row(0, 2, True)
        assert widget.table.item(0, 3).text() == "Packed"

    def test_confirm_button_disabled_when_complete(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        widget.update_item_row(0, 2, True)
        btn = widget.table.cellWidget(0, 4)
        assert not btn.isEnabled()

    def test_invalid_row_does_not_raise(self, qtbot):
        """Calling update_item_row for a row that doesn't exist should not crash."""
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        # No display_order called — table is empty
        widget.update_item_row(99, 1, False)  # Should log warning, not raise


# ============================================================================
# show_notification
# ============================================================================

class TestShowNotification:
    def test_text_set(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.show_notification("ORDER COMPLETE", "green")
        assert widget.notification_label.text() == "ORDER COMPLETE"

    def test_color_applied(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.show_notification("ERROR", "red")
        assert "red" in widget.notification_label.styleSheet()


# ============================================================================
# clear_screen
# ============================================================================

class TestClearScreen:
    def test_table_cleared(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        widget.clear_screen()
        assert widget.table.rowCount() == 0

    def test_notification_cleared(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.show_notification("TEST", "blue")
        widget.clear_screen()
        assert widget.notification_label.text() == ""

    def test_scanner_input_cleared(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.scanner_input.setText("some barcode")
        widget.clear_screen()
        assert widget.scanner_input.text() == ""

    def test_status_label_reset(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        widget.clear_screen()
        # Should say something about next order or scan, not the previous order
        assert "ORD-001" not in widget.status_label.text()


# ============================================================================
# update_raw_scan_display
# ============================================================================

class TestUpdateRawScanDisplay:
    def test_label_updated(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.update_raw_scan_display("ABC-123")
        assert widget.raw_scan_label.text() == "ABC-123"

    def test_empty_string(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.update_raw_scan_display("")
        assert widget.raw_scan_label.text() == ""


# ============================================================================
# add_order_to_history
# ============================================================================

class TestAddOrderToHistory:
    def test_first_row_inserted(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.add_order_to_history("ORD-001")
        assert widget.history_table.rowCount() == 1
        assert widget.history_table.item(0, 0).text() == "ORD-001"

    def test_most_recent_at_top(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.add_order_to_history("ORD-001")
        widget.add_order_to_history("ORD-002")
        assert widget.history_table.item(0, 0).text() == "ORD-002"

    def test_multiple_orders_count(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        for i in range(5):
            widget.add_order_to_history(f"ORD-{i:03d}")
        assert widget.history_table.rowCount() == 5


# ============================================================================
# barcode_scanned signal
# ============================================================================

class TestBarcodeScanSignal:
    def test_scan_emits_signal(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)

        received = []
        widget.barcode_scanned.connect(received.append)

        widget.scanner_input.setText("12345")
        widget.scanner_input.returnPressed.emit()

        assert received == ["12345"]

    def test_scan_clears_input_after_emit(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)

        widget.scanner_input.setText("abc")
        widget.scanner_input.returnPressed.emit()

        assert widget.scanner_input.text() == ""

    def test_manual_confirm_button_emits_signal(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)

        received = []
        widget.barcode_scanned.connect(received.append)

        btn = widget.table.cellWidget(0, 4)
        btn.click()

        assert received == ["SKU-A"]
