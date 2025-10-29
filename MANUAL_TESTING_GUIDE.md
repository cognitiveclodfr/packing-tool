# Посібник з ручного тестування

## 🎯 Виправлені проблеми в Phase 1.3

### Проблема №1: Кнопка повернення з Packer Mode не працювала
**Статус:** ✅ ВИПРАВЛЕНО

### Проблема №2: Стан Restore Session Dialog
**Статус:** ✅ Функціонал працює коректно (потрібна перевірка)

---

## 📋 Критичні тест-кейси

### TEST 1: Навігація в Packer Mode

**Мета:** Перевірити, що кнопка "Back to Menu" повертає до головного меню

**Передумови:**
- Додаток запущений
- Вибраний клієнт
- Сесія запущена
- Excel файл завантажений

**Кроки:**
1. Натисніть "Switch to Packer Mode"
2. Перевірте, що ви в режимі пакування (видно таблицю SKU)
3. Натисніть кнопку "<< Back to Menu" (праворуч вгорі)

**Очікуваний результат:**
- ✅ Додаток повертається до головного меню
- ✅ Відкрита вкладка "Session" (таб 0)
- ✅ Видно список замовлень
- ✅ Поточне замовлення очищене

**Як перевірити, що ВСЕ працює:**
```
Після натискання "Back to Menu":
→ Ви бачите вкладки: Session | Dashboard | History
→ Активна вкладка "Session"
→ Видно таблицю з замовленнями
→ Статус показує інформацію про сесію
```

---

### TEST 2: Перемикання між вкладками

**Мета:** Перевірити навігацію між Session, Dashboard, History

**Кроки:**
1. У головному меню натисніть вкладку "Dashboard"
2. Перевірте, що відображається Dashboard з метриками
3. Натисніть вкладку "History"
4. Перевірте, що відображається список історичних сесій
5. Натисніть вкладку "Session"
6. Перевірте, що повернулися до списку замовлень

**Очікуваний результат:**
- ✅ Всі вкладки перемикаються
- ✅ Дані відображаються коректно
- ✅ Немає помилок

---

### TEST 3: Restore Session - Available Session (без блокування)

**Мета:** Перевірити відновлення доступної сесії

**Передумови:**
- Є незавершена сесія (припинена некоректно)
- Сесія НЕ заблокована іншим ПК

**Кроки:**
1. Вибрати клієнта
2. Натиснути "Restore Session"
3. Перевірити список сесій

**Очікуваний результат:**
- ✅ Відображається діалог з незавершеними сесіями
- ✅ Сесія має іконку 📦
- ✅ Статус: "Available"
- ✅ Сесію можна вибрати та відновити

**Приклад:**
```
📦  20251028_143000  -  Available
```

---

### TEST 4: Restore Session - Active Lock (активна сесія на іншому ПК)

**Мета:** Перевірити відображення заблокованої сесії

**Передумови:**
- Є незавершена сесія
- Сесія АКТИВНО використовується на іншому ПК
- Heartbeat свіжий (< 2 хвилин)

**Кроки:**
1. На ПК #1: Запустити сесію (не завершувати)
2. На ПК #2: Вибрати того ж клієнта
3. На ПК #2: Натиснути "Restore Session"
4. Перевірити список

**Очікуваний результат:**
- ✅ Сесія відображається з іконкою 🔒
- ✅ Статус: "Active - [User] on [PC]"
- ✅ Сесія СІРА (неактивна, не можна вибрати)
- ✅ Кнопка "Restore Selected" неактивна

**Приклад:**
```
🔒  20251028_143000  -  Active - Іван on WAREHOUSE-PC1   [сіра]
```

---

### TEST 5: Restore Session - Stale Lock (зависла сесія після краша)

**Мета:** Перевірити відновлення сесії після краша

**Передумови:**
- Є незавершена сесія
- ПК був вимкнений або додаток крашнувся
- Heartbeat старий (> 2 хвилин)

**Спосіб створити тест:**
```bash
# На ПК #1:
1. Запустити сесію
2. Вбити процес (Ctrl+C або Task Manager)
3. НЕ запускати додаток знову

# Зачекати 3-5 хвилин

# На ПК #2 (або на тому ж ПК):
1. Запустити додаток
2. Вибрати того ж клієнта
3. Натиснути "Restore Session"
```

**Очікуваний результат:**
- ✅ Сесія відображається з іконкою ⚠️
- ✅ Статус: "Stale lock - [User] on [PC]"
- ✅ Сесію МОЖНА вибрати
- ✅ Кнопка "Restore Selected" активна
- ✅ При відновленні - пропонує force release lock

**Приклад:**
```
⚠️  20251028_143000  -  Stale lock - Іван on WAREHOUSE-PC1
```

---

### TEST 6: Множинні сесії з різними станами

**Мета:** Перевірити коректне відображення різних типів сесій

**Передумови:**
- Створити 3 сесії:
  - Сесія A: Доступна (без lock)
  - Сесія B: Активна на іншому ПК
  - Сесія C: Stale lock

**Очікуваний результат:**
```
📦  20251028_100000  -  Available                           [можна вибрати]
🔒  20251028_110000  -  Active - User1 on PC1              [сіра, неактивна]
⚠️  20251028_120000  -  Stale lock - User2 on PC2         [можна вибрати]
```

---

### TEST 7: Refresh в Restore Dialog

**Мета:** Перевірити оновлення списку

**Кроки:**
1. Відкрити "Restore Session"
2. На іншому ПК завершити активну сесію
3. Натиснути "Refresh" в діалозі

**Очікуваний результат:**
- ✅ Список оновлюється
- ✅ Завершена сесія зникає зі списку
- ✅ Нові сесії з'являються

---

### TEST 8: Dashboard - Централізовані метрики

**Мета:** Перевірити, що статистика синхронізується між ПК

**Кроки:**
```
На ПК #1:
1. Завершити сесію з 10 замовленнями
2. Перевірити Dashboard - має показати +10 orders

На ПК #2:
1. Відкрити додаток
2. Перейти на вкладку Dashboard
3. Перевірити метрики
```

**Очікуваний результат:**
- ✅ ПК #2 бачить ті ж метрики, що і ПК #1
- ✅ Total Orders включає сесії з обох ПК
- ✅ Файл зберігається: `\\SERVER\...\STATS\stats.json`

---

### TEST 9: History - Пошук та фільтрація

**Мета:** Перевірити функціонал історії

**Кроки:**
1. Перейти на вкладку "History"
2. Вибрати клієнта з фільтра
3. Ввести текст у пошук
4. Встановити діапазон дат
5. Натиснути "Refresh"

**Очікуваний результат:**
- ✅ Відображаються всі сесії для вибраного клієнта
- ✅ Пошук фільтрує по session ID, PC name, file path
- ✅ Діапазон дат працює коректно
- ✅ Можна експортувати в Excel/CSV

---

### TEST 10: SKU Mapping - Додавання та синхронізація між ПК

**Мета:** Перевірити централізовану синхронізацію SKU мапінгів

**Передумови:**
- Два ПК з доступом до файлового сервера
- Вибраний той самий клієнт на обох ПК

**Кроки:**
```
На ПК #1:
1. Tools → SKU Mapping (або F2)
2. Натиснути "Add Mapping"
3. Ввести Product Barcode: 7290123456789
4. Ввести Internal SKU: TEST-SKU-001
5. Натиснути "Save & Close"
6. Перевірити повідомлення: "Successfully saved ... to file server"

На ПК #2:
7. Tools → SKU Mapping
8. Перевірити, що мапінг відображається
```

**Очікуваний результат:**
- ✅ На ПК #1: Показується статус "Changes are now synchronized across all PCs"
- ✅ На ПК #2: Новий мапінг автоматично видимий
- ✅ Файл зберігається: `\\SERVER\...\CLIENTS\CLIENT_X\sku_mapping.json`
- ✅ Обидва ПК бачать однакові дані

**Приклад таблиці:**
```
Product Barcode   | Internal SKU
7290123456789    | TEST-SKU-001
```

---

### TEST 11: SKU Mapping - Reload from Server

**Мета:** Перевірити оновлення мапінгів з сервера

**Передумови:**
- Мапінги вже є на сервері
- Діалог SKU Mapping відкритий на ПК #1
- Інший користувач вносить зміни на ПК #2

**Кроки:**
```
На ПК #1:
1. Відкрити SKU Mapping
2. НЕ закривати діалог

На ПК #2:
3. Відкрити SKU Mapping
4. Додати новий мапінг або змінити існуючий
5. Save & Close

На ПК #1:
6. Натиснути кнопку "Reload from Server"
```

**Очікуваний результат:**
- ✅ Діалог показує попередження про незбережені зміни (якщо є)
- ✅ Після підтвердження - завантажує свіжі дані з сервера
- ✅ Статус змінюється: "X mapping(s) loaded from file server"
- ✅ Таблиця оновлюється з новими мапінгами

**Можливе попередження:**
```
This will discard any unsaved changes.

Are you sure you want to reload from the file server?
[Yes] [No]
```

---

### TEST 12: SKU Mapping - Використання в активній сесії

**Мета:** Перевірити автоматичне оновлення мапінгів в активній сесії

**Передумови:**
- Запущена активна сесія для Client M
- Excel файл завантажений

**Кроки:**
```
1. Запустити сесію для Client M
2. Перейти в Packer Mode
3. Не закриваючи сесію, повернутися до меню (Back to Menu)
4. Відкрити Tools → SKU Mapping
5. Додати новий мапінг: Barcode 7290111222333 → SKU NEW-SKU
6. Save & Close
7. Повернутися в Packer Mode (Switch to Packer Mode)
8. Відсканувати баркод 7290111222333
```

**Очікуваний результат:**
- ✅ Мапінг зберігається на файловий сервер
- ✅ Показується повідомлення: "SKU mapping updated and synchronized across all PCs"
- ✅ Мапінги автоматично перезавантажуються в активну сесію
- ✅ При скануванні баркоду - використовується новий SKU
- ✅ Логи показують: "SKU mapping reloaded into active session"

**У разі помилки:**
```
Mappings saved successfully but failed to reload into current session:

[error message]

Please restart the session to use new mappings.
[OK]
```

---

### TEST 13: SKU Mapping - Concurrent Editing з File Locking

**Мета:** Перевірити file locking при одночасному редагуванні

**Передумови:**
- Два ПК на одній мережі
- Той самий клієнт вибраний

**Спосіб тестування (складний):**
```
На ПК #1:
1. Відкрити SKU Mapping
2. Додати мапінг
3. ТРИМАТИ діалог відкритим (не Save)

На ПК #2:
4. Відкрити SKU Mapping
5. Спробувати Save & Close
```

**Очікуваний результат (ідеально):**
- ✅ File locking запобігає конфліктам
- ✅ ПК #2 може зберегти без проблем (читання не блокується)
- ✅ Якщо обидва ПК одночасно Save - один чекає на lock

**Реальність:**
- Windows `msvcrt.locking()` блокує тільки на час запису
- Конфлікти малоймовірні при нормальному використанні
- Якщо виникає конфлікт - один користувач побачить помилку

**У разі конфлікту:**
```
Failed to save mappings to file server.

Please check your network connection and try again.
```

---

### TEST 14: SKU Mapping - Міграція зі старої системи

**Мета:** Перевірити, що стара локальна система більше не використовується

**Передумови:**
- На ПК є старий файл: `~/.packers_assistant/sku_map.json`

**Кроки:**
```
1. Перевірити наявність старого файлу
2. Відкрити SKU Mapping в додатку
3. Додати новий мапінг
4. Save & Close
5. Перевірити файли
```

**Очікуваний результат:**
- ✅ Старий файл `~/.packers_assistant/sku_map.json` НЕ оновлюється
- ✅ Новий файл створюється: `\\SERVER\...\CLIENTS\CLIENT_X\sku_mapping.json`
- ✅ Додаток працює тільки з новою системою
- ✅ Логи показують: "Load SKU mappings from file server"

**Перевірка файлів:**
```bash
# Старий файл (не повинен змінюватися):
ls -la ~/.packers_assistant/sku_map.json

# Новий файл (має існувати та оновлюватися):
ls -la \\SERVER\...\CLIENTS\CLIENT_M\sku_mapping.json
```

---

## 🐛 Відомі обмеження

### Stale Lock Detection
- **Таймаут:** 120 секунд (2 хвилини)
- **Heartbeat:** Оновлюється кожні 60 секунд
- **Мінімальний час для stale:** 2-3 хвилини після краша

### File Locking
- **Працює тільки на Windows** (msvcrt.locking)
- **На Linux/Mac:** Немає блокування (можливі конфлікти)

### Синхронізація
- **Auto-refresh:** Dashboard оновлюється кожні 60 секунд
- **Manual refresh:** Потрібно натискати "Refresh" в History
- **Session Monitor:** Оновлюється кожні 30 секунд

---

## ✅ Контрольний список тестування

Перед релізом Phase 1.3 перевірте:

**Навігація та UI:**
- [ ] TEST 1: Навігація в Packer Mode (Back to Menu)
- [ ] TEST 2: Перемикання між вкладками

**Session Management:**
- [ ] TEST 3: Restore Session - Available
- [ ] TEST 4: Restore Session - Active Lock
- [ ] TEST 5: Restore Session - Stale Lock (КРИТИЧНО!)
- [ ] TEST 6: Множинні сесії
- [ ] TEST 7: Refresh в діалозі

**Analytics & History:**
- [ ] TEST 8: Dashboard синхронізація
- [ ] TEST 9: History пошук та експорт

**SKU Mapping (Phase 1.3 Redesign):**
- [ ] TEST 10: SKU Mapping - Додавання та синхронізація (КРИТИЧНО!)
- [ ] TEST 11: SKU Mapping - Reload from Server
- [ ] TEST 12: SKU Mapping - Використання в активній сесії
- [ ] TEST 13: SKU Mapping - Concurrent Editing (опціонально)
- [ ] TEST 14: SKU Mapping - Міграція зі старої системи

---

## 🔍 Як діагностувати проблеми

### Проблема: "Не бачу stale lock session"

**Діагностика:**
```bash
# Перевірте, чи існує session_info.json:
ls \\SERVER\...\SESSIONS\CLIENT_M\{timestamp}\session_info.json

# Перевірте lock файл:
cat \\SERVER\...\SESSIONS\CLIENT_M\{timestamp}\.session.lock

# Перевірте heartbeat (має бути старий):
# "heartbeat": "2025-10-28T14:00:00"  <- якщо зараз 14:05, то stale
```

**Рішення:**
- Зачекайте 3-5 хвилин після краша
- Натисніть "Refresh" в діалозі
- Перевірте логи: `~/.packers_assistant/logs/`

### Проблема: "Кнопка Back to Menu не працює"

**Діагностика:**
- Перевірте версію коду (має бути після fix)
- Перевірте логи на помилки
- Перевірте, чи є `self.tab_widget` в main.py

**Рішення:**
- Оновіть код з git branch
- Перезапустіть додаток

### Проблема: "Статистика не синхронізується"

**Діагностика:**
```bash
# Перевірте файл:
cat \\SERVER\...\STATS\stats.json

# Перевірте логи:
grep "StatisticsManager" ~/.packers_assistant/logs/*.log

# Має бути:
# "StatisticsManager using centralized storage"

# НЕ має бути:
# "StatisticsManager using LOCAL storage"
```

**Рішення:**
- Перевірте мережевий доступ
- Перевірте права запису
- Перевірте config.ini

### Проблема: "SKU Mapping не синхронізується між ПК"

**Діагностика:**
```bash
# Перевірте файл на сервері:
cat \\SERVER\...\CLIENTS\CLIENT_M\sku_mapping.json

# Перевірте логи:
grep "SKU" ~/.packers_assistant/logs/*.log

# Має бути:
# "Loaded X SKU mappings for client M"
# "Saved X SKU mappings to file server"

# Перевірте старий файл (не повинен використовуватися):
ls ~/.packers_assistant/sku_map.json
```

**Рішення:**
- Перевірте, що використовується нова версія коду (Phase 1.3)
- Перевірте доступ до `\\SERVER\...\CLIENTS\CLIENT_X\`
- Перевірте права запису для користувача
- Переконайтеся, що діалог використовує ProfileManager

### Проблема: "SKU Mapping не завантажується в активну сесію"

**Діагностика:**
```bash
# Перевірте логи:
grep "SKU mapping reloaded" ~/.packers_assistant/logs/*.log

# Має бути:
# "SKU mapping reloaded into active session"

# Або помилка:
# "Failed to reload SKU mapping into session"
```

**Рішення:**
- Перезапустіть сесію
- Перевірте, що `self.logic` існує в main.py
- Перевірте метод `set_sku_map()` в packer_logic.py

---

## 📝 Лог-файли для діагностики

```bash
# Основні логи:
~/.packers_assistant/logs/packing_tool_YYYYMMDD.log

# Що шукати:
- "SessionHistoryManager" - історія сесій
- "StatisticsManager" - статистика
- "SessionLockManager" - блокування
- "SKUMappingDialog" - SKU мапінги (Phase 1.3)
- "ProfileManager" - доступ до файлового сервера
- "ERROR" або "WARNING" - помилки
```

**Приклади корисних логів:**

```
# SKU Mapping успішно працює:
INFO - Loaded 5 SKU mappings for client M
INFO - Saved 6 SKU mappings to file server
INFO - SKU mapping reloaded into active session

# Statistics синхронізується:
INFO - StatisticsManager using centralized storage: \\SERVER\...\STATS\stats.json
INFO - Saved statistics: 25 sessions

# Session Management:
INFO - Session locked successfully
INFO - Heartbeat updated for session 20251028_143000
INFO - Stale lock detected (3.5 minutes old)

# Проблеми (що НЕ має бути):
WARNING - StatisticsManager using LOCAL storage (not recommended)
ERROR - Failed to reload SKU mapping into session
ERROR - Failed to save mappings to file server
```

---

**Дата створення:** 2025-10-29
**Версія:** Phase 1.3 (SKU Mapping redesign)
**Автор:** Claude Code
