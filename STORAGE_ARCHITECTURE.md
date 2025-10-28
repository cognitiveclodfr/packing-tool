# Storage Architecture - Phase 1.3

## ⚠️ ВАЖЛИВО: Централізоване сховище

Усі дані додатку зберігаються на **файловому сервері**, а НЕ локально на кожному ПК. Це забезпечує синхронізацію даних між усіма комп'ютерами в мережі.

## 📍 Розташування даних на файловому сервері

### Базовий шлях
```
\\SERVER\SHARE\2Packing-tool/
```

Налаштовується в `config.ini`:
```ini
[Network]
FileServerPath = \\192.168.88.101\Z_GreenDelivery\WAREHOUSE\2Packing-tool
```

### Структура каталогів

```
\\SERVER\SHARE\2Packing-tool/
│
├── CLIENTS/                          # Профілі клієнтів
│   └── CLIENT_{ID}/
│       ├── config.json              # Конфігурація клієнта
│       ├── sku_mapping.json         # SKU мапінги з file locking
│       └── backups/                 # Бекапи конфігурацій
│
├── SESSIONS/                         # Історія сесій
│   └── CLIENT_{ID}/
│       └── {TIMESTAMP}/             # Індивідуальна сесія
│           ├── .session.lock        # Файл блокування
│           ├── session_info.json    # Інформація про сесію
│           ├── packing_state.json   # Прогрес пакування
│           └── barcodes/            # Згенеровані баркоди
│
└── STATS/                            # ⭐ НОВЕ в Phase 1.3
    └── stats.json                   # Глобальна статистика та аналітика
```

## 🔄 Синхронізація між ПК

### Автоматична синхронізація:

1. **Статистика** (`STATS/stats.json`):
   - ✅ Зберігається на файловому сервері
   - ✅ Доступна з усіх ПК
   - ✅ Використовує file locking для безпечного запису
   - ✅ Оновлюється після завершення кожної сесії

2. **Історія сесій** (`SESSIONS/`):
   - ✅ Всі сесії зберігаються на сервері
   - ✅ Кожен ПК бачить сесії інших ПК
   - ✅ SessionHistoryManager читає з мережі

3. **Профілі клієнтів** (`CLIENTS/`):
   - ✅ Централізовані конфігурації
   - ✅ SKU мапінги доступні всім
   - ✅ File locking для concurrent access

## 🔒 File Locking (Блокування файлів)

Для запобігання конфліктів при одночасному доступі з кількох ПК:

### Використовуються механізми:

1. **Session Locks** (`.session.lock`):
   - Гарантує, що тільки один ПК працює над сесією
   - Heartbeat кожні 60 секунд
   - Автоматичне визначення stale locks

2. **SKU Mapping Locks**:
   - Windows `msvcrt.locking()` для безпечного запису
   - Блокування на час читання/запису

3. **Statistics Locks** (НОВЕ в Phase 1.3):
   - Windows `msvcrt.locking()` для stats.json
   - Exclusive lock при записі
   - Shared lock при читанні

## 📊 Що зберігається де?

### На файловому сервері (ЦЕНТРАЛІЗОВАНО):
✅ Профілі клієнтів (`CLIENTS/`)
✅ Історія всіх сесій (`SESSIONS/`)
✅ Глобальна статистика (`STATS/stats.json`)
✅ SKU мапінги
✅ Баркоди
✅ Звіти про завершені сесії

### Локально на ПК (тільки кеш і логи):
📁 `~/.packers_assistant/cache/` - тимчасовий кеш (60 секунд)
📁 `~/.packers_assistant/logs/` - логи додатку
📁 `~/.packers_assistant/sounds/` - звукові ефекти (опціонально)

⚠️ **ВАЖЛИВО:** Після Phase 1.3 stats.json більше НЕ зберігається локально!

## 🎯 Переваги централізованого сховища

1. **Єдине джерело правди**: Всі ПК бачать однакові дані
2. **Реальна аналітика**: Статистика по всіх ПК разом
3. **Командна робота**: Можна бачити активні сесії колег
4. **Історія**: Повна історія всіх сесій з усіх ПК
5. **Бекапи**: Централізовані дані легше бекапити

## 🔧 Технічні деталі

### ProfileManager

Методи для доступу до шляхів:

```python
# Отримати корінь сесій
sessions_root = profile_manager.get_sessions_root()
# Повертає: Path('\\\\SERVER\\...\\SESSIONS')

# Отримати корінь клієнтів
clients_root = profile_manager.get_clients_root()
# Повертає: Path('\\\\SERVER\\...\\CLIENTS')

# Отримати шлях до глобальної статистики
stats_path = profile_manager.get_global_stats_path()
# Повертає: Path('\\\\SERVER\\...\\STATS\\stats.json')
```

### StatisticsManager

Ініціалізація з ProfileManager:

```python
# ПРАВИЛЬНО - централізоване сховище
stats_manager = StatisticsManager(profile_manager=profile_manager)

# НЕПРАВИЛЬНО - локальне сховище (deprecated)
stats_manager = StatisticsManager()  # Показує warning!
```

### SessionHistoryManager

Автоматично використовує файловий сервер:

```python
history_manager = SessionHistoryManager(profile_manager)
sessions = history_manager.get_client_sessions("M")
# Читає з: \\\\SERVER\\...\\SESSIONS\\CLIENT_M\\
```

## 📝 Міграція

Якщо у вас вже є локальна статистика в `~/.packers_assistant/stats.json`:

1. Додаток автоматично створить нову централізовану базу
2. Стара локальна статистика НЕ переноситься автоматично
3. Для переносу вручну: скопіюйте stats.json на сервер у `STATS/`

## 🚨 Вимоги

1. **Мережевий доступ**: Всі ПК повинні мати доступ до файлового сервера
2. **Права запису**: Користувачі повинні мати права запису в каталоги
3. **Windows**: File locking працює тільки на Windows
4. **Час синхронізації**: ПК повинні мати синхронізований час

## 🐛 Усунення неполадок

### "Statistics using LOCAL storage" warning:
- Причина: ProfileManager не переданий до StatisticsManager
- Рішення: Перевірте ініціалізацію в main.py

### Статистика не синхронізується між ПК:
- Перевірте доступ до `\\\\SERVER\\...\\STATS\\stats.json`
- Перевірте права запису
- Перегляньте логи: `~/.packers_assistant/logs/`

### Session lock conflicts:
- Heartbeat повинен оновлюватися кожні 60 секунд
- Stale locks видаляються через 120 секунд
- Можна force-release через Session Monitor

---

**Дата оновлення:** Phase 1.3 (2025-10-28)
**Версія:** 1.3.0
