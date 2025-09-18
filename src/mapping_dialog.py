from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QDialogButtonBox, QMessageBox
)

class ColumnMappingDialog(QDialog):
    def __init__(self, required_columns, file_columns, parent=None):
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
            combo.addItems([""] + self.file_columns) # Add a blank option
            row_layout.addWidget(combo)

            self.combo_boxes[req_col] = combo
            layout.addLayout(row_layout)

        # OK and Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def validate_and_accept(self):
        """Validates that all required columns are mapped before accepting."""
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

    def get_mapping(self):
        """Returns the mapping dictionary selected by the user."""
        return self.mapping
