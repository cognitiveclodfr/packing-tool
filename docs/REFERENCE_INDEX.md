# Documentation Reference Index

**Version:** 1.3.2.0 (Pre-release)
**Last Updated:** 2026-02-24

Quick navigation guide for all Packer's Assistant documentation.

---

## Quick Start

**New to Packer's Assistant?**

1. Read [README.md](../README.md) for an overview, workflow, and setup instructions.
2. Review [CHANGELOG.md](../CHANGELOG.md) for version history and recent changes.

**Developers:**

1. [ARCHITECTURE.md](ARCHITECTURE.md) — System design, layers, and component interactions
2. [API.md](API.md) — Complete API reference with signatures and examples
3. [FUNCTIONS.md](FUNCTIONS.md) — Quick lookup by module or function name

---

## Documentation Files

### [README.md](../README.md)

User-facing overview: what the application does, features, system requirements,
Shopify Tool integration, workflow, and development setup.

---

### [CHANGELOG.md](../CHANGELOG.md)

Version history with tagged releases. Versions covered:

- `1.3.2.0` — Async state writer, background session I/O
- `1.3.1.3` — Packer Mode overhaul (metadata, extras, 3-column layout)
- `1.3.1.2` — Scanner focus fix
- `1.3.1.1` — QSS theme bundling in PyInstaller exe
- `1.3.1.0` — 8 UI fixes (dark theme, hover, crashes)
- `1.3.0.0` — Major cleanup: Excel removed, Session Browser added
- `1.2.0` — Multiple packing lists per session, session history

---

### [ARCHITECTURE.md](ARCHITECTURE.md)

System design documentation covering:

- Four-layer architecture (Presentation, Business Logic, Data Access, Storage)
- Core component responsibilities and interactions
- Data flow diagrams (session start, barcode scan, session end)
- Storage structure on the file server
- Multi-PC coordination via file-based locking
- Session lifecycle state transitions
- Session Browser architecture (SessionCacheManager, RefreshWorker)
- Technology stack

---

### [API.md](API.md)

Complete API reference for all classes and methods, including:

- `PackerLogic` — order loading, scan processing, state management
- `SessionManager` — session lifecycle
- `ProfileManager` — client profiles and SKU mappings
- `SessionLockManager` — file-based locking with heartbeat
- `SessionHistoryManager` — historical session queries
- `AsyncStateWriter` — write-behind queue for state persistence
- `SessionCacheManager` / `RefreshWorker` — Session Browser caching and background scanning
- UI components and dialogs

---

### [FUNCTIONS.md](FUNCTIONS.md)

Function catalog organized by module. Use for quick lookup of:

- Method signatures and descriptions
- Public vs private method distinction
- New methods added in recent versions
- Alphabetical index across all modules

---

## Code Organization

```text
packing-tool/
├── src/                              # Source code
│   ├── main.py                       # Main window and orchestration
│   ├── packer_logic.py               # Core business logic
│   ├── packer_mode_widget.py         # Scanning UI
│   ├── session_manager.py            # Session lifecycle
│   ├── session_lock_manager.py       # File-based locking
│   ├── session_history_manager.py    # Historical queries
│   ├── async_state_writer.py         # Write-behind state saves
│   ├── profile_manager.py            # Client profiles
│   ├── json_cache.py                 # JSON file caching
│   ├── session_browser/              # Session Browser sub-package
│   │   ├── session_browser_widget.py
│   │   ├── active_sessions_tab.py
│   │   ├── completed_sessions_tab.py
│   │   ├── available_sessions_tab.py
│   │   ├── session_cache_manager.py
│   │   └── session_details_dialog.py
│   └── ...
├── shared/                           # Shared with Shopify Tool
│   ├── stats_manager.py              # Unified statistics
│   └── worker_manager.py             # Worker profiles
├── tests/                            # pytest suite
├── docs/                             # This documentation
└── README.md
```

---

## Common Tasks

**Understand the overall system:**
→ [ARCHITECTURE.md](ARCHITECTURE.md)

**Find a specific method:**
→ [FUNCTIONS.md](FUNCTIONS.md) for quick lookup, [API.md](API.md) for full signatures

**See what changed in a release:**
→ [CHANGELOG.md](../CHANGELOG.md)

**Understand packing state persistence:**
→ [ARCHITECTURE.md — State Persistence](ARCHITECTURE.md#state-management)
→ [README.md — State Persistence](../README.md#state-persistence)

**Understand session locking:**
→ [ARCHITECTURE.md — Multi-PC Coordination](ARCHITECTURE.md#multi-pc-coordination)

---

## Version Information

| Document | Version | Last Updated |
| -------- | ------- | ------------ |
| README.md | 1.3.2.0 (Pre-release) | 2026-02-24 |
| CHANGELOG.md | 1.3.2.0 (Pre-release) | 2026-02-24 |
| ARCHITECTURE.md | 1.3.2.0 (Pre-release) | 2026-02-24 |
| FUNCTIONS.md | 1.3.2.0 (Pre-release) | 2026-02-24 |
| API.md | 1.3.2.0 (Pre-release) | 2026-02-24 |
| REFERENCE_INDEX.md | 1.3.2.0 (Pre-release) | 2026-02-24 |

---

## Feedback

Found an issue with the documentation?
Report at [GitHub Issues](https://github.com/cognitiveclodfr/packing-tool/issues).
