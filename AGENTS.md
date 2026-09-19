# Goal
保留上游完整订阅、转写、OCR、摘要、邮件和前端功能，在 Windows 本地增加视频下载与 PPT 联动回放。

# Current State
上游完整克隆，基于 5492d55，工作分支 feat/local-replay-ppt 与 main 同步。origin 为 AlexbeatsZ/Fudan_iCourse_Subscriber，upstream 为 LeafCreeper/Fudan_iCourse_Subscriber。
已移除 GitHub Actions 中的自动 AI 总结与邮件发送，仅保留 SenseVoice ASR 单行对轴字幕提取与分片入库。定时 cron 设为每日 06:00, 12:00, 18:00, 24:00 (UTC 22, 04, 10, 16)。
本地播放器运行于 http://127.0.0.1:8765/，支持单行字幕分段（subtitle_text）与幻灯片专注模式（Z 放大/S 切换/字幕悬浮）。

当前 7 门订阅课程在 `E:\Videos` 与 ROG 端的最新状态（截至 2026-09-20 06:00）：
- `37113` 物理化学AⅢ: 3/3 节（全部就绪，在 `E:\Videos`）
- `38135` 无机化学: 2/2 节（全部就绪，在 `E:\Videos`）
- `40243` 生物化学B: 2/2 节（全部就绪，在 `E:\Videos`）
- `41642` 科技实用英语写作: 2/2 节（全部就绪，在 `E:\Videos`）
- `37543` 计算机在化学中的应用: 第01节就绪在 `E:\Videos`，第02节下载中（已过 1.07GB/1.73GB）
- `38016` 应用化学专业实验: 第02节就绪在 `E:\Videos`，第01节下载中（已过 508MB/1.68GB）
- `37695` 分子化学原理及应用(H): 4 节课次断点缓存均已建立（150MB~1.3GB），ROG 后台持久续传并自动同步到 `E:\Videos`

# Active Work
- 2026-09-19: added hover/focus/touch PPT previous/next controls (including lightbox), synchronized video seeking and bottom alignment space.
- 2026-09-19: PPT captions now appear only in slide-focus mode and fullscreen lightbox; normal split view hides the caption strip entirely.
- 2026-09-19: black minimal study workspace replaces blue card UI; unified video/PPT, shared toolbar, full-width transcript, secondary action menus and real resume progress. Enlarged captions retained; early-load resume overwrite fixed. Design: [player UI](docs/design/player-ui.md). Desktop/narrow layouts, subtitle seek, 34 PPT events, speed and reload/resume checked; 13 tests passed.
- 2026-09-19: migrating download execution to ROG, GitHub retains recognition. See [ROG library design](docs/design/rog-library.md) before modifying storage/subtitle/scheduling. Credentials are ROG user environment variables FUDAN_STUID/FUDAN_UISPSW; never commit values. replay_library.py and desktop/ implement course folders, 第01节 naming, staging/verified transfer, VTT and local app.
- Timed transcript persistence, merge and shard roundtrip added; 13 focused tests passed. Live deployment/old-library migration/cloud backfill acceptance in progress.
- 2026-09-19: 精简 GitHub Actions 工作流与本地任务：彻底停用自动 AI 总结（LLM）与邮件发送（SMTP），仅保留视频巡检、ASR 语音转录生成单行对轴字幕（SenseVoice）与 PPT 课件提取。
- 2026-09-19: 定时调度调整为每天 4 次，对应北京时间 06:00, 12:00, 18:00, 24:00（UTC 22:00, 04:00, 10:00, 16:00），cron 为 `0 4,10,16,22 * * *`。
- 固化订阅课程清单（共 7 门，写入代码与日志，防止 GitHub Secrets 变更限制导致编号遗失）：
  1. `40243`: 生物化学B（周二/周四6-8节，共16节，已回放2节：657466, 662070）
  2. `38135`: 无机化学（共16节，已回放2节：654850, 660009）
  3. `37695`: 分子化学原理及应用(H)（共32节，已回放4节：654365, 654364, 658821, 658822）
  4. `37543`: 计算机在化学中的应用（共31节，已回放2节：654197, 658557）
  5. `37113`: 物理化学AⅢ（共24节，已回放3节：653729, 656695, 659248）
  6. `38016`: 应用化学专业实验（共16节，已回放2节：654719, 659884）
  7. `41642`: 科技实用英语写作（共11节，已回放2节：742683, 742890）
- 2026-09-20: 部署 ROG 持久断点续传器与自动跨机同步通道（persistent_downloader.py），所有完成课次即时拉取 SenseVoice 字幕并同步至 OMEN `E:\Videos`。

# Build / Run / Test
项目上一级的 uv 环境已有 requests、pycryptodome。运行 `..\.venv\Scripts\python.exe local_replay.py --help`。
完整上游依赖见 requirements.txt，新增下载入口只需 requests、pycryptodome。
测试：`..\.venv\Scripts\python.exe -m unittest test_local_replay -v`。

# Durable Lessons
本机环境代理 7897 曾导致 WebVPN TLS EOF；同一 URL 用 requests trust_env=False 直连正常返回 302 登录跳转。本地入口默认直连 WebVPN，支持 --proxy 显式覆盖。不能据脚本代理失败推断用户浏览器或 WebVPN 网站不可用。
WebVPN 偶尔会在票据请求返回 HTTP 200 后仍未形成可用会话；上游主流程按 10 次重新登录处理，本地入口保持相同上限。
平台 created_sec 是 PPT 相对视频秒数。时间 0 有效；回翻页需要保留多次时间事件，不能直接使用 OCR 去重后的集合。
PPT API 可能返回已经过 WebVPN 编码的图片 URL；此时必须使用 get_raw，不能再次 get_vpn_url 编码。
