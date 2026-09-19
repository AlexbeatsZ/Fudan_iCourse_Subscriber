# Player presentation

- Local entry: desktop/index.html, served fresh by desktop/server.py. Keep video, PPT, transcript, speed, offset, PiP, resume and lesson navigation working.
- Blue ink / white lecture desk; compact utility header, paired projection surfaces, transcript tabs below video. Figure margin must be explicitly zero to avoid browser default gutters.
- Normal video captions: 24px. Fullscreen captions: clamp(28px, 4.26vh, 72px), approximately 46px at 1080p (2.5 times the previous 18.4px).
- PPT captions: 28px, 32px in focus mode. Lightbox: clamp(28px, 4.86vh, 76px), approximately 52.5px at 1080p (2.5 times 21px). Let text wrap on narrow screens; flex image region shrinks to preserve caption visibility.
- No transcript timing/content changes for presentation requests. Auto-follow scrolls only the transcript container, never the page.
- Verification: open real local lecture; seek using transcript, inspect desktop and narrow layouts, PPT lightbox and native video fullscreen.
