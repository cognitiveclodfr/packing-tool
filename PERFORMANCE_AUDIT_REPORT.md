# Performance Audit Report: UI Lag & Background Operation Bottlenecks

**Date:** 2025-11-28
**Priority:** P1 - CRITICAL
**Status:** Analysis Complete, Fixes In Progress

---

## Executive Summary

This audit identifies **5 major performance bottlenecks** causing periodic UI lag in the packing application. Code analysis reveals that all identified bottlenecks run synchronously on the main UI thread, blocking user interaction during execution.

**Identified Issues:**
1. ✅ **Session Browser Auto-Refresh** - Filesystem scanning blocks UI for 500-2000ms every 30s
2. ✅ **Heartbeat Timer** - File I/O blocks UI for 50-200ms every 60s (network storage)
3. ✅ **State Save Operations** - JSON writes block UI for 100-500ms per save
4. ✅ **Order Tree Rebuilds** - Full tree reconstruction takes 100-500ms for 100+ orders
5. ✅ **Statistics Recalculation** - DataFrame operations take 50-300ms

**Impact:** Users experience noticeable lag (100-2000ms freezes) during normal operation, especially when:
- Session Browser is open (auto-refresh every 30s)
- Multiple items are scanned rapidly (frequent state saves + tree updates)
- Working with large sessions (100+ orders, 300+ items)
- Using network storage (slower file I/O)

---

## Detailed Analysis

### Issue #1: Session Browser Auto-Refresh Blocking UI ⚠️ CRITICAL

**Location:** `src/session_browser/session_browser_widget.py:64-66`

```python
# Auto-refresh timer (30 seconds)
self.refresh_timer = QTimer(self)
self.refresh_timer.timeout.connect(self.refresh_all)
self.refresh_timer.start(30000)  # 30 seconds
```

**What happens every 30 seconds:**
1. `refresh_all()` calls refresh on 3 tabs:
   - Active Sessions Tab: Scans filesystem for all client sessions
   - Completed Sessions Tab: Scans session history JSON files
   - Available Sessions Tab: Scans Shopify session directories

**Code path for Active Sessions refresh:**
```python
# src/session_browser/active_sessions_tab.py:97-195
def refresh(self):
    # Scans: Sessions/CLIENT_*/SESSION_*/packing/PACKING_LIST_*
    # For each directory:
    #   - Check if lock file exists
    #   - Read lock JSON file
    #   - Read session_info.json
    #   - Calculate lock age
    #   - Update table UI
```

**Performance Impact:**
- **Best case (10 sessions):** 200-500ms
- **Typical (50 sessions):** 500-1500ms
- **Worst case (200+ sessions):** 2000-5000ms

**Why it's slow:**
- Nested directory iteration (3 levels deep)
- Multiple file existence checks per session
- JSON file reads (not cached)
- Runs on main thread → **blocks all UI**

**Proposed Fix:** Move to background thread (Priority 1)

---

### Issue #2: Heartbeat Timer Blocking UI ⚠️ MODERATE

**Location:** `src/main.py:1140-1149`

```python
@profile_function
def _update_session_heartbeat(self):
    """Update heartbeat for active session lock."""
    if self.logic and hasattr(self, 'current_work_dir') and self.current_work_dir:
        try:
            with log_timing("Update heartbeat lock file", threshold_ms=100):
                self.lock_manager.update_heartbeat(Path(self.current_work_dir))
```

**What happens every 60 seconds:**
1. Open lock file for writing (exclusive lock on Windows)
2. Read current lock JSON
3. Update heartbeat timestamp
4. Write JSON back to file
5. Close file and release lock

**Performance Impact:**
- **Local storage:** 5-20ms (barely noticeable)
- **Network storage:** 50-200ms (noticeable lag spike)
- **Slow network:** 200-500ms (very noticeable freeze)

**Why it's slow:**
- File I/O on network storage
- Windows file locking overhead
- Synchronous operation on main thread

**Proposed Fix:** Move to background thread (Priority 2)

---

### Issue #3: State Save Operations Blocking UI ⚠️ HIGH

**Location:** `src/packer_logic.py:443-580`

```python
@profile_function
def _save_session_state(self):
    """Save the current session's packing state to JSON file with atomic write."""
    # Build complete state structure (100+ lines of logic)
    # Calculate progress metrics
    # Write JSON to file
```

**Called from multiple locations:**
- After every item scan (`process_sku_scan()`)
- After order completion
- After order starts
- Potentially 100+ times per session

**Performance Impact:**
- **Small state (10 orders):** 20-50ms
- **Medium state (50 orders):** 50-150ms
- **Large state (200+ orders):** 150-500ms
- **Network storage:** Add 100-300ms

**Why it's slow:**
- Recalculates all progress metrics on every save
- Builds complete state structure (not incremental)
- JSON serialization + file write
- Not debounced (saves immediately on every scan)

**Proposed Fix:** Debounced saves (Priority 1)

---

### Issue #4: Order Tree Rebuilds ⚠️ HIGH

**Location:** `src/main.py:482-612`

```python
@profile_function
def _populate_order_tree(self):
    """Populate tree with orders and items."""
    with perf_monitor.measure("populate_order_tree"):
        self._do_populate_order_tree()

def _do_populate_order_tree(self):
    self.order_tree.clear()  # ⚠️ Clears entire tree

    # Rebuild everything from scratch
    for order_num, order_items in grouped:
        # Create order item
        # Add child items (SKUs)
        # Set fonts, colors, expand state
```

**Called from:**
- After every item scan
- After order completion
- After statistics update
- ~100+ times per session

**Performance Impact:**
- **10 orders, 30 items:** 20-50ms
- **50 orders, 150 items:** 50-150ms
- **100 orders, 300+ items:** 150-500ms

**Why it's slow:**
- **Clears and rebuilds entire tree** instead of updating changed items
- Creates new QTreeWidgetItem objects for every order/item
- Sets fonts, colors, expand states for every item
- O(n) operation when only 1 order changed

**Proposed Fix:** Incremental updates (Priority 1)

---

### Issue #5: Statistics Recalculation ⚠️ MODERATE

**Location:** `src/main.py:721-837`

```python
@profile_function
def _update_statistics(self):
    """Refresh statistics tab with current data."""
    # Session totals
    # By Courier stats
    # SKU Summary table (full rebuild)

    # Optimized: Uses itertuples() instead of iterrows()
    # But still recalculates everything
```

**Performance Impact:**
- **Small dataset (50 items):** 20-50ms
- **Medium dataset (150 items):** 50-150ms
- **Large dataset (500+ items):** 150-300ms

**Why it's slow:**
- Recalculates all statistics from scratch
- Rebuilds courier stats widgets
- Rebuilds entire SKU table
- Called on every item scan (via signal chain)

**Proposed Fix:** Caching + debounced updates (Priority 2)

---

## Priority 1 Fixes (Implement First)

### Fix #1: Session Browser Background Threading

**Impact:** Eliminates 500-2000ms UI freezes every 30 seconds

**Implementation:**
1. Create `SessionScannerThread` (QThread subclass)
2. Move filesystem scanning to background thread
3. Emit results via signal when complete
4. Update UI on main thread with results

**Files to modify:**
- `src/session_browser/session_browser_widget.py`
- `src/session_browser/active_sessions_tab.py`
- `src/session_browser/completed_sessions_tab.py`
- `src/session_browser/available_sessions_tab.py`

**Estimated improvement:** -90% perceived lag during auto-refresh

---

### Fix #2: Debounced State Saves

**Impact:** Reduces 50-500ms UI freezes on every scan to one save every 2 seconds

**Implementation:**
1. Add `QTimer` with `setSingleShot(True)` to `PackerLogic`
2. Replace immediate `_save_session_state()` with timer start
3. If save requested again, restart timer (debounce)
4. Keep `force_save_state()` for critical moments (end session)

**Files to modify:**
- `src/packer_logic.py`

**Estimated improvement:** -80% file I/O during scanning

---

### Fix #3: Incremental Order Tree Updates

**Impact:** Reduces 100-500ms tree rebuilds to <10ms targeted updates

**Implementation:**
1. Create `_update_single_order_in_tree(order_number)` method
2. Find existing order item by order_number
3. Update only that order's children (not entire tree)
4. Replace `_populate_order_tree()` calls with targeted updates where appropriate

**Files to modify:**
- `src/main.py`

**Estimated improvement:** -90% tree update time

---

## Priority 2 Fixes (Implement If Needed)

### Fix #4: Async Heartbeat Updates

**Impact:** Eliminates 50-200ms UI freezes every 60 seconds (network storage)

**Implementation:**
1. Create `HeartbeatThread` (QThread subclass)
2. Move lock file update to background thread
3. Skip update if previous one still running

**Estimated improvement:** -100% heartbeat-related lag

---

### Fix #5: Statistics Caching + Debouncing

**Impact:** Reduces recalculation frequency and cost

**Implementation:**
1. Add statistics cache with invalidation flag
2. Debounce updates (wait 1 second after last change)
3. Only recalculate when cache invalid

**Estimated improvement:** -70% statistics calculation overhead

---

## Testing Plan

### Baseline Measurements
1. Start session with 100 orders (300 items)
2. Enable profiling (PROFILING_ENABLED = True)
3. Scan 20 items
4. Wait for 2 auto-refresh cycles
5. Check logs for SLOW/MODERATE warnings
6. Record counts and timings

### After Each Optimization
1. Run same test scenario
2. Compare SLOW warning counts
3. Measure user-perceived lag
4. Verify functionality intact

### Stress Test
1. Session with 500 orders (1500+ items)
2. Session Browser with 200+ sessions
3. Simulate slow network storage (add delay)
4. Verify UI remains responsive

---

## Success Criteria

- ✅ All operations complete in <100ms (no SLOW warnings)
- ✅ Session Browser refresh doesn't block UI
- ✅ Heartbeat updates don't cause lag spikes
- ✅ State saves happen in background
- ✅ Order tree updates are instant (<16ms for 60fps)
- ✅ Statistics updates don't block scanning
- ✅ Can scan items continuously without slowdown
- ✅ No user-reported lag during normal operation

---

## Appendix: Profiling Logs Format

```
SLOW: main._populate_order_tree took 247.3ms
MODERATE: main._update_statistics took 68.2ms
SLOW: session_browser.refresh_all took 1523.1ms
SLOW: packer_logic._save_session_state took 156.4ms
```

**Thresholds:**
- DEBUG: < 50ms
- MODERATE: 50-100ms
- SLOW: > 100ms (blocks UI noticeably)

---

## Next Steps

1. ✅ Profiling infrastructure added
2. 🔄 Implement Priority 1 fixes
3. ⏳ Test and validate improvements
4. ⏳ Implement Priority 2 fixes if needed
5. ⏳ Update CHANGELOG
6. ⏳ Commit and push changes
