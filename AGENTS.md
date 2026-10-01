# Goal
保留上游完整订阅、转写、OCR、摘要、邮件和前端功能，在 Windows 本地增加视频下载与 PPT 联动回放。
增加 eLearning 文件增量归档：当前课程可配置定时同步，往期课程一次性归档，保留平台文件目录层级并预留通知发送接口。

# Current State
上游完整克隆，基于 5492d55，工作分支 feat/local-replay-ppt 与 main 同步。origin 为 AlexbeatsZ/Fudan_iCourse_Subscriber，upstream 为 LeafCreeper/Fudan_iCourse_Subscriber。
已移除 GitHub Actions 中的自动 AI 总结与邮件发送，仅保留 SenseVoice ASR 单行对轴字幕提取与分片入库。定时 cron 设为每日 06:00, 12:00, 18:00, 24:00 (UTC 22, 04, 10, 16)。
本地播放器运行于 http://127.0.0.1:8765/，支持单行字幕分段（subtitle_text）与幻灯片专注模式（Z 放大/S 切换/字幕悬浮）。
eLearning 当前 9 个课程/站点在 ROG 每天四次同步至 OMEN `D:\Documents\Elearning`。2026-09-22 已完成用户选择的 10 门往期课程一次性归档：157 个文件、2,253,721,442 字节，数据库和磁盘逐门一致，无历史断点/转存残留。设计见 [eLearning archive](docs/design/elearning-sync.md)。

截至 2026-09-28，本机 `D:\Videos` 的 7 门订阅课程有 27 节视频、27 个课件目录、19 份 VTT 字幕；新增录像的字幕尚未全部生成。课程对应数量：物理化学AⅢ 5、生物化学B 3、量子化学原理及应用(H) 6、人工智能在化学中的应用 3、应用化学专题 4、无机化学 4、数智化实用英文写作 2。

# Active Work
- 2026-10-01: 本机播放器已拆分部署到 `C:\Portable Programs\iCourse Player`，使用独立 Python 3.13.16 便携运行时和标准库服务，保留原播放界面、字幕/PPT 联动和同浏览器学习进度；本机播放不再依赖开发项目及其虚拟环境。部署源码与导出器在 `portable/`，设计见 [Portable player](docs/design/portable-player.md)。
- 2026-09-28: ROG 下载和转存逻辑已改为同名文件按大小判断，大小冲突报错并保留源与目标；`.transfer` 失败即清理，自动下载失败清理不完整片段并从头重试。三门课程共 14 节视频及 14 个课件目录已在本机 `D:\Videos`，ROG `Downloads\iCourse` 已清空并移除。设计见 [ROG library](docs/design/rog-library.md)。
- 2026-09-24: E: 的 2907 个文件已复制到 D:，Robocopy 只读差异检查为 0 漏拷/失败；E: 保留迁移前副本作备份。播放器和归档目标改为 D:。ROG 旧直连映射按用户要求保持原样，远程读写待扩展坞恢复后验收。

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
- 2026-09-22: eLearning 当前课程轮询、公告/讯息事件队列、可恢复文件发布和历史课程一次性归档完成；历史 10 门经真实下载及三轮断点续传验收，当前定时订阅未被历史课程污染。

# Build / Run / Test
独立播放器：双击 `C:\Portable Programs\iCourse Player\启动播放器.vbs`；退出后台服务使用同目录 `停止播放器.vbs`。默认读取 `D:\Videos`。便携部署测试：`uv run --no-project --python ..\.venv\Scripts\python.exe python -m unittest test_portable_player -v`（5 项）；导出及运行时说明见 `docs/design/portable-player.md`。
项目上一级的 uv 环境已有 requests、pycryptodome。运行 `..\.venv\Scripts\python.exe local_replay.py --help`。
完整上游依赖见 requirements.txt，新增下载入口只需 requests、pycryptodome。
测试：`..\.venv\Scripts\python.exe -m unittest test_local_replay -v`。
eLearning 测试：`..\.venv\Scripts\python.exe -X utf8 -m unittest test_elearning -v`（8 项）；操作说明见 [ELEARNING.md](ELEARNING.md)。

# Durable Lessons
本机环境代理 7897 曾导致 WebVPN TLS EOF；同一 URL 用 requests trust_env=False 直连正常返回 302 登录跳转。本地入口默认直连 WebVPN，支持 --proxy 显式覆盖。不能据脚本代理失败推断用户浏览器或 WebVPN 网站不可用。
WebVPN 偶尔会在票据请求返回 HTTP 200 后仍未形成可用会话；上游主流程按 10 次重新登录处理，本地入口保持相同上限。
平台 created_sec 是 PPT 相对视频秒数。时间 0 有效；回翻页需要保留多次时间事件，不能直接使用 OCR 去重后的集合。
PPT API 可能返回已经过 WebVPN 编码的图片 URL；此时必须使用 get_raw，不能再次 get_vpn_url 编码。
一次性 eLearning 历史归档必须与当前课程 `sync` 分开执行；使用 `sync && archive` 会在前者出现暂时性文件传输错误时完全跳过历史归档。验收需同时对齐平台文件数、SQLite 记录、目标盘文件/字节与暂存残留。
