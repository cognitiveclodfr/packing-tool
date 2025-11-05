# План виправлення багів - Phase 1 Critical Fixes

**Дата створення:** 05.11.2025  
**Версія:** 1.0  
**Пріоритет:** КРИТИЧНИЙ

---

## 📊 Загальна оцінка

### Shopify Tool
**Статус:** 🔴 Критичні проблеми  
**Юніт тести:** ✅ ВСІ ПРОХОДЯТЬ  
**Функціональність:** ❌ НЕ ПРАЦЮЄ

**Проблеми:**
1. 🔴 Кнопка "Run Analysis" не активується
2. 🔴 Помилка "Order_Fulfillment_Status not found" при перемиканні клієнтів  
3. 🟡 Кнопка "Client Settings" не працює
4. 🟡 Пропала валідація файлів

### Packing Tool
**Статус:** 🟡 Треба виправити тести  
**Юніт тести:** 🟡 35 failed, 142 passed  
**Функціональність:** ❓ НЕМОЖЛИВО ЗІБРАТИ ЗБІРКУ

**Проблеми:**
1. 🔴 Logger tests - file locking issues (7 failures)
2. 🔴 PackerLogic tests - missing constructor args (11 failures)
3. 🟡 SessionManager tests - API changes (3 failures)
4. 🟡 SessionHistoryManager - wrong assertions (7 failures)
5. 🟡 GUI tests - Mock issues (4 errors)

---

## 🛠️ SHOPIFY TOOL - Critical Fixes

### Проблема №1: Кнопка "Run Analysis" не активується

**Root Cause:**  
Після міграції на нову архітектуру, логіка валідації файлів перестала працювати коректно. Config не завантажується правильно для нового клієнта.

**Локація:** `gui/file_handler.py:71-89`

**Діагностика:**
```python
# Поточний код (НЕ ПРАЦЮЄ):
def validate_file(self, file_type):
    if file_type == "orders":
        required_cols = self.mw.config.get("column_mappings", {}).get("orders_required", [])
    # ...
    
# ПРОБЛЕМА: self.mw.config - це старий config, не client-specific
```

**Рішення:**

**Крок 1:** Оновити `FileHandler.validate_file()` для використання client config

```python
def validate_file(self, file_type):
    """Validates CSV file headers using client-specific configuration."""
    
    # Get client_id from main window
    client_id = self.mw.current_client_id
    if not client_id:
        self.log.warning(f"No client selected, skipping validation")
        return
    
    # Load client-specific config
    try:
        client_config = self.mw.profile_manager.load_shopify_config(client_id)
        if not client_config:
            self.log.error(f"Failed to load config for client {client_id}")
            return
    except Exception as e:
        self.log.error(f"Error loading client config: {e}")
        return
    
    if file_type == "orders":
        path = self.mw.orders_file_path
        label = self.mw.orders_file_status_label
        # Get from client-specific config
        required_cols = client_config.get("column_mappings", {}).get("orders_required", [])
        delimiter = ","
    else:  # stock
        path = self.mw.stock_file_path
        label = self.mw.stock_file_status_label
        required_cols = client_config.get("column_mappings", {}).get("stock_required", [])
        delimiter = client_config.get("settings", {}).get("stock_csv_delimiter", ";")
    
    # ... rest of validation logic
```

**Крок 2:** Додати `current_client_id` в MainWindow

```python
# В gui/main_window_pyside.py __init__:
self.current_client_id = None
self.current_client_config = None
```

**Крок 3:** Оновити метод `on_client_changed()`

```python
def on_client_changed(self, client_id: str):
    """Handle client selection change."""
    self.log.info(f"Client changed to: {client_id}")
    self.current_client_id = client_id
    
    # Load client configuration
    try:
        self.current_client_config = self.profile_manager.load_shopify_config(client_id)
        if not self.current_client_config:
            QMessageBox.warning(
                self,
                "Configuration Error",
                f"Failed to load configuration for client {client_id}"
            )
            return
        
        # Enable client settings button
        self.settings_button.setEnabled(True)
        
        # Update session browser for this client
        self.session_browser.set_client(client_id)
        
        # Clear currently loaded files (they're for different client)
        self.orders_file_path = None
        self.stock_file_path = None
        self.orders_file_path_label.setText("No file loaded")
        self.stock_file_path_label.setText("No file loaded")
        self.orders_file_status_label.setText("")
        self.stock_file_status_label.setText("")
        
        # Disable Run Analysis button until files are loaded
        self.run_analysis_button.setEnabled(False)
        
        self.log.info(f"Client {client_id} loaded successfully")
        
    except Exception as e:
        self.log.error(f"Error changing client: {e}", exc_info=True)
        QMessageBox.critical(
            self,
            "Error",
            f"Failed to change client: {str(e)}"
        )
```

**Промпт для Claude Code:**
```
Репозиторій: shopify-fulfillment-tool

Задача: Виправити валідацію файлів для роботи з client-specific config

Файли для оновлення:
1. gui/file_handler.py:
   - Метод validate_file() - використовувати client config
   - Додати перевірку наявності client_id

2. gui/main_window_pyside.py:
   - Додати self.current_client_id = None в __init__
   - Додати self.current_client_config = None в __init__
   - Оновити on_client_changed() як показано вище

3. Тестування:
   - Запустити додаток
   - Обрати клієнта
   - Завантажити files → перевірити що валідація працює
   - Кнопка Run Analysis має активуватись

Критичні моменти:
- При зміні клієнта очищати завантажені файли
- Валідація має використовувати client-specific column_mappings
- Обробка помилок якщо config не завантажується
```

---

### Проблема №2: "Order_Fulfillment_Status not found"

**Root Cause:**  
Після запуску аналізу, DataFrame не містить колонки `Order_Fulfillment_Status`, але код очікує її наявність.

**Локація:** `shopify_tool/analysis.py:recalculate_statistics()`

**Діагностика:**
```python
# Код очікує цю колонку:
stats["total_orders_completed"] = df["Order_Fulfillment_Status"].value_counts().get("Fulfillable", 0)

# Але analysis.run_analysis() повертає DataFrame з іншою назвою колонки
```

**Рішення:**

**Крок 1:** Перевірити що `run_analysis()` повертає правильні назви колонок

```python
# В shopify_tool/analysis.py:run_analysis()
# Переконатись що колонка називається "Order_Fulfillment_Status", не "Status"
```

**Крок 2:** Додати перевірку наявності колонки

```python
def recalculate_statistics(df: pd.DataFrame) -> dict:
    """Recalculates statistics from the analysis DataFrame."""
    
    # Validate DataFrame has required columns
    required_cols = ["Order_Fulfillment_Status", "SKU", "Quantity", "Final_Stock"]
    missing = [col for col in required_cols if col not in df.columns]
    
    if missing:
        logger.error(f"Missing required columns in DataFrame: {missing}")
        logger.error(f"Available columns: {list(df.columns)}")
        raise ValueError(f"DataFrame missing required columns: {missing}")
    
    # ... rest of function
```

**Крок 3:** Перевірити core.py що правильно зберігає результат

```python
# В shopify_tool/core.py після run_analysis():
logger.info(f"Analysis result columns: {list(final_df.columns)}")
logger.info(f"Sample row: {final_df.iloc[0].to_dict()}")
```

**Промпт для Claude Code:**
```
Репозиторій: shopify-fulfillment-tool

Задача: Виправити помилку "Order_Fulfillment_Status not found"

Файли для оновлення:
1. shopify_tool/analysis.py:
   - run_analysis() - переконатись що колонка називається "Order_Fulfillment_Status"
   - recalculate_statistics() - додати валідацію DataFrame

2. shopify_tool/core.py:
   - Після run_analysis додати debug logging для перевірки колонок

3. Діагностика:
   - Запустити аналіз
   - Подивитись логи які колонки повертає run_analysis
   - Якщо колонка називається інакше - виправити

4. Тестування:
   - Запустити test_analysis.py - має пройти
   - Запустити аналіз в GUI
   - Перемкнути клієнта - помилки не має бути
```

---

### Проблема №3: Кнопка "Client Settings" не працює

**Root Cause:**  
Кнопка налаштувань викликає старий діалог який не адаптований під нову архітектуру.

**Локація:** `gui/actions_handler.py:open_settings_window()`

**Рішення:**

**Крок 1:** Оновити `ActionsHandler.open_settings_window()`

```python
def open_settings_window(self):
    """Opens the settings window for the active client."""
    
    # Check if client is selected
    if not self.mw.current_client_id:
        QMessageBox.warning(
            self.mw,
            "No Client Selected",
            "Please select a client first."
        )
        return
    
    # Load current client config
    client_config = self.mw.current_client_config
    if not client_config:
        try:
            client_config = self.mw.profile_manager.load_shopify_config(
                self.mw.current_client_id
            )
        except Exception as e:
            QMessageBox.critical(
                self.mw,
                "Error",
                f"Failed to load client configuration: {str(e)}"
            )
            return
    
    # Open settings dialog with client config
    from gui.settings_window_pyside import SettingsWindow
    settings_win = SettingsWindow(
        client_id=self.mw.current_client_id,
        client_config=client_config,
        profile_manager=self.mw.profile_manager,
        parent=self.mw
    )
    
    if settings_win.exec():
        # Settings were saved, reload config
        self.mw.current_client_config = self.mw.profile_manager.load_shopify_config(
            self.mw.current_client_id
        )
        self.log.info(f"Client {self.mw.current_client_id} settings updated")
```

**Крок 2:** Оновити `SettingsWindow` constructor

```python
# В gui/settings_window_pyside.py
class SettingsWindow(QDialog):
    def __init__(self, client_id, client_config, profile_manager, parent=None):
        super().__init__(parent)
        self.client_id = client_id
        self.client_config = client_config
        self.profile_manager = profile_manager
        
        self.setWindowTitle(f"Settings - Client {client_id}")
        # ... rest of init
    
    def save_settings(self):
        """Save settings back to server."""
        try:
            # Update config dict with UI values
            # ...
            
            # Save to server
            success = self.profile_manager.save_shopify_config(
                self.client_id,
                self.client_config
            )
            
            if success:
                QMessageBox.information(self, "Success", "Settings saved successfully!")
                self.accept()
            else:
                QMessageBox.warning(self, "Error", "Failed to save settings")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {str(e)}")
```

**Промпт для Claude Code:**
```
Репозиторій: shopify-fulfillment-tool

Задача: Виправити кнопку Client Settings

Файли для оновлення:
1. gui/actions_handler.py:
   - Метод open_settings_window() як показано вище
   - Перевірка current_client_id
   - Передача client-specific config

2. gui/settings_window_pyside.py:
   - Оновити constructor для прийому client_id та profile_manager
   - Оновити save_settings() для збереження через profile_manager
   - Оновити всі UI елементи щоб працювали з client_config

3. Тестування:
   - Обрати клієнта
   - Натиснути Settings
   - Змінити налаштування
   - Зберегти → має зберегтись на сервері
```

---

### Проблема №4: Пропала валідація файлів в інтерфейсі

**Root Cause:**  
Статус лейбли (✓ / ✗) не оновлюються після завантаження файлів.

**Локація:** `gui/file_handler.py:validate_file()`

**Рішення:**

**Крок 1:** Переконатись що `validate_file()` викликається

```python
def select_orders_file(self):
    """Opens file dialog for orders file."""
    filepath, _ = QFileDialog.getOpenFileName(...)
    if filepath:
        self.mw.orders_file_path = filepath
        self.mw.orders_file_path_label.setText(os.path.basename(filepath))
        self.log.info(f"Orders file selected: {filepath}")
        
        # IMPORTANT: Call validation
        self.validate_file("orders")
        self.check_files_ready()
```

**Крок 2:** Переконатись що UI labels існують

```python
# В gui/ui_manager.py при створенні файлової секції:
self.mw.orders_file_status_label = QLabel("")
self.mw.orders_file_status_label.setMinimumWidth(30)
layout.addWidget(self.mw.orders_file_status_label)
```

**Крок 3:** Додати debug logging

```python
def validate_file(self, file_type):
    # ... validation code
    
    if is_valid:
        label.setText("✓")
        label.setStyleSheet("color: green; font-weight: bold;")
        label.setToolTip("File is valid.")
        self.log.info(f"'{file_type}' file is valid: {path}")
    else:
        label.setText("✗")
        label.setStyleSheet("color: red; font-weight: bold;")
        tooltip_text = f"Missing columns: {', '.join(missing_cols)}"
        label.setToolTip(tooltip_text)
        self.log.warning(f"'{file_type}' file is invalid: {tooltip_text}")
    
    # Force UI update
    label.update()
    label.repaint()
```

**Промпт для Claude Code:**
```
Репозиторій: shopify-fulfillment-tool

Задача: Відновити валідацію файлів в UI

Файли для перевірки:
1. gui/file_handler.py:
   - select_orders_file() - переконатись що validate_file() викликається
   - select_stock_file() - те саме
   - validate_file() - додати debug logging та force update

2. gui/ui_manager.py:
   - Перевірити що status labels створюються
   - Перевірити що вони додаються в layout

3. Тестування:
   - Завантажити файл → має з'явитись ✓ або ✗
   - Завантажити невалідний файл → має показати ✗ з tooltip
   - Run Analysis має активуватись тільки після ✓✓
```

---

## 🛠️ PACKING TOOL - Test Fixes

### Проблема №1: Logger file locking (7 failures)

**Root Cause:**  
RotatingFileHandler тримає файл відкритим, tempfile не може видалити папку.

**Локація:** `tests/test_logger.py:230-330`

**Рішення:**

**Крок 1:** Додати proper cleanup в logger тестах

```python
@pytest.fixture
def temp_dir_with_cleanup():
    """Create temp directory with proper cleanup of file handlers."""
    temp_dir = tempfile.mkdtemp()
    
    yield temp_dir
    
    # Close all handlers before cleanup
    logger = logging.getLogger("PackingTool")
    handlers_copy = logger.handlers[:]
    for handler in handlers_copy:
        handler.close()
        logger.removeHandler(handler)
    
    # Now safe to remove
    try:
        shutil.rmtree(temp_dir)
    except PermissionError:
        # Last resort: wait and retry
        import time
        time.sleep(0.1)
        shutil.rmtree(temp_dir)
```

**Крок 2:** Оновити всі logger тести

```python
def test_logger_creates_log_file(temp_dir_with_cleanup):
    """Test logger creates log file."""
    temp_dir = temp_dir_with_cleanup
    
    # Initialize logger
    logger = get_logger("Test", base_path=temp_dir)
    logger.info("Test message")
    
    # Close handler before checking file
    for handler in logger.handlers[:]:
        handler.close()
    
    # Now check file
    log_file = Path(temp_dir) / "Logs" / "packing_tool" / f"{datetime.now():%Y-%m-%d}.log"
    assert log_file.exists()
    
    # Cleanup is automatic via fixture
```

**Промпт для Claude Code:**
```
Репозиторій: packing-tool

Задача: Виправити logger file locking в тестах

Файли для оновлення:
1. tests/test_logger.py:
   - Створити fixture temp_dir_with_cleanup
   - Оновити ВСІ тести що використовують tempfile
   - Додати handler.close() перед перевіркою файлів
   - Використовувати новий fixture замість tempfile.TemporaryDirectory

2. Всі affected tests (7 штук):
   - test_get_logger_singleton
   - test_logger_creates_log_directory
   - test_logger_creates_log_file
   - test_logger_writes_json_format
   - test_logger_fallback_to_local
   - test_logger_rotation_settings
   - test_complete_logging_workflow

Запустити: pytest tests/test_logger.py -v
```

---

### Проблема №2: PackerLogic missing constructor args (11 failures)

**Root Cause:**  
PackerLogic constructor змінився (додано `client_id` та `profile_manager`), але старі тести використовують старий API.

**Локація:** `tests/test_packer_logic.py`

**Рішення:**

**Крок 1:** Створити fixture з mock profile_manager

```python
@pytest.fixture
def mock_profile_manager(tmp_path):
    """Create mock ProfileManager for testing."""
    pm = Mock(spec=ProfileManager)
    pm.get_client_directory.return_value = tmp_path / "CLIENT_TEST"
    pm.load_sku_mapping.return_value = {}
    return pm

@pytest.fixture
def packer_logic(tmp_path, mock_profile_manager):
    """Create PackerLogic instance for testing."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    
    # Create mock sku_mapping_manager
    sku_mgr = Mock()
    sku_mgr.get_mapping.return_value = {}
    
    logic = PackerLogic(
        session_dir=session_dir,
        client_id="TEST",
        profile_manager=mock_profile_manager,
        sku_mapping_manager=sku_mgr
    )
    return logic
```

**Крок 2:** Оновити всі тести

```python
def test_load_file_not_found(packer_logic):
    """Test loading non-existent file."""
    result = packer_logic.load_packing_list_from_file("nonexistent.xlsx")
    assert not result

def test_packing_logic_flow(packer_logic, sample_excel_file):
    """Test complete packing flow."""
    # Load file
    assert packer_logic.load_packing_list_from_file(str(sample_excel_file))
    
    # Process and generate barcodes
    summary_df = packer_logic.process_data_and_generate_barcodes()
    assert not summary_df.empty
    # ... rest of test
```

**Промпт для Claude Code:**
```
Репозиторій: packing-tool

Задача: Виправити PackerLogic tests для нового API

Файли для оновлення:
1. tests/test_packer_logic.py:
   - Створити fixtures: mock_profile_manager та packer_logic
   - Оновити ВСІ 11 failed tests використовувати нові fixtures
   - Видалити старі прямі виклики PackerLogic()

2. Affected tests:
   - test_clear_current_order
   - test_empty_sku_in_data
   - test_invalid_quantity_in_excel
   - test_load_file_not_found
   - test_packing_logic_flow
   - test_packing_with_duplicate_sku_rows
   - test_packing_with_extra_and_unknown_skus
   - test_process_with_missing_courier_mapping
   - test_scan_sku_for_wrong_order
   - test_sku_normalization
   - test_start_packing_unknown_order
   - test_successful_processing_and_barcode_generation

Запустити: pytest tests/test_packer_logic.py -v
```

---

### Проблема №3: SessionManager unexpected keyword `base_dir` (3 failures)

**Root Cause:**  
SessionManager API змінився, тепер приймає `profile_manager` замість `base_dir`.

**Локація:** `tests/test_session_manager.py`

**Рішення:**

**Крок 1:** Оновити fixtures

```python
@pytest.fixture
def mock_profile_manager(tmp_path):
    """Create mock ProfileManager."""
    pm = Mock(spec=ProfileManager)
    pm.get_sessions_root.return_value = tmp_path / "Sessions"
    return pm

@pytest.fixture
def session_manager(mock_profile_manager):
    """Create SessionManager instance."""
    return SessionManager(profile_manager=mock_profile_manager)
```

**Крок 2:** Оновити тести

```python
def test_start_session_creates_directory_and_info_file(session_manager, mock_profile_manager):
    """Test session creation."""
    # Override sessions root to tmp_path
    sessions_root = mock_profile_manager.get_sessions_root()
    sessions_root.mkdir(parents=True, exist_ok=True)
    
    session_path = session_manager.start_session(client_id="TEST")
    
    assert Path(session_path).exists()
    assert (Path(session_path) / "session_info.json").exists()
```

**Промпт для Claude Code:**
```
Репозиторій: packing-tool

Задача: Виправити SessionManager tests для нового API

Файли для оновлення:
1. tests/test_session_manager.py:
   - Оновити fixtures використовувати profile_manager
   - Видалити всі виклики SessionManager(base_dir=...)
   - Замінити на SessionManager(profile_manager=mock_pm)

2. Affected tests (3 штуки):
   - test_end_session_removes_info_file
   - test_get_next_session_number_increments_correctly
   - test_start_session_creates_directory_and_info_file

Запустити: pytest tests/test_session_manager.py -v
```

---

### Проблема №4: SessionHistoryManager wrong assertions (7 failures)

**Root Cause:**  
Тести очікують певну кількість сесій, але структура папок змінилась.

**Локація:** `tests/test_session_history_manager.py`

**Рішення:**

**Крок 1:** Перевірити що тестові дані створюються правильно

```python
def create_test_session(client_id, session_name, base_path):
    """Helper to create test session structure."""
    session_path = base_path / "Sessions" / f"CLIENT_{client_id}" / session_name
    session_path.mkdir(parents=True, exist_ok=True)
    
    # Create session_info.json
    session_info = {
        "client_id": client_id,
        "created_at": datetime.now().isoformat(),
        "session_name": session_name,
        "status": "completed"
    }
    
    with open(session_path / "session_info.json", 'w') as f:
        json.dump(session_info, f)
    
    # Create analysis directory with orders data
    analysis_dir = session_path / "analysis"
    analysis_dir.mkdir()
    
    # Create analysis_data.json
    analysis_data = {
        "total_orders": 10,
        "orders": []
    }
    
    with open(analysis_dir / "analysis_data.json", 'w') as f:
        json.dump(analysis_data, f)
    
    return session_path
```

**Крок 2:** Оновити тести використовувати helper

```python
def test_get_client_sessions_retrieves_sessions(tmp_path):
    """Test retrieving client sessions."""
    # Create test sessions
    create_test_session("M", "2025-11-01_1", tmp_path)
    create_test_session("M", "2025-11-02_1", tmp_path)
    
    # Create history manager
    mock_pm = Mock()
    mock_pm.get_sessions_root.return_value = tmp_path / "Sessions"
    
    hist_mgr = SessionHistoryManager(mock_pm)
    sessions = hist_mgr.get_client_sessions("M")
    
    # Should find 2 sessions
    assert len(sessions) == 2
```

**Промпт для Claude Code:**
```
Репозиторій: packing-tool

Задача: Виправити SessionHistoryManager tests

Файли для оновлення:
1. tests/test_session_history_manager.py:
   - Створити helper create_test_session()
   - Оновити ВСІ тести використовувати helper
   - Перевірити що очікувані counts відповідають created data

2. Affected tests (7 штук):
   - test_export_sessions_to_dict
   - test_get_client_analytics
   - test_get_client_sessions_excludes_incomplete
   - test_get_client_sessions_filters_by_date
   - test_get_client_sessions_retrieves_sessions
   - test_parse_session_directory_extracts_metrics
   - test_search_sessions

Кожен тест має:
- Створити правильну структуру сесій
- Очікувати правильну кількість результатів

Запустити: pytest tests/test_session_history_manager.py -v
```

---

### Проблема №5: GUI integration Mock issues (4 errors)

**Root Cause:**  
Тести використовують `Mock()` замість реальних QWidget, але PySide6 не приймає Mocks.

**Локація:** `tests/test_gui_integration.py`

**Рішення:**

**Крок 1:** Замінити Mocks на реальні widgets

```python
@pytest.fixture
def app_duplicates(qtbot):
    """Create MainWindow with real widgets."""
    
    # Use real DashboardWidget instead of Mock
    with patch('src.main.DashboardWidget') as MockDash:
        real_dashboard = QWidget()  # Use real QWidget
        MockDash.return_value = real_dashboard
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        return window
```

**Крок 2:** Або використовувати spy замість mock

```python
@pytest.fixture
def app_duplicates(qtbot, monkeypatch):
    """Create MainWindow with spies."""
    
    # Don't mock widgets, but spy on methods
    window = MainWindow()
    qtbot.addWidget(window)
    
    # Spy on methods instead of mocking widgets
    spy_scan = Mock()
    monkeypatch.setattr(window.packer_logic, 'process_sku_scan', spy_scan)
    
    return window
```

**Промпт для Claude Code:**
```
Репозиторій: packing-tool

Задача: Виправити GUI integration tests

Файли для оновлення:
1. tests/test_gui_integration.py:
   - Замінити всі Mock widgets на реальні QWidget
   - Використовувати spy для методів замість mock widgets
   - Оновити fixtures app_duplicates

2. Affected tests (4 штуки):
   - test_start_session_and_load_data
   - test_packer_mode_and_scan_simulation
   - test_search_filter
   - test_reload_in_progress_order_restores_ui_state

3. Pattern для виправлення:
   # НЕПРАВИЛЬНО:
   mock_widget = Mock()
   tab_widget.addTab(mock_widget, "Dashboard")
   
   # ПРАВИЛЬНО:
   real_widget = QWidget()
   tab_widget.addTab(real_widget, "Dashboard")

Запустити: pytest tests/test_gui_integration.py -v
```

---

## 📝 Додаткові покращення

### Shopify Tool

**1. Покращити error handling:**

```python
# В gui/main_window_pyside.py:
def on_client_changed(self, client_id: str):
    try:
        # ... load config
    except NetworkError as e:
        QMessageBox.critical(
            self,
            "Network Error",
            f"Cannot connect to file server:\n{str(e)}\n\nCheck network connection."
        )
    except Exception as e:
        QMessageBox.critical(
            self,
            "Error",
            f"Unexpected error: {str(e)}"
        )
        self.log.error(f"Error in on_client_changed: {e}", exc_info=True)
```

**2. Додати loading indicator:**

```python
# В gui/actions_handler.py:run_analysis
self.mw.statusBar().showMessage("Running analysis...")
QApplication.setOverrideCursor(Qt.WaitCursor)

try:
    # ... run analysis
finally:
    QApplication.restoreOverrideCursor()
    self.mw.statusBar().clearMessage()
```

---

### Packing Tool

**1. Виправити залишкові minor issues:**

```python
# test_stats_concurrent_access.py:test_retry_mechanism_on_lock_failure
# Збільшити timeout або зменшити кількість retries в тесті

# test_worker_manager.py:test_get_worker_activities_sorted_by_timestamp
# Додати explicit sort key в assert

# test_shopify_integration.py:test_load_from_shopify_analysis_missing_required_columns
# Додати pytest.raises для очікуваного ValueError

# test_session_summary.py:test_summary_with_null_started_at
# Виправити assertion для edge case
```

---

## ⚡ Пріоритет виконання

### CRITICAL (Робити першими):
1. 🔴 Shopify: Проблема №1 (Кнопка Run Analysis)
2. 🔴 Shopify: Проблема №2 (Order_Fulfillment_Status)
3. 🔴 Packing: Проблема №2 (PackerLogic tests)

### HIGH (Робити другими):
4. 🟠 Shopify: Проблема №3 (Client Settings)
5. 🟠 Packing: Проблема №1 (Logger file locking)
6. 🟠 Packing: Проблема №3 (SessionManager tests)

### MEDIUM (Робити третіми):
7. 🟡 Shopify: Проблема №4 (Валідація файлів UI)
8. 🟡 Packing: Проблема №4 (SessionHistoryManager)
9. 🟡 Packing: Проблема №5 (GUI Mock issues)

### LOW (Опціонально):
10. 🟢 Minor test fixes
11. 🟢 Error handling improvements
12. 🟢 Loading indicators

---

## 🎯 Очікуваний результат

### Shopify Tool
- ✅ Всі юніт тести проходять (вже є)
- ✅ Кнопка Run Analysis активується після завантаження файлів
- ✅ Аналіз запускається без помилок
- ✅ Перемикання між клієнтами працює
- ✅ Client Settings відкриваються та зберігають зміни
- ✅ Валідація файлів показує статус ✓/✗

### Packing Tool
- ✅ Всі юніт тести проходять (142 → 183)
- ✅ Збірка компілюється успішно
- ✅ Додаток запускається та функціонує
- ✅ Інтеграція з Shopify Tool працює
- ✅ Сесії створюються та завантажуються правильно

---

## 📊 Timeline

**Shopify Tool Critical Fixes:** 2-3 години
**Packing Tool Test Fixes:** 3-4 години
**Testing & Verification:** 1-2 години

**Загальний час:** 6-9 годин роботи

---

**Готовий почати виправлення!** 🚀

Давай почнемо з CRITICAL issues:
1. Shopify Tool - Проблема №1 (валідація файлів)
2. Shopify Tool - Проблема №2 (Order_Fulfillment_Status)
3. Packing Tool - Проблема №2 (PackerLogic tests)

Який хочеш робити першим?
