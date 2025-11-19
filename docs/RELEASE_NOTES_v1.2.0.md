# Release Notes - Packing Tool v1.2.0

**Release Date:** November 19, 2025
**Release Type:** Major Update - Session Management & Print Optimization
**Status:** ✅ Stable - Production Ready

---

## 🎯 Overview

Version 1.2.0 addresses critical session detection issues and optimizes barcode printing for production environments. This release ensures Dashboard and History Browser work correctly with Shopify sessions while maintaining full backward compatibility.

---

## 🚀 What's New

### Major Features

#### 1. Fixed Session Management ✨

**Problem Solved:**
- Dashboard showing zero sessions
- History Browser not finding completed sessions
- Session files not being detected

**Solution:**
- Updated SessionHistoryManager to support Phase 1 directory structure
- Now correctly searches in `packing/*/` subdirectories
- Supports multiple packing lists per Shopify session

**Impact:**
- ✅ Dashboard now shows real-time statistics
- ✅ History Browser displays all completed sessions
- ✅ Session restore works for Shopify sessions

---

#### 2. Optimized Barcode Printing 🖨️

**Problem Solved:**
- Barcodes printing too small (~1/5 of label)
- Manual print from folder resulted in oversized barcodes

**Solution:**
- Optimized for Citizen CL-E300 printer (203 DPI)
- Correct image size: 543x303px = 68x38mm @ 203 DPI
- 1:1 scale printing with proper DPI metadata
- No scaling applied during print

**Impact:**
- ✅ Barcodes fill ~90-95% of 68x38mm label
- ✅ Readable from 20-30cm distance
- ✅ Professional-quality labels for production

---

#### 3. Improved User Experience 💫

**Client Selection:**
- No more double selection - client pre-selected in dialogs
- Streamlined workflow saves time
- Reduces potential for errors

**Error Messages:**
- More descriptive and actionable
- Clear guidance on what went wrong
- Better logging for troubleshooting

---

## 🔧 Bug Fixes

### Critical Fixes

1. **SessionHistoryManager Path Mismatch**
   - Fixed search paths for Phase 1 Shopify sessions
   - Now searches in `packing/{list_name}/packing_state.json`
   - Maintains backward compatibility with `barcodes/packing_state.json`

2. **Barcode Print Scaling**
   - Fixed QPrinter configuration for 1:1 scale
   - Corrected page size and margins
   - Added DPI metadata to generated PNG files

3. **Session Detection**
   - Multiple packing lists per session now detected
   - Correctly identifies in-progress vs completed sessions
   - Session summary files properly located

---

## 📊 Performance Improvements

- **Faster session scanning** for large directories
- **Optimized file search** with Phase 1 structure
- **Reduced memory usage** in session history parsing

---

## 🛠️ Technical Details

### Architecture Changes

**Phase 1 Integration Complete:**
- Unified session state management
- Consistent directory structure across tools
- Proper StatsManager integration

**Directory Structure Support:**
```
Shopify Session (Phase 1):
Sessions/CLIENT_X/2025-11-19_1/
├── packing/
│   ├── DHL_Orders/
│   │   ├── packing_state.json      ← Now detected ✅
│   │   ├── session_summary.json    ← Now detected ✅
│   │   └── barcodes/
│   └── PostOne_Orders/
│       └── ...

Legacy Excel Session:
Sessions/CLIENT_X/2025-11-19_2/
└── barcodes/
    ├── packing_state.json          ← Still supported ✅
    └── session_summary.json
```

---

## 📚 Documentation Updates

- Updated README with v1.2.0 features
- Added printer specifications (Citizen CL-E300)
- Enhanced troubleshooting guide
- Updated system requirements

---

## ⚙️ System Requirements

**Minimum Requirements:**
- Windows 10/11
- Python 3.9+
- Network access to file server
- Citizen CL-E300 printer or compatible (203 DPI)
- 68mm x 38mm thermal labels

**Recommended:**
- Windows 11
- Python 3.11+
- SSD for faster session scanning
- Dedicated thermal label printer

---

## 🔄 Migration Guide

### From v1.1.x to v1.2.0

**No migration required!** ✅

This release is fully backward compatible:
- ✅ Existing Excel workflow unchanged
- ✅ Old sessions still accessible
- ✅ Configuration files compatible
- ✅ No data loss or corruption

**What happens automatically:**
- Dashboard will start showing sessions immediately
- History Browser will populate with past sessions
- Print function will use new optimized settings

---

## 🐛 Known Issues

**Minor (will be addressed in v1.3.0):**
- Dashboard UI is minimal (functional but basic)
- History Browser lacks advanced filtering
- Some TODO comments remain for future features

**Workarounds:**
- None needed - these are enhancement opportunities

---

## 🧪 Testing

**Tested Scenarios:**
- ✅ Excel workflow (backward compatibility)
- ✅ Shopify workflow (single packing list)
- ✅ Shopify workflow (multiple packing lists)
- ✅ Session locking with multiple users
- ✅ Crash recovery
- ✅ Barcode printing on Citizen CL-E300
- ✅ Network path access
- ✅ Dashboard statistics
- ✅ History Browser display

**Test Coverage:**
- Unit tests: Present and passing
- Integration tests: Manual verification completed
- User acceptance: Production workflow validated

---

## 📦 Installation

### New Installation

```bash
# Clone repository
git clone [repository-url]
cd packing-tool

# Install dependencies
pip install -r requirements.txt

# Configure
cp config.ini.example config.ini
# Edit config.ini with your settings

# Run
python src/main.py
```

### Upgrade from v1.1.x

```bash
# Pull latest
git pull origin main

# Update dependencies (if needed)
pip install -r requirements.txt --upgrade

# Run
python src/main.py
```

No additional configuration needed!

---

## 🙏 Acknowledgments

Thanks to the warehouse team for testing and feedback that made this release possible.

---

## 📞 Support

**Issues:** Open GitHub issue
**Questions:** Check documentation in `docs/`
**Logs:** `\\server\...\Logs\packing_tool\`

---

**Release Manager:** Development Team
**Release Date:** November 19, 2025
**Git Tag:** `v1.2.0`
