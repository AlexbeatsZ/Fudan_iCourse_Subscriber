# Goal
保留上游完整订阅、转写、OCR、摘要、邮件和前端功能，在 Windows 本地增加视频下载与 PPT 联动回放。

# Current State
上游完整克隆，基于 5492d55，工作分支 feat/local-replay-ppt。origin 为 AlexbeatsZ/Fudan_iCourse_Subscriber，upstream 为 LeafCreeper/Fudan_iCourse_Subscriber。local_replay.py 是已完成单节真实验收的独立入口。上游 main.py 未修改。个人文件存 local-data/，不提交。

已验证真实登录和课程 37113 枚举（24 节），课次 653729 已完整下载 1,773,490,386 字节视频并保存 34 个 PPT 时间事件和离线页面；中断后从 638,187,325 字节续传成功。serve 浏览器实测首/中/末事件跳到 0、4574、6386 秒，视频时长 6438.378833 秒。新增只监听本机且支持 Range 的 serve 命令供浏览器随机跳转。9 项单元测试通过。

# Active Work
- 仍待覆盖无 PPT、签名失效、重复图片回翻和批量多课次的真实边界验收。
- 本地 AI/邮件尚需用户服务配置；保留功能，不主动发送邮件。
- 用户已确认本机先验证视频和 PPT，AI/邮件稍后配置，后续考虑服务器。

# Build / Run / Test
项目上一级的 uv 环境已有 requests、pycryptodome。运行 `..\.venv\Scripts\python.exe local_replay.py --help`。
完整上游依赖见 requirements.txt，新增下载入口只需 requests、pycryptodome。
测试：`..\.venv\Scripts\python.exe -m unittest test_local_replay -v`。

# Durable Lessons
本机环境代理 7897 曾导致 WebVPN TLS EOF；同一 URL 用 requests trust_env=False 直连正常返回 302 登录跳转。本地入口默认直连 WebVPN，支持 --proxy 显式覆盖。不能据脚本代理失败推断用户浏览器或 WebVPN 网站不可用。
WebVPN 偶尔会在票据请求返回 HTTP 200 后仍未形成可用会话；上游主流程按 10 次重新登录处理，本地入口保持相同上限。
平台 created_sec 是 PPT 相对视频秒数。时间 0 有效；回翻页需要保留多次时间事件，不能直接使用 OCR 去重后的集合。
PPT API 可能返回已经过 WebVPN 编码的图片 URL；此时必须使用 get_raw，不能再次 get_vpn_url 编码。
