# Player presentation

- Local entry: desktop/index.html, served fresh by desktop/server.py. Keep video, PPT, transcript, speed, offset, PiP, resume and lesson navigation working.
- The 2026-10-30 library redesign uses Swiss typography, paper #f2f1ed, ink #171717, vermilion #f34225 and real course stills. Dark and system appearances use #151716 / #f1f0e8 / #ff654a. See [Swiss library](swiss-player.md). The video/PPT projection workspace stays dark.
- Library uses a searchable course grid, observed-progress filters and a clear resume action; course detail shows real saved position. Progress bars appear only after video duration has been observed. Never invent chapter titles or completion percentages.
- Video and PPT share one viewing surface, a shared toolbar and full-width transcript/slide tabs. Native video controls own the timeline. Keep enlarged captions and focus switching.
- Download/transfer/sync live in Manage courses; offset, autoplay, PiP and shortcut help live in Playback settings. Do not add chapters/notes/extra modes solely from reference suggestions.
- Capture saved position before loading a new source. Persist time only once media metadata is ready, to prevent initial timeupdate from erasing resume state. Cache only finite duration.
- Figure margin must be explicitly zero to avoid browser default gutters.
- Normal video captions: 24px. Fullscreen captions: clamp(28px, 4.26vh, 72px), approximately 46px at 1080p (2.5 times the previous 18.4px).
- PPT captions are hidden (with no reserved space) in normal split view; show only in slide-focus mode and the fullscreen lightbox. Focus captions: 32px. Lightbox: clamp(28px, 4.86vh, 76px), approximately 52.5px at 1080p (2.5 times 21px). Let text wrap on narrow screens; flex image region shrinks to preserve caption visibility.
- No transcript timing/content changes for presentation requests. Auto-follow scrolls only the transcript container, never the page.
- Verification: open real local lecture; seek using transcript, inspect desktop and narrow layouts, PPT lightbox and native video fullscreen.

- Slide and lightbox left/right hover buttons navigate chronological PPT events and seek the shared video timeline; first/last boundaries are disabled. Clicks must not bubble into the focus toggle. Keyboard focus and touch reveal controls. Two explicit alignment buttons choose the height reference: video or slide. Use the reference media aspect ratio and pane width, capped at 58vh; contain both images without cropping. Persist the mode, recompute on resize/metadata/image load and keep captions hidden in normal mode.
