from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QDialogButtonBox
)

class ColumnMappingDialog(QDialog):
    def __init__(self, required_columns, file_columns, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Зіставлення колонок")

        self.mapping = {}
        self.required_columns = required_columns
        self.file_columns = file_columns

        layout = QVBoxLayout(self)

        description = QLabel("Будь ласка, вкажіть, які колонки у вашому файлі відповідають необхідним полям.")
        layout.addWidget(description)

        self.combo_boxes = {}
        for req_col in self.required_columns:
            row_layout = QHBoxLayout()

            label = QLabel(f"Потрібна колонка: <b>{req_col}</b>")
            row_layout.addWidget(label)

            combo = QComboBox()
            combo.addItems([""] + self.file_columns) # Додаємо порожній варіант
            row_layout.addWidget(combo)

            self.combo_boxes[req_col] = combo
            layout.addLayout(row_layout)

        # Кнопки OK та Cancel
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_mapping(self):
        """Повертає словник зіставлення, вибраний користувачем."""
        for req_col, combo in self.combo_boxes.items():
            selected_col = combo.currentText()
            if selected_col:
                self.mapping[req_col] = selected_col
        return self.mapping
