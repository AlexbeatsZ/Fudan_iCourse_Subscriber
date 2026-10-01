# Goal
Deploy the existing iCourse video/PPT/subtitle player as an independent portable Windows app.

# Current State
- Deployment: `C:\Portable Programs\iCourse Player`, version 1.0.0, Python 3.13.16 x64 embeddable runtime.
- Library: `D:\Videos`; server: `http://127.0.0.1:8765/`, loopback only.
- No dependency on the development checkout, installed Python, user credentials or third-party Python packages.
- Source and exporter: `subscriber/portable/` in `AlexbeatsZ/Fudan_iCourse_Subscriber`; design: `subscriber/docs/design/portable-player.md`.

# Active Work
- 2026-10-01: independent deployment added. Live catalog: 7 courses, 27 videos, 19 VTT files. Real lecture loads 1920x1080 video, 1280x720 PPT, 34 slide events and 1207 subtitle cues. Existing browser resume position is retained.

# Build / Run / Test
- Double-click `启动播放器.vbs`; change the video directory through Settings.
- Double-click `停止播放器.vbs` to stop this deployment's server.
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\start-player.ps1 -NoBrowser` starts without opening the browser. Add `-Stop` for shutdown.
- Runtime/settings/logs are local to this folder. Logs: `data/server.log`, `data/server-error.log`.
- Export/test commands and implementation details are recorded in the source repository's portable-player design document.

# Durable Lessons
- Keep the same browser/profile and `127.0.0.1:8765` origin for old browser localStorage progress; moving the program directory alone does not move or erase progress.
- Chromium can cancel media and idle keep-alive requests during seeks or tab closure. Expected connection cancellation should not fill the error log with server tracebacks.
