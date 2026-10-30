# Mac offline library

## Ownership and storage
ROG owns campus downloads and cloud transcripts. OMEN D:\\Videos\\Icouse and
D:\\Documents\\Elearning remain the primary archives. The Mac receives independent
copies in ~/Movies/icouse and ~/Documents/Elearning; source deletion never deletes
a Mac file. Use the project's isolated Python and the existing portable player.
Credentials and downloader databases are never copied to the Mac.

## Transport boundary
ROG archives to OMEN over its separate wired link at 192.168.137.1. The Mac is
not on that link and uses OMEN 192.168.31.214 on the dorm LAN. Do not replace
either address with the other.
Separate video and eLearning workers, state, and locks. Video connects only to
192.168.31.214 via a direct on-link physical interface in 192.168.31.0/24. Reject
gateway/VPN routes; bind SSH to the detected interface. Disable SSH config,
proxies, multiplexing, and forwarding. Check routes and pause controls while
commands run. A failed LAN connection never falls back for video.
eLearning prefers LAN but can use 100.113.70.121 with the same pinned OMEN key.
OpenSSH SFTP transfers data; a read-only standard-library helper on OMEN returns
machine-readable file size and nanosecond mtime. Do not mount remote filesystems.

## Publication and recovery
Only iCourse directories with course.json and completed MP4 receipts qualify.
Copy course/lesson metadata, VTT, and timeline images before publishing MP4.
Exclude download/transfer temporary files. Source size/mtime must match before
and after each transfer. Resume only a partial tied to that source version;
otherwise restart that partial. Publish atomically on the destination filesystem.
Record the resulting local stat. Skip unchanged files without rereading all media.
Existing or locally changed files are compared with the completed incoming file;
different contents are moved to local .icourse-sync/history before replacement.
No propagation of local edits or source deletion; no routine whole-library hashes.

## Lifecycle and UI
User LaunchAgents run the local server and independent workers. Workers poll every
five minutes when idle and immediately continue queued transfers without a limit.
Sleep normally; on wake resume on the next check. Local UI exposes progress,
pause/resume/retry, and eLearning browsing. Token-protected mutations cannot
override the video LAN rule. UI playback reuses the established portable view.
Keep source paths fixed and reject traversal/symlinks for local material access.

## Acceptance
Test network policy, resume/version changes, interrupted publication, existing
file preservation, ignored deletions, materials/API boundaries, real byte-range
playback, and route loss. Validate a real lecture and the initial archive, then
observe new files from ROG reaching OMEN and Mac. Preserve incomplete upstream
work and report upstream recovery independently of Mac playback acceptance.

## Public local interfaces
Portable make_app accepts optional get/post hooks; Windows defaults are unchanged. Mac adds GET /api/sync, token-protected POST /api/sync (kind/action), GET /api/materials?path=..., GET /materials/<relative-file>, and token-protected POST /api/materials/open. Material HTML/JS is attachment-only. The sync manifest root is verified against the fixed archive for each kind; video manifest and file calls both reject a non-LAN host. Empty eLearning directories are retained as well as files. An updated source sidecar is skipped until the next pass without blocking other transfers.
