# Phase 1.2: Session Locking & Conflict Prevention

## Огляд проблеми

**Поточна критична проблема:**
Коли користувач відкриває додаток на своєму ПК, поки на іншому ПК вже працює інша людина з тим самим клієнтом, додаток пропонує відновити активну сесію. Це призводить до:
- Конфліктів даних між двома ПК
- Втрати даних при одночасному записі
- Плутанини у користувачів

**Рішення Phase 1.2:**
Система блокування сесій, яка запобігає одночасному доступу до однієї сесії з різних ПК та коректно показує статус активних сесій.

---

## Технічна архітектура

### 1. Файл блокування сесії `.session.lock`

**Розташування:** `{client_dir}/sessions/{session_timestamp}/.session.lock`

**Структура JSON:**
```json
{
  "locked_by": "DESKTOP-ABC123",
  "user_name": "Іван Петренко",
  "lock_time": "2025-10-28T14:30:45",
  "process_id": 12345,
  "app_version": "1.2.0",
  "heartbeat": "2025-10-28T14:35:12"
}
```

**Поля:**
- `locked_by` - Ім'я комп'ютера (socket.gethostname())
- `user_name` - Ім'я користувача Windows (os.getlogin())
- `lock_time` - Коли сесію було заблоковано (ISO 8601)
- `process_id` - PID процесу Python
- `app_version` - Версія додатку
- `heartbeat` - Останнє оновлення heartbeat (кожні 30 сек)

### 2. SessionLockManager клас

**Файл:** `src/session_lock_manager.py` (новий)

**Відповідальності:**
- Створення та звільнення блокувань
- Перевірка статусу блокування
- Heartbeat для підтримки живості
- Crash recovery для застарілих locks
- Інформація про власника блокування

**Ключові методи:**

```python
class SessionLockManager:
    def __init__(self, profile_manager):
        """Ініціалізує менеджер блокувань"""

    def acquire_lock(self, client_id: str, session_dir: Path) -> Tuple[bool, Optional[str]]:
        """
        Спроба захопити блокування сесії.

        Returns:
            (success: bool, error_message: Optional[str])
            - (True, None) якщо блокування успішно
            - (False, "message") якщо сесія вже заблокована з деталями
        """

    def release_lock(self, session_dir: Path) -> bool:
        """Звільнити блокування при закритті сесії"""

    def is_locked(self, session_dir: Path) -> Tuple[bool, Optional[Dict]]:
        """
        Перевірити чи заблокована сесія.

        Returns:
            (is_locked: bool, lock_info: Optional[Dict])
            - (False, None) якщо не заблокована
            - (True, {...}) якщо заблокована з інфо про власника
        """

    def update_heartbeat(self, session_dir: Path) -> bool:
        """Оновити heartbeat для активної сесії (кожні 30 сек)"""

    def is_lock_stale(self, lock_info: Dict, stale_timeout: int = 300) -> bool:
        """
        Перевірити чи lock застарілий (можливо програма впала).

        Args:
            stale_timeout: Секунд без heartbeat після якого lock вважається застарілим
                         (за замовчуванням 5 хвилин)
        """

    def force_release_lock(self, session_dir: Path) -> bool:
        """Примусово звільнити lock (для recovery після crash)"""

    def get_lock_display_info(self, lock_info: Dict) -> str:
        """
        Форматувати інформацію про lock для відображення користувачу.

        Returns:
            "Заблоковано користувачем Іван Петренко на ПК DESKTOP-ABC123\n
             Час блокування: 28.10.2025 14:30"
        """
```

### 3. Інтеграція з SessionManager

**Зміни у `src/session_manager.py`:**

```python
class SessionManager:
    def __init__(self, client_id: str, profile_manager, lock_manager):
        self.client_id = client_id
        self.profile_manager = profile_manager
        self.lock_manager = lock_manager  # НОВИЙ
        self.heartbeat_timer = None  # НОВИЙ

    def start_session(self, packing_list_path: str, restore_dir: str = None) -> str:
        """Модифікований для роботи з блокуваннями"""

        if restore_dir:
            # Перевірити чи сесія не заблокована
            is_locked, lock_info = self.lock_manager.is_locked(Path(restore_dir))

            if is_locked:
                # Перевірити чи це наш власний lock
                if lock_info['locked_by'] == socket.gethostname() and \
                   lock_info['process_id'] == os.getpid():
                    # Це ми самі - продовжуємо
                    pass
                else:
                    # Сесія заблокована іншим ПК
                    raise SessionLockedError(
                        f"Session is locked by another PC",
                        lock_info=lock_info
                    )

        # Створити або відновити сесію
        self.output_dir = Path(restore_dir) if restore_dir else \
                         self.profile_manager.get_session_dir(self.client_id)

        # Захопити блокування
        success, error_msg = self.lock_manager.acquire_lock(
            self.client_id,
            self.output_dir
        )

        if not success:
            raise SessionLockedError(error_msg)

        # Запустити heartbeat таймер
        self._start_heartbeat()

        # ... решта коду

    def end_session(self):
        """Модифікований для звільнення блокування"""
        self._stop_heartbeat()
        self.lock_manager.release_lock(self.output_dir)
        # ... решта коду

    def _start_heartbeat(self):
        """Запустити періодичне оновлення heartbeat"""
        # Оновлювати кожні 30 секунд

    def _stop_heartbeat(self):
        """Зупинити heartbeat при закритті сесії"""
```

### 4. Нові виключення

**Файл:** `src/exceptions.py` (новий або доповнити існуючий)

```python
class SessionLockedError(Exception):
    """Виключення коли сесія заблокована іншим процесом"""
    def __init__(self, message: str, lock_info: Optional[Dict] = None):
        super().__init__(message)
        self.lock_info = lock_info
```

---

## UI/UX зміни

### 1. Відображення активних сесій у списку відновлення

**Файл:** `src/main.py` - метод `load_previous_sessions()`

**Поточна поведінка:**
```
Незавершені сесії:
  📦 Session_2025-10-28_143045
  📦 Session_2025-10-27_091523
```

**Нова поведінка:**
```
Незавершені сесії:
  🔒 Session_2025-10-28_143045  [АКТИВНА на DESKTOP-PC2 - Марія Іванова]
  📦 Session_2025-10-27_091523
```

**Реалізація:**
```python
def load_previous_sessions(self):
    """Завантажити список незавершених сесій з індикацією блокувань"""
    sessions = self.profile_manager.get_incomplete_sessions(self.current_client_id)

    for session_dir in sessions:
        # Перевірити статус блокування
        is_locked, lock_info = self.lock_manager.is_locked(session_dir)

        if is_locked:
            # Перевірити чи це застарілий lock
            if self.lock_manager.is_lock_stale(lock_info):
                icon = "⚠️"  # Застарілий lock (можливо crash)
                status = " [ЗАСТАРІЛИЙ LOCK - можливо crash]"
                self.session_combo.addItem(
                    f"{icon} {session_dir.name}{status}",
                    userData={"path": session_dir, "locked": True, "stale": True}
                )
            else:
                icon = "🔒"
                pc_name = lock_info.get('locked_by', 'Unknown')
                user_name = lock_info.get('user_name', 'Unknown')
                status = f" [АКТИВНА на {pc_name} - {user_name}]"
                self.session_combo.addItem(
                    f"{icon} {session_dir.name}{status}",
                    userData={"path": session_dir, "locked": True, "stale": False}
                )
        else:
            icon = "📦"
            self.session_combo.addItem(
                f"{icon} {session_dir.name}",
                userData={"path": session_dir, "locked": False}
            )
```

### 2. Діалог при спробі відкрити заблоковану сесію

**Три сценарії:**

#### Сценарій A: Сесія активна на іншому ПК (нормальний lock)

```
┌─────────────────────────────────────────────────────┐
│  ⚠️  Сесія вже використовується                     │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Ця сесія зараз активна на іншому комп'ютері:       │
│                                                      │
│  👤 Користувач: Марія Іванова                        │
│  💻 Комп'ютер: DESKTOP-PC2                          │
│  🕐 Початок роботи: 28.10.2025 14:30               │
│  ✅ Статус: Активна (heartbeat 30 сек тому)         │
│                                                      │
│  Ви не можете відновити цю сесію, поки вона         │
│  використовується іншим користувачем.                │
│                                                      │
│  Зачекайте, поки користувач завершить роботу,       │
│  або оберіть іншу сесію / створіть нову.            │
│                                                      │
│                           [ OK ]                     │
└─────────────────────────────────────────────────────┘
```

**Дія:** Заборонити відновлення, показати тільки кнопку OK.

#### Сценарій B: Застарілий lock (можливо crash)

```
┌─────────────────────────────────────────────────────┐
│  ⚠️  Застарілий lock                                │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Ця сесія була заблокована, але heartbeat не        │
│  оновлювався більше 5 хвилин.                       │
│                                                      │
│  👤 Користувач: Іван Петренко                       │
│  💻 Комп'ютер: DESKTOP-PC1                         │
│  🕐 Останній heartbeat: 28.10.2025 14:15           │
│  ❌ Статус: Немає зв'язку (можливо crash)          │
│                                                      │
│  Можливо програма аварійно закрилася на тому ПК.    │
│                                                      │
│  Що ви хочете зробити?                              │
│                                                      │
│         [ Звільнити lock і відкрити ]               │
│                  [ Скасувати ]                       │
└─────────────────────────────────────────────────────┘
```

**Дія:** Дозволити force release lock та відкрити сесію.

#### Сценарій C: Сесія не заблокована (нормальне відновлення)

**Нічого не показуємо** - просто відновлюємо як зараз.

### 3. Індикатор поточної активної сесії у головному вікні

**Розташування:** У верхній частині головного вікна під вибором клієнта

```
┌────────────────────────────────────────────┐
│  Клієнт: [M - Manufacturer    ▼] [+ Новий] │
│  📍 Активна сесія: Session_2025-10-28_143045│
│  🔒 Заблоковано на: DESKTOP-PC1 (ви)        │
└────────────────────────────────────────────┘
```

---

## Логіка роботи (детальні сценарії)

### Сценарій 1: Нормальний старт нової сесії

**Кроки:**
1. Користувач обирає клієнта M
2. Натискає "Start Session"
3. Обирає packing list файл
4. `SessionManager.start_session()` викликається
5. `lock_manager.acquire_lock()` створює `.session.lock`
6. Сесія стартує, heartbeat таймер запускається кожні 30 сек
7. Користувач працює...
8. Натискає "End Session"
9. `lock_manager.release_lock()` видаляє `.session.lock`
10. Сесія завершується

### Сценарій 2: Відновлення незаблокованої сесії

**Кроки:**
1. Користувач обирає клієнта M
2. Бачить список незавершених сесій:
   - `📦 Session_2025-10-27_091523`
3. Обирає цю сесію
4. Натискає "Restore Session"
5. `lock_manager.is_locked()` повертає `(False, None)`
6. `lock_manager.acquire_lock()` створює `.session.lock`
7. Сесія відновлюється, heartbeat запускається
8. Користувач працює...

### Сценарій 3: Спроба відкрити активну сесію (заблоковано)

**ПК1 (Марія):** Працює з Session_2025-10-28_143045

**ПК2 (Іван):**
1. Відкриває додаток, обирає клієнта M
2. Бачить:
   - `🔒 Session_2025-10-28_143045 [АКТИВНА на DESKTOP-PC1 - Марія Іванова]`
   - `📦 Session_2025-10-27_091523`
3. Намагається обрати заблоковану сесію
4. Натискає "Restore Session"
5. `lock_manager.is_locked()` повертає `(True, {...})`
6. **Діалог "Сесія вже використовується"** показується
7. Іван натискає OK
8. Сесія НЕ відкривається
9. Іван обирає іншу сесію або створює нову

### Сценарій 4: Crash recovery (застарілий lock)

**ПК1 (Марія):** Програма аварійно закрилася о 14:15, lock залишився

**ПК2 (Іван), о 14:25:**
1. Відкриває додаток, обирає клієнта M
2. Бачить:
   - `⚠️ Session_2025-10-28_143045 [ЗАСТАРІЛИЙ LOCK - можливо crash]`
3. Обирає цю сесію
4. Натискає "Restore Session"
5. `lock_manager.is_locked()` повертає `(True, {...})`
6. `lock_manager.is_lock_stale()` повертає `True` (heartbeat > 5 хв тому)
7. **Діалог "Застарілий lock"** показується з опцією "Звільнити lock"
8. Іван натискає "Звільнити lock і відкрити"
9. `lock_manager.force_release_lock()` видаляє старий lock
10. `lock_manager.acquire_lock()` створює новий lock
11. Сесія відновлюється

### Сценарій 5: Graceful shutdown (правильне закриття)

**Кроки:**
1. Користувач працює з активною сесією
2. Натискає кнопку закриття вікна (X)
3. `closeEvent()` обробник викликається
4. `session_manager.end_session()` викликається
5. Heartbeat таймер зупиняється
6. `lock_manager.release_lock()` видаляє `.session.lock`
7. Сесія коректно завершується
8. Додаток закривається

### Сценарій 6: Ungraceful shutdown (аварійне закриття)

**ПК1 (о 14:30):**
1. Користувач працює з активною сесією
2. Windows crash / Python crash / Kill process / Вимкнення світла
3. `.session.lock` залишається на диску з `heartbeat: "2025-10-28T14:30:00"`

**ПК1 (о 14:40 - після перезавантаження):**
1. Користувач відкриває додаток знову
2. Обирає клієнта M
3. Бачить:
   - `⚠️ Session_2025-10-28_143045 [ЗАСТАРІЛИЙ LOCK - можливо crash]`
4. Розуміє що це його власна сесія після crash
5. Відновлює через діалог "Звільнити lock"

---

## Heartbeat механізм

### Що таке heartbeat?

**Heartbeat** - це періодичне оновлення часу в `.session.lock` файлі, яке доводить що програма ще працює.

### Реалізація

```python
class SessionManager:
    def _start_heartbeat(self):
        """Запустити heartbeat кожні 30 секунд"""
        from PySide6.QtCore import QTimer

        self.heartbeat_timer = QTimer()
        self.heartbeat_timer.timeout.connect(self._update_heartbeat)
        self.heartbeat_timer.start(30000)  # 30 секунд

    def _update_heartbeat(self):
        """Оновити heartbeat у lock файлі"""
        try:
            self.lock_manager.update_heartbeat(self.output_dir)
        except Exception as e:
            self.logger.error(f"Failed to update heartbeat: {e}")
            # Не падати, просто залогувати

    def _stop_heartbeat(self):
        """Зупинити heartbeat при закритті"""
        if self.heartbeat_timer:
            self.heartbeat_timer.stop()
            self.heartbeat_timer = None
```

### Чому 30 секунд?

- Досить часто щоб швидко виявити crash (< 5 хвилин)
- Досить рідко щоб не навантажувати мережу (30 сек = 120 запитів/годину)
- Stale timeout = 5 хвилин = 10 пропущених heartbeats

### Що якщо мережа тимчасово недоступна?

```python
def update_heartbeat(self, session_dir: Path) -> bool:
    """Оновити heartbeat, не падати при помилках мережі"""
    try:
        lock_path = session_dir / ".session.lock"

        # Спробувати оновити
        with open(lock_path, 'r+', encoding='utf-8') as f:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                data = json.load(f)
                data['heartbeat'] = datetime.now().isoformat()
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2)
            finally:
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        return True

    except (IOError, OSError) as e:
        # Мережа недоступна - НЕ падати
        self.logger.warning(f"Failed to update heartbeat (network issue?): {e}")
        return False  # Просто пропустити цей heartbeat
```

**Результат:** Якщо мережа недоступна 2-3 хвилини, heartbeat просто не оновлюється, але програма продовжує працювати. Lock стане "stale" після 5 хвилин без heartbeat.

---

## Файлова структура (доповнення)

```
\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\2Packing-tool\
├── clients\
│   └── M\
│       ├── client_info.json
│       ├── sku_mappings.json
│       └── sessions\
│           ├── Session_2025-10-28_143045\
│           │   ├── .session.lock          # ← НОВИЙ файл
│           │   ├── session_state.json
│           │   ├── packing_list.xlsx
│           │   ├── output.xlsx
│           │   └── barcodes\
│           │       └── ...
│           └── Session_2025-10-27_091523\
│               ├── .session.lock          # ← якщо активна
│               └── ...
└── logs\
    └── packing_tool_2025-10-28.log
```

**Примітка:** `.session.lock` існує ТІЛЬКИ коли сесія активна. При end_session файл видаляється.

---

## Логування

### События для логування

```python
# Успішне захоплення lock
logger.info(f"Session lock acquired", extra={
    "client_id": "M",
    "session_dir": "Session_2025-10-28_143045",
    "locked_by": "DESKTOP-PC1",
    "user_name": "Іван Петренко"
})

# Звільнення lock
logger.info(f"Session lock released", extra={
    "client_id": "M",
    "session_dir": "Session_2025-10-28_143045"
})

# Спроба відкрити заблоковану сесію
logger.warning(f"Attempt to open locked session", extra={
    "client_id": "M",
    "session_dir": "Session_2025-10-28_143045",
    "locked_by": "DESKTOP-PC2",
    "attempted_by": "DESKTOP-PC1"
})

# Force release застарілого lock
logger.warning(f"Stale lock force-released", extra={
    "session_dir": "Session_2025-10-28_143045",
    "original_lock_by": "DESKTOP-PC2",
    "released_by": "DESKTOP-PC1",
    "stale_for_minutes": 12
})

# Heartbeat update
logger.debug(f"Heartbeat updated", extra={
    "session_dir": "Session_2025-10-28_143045"
})

# Heartbeat failure (мережа)
logger.warning(f"Heartbeat update failed", extra={
    "session_dir": "Session_2025-10-28_143045",
    "error": str(e)
})
```

---

## Тестування

### Тест-кейси для перевірки

#### 1. Базове блокування
- [ ] Старт нової сесії створює `.session.lock`
- [ ] End session видаляє `.session.lock`
- [ ] Закриття вікна (X) видаляє `.session.lock`

#### 2. Concurrent доступ
- [ ] ПК1: відкрити сесію для клієнта M
- [ ] ПК2: спробувати відкрити ту саму сесію
- [ ] ПК2: має побачити 🔒 іконку
- [ ] ПК2: при спробі відкрити - діалог "вже використовується"
- [ ] ПК2: не може відкрити сесію
- [ ] ПК1: завершити сесію
- [ ] ПК2: оновити список (або авто-оновлення)
- [ ] ПК2: тепер може відкрити сесію

#### 3. Heartbeat
- [ ] Heartbeat оновлюється кожні 30 сек
- [ ] Lock файл має актуальний timestamp в `heartbeat`
- [ ] Після 5+ хвилин без heartbeat lock стає "stale"

#### 4. Crash recovery
- [ ] ПК1: відкрити сесію
- [ ] ПК1: Force kill процесу Python (Task Manager)
- [ ] ПК1: `.session.lock` залишається на диску
- [ ] ПК2: через 5+ хвилин побачить ⚠️ іконку "ЗАСТАРІЛИЙ LOCK"
- [ ] ПК2: може force release lock
- [ ] ПК2: може відкрити сесію

#### 5. Мережеві збої
- [ ] Сесія активна, відключити мережу на 2 хвилини
- [ ] Heartbeat НЕ оновлюється, але програма працює
- [ ] Підключити мережу знову
- [ ] Heartbeat відновлюється
- [ ] Lock не став "stale" (< 5 хвилин без мережі)

#### 6. Одночасний старт
- [ ] ПК1 і ПК2: одночасно обрати клієнта M
- [ ] ПК1 і ПК2: одночасно натиснути "Start Session"
- [ ] Тільки один ПК має успішно створити lock
- [ ] Другий ПК має отримати помилку блокування

#### 7. UI тестування
- [ ] 🔒 іконка показується для активних сесій
- [ ] ⚠️ іконка показується для застарілих locks
- [ ] 📦 іконка показується для вільних сесій
- [ ] Ім'я користувача та ПК показується коректно
- [ ] Індикатор активної сесії у головному вікні

---

## Міграція з Phase 1.1

### Чи потрібна міграція даних?

**НІ** - Phase 1.2 повністю зворотньо сумісна з Phase 1.1.

**Причини:**
- `.session.lock` файл - це НОВИЙ файл, старі сесії його не мають
- Якщо `.session.lock` відсутній = сесія не заблокована
- Всі існуючі сесії будуть показані як 📦 (вільні)
- Користувачі можуть продовжити роботу без змін

### Що станеться при оновленні?

1. Зупинити всі програми на всіх ПК
2. Оновити .exe файл на всіх ПК (нова версія з Phase 1.2)
3. Запустити програму знову
4. Всі старі незавершені сесії будуть доступні для відновлення
5. Нові сесії автоматично використовуватимуть блокування

**Рекомендація:** Попередити користувачів завершити активні сесії перед оновленням.

---

## Обмеження та компроміси

### 1. Залежність від мережі для heartbeat

**Проблема:** Якщо мережа нестабільна, heartbeat може не оновлюватись.

**Рішення:**
- Stale timeout = 5 хвилин (достатньо для короткочасних збоїв)
- Програма НЕ падає при невдалому heartbeat
- Логування для діагностики

### 2. Можливість force release чужих locks

**Проблема:** ПК2 може force release lock від ПК1, навіть якщо ПК1 ще працює (якщо heartbeat застарів).

**Рішення:**
- Діалог попереджає користувача
- Логування force release для аудиту
- Stale timeout досить великий (5 хвилин) щоб уникнути false positives

### 3. Race condition при одночасному старті

**Проблема:** ПК1 і ПК2 одночасно намагаються створити lock.

**Рішення:**
- Файлове блокування Windows (`msvcrt.locking()`) гарантує атомарність
- Один ПК успішно створить lock, другий отримає помилку
- Retry logic з exponential backoff

---

## Версіонування

**Версія:** 1.2.0

**Changelog:**
```
v1.2.0 (2025-10-28)
- Added session locking mechanism to prevent concurrent access
- Added heartbeat system to detect crashed sessions
- Added UI indicators for locked/active sessions
- Added dialogs for handling lock conflicts
- Added crash recovery with force lock release option
- Improved session restoration logic
```

---

## Питання для уточнення

Перед початком реалізації, підтвердіть:

1. **Stale timeout = 5 хвилин** - це достатньо? Або зробити більше/менше?
2. **Heartbeat інтервал = 30 секунд** - це OK?
3. **Force release** - чи дозволяти користувачам вручну звільняти чужі locks, чи тільки stale locks?
4. **Auto-refresh списку сесій** - чи потрібно автоматично оновлювати список кожні 30 сек, щоб бачити коли інший користувач звільнив сесію?

Якщо все OK - почнемо реалізацію! 🚀
