# Portable local player

## Scope and deployment
- OMEN playback is independent of the development checkout. Deployment: `C:\Portable Programs\iCourse Player`.
- Keep the established desktop/index.html playback UI: media seeking, subtitle/PPT timeline, focus/lightbox, PiP, keyboard shortcuts, speed, autoplay and resume.
- Standalone server and exporter: `portable/player.py`, `portable/export_player.py`. Python standard library only; bundle official Python 3.13.16 Windows x64 embeddable runtime. No installed Python, virtual environment, account, AI/model dependency or remote download worker is needed.
- Export the current shared UI and replace only management/credential settings with refresh and video-directory settings. Fail export if these UI anchors change, so a future redesign cannot silently produce a broken player.
- Download, transfer, subtitle generation and eLearning remain ROG/cloud responsibilities. The portable player reads existing media and does not create scheduled tasks or change environment variables.

## Storage and identity
- Default library: `D:\Videos`. Read existing course directories, MP4, VTT, lesson metadata, `.assets/timeline.json` and slide images without copying or editing them.
- Preserve course folder, lesson stem, root index 0 and `http://127.0.0.1:8765/`. Existing browser localStorage progress and preferences remain available in the same browser/profile/origin. Browser profiles are not exported.
- `settings.json` only contains destination and port. `data` contains server logs. Runtime, server, page, launchers and documentation all live under the deployment directory.
- Launch via `启动播放器.vbs` with no console; readiness and deployment identity are checked before opening the default browser. Reopening reuses the existing server. `停止播放器.vbs` requests authenticated shutdown of this deployment only. Browser closure alone does not stop the server.

## Validation
- `uv run --no-project --python ..\.venv\Scripts\python.exe python -m unittest test_portable_player -v`.
- Run the exported server with its embedded runtime; inspect real course catalog, MP4 206 ranges, VTT, slide timeline/images, service reuse and stop/restart. Confirm process executable and deployment path are inside the portable folder.
- Export: `uv run --no-project --python ..\.venv\Scripts\python.exe python portable\export_player.py "C:\Portable Programs\iCourse Player" --runtime-archive "C:\Users\Meta\AppData\Local\Temp\.agents\icourse-player-deploy\python-3.13.16-embed-amd64.zip"`.
