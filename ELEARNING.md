# eLearning 文件归档

入口：`elearning_sync.py`。使用项目 Python 环境，仅需要已有的 requests、pycryptodome。
账户从 `FUDAN_STUID`、`FUDAN_UISPSW` 读取；Windows 每次运行读取当前用户环境变量。

```powershell
# 查看本学期或全部往期课程
..\.venv\Scripts\python.exe elearning_sync.py courses
..\.venv\Scripts\python.exe elearning_sync.py courses --all-terms

# 选择课程（课程编号和完整课程链接均可）；--all 选择当前活跃课程
..\.venv\Scripts\python.exe elearning_sync.py select --all
..\.venv\Scripts\python.exe elearning_sync.py select --interactive
..\.venv\Scripts\python.exe elearning_sync.py select 114173 114183

# 单次同步、查看结果、一次性归档（不改变定时订阅）
..\.venv\Scripts\python.exe elearning_sync.py sync
..\.venv\Scripts\python.exe elearning_sync.py status
..\.venv\Scripts\python.exe elearning_sync.py archive 110632 108228

# 修改时间后重新安装任务
..\.venv\Scripts\python.exe elearning_sync.py select --all --times 00:00 06:00 12:00 18:00
powershell -NoProfile -ExecutionPolicy Bypass -File desktop\install-elearning-task.ps1
```

ROG 的 Python 位于仓库内 `.venv\Scripts\python.exe`。安装的 `eLearning Sync` 任务在登录用户会话中每天四次执行，错过后补跑，失败后间隔 15 分钟重试两次。`desktop/run-elearning.ps1` 保存轮转日志至 `local-data/elearning/sync.log`。

配置：`local-data/elearning/settings.json`。默认目的地 `D:\Documents\Elearning`，ROG 部署使用同一磁盘的 UNC 地址 `\\192.168.137.1\D\Documents\Elearning`，避免后台会话没有 D 盘映射。不要在两台机器同时运行针对同一目标的同步器。

每门课程一个目录，里面按平台“文件”的文件夹层级归档。非法 Windows 字符替换为下划线，同名冲突加编号。下载先写项目 `local-data/elearning/staging`，完整后复制、核对字节并发布。更新之前的内容保留到目标 `.elearning/history`；平台删除文件或取消订阅不会删除已有资料。平台锁定/隐藏的文件不下载。名字映射保持稳定；平台重命名既有文件时保留首次归档名称，移动到另一文件夹会在新位置保存，旧路径保留。

通知保存在本地 `state.sqlite3`，读取公告和收件箱不会标记已读。首次观察到的历史公告/讯息也会入队，以后按内容版本去重。`events` 可查看待发送事件。当前没有开启外发。

发送扩展：实现 `elearning.notifications.Sender.send(event)`，传给 `dispatch(db, sender)`；已有 `WebhookSender(url, token)` 可选实现。成功后标记送达，失败保留待重试，接收端用 `event.id` 去重。事件种类：`file.created`、`file.updated`、`announcement`、`message`。`Client.send_message(..., confirmed=True)` 另提供显式站内信 API，轮询和 CLI 均不调用。

接口依据：[Canvas Files/Folders](https://developerdocs.instructure.com/services/canvas/resources/files)。同步只读取当前用户有权限访问的资源。

测试：`..\.venv\Scripts\python.exe -X utf8 -m unittest test_elearning -v`。
