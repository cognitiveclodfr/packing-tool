"""
Unit tests for src/packer_mode_widget.py — PackerModeWidget.

Requires: pytest-qt (qtbot fixture from conftest via pytest-qt plugin).

Tests cover:
- Widget initialization (UI elements created)
- display_order() — table populated, status label updated, qty highlighting
- update_item_row() — quantity and status column updated
- show_notification() — label text and style set
- clear_screen() — table cleared, status/notification reset
- update_raw_scan_display() — raw scan label updated
- add_order_to_history() — row inserted at top of history table (2 columns)
- _on_scan() / barcode_scanned signal emitted
- _on_manual_confirm() / barcode_scanned signal emitted from button
- skip_order_requested signal
- force_complete_sku signal
- update_session_progress() — progress bar updated
- display_order_metadata() — left panel populated
- update_order_summary() — summary table populated with aggregated SKUs
- show_previous_order_items() — dimmed previous order table populated
- clear_order_info() — hides metadata/summary sections
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from packer_mode_widget import PackerModeWidget


# ---------------------------------------------------------------------------
# Sample test data
# ---------------------------------------------------------------------------

SAMPLE_ITEMS = [
    {"Order_Number": "ORD-001", "SKU": "SKU-A", "Product_Name": "Product Alpha", "Quantity": 2},
    {"Order_Number": "ORD-001", "SKU": "SKU-B", "Product_Name": "Product Beta", "Quantity": 1},
]

MULTI_QTY_ITEMS = [
    {"Order_Number": "ORD-002", "SKU": "SKU-X", "Product_Name": "Widget X", "Quantity": 5},
    {"Order_Number": "ORD-002", "SKU": "SKU-Y", "Product_Name": "Widget Y", "Quantity": 1},
]

EMPTY_STATE = []

PARTIAL_STATE = [
    {"row": 0, "packed": 1, "required": 2},
]

SAMPLE_METADATA = {
    'system_note': 'Handle with care',
    'status_note': 'VIP customer — expedite',
    'internal_tags': ['priority', 'fragile'],
    'tags': ['summer-sale'],
    'created_at': '2026-01-15T10:00:00',
    'status': 'Fulfillable',
    'recommended_box': 'Box_Large',
    'shipping_method': 'express',
    'destination': 'BG',
    'order_type': 'Multi',
}


# ============================================================================
# Initialization
# ============================================================================

class TestPackerModeWidgetInit:
    def test_widget_creates(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget is not None

    def test_table_has_six_columns(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget.table.columnCount() == 6

    def test_history_table_has_two_columns(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget.history_table.columnCount() == 2

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

    def test_skip_button_initially_disabled(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert not widget.skip_button.isEnabled()

    def test_metadata_frame_initially_hidden(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget.metadata_frame.isHidden()

    def test_summary_table_initially_empty(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget.summary_table.rowCount() == 0

    def test_prev_order_table_initially_hidden(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget.prev_order_table.isHidden()

    def test_session_progress_bar_exists(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        assert widget.session_progress_bar is not None


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
        qty_text = widget.table.item(0, 2).text()
        assert qty_text == "1 / 2"

    def test_confirm_button_in_column_4(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        btn = widget.table.cellWidget(0, 4)
        assert btn is not None
        assert "Confirm" in btn.text()

    def test_force_button_in_column_5(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        btn = widget.table.cellWidget(0, 5)
        assert btn is not None
        assert "Force" in btn.text()

    def test_skip_button_enabled_after_display_order(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        assert widget.skip_button.isEnabled()

    def test_summary_table_populated_after_display_order(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        assert widget.summary_table.rowCount() > 0

    def test_qty_gt1_has_bold_font(self, qtbot):
        """Items with quantity > 1 should have bold font in the qty cell."""
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(MULTI_QTY_ITEMS, EMPTY_STATE)
        qty_item = widget.table.item(0, 2)  # SKU-X, qty=5
        assert qty_item.font().bold()

    def test_qty_eq1_not_bold(self, qtbot):
        """Items with quantity == 1 should not have bold font in qty cell."""
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(MULTI_QTY_ITEMS, EMPTY_STATE)
        qty_item = widget.table.item(1, 2)  # SKU-Y, qty=1
        assert not qty_item.font().bold()


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

    def test_force_button_stays_enabled_when_complete(self, qtbot):
        """Force button stays enabled even after row is complete (allows undo-style re-force)."""
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        widget.update_item_row(0, 2, True)
        btn = widget.table.cellWidget(0, 5)
        assert btn.isEnabled()

    def test_invalid_row_does_not_raise(self, qtbot):
        """Calling update_item_row for a row that doesn't exist should not crash."""
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
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
        assert "ORD-001" not in widget.status_label.text()

    def test_skip_button_disabled_after_clear(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        assert widget.skip_button.isEnabled()
        widget.clear_screen()
        assert not widget.skip_button.isEnabled()

    def test_metadata_frame_hidden_after_clear(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA, 'DHL')
        widget.clear_screen()
        assert widget.metadata_frame.isHidden()

    def test_summary_table_cleared_after_clear(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)
        widget.clear_screen()
        assert widget.summary_table.rowCount() == 0


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

    def test_item_count_in_second_column(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.add_order_to_history("ORD-001", item_count=3)
        assert widget.history_table.item(0, 1).text() == "3"

    def test_item_count_zero_shows_empty(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.add_order_to_history("ORD-001", item_count=0)
        # item_count=0 shows empty string per implementation
        text = widget.history_table.item(0, 1).text()
        assert text == ""


# ============================================================================
# Session progress
# ============================================================================

class TestSessionProgress:
    def test_update_session_progress_sets_value(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.update_session_progress(3, 10)
        assert widget.session_progress_bar.value() == 3
        assert widget.session_progress_bar.maximum() == 10

    def test_update_session_progress_label(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.update_session_progress(5, 20)
        assert "5" in widget.session_progress_label.text()
        assert "20" in widget.session_progress_label.text()

    def test_zero_total_does_not_crash(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.update_session_progress(0, 0)  # Should not raise (max=max(0,1)=1)


# ============================================================================
# Order metadata (left panel)
# ============================================================================

class TestDisplayOrderMetadata:
    def test_metadata_frame_becomes_visible(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA)
        assert not widget.metadata_frame.isHidden()

    def test_status_label_populated(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA)
        assert "Fulfillable" in widget.meta_status_label.text()

    def test_courier_badge_populated(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA, courier='DHL')
        assert "DHL" in widget.meta_courier_label.text()
        assert not widget.meta_courier_label.isHidden()

    def test_recommended_box_shown(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA)
        assert "Box_Large" in widget.meta_box_label.text()

    def test_created_date_shown(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA)
        assert "2026-01-15" in widget.meta_created_label.text()

    def test_tags_shown(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA)
        assert "summer-sale" in widget.meta_tags_label.text()

    def test_internal_tags_shown(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA)
        assert "priority" in widget.meta_internal_tags_label.text()

    def test_system_note_shown(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA)
        assert "Handle with care" in widget.meta_note_label.text()

    def test_status_note_shown(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA)
        assert "VIP customer" in widget.meta_status_note_label.text()
        assert not widget.meta_status_note_label.isHidden()

    def test_empty_status_note_hidden(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata({'status_note': ''})
        assert widget.meta_status_note_label.isHidden()

    def test_destination_shown(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA)
        assert "BG" in widget.meta_destination_label.text()
        assert not widget.meta_destination_label.isHidden()

    def test_order_type_shown(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA)
        assert "Multi" in widget.meta_order_type_label.text()
        assert not widget.meta_order_type_label.isHidden()

    def test_empty_destination_hidden(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata({'destination': ''})
        assert widget.meta_destination_label.isHidden()

    def test_empty_metadata_does_not_crash(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata({})  # Should not raise

    def test_missing_status_hides_status_label(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata({'system_note': 'hi'})
        assert widget.meta_status_label.isHidden()


# ============================================================================
# Order summary (aggregated items)
# ============================================================================

class TestUpdateOrderSummary:
    def test_summary_table_populated_after_update(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.update_order_summary(SAMPLE_ITEMS)
        assert widget.summary_table.rowCount() > 0

    def test_unique_skus_in_summary(self, qtbot):
        """Duplicate SKU rows should be aggregated into one summary row."""
        items_with_dup = [
            {"SKU": "SKU-A", "Product_Name": "Alpha", "Quantity": 2},
            {"SKU": "SKU-A", "Product_Name": "Alpha", "Quantity": 1},
            {"SKU": "SKU-B", "Product_Name": "Beta", "Quantity": 1},
        ]
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.update_order_summary(items_with_dup)
        assert widget.summary_table.rowCount() == 2  # SKU-A + SKU-B

    def test_aggregated_qty_correct(self, qtbot):
        """Duplicate SKU quantities should be summed."""
        items_with_dup = [
            {"SKU": "SKU-A", "Product_Name": "Alpha", "Quantity": 2},
            {"SKU": "SKU-A", "Product_Name": "Alpha", "Quantity": 3},
        ]
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.update_order_summary(items_with_dup)
        assert widget.summary_table.rowCount() == 1
        assert widget.summary_table.item(0, 2).text() == "5"

    def test_empty_items_does_not_crash(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.update_order_summary([])  # Should not raise


# ============================================================================
# Previous order items (dimmed history)
# ============================================================================

class TestShowPreviousOrderItems:
    def test_prev_table_becomes_visible(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.show_previous_order_items(SAMPLE_ITEMS)
        assert not widget.prev_order_table.isHidden()

    def test_prev_table_row_count(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.show_previous_order_items(SAMPLE_ITEMS)
        assert widget.prev_order_table.rowCount() == len(SAMPLE_ITEMS)

    def test_prev_table_sku_populated(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.show_previous_order_items(SAMPLE_ITEMS)
        assert widget.prev_order_table.item(0, 0).text() == "SKU-A"

    def test_empty_items_does_not_crash(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.show_previous_order_items([])  # Should not raise


# ============================================================================
# clear_order_info
# ============================================================================

class TestClearOrderInfo:
    def test_hides_metadata_frame(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA)
        assert not widget.metadata_frame.isHidden()
        widget.clear_order_info()
        assert widget.metadata_frame.isHidden()

    def test_hides_metadata_frame_via_clear_order_info(self, qtbot):
        """clear_order_info() hides metadata frame; summary table is cleared separately by clear_screen."""
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order_metadata(SAMPLE_METADATA)
        assert not widget.metadata_frame.isHidden()
        widget.clear_order_info()
        assert widget.metadata_frame.isHidden()


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


# ============================================================================
# skip_order_requested signal
# ============================================================================

class TestSkipOrderSignal:
    def test_skip_button_emits_signal(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)  # enables skip button

        received = []
        widget.skip_order_requested.connect(lambda: received.append(True))

        widget.skip_button.click()

        assert received == [True]

    def test_skip_button_disabled_does_not_emit(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        # Skip button is disabled initially — clicking it should not emit

        received = []
        widget.skip_order_requested.connect(lambda: received.append(True))

        # Programmatically click when disabled — Qt won't emit for disabled buttons
        widget.skip_button.click()

        assert received == []


# ============================================================================
# force_complete_sku signal
# ============================================================================

class TestForceCompleteSkuSignal:
    def test_force_button_emits_signal(self, qtbot):
        widget = PackerModeWidget()
        qtbot.addWidget(widget)
        widget.display_order(SAMPLE_ITEMS, EMPTY_STATE)

        received = []
        widget.force_complete_sku.connect(received.append)

        btn = widget.table.cellWidget(0, 5)
        btn.click()

        assert received == ["SKU-A"]
