# Goal
保留上游完整订阅、转写、OCR、摘要、邮件和前端功能，在 Windows 本地增加视频下载与 PPT 联动回放。

# Current State
上游完整克隆，基于 5492d55，工作分支 feat/local-replay-ppt。origin 为 AlexbeatsZ/Fudan_iCourse_Subscriber，upstream 为 LeafCreeper/Fudan_iCourse_Subscriber。local_replay.py 是新增独立入口，仍需实际下载验收。上游 main.py 未修改。个人文件存 local-data/，不提交。

已验证真实登录和课程 37113 枚举（24 节），曾收到视频分段数据，但任务退出后片段为 0 字节，不能计为下载成功。2026-09-16 重试时 WebVPN 建立会话持续超时。6 项单元测试通过。已增加原子记录写入、片段落盘、有限登录重试、损坏空片段记录恢复。

# Active Work
- 验证本地登录、完整视频下载、PPT 首中末时间对齐。
- 本地 AI/邮件尚需用户服务配置；保留功能，不主动发送邮件。
- 用户已确认本机先验证视频和 PPT，AI/邮件稍后配置，后续考虑服务器。

# Build / Run / Test
项目上一级的 uv 环境已有 requests、pycryptodome。运行 `..\.venv\Scripts\python.exe local_replay.py --help`。
完整上游依赖见 requirements.txt，新增下载入口只需 requests、pycryptodome。
测试：`..\.venv\Scripts\python.exe -m unittest test_local_replay -v`。

# Durable Lessons
平台 created_sec 是 PPT 相对视频秒数。时间 0 有效；回翻页需要保留多次时间事件，不能直接使用 OCR 去重后的集合。
