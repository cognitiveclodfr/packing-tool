# Phase 1.2: Session Locking - User Guide

## What's New in Phase 1.2?

Phase 1.2 adds session locking to prevent conflicts when multiple users work with the Packing Tool simultaneously. Now you can safely work knowing that no one else can accidentally open your active session.

---

## Key Features

### 1. Session Locking

When you start or restore a session, it's automatically locked to your computer. Other users will see that the session is active and won't be able to open it until you finish.

**Visual Indicators:**
- 🔒 **Active Session** - Currently being used by someone on another PC
- ⚠️ **Stale Lock** - Session was locked but the application may have crashed
- 📦 **Available** - Session is free to open

### 2. Heartbeat System

Every 60 seconds, the application updates a "heartbeat" to prove it's still running. If a session hasn't updated its heartbeat for 2 minutes, it's considered "stale" and can be force-released by another user.

### 3. Crash Recovery

If the application crashes while you're working on a session, the lock becomes "stale" after 2 minutes. You or another user can then force-release the lock to continue working.

---

## How to Use

### Starting a New Session

1. Select a client from the dropdown
2. Click **"Start Session"**
3. Choose your packing list file
4. The session is automatically locked to your PC
5. Work normally - the lock is maintained automatically

### Restoring a Previous Session

1. Select the same client
2. Click **"Restore Session"** button
3. A dialog shows all incomplete sessions with their status:
   - 📦 **Green** - Available to restore
   - 🔒 **Red** - Active on another PC (shows who is using it)
   - ⚠️ **Yellow** - Stale lock (possible crash)
4. Select an available session and click **"Restore Selected"**

### If You See a Locked Session (🔒)

When you try to restore a session that someone else is using, you'll see:

```
Session Already in Use

This session is currently active on another computer.

User: Maria Ivanova
Computer: DESKTOP-PC2
Started: 28.10.2025 14:30

Please wait for the user to finish, or choose another session.
```

**What to do:** Wait for the other user to finish, or select a different session.

### If You See a Stale Lock (⚠️)

If a session has a stale lock (no heartbeat for 2+ minutes), you can force-release it:

```
Stale Session Lock Detected

This session has a stale lock - the application may have crashed.

Original user: Ivan Petrenko
Computer: DESKTOP-PC1
Last heartbeat: 28.10.2025 14:15
No response for: 3 minutes

The application may have crashed on that PC.

Do you want to force-release the lock and open this session?
```

**What to do:**
- Click **"Yes"** to release the lock and open the session
- Click **"No"** to cancel

⚠️ **Warning:** Only force-release if you're sure the other user is no longer working. Check with them first if possible.

### Ending a Session

When you click **"End Session"**, the lock is automatically released and others can access it.

---

## Session Monitor

The **Session Monitor** shows all active sessions across all clients in real-time.

### Opening the Monitor

Click the **"Session Monitor"** button in the main window.

### What You'll See

A table showing:
- **Client** - Client ID (M, R, A, etc.)
- **Session** - Session name with timestamp
- **User** - Name of the user working on this session
- **Computer** - Computer name where session is active
- **Started** - Time when session was started
- **Last Heartbeat** - Last time the session proved it's alive

### Auto-Refresh

The monitor automatically refreshes every 30 seconds to show the latest information.

---

## Common Scenarios

### Scenario 1: Both Users Start Same Client at Same Time

**What happens:** Only one user will successfully lock the session. The other will see an error.

**Solution:** The second user should wait or start a different session.

### Scenario 2: Application Crashes

**What happens:** The lock file remains, but heartbeat stops updating.

**After 2 minutes:** Lock becomes "stale" and can be force-released.

**Solution:**
1. Restart the application
2. Open **"Restore Session"**
3. Select the stale session
4. Force-release the lock when prompted

### Scenario 3: Forgot to End Session

**What happens:** Lock remains active as long as application is running and heartbeat updates.

**Solution:**
- Go back to the PC and click "End Session"
- Or wait for heartbeat to timeout if application was closed incorrectly

### Scenario 4: Network Interruption

**What happens:** Heartbeat may fail to update temporarily.

**Impact:** If network is down for 2+ minutes, lock becomes stale.

**Solution:** Keep network connection stable. Short interruptions (<2 min) are OK.

---

## Configuration

### Heartbeat Interval

- **Default:** 60 seconds
- **Location:** Configured in code, cannot be changed by user

### Stale Timeout

- **Default:** 2 minutes (120 seconds)
- **Location:** Configured in code, cannot be changed by user

**Rationale:** 2 minutes is enough to detect crashes quickly while avoiding false positives from temporary network issues.

---

## Troubleshooting

### "Session is locked" but no one is using it

**Cause:** The lock may be stale due to a crash.

**Solution:** Wait 2 minutes for it to become stale, then force-release.

### Lock file not releasing after End Session

**Cause:** Application crashed or network error during cleanup.

**Solution:**
1. Check if application is still running (Task Manager)
2. Close it completely
3. Wait 2 minutes
4. Force-release the lock

### Heartbeat not updating

**Cause:** Network connection issues.

**Check:**
- File server is accessible: `\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\2Packing-tool`
- Network is stable
- Firewall not blocking access

**Impact:** If heartbeat fails for 2+ minutes, lock becomes stale.

### Cannot force-release stale lock

**Cause:** File permissions or network access issue.

**Solution:**
1. Check network connection
2. Verify you have write permissions to the session folder
3. Try restarting the application
4. Contact IT if problem persists

---

## Technical Details (For IT/Admins)

### Lock File Location

```
\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\2Packing-tool\
└── clients\
    └── M\
        └── sessions\
            └── Session_2025-10-28_143045\
                └── .session.lock
```

### Lock File Format

```json
{
  "locked_by": "DESKTOP-PC1",
  "user_name": "Ivan Petrenko",
  "lock_time": "2025-10-28T14:30:45",
  "process_id": 12345,
  "app_version": "1.2.0",
  "heartbeat": "2025-10-28T14:35:12"
}
```

### Lock Mechanism

- Uses Windows `msvcrt.locking()` for file-level locking
- Atomic writes with temporary files
- Automatic retry with exponential backoff
- Graceful cleanup on application exit

### Logging

All lock operations are logged to:
```
\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\2Packing-tool\logs\packing_tool_YYYY-MM-DD.log
```

Search for:
- `Session lock acquired`
- `Session lock released`
- `Heartbeat updated`
- `Stale lock force-released`

---

## Best Practices

1. ✅ **Always end sessions properly** - Click "End Session" before closing
2. ✅ **Check Session Monitor** - Before starting work, see who's active
3. ✅ **Communicate with team** - Let others know what you're working on
4. ✅ **Maintain network stability** - Avoid long network disconnections
5. ✅ **Restart after crashes** - Close completely and restart cleanly
6. ⚠️ **Don't force-release active locks** - Only for stale locks (crashed sessions)
7. ⚠️ **Don't kill the application** - Use proper "End Session" button

---

## FAQ

**Q: What if I need to work on a session but someone else has it locked?**

A: Check the Session Monitor to see who has it. Contact them to coordinate, or wait for them to finish.

**Q: Can I disable locking?**

A: No, locking is a core safety feature to prevent data corruption from concurrent access.

**Q: What happens if I close the application without ending the session?**

A: The lock will remain for 2 minutes until it becomes stale and can be force-released.

**Q: Can I have multiple sessions open on different PCs?**

A: Yes, as long as they're for different clients or different sessions of the same client.

**Q: Why 2 minutes for stale timeout?**

A: It's a balance between detecting crashes quickly and avoiding false positives from temporary network issues.

**Q: What if two users try to force-release a stale lock at the same time?**

A: File locking ensures only one will succeed. The other will see the session is already open.

---

## Support

If you encounter issues:

1. Check the logs in `\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\2Packing-tool\logs\`
2. Try restarting the application
3. Wait for stale locks to timeout (2 minutes)
4. Contact your system administrator with:
   - Screenshot of the error
   - Time when it occurred
   - Which client/session you were trying to access
   - Computer name and user name

---

**Version:** 1.2.0
**Last Updated:** 2025-10-28
