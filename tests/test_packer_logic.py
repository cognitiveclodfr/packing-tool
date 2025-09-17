import unittest
import sys
import os
import tempfile
import shutil

# Додаємо шлях до src, щоб можна було імпортувати packer_logic
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from packer_logic import PackerLogic

class TestPackerLogic(unittest.TestCase):

    def setUp(self):
        """Налаштовує тимчасову папку для тестів."""
        self.test_dir = tempfile.mkdtemp()
        self.logic = PackerLogic(barcode_dir=self.test_dir)

    def tearDown(self):
        """Прибирає тимчасову папку після тестів."""
        shutil.rmtree(self.test_dir)

    def test_load_and_process_user_file(self):
        """
        Тест, що відтворює помилку користувача, використовуючи його файл.
        Ми очікуємо, що цей тест впаде з тією ж помилкою.
        """
        user_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../packing_list_ALL.xlsx'))

        # Перевіряємо, чи файл існує, перш ніж запускати тест
        if not os.path.exists(user_file_path):
            self.skipTest(f"Тестовий файл не знайдено: {user_file_path}")

        print(f"Тестування з файлом: {user_file_path}")

        # Етап 1: Завантаження
        df = self.logic.load_packing_list_from_file(user_file_path)
        file_columns = df.columns.tolist()
        print(f"Знайдено колонки: {file_columns}")

        # Етап 2: Симуляція мапінгу від користувача.
        # Product_Name відсутній у файлі, тому ми не можемо його зіставити.
        mapping = {
            'Order_Number': 'Order_Number',
            'SKU': 'SKU',
            'Quantity': 'Quantity',
            # 'Product_Name': ???
        }

        # Етап 3: Обробка. Ми очікуємо, що цей крок викличе помилку,
        # оскільки Product_Name не може бути зіставлений.
        # В ідеалі, логіка має кидати ValueError.
        with self.assertRaises(ValueError):
            self.logic.process_data_and_generate_barcodes(mapping)

if __name__ == '__main__':
    unittest.main()
