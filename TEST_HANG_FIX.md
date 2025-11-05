# Виправлення зависання інтеграційних тестів

## Проблема

Інтеграційний тест `test_start_session_and_load_data` в файлі `tests/test_gui_integration.py` зависав при виконанні.

### Симптоми
- Тест починався (виводився "Starting test: ..."), але ніколи не завершувався
- Зависання відбувалося як при пул реквестах, так і при релізах
- Тест не виводив жодних помилок, просто зупинявся

## Діагностика

### Причина зависання

Проблема полягала в тому, що тести **не мокували** критичні залежності `MainWindow`, які намагалися підключитися до реального файлового сервера:

1. **ProfileManager** - при ініціалізації намагається підключитися до мережевого шляху `\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment` (з `config.ini`)

2. Якщо підключення не вдається, `ProfileManager` викидає `NetworkError`

3. В `MainWindow.__init__()` цей exception перехоплюється і показується **модальне вікно** `QMessageBox.critical`:
   ```python
   except NetworkError as e:
       QMessageBox.critical(
           self,
           "Network Error",
           f"Cannot connect to file server:\n\n{e}\n\n"
           f"Please check your network connection and try again."
       )
       sys.exit(1)
   ```

4. Модальне вікно **блокує** виконання тесту в очікуванні взаємодії користувача
5. Оскільки в CI/CD немає GUI та користувача, тест зависає назавжди

### Додаткові проблеми

Навіть якщо `ProfileManager` був би замоканий, були б інші точки зависання:

1. При виклику `start_session()` без вибраного клієнта показується `QMessageBox.warning`:
   ```python
   if not self.current_client_id:
       QMessageBox.warning(self, "No Client Selected", "...")
       return
   ```

2. Інші залежності які не були замокані:
   - `SessionLockManager`
   - `StatisticsManager`
   - `DashboardWidget`
   - `SessionHistoryWidget`
   - `SessionManager` (створюється в `start_session()`)
   - `PackerLogic` (створюється в `start_session()`)

## Рішення

Додано комплексне мокування всіх залежностей для ізоляції тестів від файлового сервера та мережі.

### Додані моки

1. **`mock_profile_manager`** - мокає `ProfileManager`:
   ```python
   @pytest.fixture
   def mock_profile_manager(tmp_path):
       with patch('main.ProfileManager') as mock_pm_class:
           mock_pm = Mock()
           mock_pm.get_available_clients.return_value = ['TEST_CLIENT']
           mock_pm.load_client_config.return_value = {...}
           # ... інші методи
           mock_pm_class.return_value = mock_pm
           yield mock_pm
   ```

2. **`mock_session_lock_manager`** - мокає `SessionLockManager`

3. **`mock_stats_manager`** - мокає `StatisticsManager`

4. **`mock_widgets`** - мокає `DashboardWidget` та `SessionHistoryWidget`

5. **Вбудовані моки в fixtures `app_basic` та `app_duplicates`**:
   - `SessionManager` - мокається з необхідними методами
   - `PackerLogic` - мокається з базовим станом

### Оновлені фікстури

Обидві тестові фікстури (`app_basic` та `app_duplicates`) оновлені:

```python
@pytest.fixture
def app_basic(qtbot, test_excel_file_basic, mock_profile_manager,
              mock_session_lock_manager, mock_stats_manager, mock_widgets, tmp_path):
    with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName') as mock_dialog, \
         patch('main.SessionManager') as mock_session_mgr_class, \
         patch('main.PackerLogic') as mock_packer_logic_class:

        # ... налаштування моків ...

        window = MainWindow()
        window.current_client_id = 'TEST_CLIENT'  # Вручну встановлюємо клієнта

        yield window, qtbot
```

### Ключові зміни

1. ✅ Всі мережеві залежності замокані
2. ✅ Модальні діалоги не можуть з'явитися (немає реальних помилок)
3. ✅ `current_client_id` встановлюється вручну, щоб уникнути діалогу "No Client Selected"
4. ✅ Використовується `tmp_path` для тимчасових директорій
5. ✅ Всі моки налаштовані з відповідними return values

## Результат

- Тести тепер повністю ізольовані від файлової системи та мережі
- Немає залежностей від зовнішніх ресурсів
- Тести можуть виконуватися в CI/CD середовищі без GUI
- Час виконання тестів скоротився (немає мережевих затримок)

## Уроки

1. **Завжди мокайте зовнішні залежності** в інтеграційних тестах GUI
2. **Модальні діалоги блокують тести** - перевіряйте код на їх наявність
3. **Використовуйте pattern** з `test_gui_navigation.py` для нових тестів
4. **Тестуйте локально з тими ж моками**, що і в CI/CD

## Файли змінені

- `tests/test_gui_integration.py` - додано моки для всіх залежностей

## Як запустити тести

```bash
# Встановити залежності
pip install pytest pytest-qt PySide6 pandas openpyxl

# Запустити конкретний тест
pytest tests/test_gui_integration.py::test_start_session_and_load_data -v

# Запустити всі інтеграційні тести
pytest tests/test_gui_integration.py -v
```

## Подяки

Проблему діагностовано шляхом аналізу коду:
1. Виявлено що `ProfileManager` намагається підключитися до мережі
2. Знайдено модальні діалоги які блокують виконання
3. Використано pattern з `test_gui_navigation.py` для виправлення
