# Mac iCourse

The local player uses the existing portable UI. It reads videos from
`~/Movies/icouse` and course materials from `~/Documents/Elearning`.

Run `macos/启动播放器.command` to open the local player. The server is
`http://127.0.0.1:8765/`; closing the browser leaves synchronization running.
Open **资料同步状态** for progress, pause/resume, and immediate retry.
**课程资料** browses local eLearning files; PowerPoint files can open in their
installed default app, while PDF/image links open in the browser.

Video synchronization runs only on the on-link dorm network to OMEN
192.168.31.214. No gateway/VPN route, SSH proxy, or Tailscale fallback is allowed.
eLearning prefers that LAN and otherwise can use OMEN 100.113.70.121. It needs
OMEN online and the Mac awake. Normal sleep is allowed. Copies resume afterward.
Neither job mirrors source deletions or sends Mac edits back to OMEN. Replaced
local files remain in the target's hidden `.icourse-sync/history` directory.

## Setup and maintenance

Use an existing Python to create the project `.venv`. The Mac runtime has no
third-party Python dependencies. Test dependencies are requests and pycryptodome.
Deploy `macos/manifest.py` to OMEN's portable player's `app/mac_manifest.py`.
Run `.venv/bin/python -m macos.install` to build the shared UI and install the
three task-owned user LaunchAgents. No system service or global runtime changes.
Keep SSH's existing OMEN LAN host key and key authentication in place.

Logs/status/config are ignored files in `local-data/mac`. List the three
services with `launchctl print gui/$(id -u)/com.meta.icourse.player` (also
`.videos` and `.elearning`). Stop them with `launchctl bootout` using their
corresponding files in `~/Library/LaunchAgents`; existing copies remain intact.
Reinstall with `python -m macos.install`. See the design doc before changing
transport or publication semantics.
