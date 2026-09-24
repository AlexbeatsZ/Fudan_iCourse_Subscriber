# GitHub recognition and ROG replay library

## Ownership
GitHub Actions discovers courses hourly and runs SenseVoice/OCR/summary only when processing or timed-subtitle backfill is needed. Videos are downloaded directly on META-ROGALLY. No video artifact relay or school session export is used.

## Storage and credentials
- ROG project: `C:\Users\Meta\Project\Workspaces\icourse`.
- Persistent user environment variables: `FUDAN_STUID`, `FUDAN_UISPSW`. Read HKCU Environment on each operation so edits take effect without restarting Explorer. GitHub retains `STUID`, `UISPSW`; local edits do not update GitHub Secrets.
- Target: `D:\Videos`, backed by `\\192.168.137.1\D\Videos`; use UNC for background work. ROG's existing Z/D/E mappings are left untouched while the dock is unavailable; Windows Credential Manager owns SMB credentials.
- Download first to `Downloads\iCourse\<course title>\第01节.mp4`, then transfer completed lectures to target. No mandatory wait for OCR or subtitles.
- Copy into a `.transfer` file, flush, byte-compare, rename, and only then remove source. Conflicting existing target content is preserved and reported. Unavailable network storage never removes staged video.
- Number chronological deduplicated course sessions (including not-yet-playable sessions), zero-pad to at least two digits. Do not overwrite an existing different sub_id when upstream order changes.
- PPT events retain repeated images and zero timestamps. Assets: `第01节.assets`; metadata: `第01节.lesson.json`; subtitle: `第01节.vtt`.

## Subtitle fidelity
Persist original `{start_ms,end_ms,text}` ASR/official segments in lectures.transcript_segments; keep schema, JS mirror, merge and encrypted shard paths consistent. Backfill processed old lectures missing segments, without re-emailing existing summaries. Never manufacture timecodes by splitting a flat transcript. The local player uses original media-relative times, allows per-lecture subtitle offset, and preserves playback position.

## App and schedules
Loopback HTTP app in Edge app window, file-system course discovery, course/lesson selection, video seeking, synchronized PPT, clickable transcript. Mutating requests require per-process token; do not expose credentials through API or static paths.
Scheduled tasks run as the logged-in Meta user: hourly + logon download, daily configurable transfer (default 22:00), logon app server and mapped drives. Missed tasks start when available; commands and UI allow immediate retry. Downloads require the user session; do not claim service operation before Windows login.

## Validation
`python -m unittest test_local_replay test_replay_library -v` checks byte-range resume, subtitle timing, encrypted DB roundtrip, offline/conflict transfer and local API boundaries. Live ROG download, transfer, app and cloud backfill are additional acceptance steps.
