import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QFileDialog, QStackedWidget
)
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtMultimedia import QSoundEffect

from mapping_dialog import ColumnMappingDialog
from print_dialog import PrintDialog
from packer_mode_widget import PackerModeWidget
from packer_logic import PackerLogic, REQUIRED_COLUMNS # Keep for dialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Packer's Assistant")
        self.resize(1024, 768)

        # Створюємо локальну папку для баркодів
        self.barcode_dir = "barcodes"
        os.makedirs(self.barcode_dir, exist_ok=True)

        self.logic = PackerLogic(self.barcode_dir)

        self._init_sounds()
        self._init_ui()

        if self.sounds_missing:
            self.status_label.setText(self.status_label.text() + "\nПопередження: Звукові файли не знайдено.")

    def _init_ui(self):
        self.setup_widget = QWidget()
        self.packer_mode_widget = PackerModeWidget()
        self.packer_mode_widget.barcode_scanned.connect(self.on_scanner_input)
        self.packer_mode_widget.exit_packing_mode.connect(self.switch_to_setup_mode)

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

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.setup_widget)
        self.stacked_widget.addWidget(self.packer_mode_widget)
        self.setCentralWidget(self.stacked_widget)

    def _init_sounds(self):
        self.sounds_missing = False
        sound_files = {"success": "sounds/success.wav", "error": "sounds/error.wav", "victory": "sounds/victory.wav"}

        self.success_sound = QSoundEffect()
        if os.path.exists(sound_files["success"]): self.success_sound.setSource(QUrl.fromLocalFile(sound_files["success"]))
        else: self.sounds_missing = True

        self.error_sound = QSoundEffect()
        if os.path.exists(sound_files["error"]): self.error_sound.setSource(QUrl.fromLocalFile(sound_files["error"]))
        else: self.sounds_missing = True

        self.victory_sound = QSoundEffect()
        if os.path.exists(sound_files["victory"]): self.victory_sound.setSource(QUrl.fromLocalFile(sound_files["victory"]))
        else: self.sounds_missing = True

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Виберіть пакувальний лист", "", "Excel Files (*.xlsx)")
        if file_path:
            self.load_and_process_file(file_path)

    def load_and_process_file(self, file_path):
        try:
            df = self.logic.load_packing_list_from_file(file_path)

            file_columns = list(df.columns)
            mapping = None
            if not all(col in file_columns for col in REQUIRED_COLUMNS):
                dialog = ColumnMappingDialog(REQUIRED_COLUMNS, file_columns, self)
                if not dialog.exec():
                    self.status_label.setText("Завантаження скасовано.")
                    return
                mapping = dialog.get_mapping()
                # The detailed validation is now inside PackerLogic,
                # which will raise a ValueError caught below.

            self.status_label.setText("Файл завантажено, обробка...")
            order_count = self.logic.process_data_and_generate_barcodes(mapping)

            self.status_label.setText(f"Успішно оброблено {order_count} замовлень.")
            self.print_button.setEnabled(True)
            self.packer_mode_button.setEnabled(True)

        except (ValueError, RuntimeError) as e:
            self.status_label.setText(f"Помилка: {e}")
        except Exception as e:
            self.status_label.setText(f"Неочікувана помилка: {e}")

    def switch_to_packer_mode(self):
        self.stacked_widget.setCurrentWidget(self.packer_mode_widget)
        self.packer_mode_widget.set_focus_to_scanner()

    def switch_to_setup_mode(self):
        """Switches the view back to the main setup screen."""
        self.logic.clear_current_order()
        self.packer_mode_widget.clear_screen()
        self.stacked_widget.setCurrentWidget(self.setup_widget)

    def open_print_dialog(self):
        if not self.logic.orders_data:
            self.status_label.setText("Немає даних для друку.")
            return
        dialog = PrintDialog(self.logic.orders_data, self)
        dialog.exec()

    def on_scanner_input(self, text: str):
        self.packer_mode_widget.show_notification("", "black")

        if self.logic.current_order_number is None:
            items, status = self.logic.start_order_packing(text)
            if status == "ORDER_LOADED":
                self.packer_mode_widget.display_order(items)
            else: # ORDER_NOT_FOUND
                self.packer_mode_widget.show_notification("ЗАМОВЛЕННЯ НЕ ЗНАЙДЕНО", "red")
                self.error_sound.play()
        else:
            result, status = self.logic.process_sku_scan(text)
            if status == "SKU_OK":
                self.packer_mode_widget.update_item_row(result["row"], result["packed"], result["is_complete"])
                self.success_sound.play()
            elif status == "SKU_NOT_FOUND":
                self.packer_mode_widget.show_notification("НЕПРАВИЛЬНИЙ ТОВАР!", "red")
                self.error_sound.play()
            elif status == "ORDER_COMPLETE":
                self.packer_mode_widget.update_item_row(result["row"], result["packed"], result["is_complete"])
                self.packer_mode_widget.show_notification(f"ЗАМОВЛЕННЯ {self.logic.current_order_number} ЗІБРАНО!", "green")
                self.victory_sound.play()
                self.logic.clear_current_order()
                QTimer.singleShot(3000, self.packer_mode_widget.clear_screen)
            # SKU_EXTRA is ignored

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
