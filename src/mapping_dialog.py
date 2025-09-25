from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDialogButtonBox, QMessageBox, QWidget
)
from typing import List, Dict

class ColumnMappingDialog(QDialog):
    """
    A dialog window for mapping required columns to columns from an imported file.

    This dialog is presented to the user when an imported Excel file does not
    contain the standard required column names. It allows the user to manually
    associate the application's required fields (e.g., 'Order_Number', 'SKU')
    with the actual column names present in their file.

    Attributes:
        mapping (Dict[str, str]): The resulting mapping from required columns
                                   to file columns.
        required_columns (List[str]): The list of column names the application needs.
        file_columns (List[str]): The list of column names found in the user's file.
        combo_boxes (Dict[str, QComboBox]): A dictionary holding the QComboBox
                                            widgets for each required column.
    """
    def __init__(self, required_columns: List[str], file_columns: List[str], parent: QWidget = None):
        """
        Initializes the ColumnMappingDialog.

        Args:
            required_columns (List[str]): A list of column names that the
                                          application requires.
            file_columns (List[str]): A list of column names found in the
                                      imported file.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setWindowTitle("Column Mapping")

        self.mapping = {}
        self.required_columns = required_columns
        self.file_columns = file_columns

        layout = QVBoxLayout(self)

        description = QLabel("Please specify which columns in your file correspond to the required fields.")
        layout.addWidget(description)

        self.combo_boxes = {}
        for req_col in self.required_columns:
            row_layout = QHBoxLayout()

            label = QLabel(f"Required column: <b>{req_col}</b>")
            row_layout.addWidget(label)

            combo = QComboBox()
            combo.addItems([""] + self.file_columns)  # Add a blank option
            row_layout.addWidget(combo)

            self.combo_boxes[req_col] = combo
            layout.addLayout(row_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def validate_and_accept(self):
        """
        Validates that all required columns are mapped before closing the dialog.

        This method is connected to the 'OK' button's accepted signal. It checks
        if every required column has been assigned a corresponding file column.
        If the mapping is incomplete, it shows a warning message. Otherwise, it
        accepts the dialog.
        """
        self.mapping = {}
        unmapped_columns = []
        for req_col, combo in self.combo_boxes.items():
            selected_col = combo.currentText()
            if selected_col:
                self.mapping[req_col] = selected_col
            else:
                unmapped_columns.append(req_col)

        if unmapped_columns:
            msg = "All required fields must be mapped.\nPlease map the following columns:\n\n"
            msg += "\n".join(unmapped_columns)
            QMessageBox.warning(self, "Incomplete Mapping", msg)
        else:
            self.accept()

    def get_mapping(self) -> Dict[str, str]:
        """
        Returns the final mapping dictionary created by the user.

        Returns:
            Dict[str, str]: A dictionary where keys are the required column
                            names and values are the corresponding column names
                            from the user's file.
        """
        return self.mapping
