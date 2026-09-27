# GitHub recognition and ROG replay library

## Ownership
GitHub Actions discovers courses hourly and runs SenseVoice/OCR/summary only when processing or timed-subtitle backfill is needed. Videos are downloaded directly on META-ROGALLY. No video artifact relay or school session export is used.

## Storage and credentials
- ROG project: `C:\Users\Meta\Project\Workspaces\icourse`.
- Persistent user environment variables: `FUDAN_STUID`, `FUDAN_UISPSW`. Read HKCU Environment on each operation so edits take effect without restarting Explorer. GitHub retains `STUID`, `UISPSW`; local edits do not update GitHub Secrets.
- Target: `D:\Videos`, backed by `\\192.168.137.1\D\Videos`; use UNC for background work. ROG's existing Z/D/E mappings are left untouched while the dock is unavailable; Windows Credential Manager owns SMB credentials.
- Download first to `Downloads\iCourse\<course title>\第01节.mp4`, then transfer completed lectures to target. No mandatory wait for OCR or subtitles.
- Copy into a `.transfer` file, flush, check its size, rename, and only then remove source. Existing same-name, same-size target files count as transferred without reading their contents; size conflicts are preserved and reported. A target `*.mp4.json` sidecar may differ in text length when its `complete` and `total` fields still match the video, so keep that valid target record. Remove failed or stale `.transfer` files. Unavailable network storage never removes staged video.
- After verified transfer, remove a staging course's `course.json` and directory once no video, lesson metadata, PPT asset, partial download, or other content remains. Remove the empty `Downloads\iCourse` directory too; preserve any course directory with pending or unknown content.
- ROG automatic downloads restart incomplete videos from zero: remove `*.mp4.part`, orphan download records, interrupted lesson metadata, subtitle, and PPT partial files after failure or before the next run. Preserve complete MP4 files and published target files. The standalone `local_replay.py` downloader retains its separate verified-resume behavior.
- Number chronological deduplicated course sessions (including not-yet-playable sessions), zero-pad to at least two digits. Do not overwrite an existing different sub_id when upstream order changes.
- PPT events retain repeated images and zero timestamps. Assets: `第01节.assets`; metadata: `第01节.lesson.json`; subtitle: `第01节.vtt`.

## Subtitle fidelity
Persist original `{start_ms,end_ms,text}` ASR/official segments in lectures.transcript_segments; keep schema, JS mirror, merge and encrypted shard paths consistent. Backfill processed old lectures missing segments, without re-emailing existing summaries. Never manufacture timecodes by splitting a flat transcript. The local player uses original media-relative times, allows per-lecture subtitle offset, and preserves playback position.

## App and schedules
Loopback HTTP app in Edge app window, file-system course discovery, course/lesson selection, video seeking, synchronized PPT, clickable transcript. Mutating requests require per-process token; do not expose credentials through API or static paths.
Scheduled tasks run as the logged-in Meta user: hourly + logon download, daily configurable transfer (default 22:00), logon app server and mapped drives. Missed tasks start when available; commands and UI allow immediate retry. Downloads require the user session; do not claim service operation before Windows login.

## Validation
`python -m unittest test_local_replay test_replay_library -v` checks byte-range resume, subtitle timing, encrypted DB roundtrip, offline/conflict transfer and local API boundaries. Live ROG download, transfer, app and cloud backfill are additional acceptance steps.
