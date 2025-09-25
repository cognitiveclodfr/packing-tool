from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QMessageBox, QInputDialog, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt
from typing import Dict

class SKUMappingDialog(QDialog):
    """
    A dialog window for users to manage Barcode-to-SKU mappings.

    Provides a table view to display the current mappings and buttons to
    add, edit, or delete entries. Changes are only saved when the user
    clicks the "Save" button.
    """

    def __init__(self, sku_mapping_manager, parent=None):
        """
        Initializes the dialog.

        Args:
            sku_mapping_manager: An instance of SKUMappingManager to handle
                                 data persistence.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("SKU Mapping Management")
        self.setMinimumSize(600, 400)

        self.manager = sku_mapping_manager
        # Work on a copy, so changes can be cancelled
        self.current_map = self.manager.get_map().copy()

        self._init_ui()
        self._populate_table()

    def _init_ui(self):
        """Sets up the UI components and layout."""
        layout = QVBoxLayout(self)

        # Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Product Barcode", "Internal SKU"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)

        # CRUD Buttons
        button_layout = QHBoxLayout()
        add_button = QPushButton("Add")
        add_button.clicked.connect(self._add_item)
        edit_button = QPushButton("Edit")
        edit_button.clicked.connect(self._edit_item)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self._delete_item)

        button_layout.addWidget(add_button)
        button_layout.addWidget(edit_button)
        button_layout.addWidget(delete_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Dialog Buttons
        dialog_button_layout = QHBoxLayout()
        dialog_button_layout.addStretch()
        save_button = QPushButton("Save & Close")
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        dialog_button_layout.addWidget(save_button)
        dialog_button_layout.addWidget(cancel_button)
        layout.addLayout(dialog_button_layout)

    def _populate_table(self):
        """Fills the table with data from the current map."""
        self.table.setRowCount(0) # Clear table
        for barcode, sku in sorted(self.current_map.items()):
            row_position = self.table.rowCount()
            self.table.insertRow(row_position)
            self.table.setItem(row_position, 0, QTableWidgetItem(barcode))
            self.table.setItem(row_position, 1, QTableWidgetItem(sku))

    def _add_item(self):
        """Handles the logic for adding a new mapping entry."""
        barcode, ok1 = QInputDialog.getText(self, "Add Entry", "Enter Product Barcode:")
        if not (ok1 and barcode):
            return

        if barcode in self.current_map:
            QMessageBox.warning(self, "Duplicate Barcode", "This barcode already exists in the map.")
            return

        sku, ok2 = QInputDialog.getText(self, "Add Entry", f"Enter Internal SKU for '{barcode}':")
        if not (ok2 and sku):
            return

        self.current_map[barcode] = sku
        self._populate_table()

    def _edit_item(self):
        """Handles the logic for editing an existing entry."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Selection Error", "Please select a row to edit.")
            return

        row_index = selected_rows[0].row()
        barcode_item = self.table.item(row_index, 0)
        old_sku_item = self.table.item(row_index, 1)

        barcode = barcode_item.text()
        old_sku = old_sku_item.text()

        new_sku, ok = QInputDialog.getText(self, "Edit SKU", f"Enter new Internal SKU for barcode '{barcode}':", text=old_sku)

        if ok and new_sku and new_sku != old_sku:
            self.current_map[barcode] = new_sku
            self._populate_table()
            # Reselect the edited row for better UX
            self.table.selectRow(row_index)

    def _delete_item(self):
        """Handles the logic for deleting an entry."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Selection Error", "Please select a row to delete.")
            return

        row_index = selected_rows[0].row()
        barcode = self.table.item(row_index, 0).text()

        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete the mapping for barcode '{barcode}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if barcode in self.current_map:
                del self.current_map[barcode]
            self._populate_table()

    def accept(self):
        """
        Saves the changes via the manager when the dialog is accepted.
        """
        self.manager.save_map(self.current_map)
        super().accept()