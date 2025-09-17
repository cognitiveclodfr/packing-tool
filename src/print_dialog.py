import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QPushButton, QScrollArea, QWidget
)
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter

class PrintDialog(QDialog):
    def __init__(self, orders_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Друк баркодів")
        self.setMinimumSize(800, 600)

        self.orders_data = orders_data

        main_layout = QVBoxLayout(self)

        # Створюємо область для прокрутки, якщо баркодів багато
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)

        # Віджет, що буде містити сітку з баркодами
        self.scroll_content = QWidget()
        scroll_area.setWidget(self.scroll_content)

        grid_layout = QGridLayout(self.scroll_content)

        # Заповнюємо сітку баркодами та номерами
        row, col = 0, 0
        for order_number, data in self.orders_data.items():
            barcode_path = data['barcode_path']

            # Контейнер для одного баркоду
            item_widget = QWidget()
            item_layout = QVBoxLayout(item_widget)

            # Зображення баркоду
            pixmap = QPixmap(barcode_path)
            barcode_label = QLabel()
            barcode_label.setPixmap(pixmap.scaledToWidth(200)) # Масштабуємо для відображення
            item_layout.addWidget(barcode_label)

            # Номер замовлення
            number_label = QLabel(order_number)
            item_layout.addWidget(number_label)

            grid_layout.addWidget(item_widget, row, col)

            col += 1
            if col >= 3: # 3 баркоди в ряд
                col = 0
                row += 1

        # Кнопка друку
        print_button = QPushButton("Надрукувати")
        print_button.clicked.connect(self.print_widget)
        main_layout.addWidget(print_button)

    def print_widget(self):
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)

        if dialog.exec() == QDialog.Accepted:
            painter = QPainter()
            painter.begin(printer)

            # Рендеримо вміст scroll area на принтер
            self.scroll_content.render(painter)

            painter.end()
