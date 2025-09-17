import sys
import os
import shutil
import tempfile
import pandas as pd
import barcode
from barcode.writer import ImageWriter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QFileDialog, QStackedWidget
)
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtMultimedia import QSoundEffect

from mapping_dialog import ColumnMappingDialog
from print_dialog import PrintDialog
from packer_mode_widget import PackerModeWidget

REQUIRED_COLUMNS = ['Order_Number', 'SKU', 'Product_Name', 'Quantity']

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Packer's Assistant")
        self.resize(1024, 768)

        self.packing_list_df = None
        self.orders_data = None
        self.barcode_dir = tempfile.mkdtemp(prefix="packers-assistant-")

        # Стан пакувальника
        self.current_order_number = None
        self.current_order_state = {} # {sku: {'required': X, 'packed': Y, 'row': Z}}

        self._init_sounds()

        # --- Створення віджетів для сторінок ---
        self.setup_widget = QWidget()
        self.packer_mode_widget = PackerModeWidget()
        self.packer_mode_widget.barcode_scanned.connect(self.on_scanner_input)

        # --- Налаштування сторінки 1 (Setup) ---
        setup_layout = QVBoxLayout(self.setup_widget)
        self.load_button = QPushButton("Завантажити пакувальний лист (.xlsx)")
        self.load_button.clicked.connect(self.open_file_dialog)
        self.print_button = QPushButton("Перейти до друку баркодів")
        self.print_button.setEnabled(False)
        self.print_button.clicked.connect(self.open_print_dialog)
        self.packer_mode_button = QPushButton("Перейти в режим пакувальника")
        self.packer_mode_button.setEnabled(False)
        self.packer_mode_button.clicked.connect(self.switch_to_packer_mode)
        self.status_label = QLabel("Будь ласка, завантажте пакувальний лист.")

        setup_layout.addWidget(self.load_button)
        setup_layout.addWidget(self.print_button)
        setup_layout.addWidget(self.packer_mode_button)
        setup_layout.addWidget(self.status_label)

        # --- Головний QStackedWidget ---
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.setup_widget)
        self.stacked_widget.addWidget(self.packer_mode_widget)
        self.setCentralWidget(self.stacked_widget)

    def _init_sounds(self):
        """Ініціалізує звукові ефекти."""
        # Примітка: Файли .wav повинні знаходитись у папці 'sounds'
        self.success_sound = QSoundEffect()
        self.success_sound.setSource(QUrl.fromLocalFile("sounds/success.wav"))
        self.error_sound = QSoundEffect()
        self.error_sound.setSource(QUrl.fromLocalFile("sounds/error.wav"))
        self.victory_sound = QSoundEffect()
        self.victory_sound.setSource(QUrl.fromLocalFile("sounds/victory.wav"))

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Виберіть пакувальний лист", "", "Excel Files (*.xlsx)")
        if file_path:
            self.load_packing_list(file_path)

    def load_packing_list(self, file_path: str):
        try:
            df = pd.read_excel(file_path, dtype=str).fillna('')
            self.process_columns(df)
        except Exception as e:
            self.status_label.setText(f"Помилка завантаження файлу: {e}")

    def process_columns(self, df: pd.DataFrame):
        file_columns = list(df.columns)
        if not all(col in file_columns for col in REQUIRED_COLUMNS):
            dialog = ColumnMappingDialog(REQUIRED_COLUMNS, file_columns, self)
            if not dialog.exec():
                self.status_label.setText("Завантаження скасовано.")
                return

            mapping = dialog.get_mapping()
            if len(mapping) != len(REQUIRED_COLUMNS):
                self.status_label.setText("Помилка: Не всі необхідні колонки були зіставлені.")
                return

            inverted_mapping = {v: k for k, v in mapping.items()}
            df.rename(columns=inverted_mapping, inplace=True)

        self.packing_list_df = df
        self.status_label.setText("Файл завантажено, обробка...")
        self.generate_barcodes_and_process_orders()

    def generate_barcodes_and_process_orders(self):
        try:
            self.orders_data = {}
            code128 = barcode.get_barcode_class('code128')

            # Групуємо дані по номеру замовлення
            grouped = self.packing_list_df.groupby('Order_Number')

            unnamed_counter = 1
            for order_number, group in grouped:
                # Генерація баркоду
                # Замінюємо символи, що не підходять для назв файлів
                safe_order_number = "".join(c for c in order_number if c.isalnum() or c in ('-', '_')).rstrip()

                if not safe_order_number:
                    safe_order_number = f"unnamed_order_{unnamed_counter}"
                    unnamed_counter += 1

                barcode_path = os.path.join(self.barcode_dir, f"{safe_order_number}.png")
                bc = code128(order_number, writer=ImageWriter())
                bc.write(barcode_path)

                # Зберігаємо інформацію про замовлення
                self.orders_data[order_number] = {
                    'barcode_path': barcode_path,
                    'items': group.to_dict('records')
                }

            self.status_label.setText(f"Успішно оброблено {len(self.orders_data)} замовлень. Можна переходити до друку або пакування.")
            self.print_button.setEnabled(True)
            self.packer_mode_button.setEnabled(True)
            print(f"Generated {len(self.orders_data)} barcodes in {self.barcode_dir}")

        except Exception as e:
            self.status_label.setText(f"Помилка під час генерації баркодів: {e}")

    def switch_to_packer_mode(self):
        self.stacked_widget.setCurrentWidget(self.packer_mode_widget)
        self.packer_mode_widget.set_focus_to_scanner()

    def open_print_dialog(self):
        if not self.orders_data:
            self.status_label.setText("Немає даних для друку. Спочатку завантажте файл.")
            return

        dialog = PrintDialog(self.orders_data, self)
        dialog.exec()

    def on_scanner_input(self, text: str):
        self.packer_mode_widget.show_notification("", "black") # Очищуємо попередні повідомлення

        if self.current_order_number is None:
            # Очікуємо на сканування замовлення
            self.process_order_scan(text)
        else:
            # Очікуємо на сканування товару (SKU)
            self.process_sku_scan(text)

    def process_order_scan(self, order_number: str):
        if order_number in self.orders_data:
            self.current_order_number = order_number
            items = self.orders_data[order_number]['items']

            # Ініціалізуємо стан замовлення
            self.current_order_state = {}
            for i, item in enumerate(items):
                sku = item['SKU']
                self.current_order_state[sku] = {
                    'required': int(item['Quantity']),
                    'packed': 0,
                    'row': i
                }

            self.packer_mode_widget.display_order(items)
        else:
            self.packer_mode_widget.show_notification("ЗАМОВЛЕННЯ НЕ ЗНАЙДЕНО", "red")
            self.error_sound.play()

    def process_sku_scan(self, sku: str):
        if sku in self.current_order_state:
            state = self.current_order_state[sku]
            if state['packed'] < state['required']:
                state['packed'] += 1
                is_complete = state['packed'] == state['required']
                self.packer_mode_widget.update_item_row(state['row'], state['packed'], is_complete)
                self.success_sound.play()
                self.check_order_completion()
            else:
                # Зайвий товар, ігноруємо згідно з вимогами
                pass
        else:
            self.packer_mode_widget.show_notification("НЕПРАВИЛЬНИЙ ТОВАР!", "red")
            self.error_sound.play()

    def check_order_completion(self):
        if all(s['packed'] == s['required'] for s in self.current_order_state.values()):
            self.packer_mode_widget.show_notification(f"ЗАМОВЛЕННЯ {self.current_order_number} ЗІБРАНО!", "green")
            self.victory_sound.play()
            self.current_order_number = None
            self.current_order_state = {}
            QTimer.singleShot(3000, self.packer_mode_widget.clear_screen)

    def closeEvent(self, event):
        """Прибираємо за собою тимчасову папку при закритті."""
        print(f"Cleaning up temporary directory: {self.barcode_dir}")
        shutil.rmtree(self.barcode_dir)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
