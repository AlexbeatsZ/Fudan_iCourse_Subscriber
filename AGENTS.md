# Goal
保留上游完整订阅、转写、OCR、摘要、邮件和前端功能，在 Windows 本地增加视频下载与 PPT 联动回放。
增加 eLearning 文件增量归档：当前课程可配置定时同步，往期课程一次性归档，保留平台文件目录层级并预留通知发送接口。

# Current State
Mac 部署在 `/Users/meta/Project/Workspaces/icourse`，使用项目 `.venv` 与 `macos/` 标准库同步/播放器。视频副本 `~/Movies/icouse` 只经宿舍直连 LAN 拉取；`~/Documents/Elearning` 外出可经 Tailscale。源删除不传播，本地修改先保留历史。设计索引：[Mac offline sync](docs/design/mac-offline-sync.md)。
上游完整克隆，基于 5492d55，工作分支 feat/local-replay-ppt 与 main 同步。origin 为 AlexbeatsZ/Fudan_iCourse_Subscriber，upstream 为 LeafCreeper/Fudan_iCourse_Subscriber。
已移除 GitHub Actions 中的自动 AI 总结与邮件发送，仅保留 SenseVoice ASR 单行对轴字幕提取与分片入库。定时 cron 设为每日 06:00, 12:00, 18:00, 24:00 (UTC 22, 04, 10, 16)。
本地播放器运行于 http://127.0.0.1:8765/，支持单行字幕分段（subtitle_text）与幻灯片专注模式（Z 放大/S 切换/字幕悬浮）。
eLearning 当前 9 个课程/站点在 ROG 每天四次同步至 OMEN `D:\Documents\Elearning`。2026-09-22 已完成用户选择的 10 门往期课程一次性归档：157 个文件、2,253,721,442 字节，数据库和磁盘逐门一致，无历史断点/转存残留。设计见 [eLearning archive](docs/design/elearning-sync.md)。

截至 2026-09-28，本机 `D:\Videos` 的 7 门订阅课程有 27 节视频、27 个课件目录、19 份 VTT 字幕；新增录像的字幕尚未全部生成。课程对应数量：物理化学AⅢ 5、生物化学B 3、量子化学原理及应用(H) 6、人工智能在化学中的应用 3、应用化学专题 4、无机化学 4、数智化实用英文写作 2。

# Active Work
- 2026-10-17: `9029ce8` 已推送 main；修复已合入 feat/local-replay-ppt（`b57685e`），相关测试 main 21 项、工作分支 30 项通过。GitHub 自动停用了 fork 工作流，已在网页重新启用。真实巡检 #90 成功（2m55s）：复旦登录、云端数据库解密、7 门课程检查通过，needed=true。已启动正式工作流 #91（38997984175）；ASR/数据更新尚未验收完成。巡检使用 GitHub 自带令牌，临时 HTTP/连接/非 JSON 故障最多尝试 3 次，持续故障保持失败；错误仅记录状态码和主机。新增 `probe_only`，默认手动强制处理行为保留。设计：[Actions probe](docs/design/actions-probe.md)。截图 #2（2026-09-16）的日志已不可用，历史根因未知；#23/#80 为登录成功后的 HTTPError，旧日志没有状态码。
- 2026-10-13: Mac 三个独立用户 LaunchAgent 已部署；190 个 eLearning 文件（2,606,957,839 字节）初始副本完成，视频全量队列运行中。真实英文写作录像、字幕跳转、PPT、暂停和续传已验收。ROG 主程序课件轮询完成（32 unchanged、0 errors），原有 eLearning 定时任务已实际返回 0（32 unchanged、0 errors）；iCourse 下载已交回原有定时任务，补下载继续运行。
- 2026-10-13: ROG 两个目标配置按用户最终确认使用 OMEN `192.168.137.1` 直连 UNC；Mac 独立使用 `192.168.31.214` LAN，SMB 认证随目标服务器变化，读取当前注册表密码并使用明确的 OMEN 本地账户；避免对已可达共享重新认证。非 JSON 课次列表会有限重登录重试，单门失败不终止其他课程；完成每节视频/课件后立即转存。Mac 路径规范化兼容性与播放器扩展保留 Windows 行为。
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
Mac: `uv venv --python python3 .venv`；运行 `.venv/bin/python -m macos.install` 构建播放器与专用 LaunchAgent。入口 `macos/启动播放器.command`，服务 `http://127.0.0.1:8765/`。运行/卸载见 [Mac README](macos/README.md)。Mac 运行无需第三方包；测试需项目内 requests、pycryptodome。检查：`TMPDIR=/tmp/.agents .venv/bin/python -m unittest test_mac_sync test_portable_player test_replay_library test_elearning test_local_replay -q`（44 项）。
独立播放器：双击 `C:\Portable Programs\iCourse Player\启动播放器.vbs`；退出后台服务使用同目录 `停止播放器.vbs`。默认读取 `D:\Videos`。便携部署测试：`uv run --no-project --python ..\.venv\Scripts\python.exe python -m unittest test_portable_player -v`（5 项）；导出及运行时说明见 `docs/design/portable-player.md`。
Actions 巡检回归：`python -m unittest test_check_new_replays test_local_replay test_replay_library -v`。线上只读巡检：`gh workflow run check.yml --ref main -f probe_only=true`；此模式仍真实登录、解密云端数据库并枚举课程，只跳过后续强制 ASR。
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

- macOS `/tmp` 等目录可能是系统别名；归档根与子路径必须一致规范化，否则备份旧版本时 relative_to 会误判越界。
- OpenSSH 10.3 的 SFTP 双引号路径已经保护方括号；再次手动转义方括号会查找带反斜杠的文件名。真实 Windows 端同名 `[1]` 与 `1` 文件验证了此行为。

- Windows 导入时不要直接 exists() 探测网络映射盘；ROG 的旧 D: 返回 WinError 1272，使整个课件任务在加载显式 UNC 配置前退出。先用 GetDriveTypeW 排除网络盘，再读取配置或验证本地目录。
