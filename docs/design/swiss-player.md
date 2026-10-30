# Swiss course library and archive paths

Shared Swiss direction: paper `#f2f1ed`, ink `#171717`, vermilion `#f34225`,
divider `#d4d4ce`, secondary surface `#e7e7e0`, muted text `#60605b`.
Dark appearance: paper `#151716`, ink `#f1f0e8`, accent `#ff654a`,
divider `#3c403c`, surface `#242824`, muted text `#adb1a7`.
Display type uses Arial / Helvetica Neue / Microsoft YaHei at weight 800;
utility labels use Consolas / SFMono-Regular. Fonts and media work offline.
Appearance defaults to system; explicit light/dark choice persists in browser
`icourse_theme`. Apply it in the head to avoid a flash of the wrong appearance.
Native controls, search, menus and dialogs inherit the chosen color scheme.

The library opens with a real course still and recent lesson, followed by a
collection filter and responsive grid. Search matches course, lesson and date.
Sorting uses titles or recording counts. Filters use observed browser progress
and real VTT availability. No invented durations, completion or chapter labels.

`desktop/index.html` remains the shared UI. The portable exporter replaces only
management/settings hooks; the Mac builder adds sync/material controls. Preserve
exporter anchors. Video, slides, repeat/zero slide events, transcript seeking,
offset, speed, PiP, fullscreen, alignment, autoplay and shortcuts remain shared.
The projection stage stays dark in both library appearances.

`scripts/create_previews.py <archive>` uses existing FFmpeg to cache a still at
90 seconds (zero for short recordings) as `<lesson>.assets/preview.jpg`. Existing
stills/videos are never overwritten. Catalogs prefer the still, then a real
timeline image, then a neutral text fallback.

## Archive identity

- OMEN: `D:\Videos\Icouse`.
- ROG: `\\192.168.137.1\D\Videos\Icouse`; retain wired transport and local
  `Downloads\iCourse` staging.
- Mac source manifest: `D:/Videos/Icouse`, fetched only over existing direct
  `192.168.31.214` LAN. Local copies remain `~/Movies/icouse`.
- eLearning paths, transport, credentials, sessions and queues are separate.
- Preserve port 8765, loopback binding, root zero, course directory and lesson
  stems so existing browser storage keys and playback progress survive.
- Relocate whole course directories on the same OMEN volume, retaining all
  assets and timestamps. Never put videos in the source repository.
- Pause idle ROG scheduled triggers and the Mac video worker for cutover,
  preserving and restoring their prior enabled/pause state.

## Deployment and checks

OMEN entry is `C:\Portable Programs\iCourse Player\播放器.vbs`. Update app files
and destination/version; retain runtime, toggle launcher and identity checks.
Mac retains its three LaunchAgents; rebuild the shared HTML and reload only
processes whose code changed. ROG has newer download/SMB recovery than main:
patch its archive defaults and preview metadata without replacing those behaviors.

Run portable/range/export/library tests on Windows, sync/network/material tests
on Mac, then real catalog, range, browser video, transcript and slide checks.
Service/catalog success does not establish a fully synchronized Mac archive;
report actual local counts and any remaining backlog separately.
