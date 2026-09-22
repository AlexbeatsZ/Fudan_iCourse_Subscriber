# eLearning archive design

## Scope
Poll selected active Canvas courses into E:\Documents\Elearning. Preserve the platform Files hierarchy below one directory per course. Historical courses use a separate one-shot archive command and never change recurring subscriptions. Gather announcements and inbox changes; notification sending is an explicit extension, disabled during polling.

## Ownership and recovery
- Fudan direct CAS login uses the existing IDP authentication primitives and user environment variables; session cookies and signed URLs stay in memory.
- Runtime configuration, SQLite journal, downloads, course catalog and run status live under local-data/elearning (ignored by Git). Target paths contain only course files and recoverable .elearning/history.
- The ROG worker writes to the existing OMEN SMB share via UNC. Do not depend on interactive mapped-drive visibility. Existing SMB credentials remain in the user's environment/credential store.
- A process-level OS lock prevents concurrent commands on one deployment. There must be only one worker per target archive.
- All Canvas list endpoints follow rel=next links. A filtered folder list can omit hidden ancestors; full_name supplies their hierarchy without requesting inaccessible content.
- Course/file identifiers and version metadata determine whether an object is current. Local size and mtime detect missing/edited files. No repeated whole-library hash audit.
- Stage complete bytes, check expected size, copy and byte-compare destination temporary data, preserve previous content, atomically rename, then commit state/event and clear staging. Failed publication retains the complete staging file for retry.
- Stable names handle Windows invalid/reserved names and case-insensitive collisions. Never mirror remote deletions. Existing filenames remain stable after platform rename; folder moves create the new path without deleting the old copy.
- Notification dispatch is at least once. Event IDs are stable for retry, and receivers deduplicate. No automatic external sender or station message is invoked by sync.

## Schedule and acceptance
Windows task uses configuration times (default 00:00, 06:00, 12:00, 18:00 local UTC+8), limited interactive user, missed-start recovery and IgnoreNew. Existing iCourse tasks are not changed. Validate real CAS, complete pagination, disk files, second-run skips, historical-only selection, task result and notification API stubs.
