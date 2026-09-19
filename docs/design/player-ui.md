# Player presentation

- Local entry: desktop/index.html, served fresh by desktop/server.py. Keep video, PPT, transcript, speed, offset, PiP, resume and lesson navigation working.
- User prefers black minimalism with Swiss-style alignment. Background #141414, surfaces #191919, text #ededeb, secondary #a2a29e, divider #333331. No decorative cards or bright accent palette.
- Library uses compact rows and a clear resume action; course detail shows real saved position. Progress bars appear only after video duration has been observed. Never invent chapter titles or completion percentages.
- Video and PPT share one viewing surface, a shared toolbar and full-width transcript/slide tabs. Native video controls own the timeline. Keep enlarged captions and focus switching.
- Download/transfer/sync live in Manage courses; offset, autoplay, PiP and shortcut help live in Playback settings. Do not add chapters/notes/extra modes solely from reference suggestions.
- Capture saved position before loading a new source. Persist time only once media metadata is ready, to prevent initial timeupdate from erasing resume state. Cache only finite duration.
- Figure margin must be explicitly zero to avoid browser default gutters.
- Normal video captions: 24px. Fullscreen captions: clamp(28px, 4.26vh, 72px), approximately 46px at 1080p (2.5 times the previous 18.4px).
- PPT captions are hidden (with no reserved space) in normal split view; show only in slide-focus mode and the fullscreen lightbox. Focus captions: 32px. Lightbox: clamp(28px, 4.86vh, 76px), approximately 52.5px at 1080p (2.5 times 21px). Let text wrap on narrow screens; flex image region shrinks to preserve caption visibility.
- No transcript timing/content changes for presentation requests. Auto-follow scrolls only the transcript container, never the page.
- Verification: open real local lecture; seek using transcript, inspect desktop and narrow layouts, PPT lightbox and native video fullscreen.
