# Windows 本地视频与 PPT

原有 main.py、AI、邮件及前端功能保留；新增入口不触发邮件或调用大模型。

本地入口默认直连 WebVPN，不继承 HTTP_PROXY/HTTPS_PROXY；需要代理时显式指定 `--proxy http://127.0.0.1:7897`。这只影响此程序，不修改系统配置。

在本目录运行（首次需要学号和密码，密码仅在内存中）：

```powershell
..\.venv\Scripts\python.exe local_replay.py add "https://icourse.fudan.edu.cn/coursedetail?course_id=37113&tenant_code=222"
..\.venv\Scripts\python.exe local_replay.py list
..\.venv\Scripts\python.exe local_replay.py download 37113 --lesson 653729
..\.venv\Scripts\python.exe local_replay.py download 37113
..\.venv\Scripts\python.exe local_replay.py serve 37113 --lesson 653729
```

输出为 `local-data/课程编号/课次编号/`：视频、PPT 图片、timeline.json、index.html。运行 `serve` 后打开程序显示的本机地址；它支持视频随机读取，因此点击 PPT 可立即跳转，视频播放也会自动切页。服务默认只监听 `127.0.0.1`，不对局域网开放。PPT 时间来自平台，缺少时间的项不会被猜测对齐。重复图片保留不同出现时间。

视频下载中断后重复命令续传；服务器必须提供匹配的版本标识和 Range 响应，否则停止以免混合不同视频。课程库与下载状态保存在 local-data/library.sqlite3。

已真实验收一节完整视频、断点续传、34 个 PPT 时间事件与浏览器跳转。上游完整 AI 流程仍需 requirements.txt 中的依赖、ffmpeg、模型以及个人 API/邮箱配置，不能把下载入口可用等同于整套系统已部署完成。
