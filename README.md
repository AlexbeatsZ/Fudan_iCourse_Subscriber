# iCourse Subscriber V2

自动监控复旦大学 iCourse 智慧教学平台的课程更新，对新课次录播执行**语音转文字 + PPT OCR**，将加密的课程数据保存在你自己仓库的 `data` 分支，并通过 GitHub Pages 浏览。

部署在 GitHub Actions 上定时运行，无需自建服务器。**当前主工作流已停用自动 AI 摘要和 SMTP 邮件发送**；相关历史模块仍保留在仓库中。

> [!NOTE]
> 本项目严禁大规模传播（例如，不准分享到树洞、班级群、大群等地），否则信息办可能随时ban掉该项目。
> 如果该项目对你有用，请点个**star**⭐作为对作者的鼓励，并将项目**单独**分享给你的好朋友。


## 它能做什么？

假设你选了「摸鱼学导论」和「躺平学原理」两门课。在每天设定的时间，iCourse Subscriber 会自动：

1. 登录你的复旦 iCourse 账号（通过 WebVPN）
2. 检查这两门课是否有新的录播视频
3. 如果有：提取音频 → 语音识别 → 提取 PPT 图片 → OCR 转写
4. 加密分片数据库，更新你 Fork 仓库中的 `data` 分支，供网页查看


## 首次部署（Fork 用户必读）

### 第 1 步：Fork 本仓库

点击页面右上角的 **Fork** 按钮，将仓库复制到你的 GitHub 账号下。

进入 Fork 仓库的 **Actions** 标签，先启用 GitHub Actions。Fork 默认不自动运行工作流。

### 第 2 步：配置你自己的 Secrets

进入你 Fork 后的仓库，点击 **Settings → Secrets and variables → Actions → New repository secret**，逐个添加以下 Secret：

| Secret 名称 | 必填 | 说明 | 示例 |
|---|---|---|---|
| `STUID` | ✅ | 复旦学号 | `22307110000` |
| `UISPSW` | ✅ | UIS 统一身份认证密码 | `your_password` |
| `DB_PASSWORD` | ⬜ | **独立数据库密码**；设置后不再依靠学号和 UIS 密码加密数据库 | 随机强密码（不要公开） |
| `DB_PASSWORD_PREVIOUS` | ⬜ | 仅修改已有独立密码时临时配置旧密码，迁移后删除 | 旧数据库密码 |
| `DASHSCOPE_API_KEY` | ⬜ | 保留给可选摘要模块 | `ms-xxxxxxxx` |
| `DEEPSEEK_API_KEY` | ⬜ | 保留给可选摘要模块 | `sk-xxxxxxxx` |
| `GEMINI_API_KEY` | ⬜ | 保留给可选摘要模块 | `AIza...` |
| `SMTP_EMAIL` | ⬜ | 保留给单独的导出/邮件功能 | `123456@qq.com` |
| `SMTP_PASSWORD` | ⬜ | SMTP 授权码，不是邮箱登录密码 | `abcdefghijklmnop` |
| `RECEIVER_EMAIL` | ⬜ | 导出工作流的接收邮箱 | `you@example.com` |
| `SMTP_HOST` | ⬜ | SMTP SSL 服务器（默认 QQ） | `smtp.gmail.com` |
| `SMTP_PORT` | ⬜ | SMTP SSL 端口 | `465` |

**只有 `STUID` 和 `UISPSW` 两项必填。** 当前 ASR + OCR 主流程不需要 LLM API Key 或 SMTP。**`COURSE_IDS` Secret 已弃用**：订阅列表保存在当前 Fork 的公开 `data/subscriptions.json`，而不是存入 Secrets。GitHub Actions 会自动使用当前 Fork 自己的仓库名。

独立密码建议使用密码管理器生成的长随机密码。GitHub 的 `data` 分支是公开的加密数据；密码过弱有离线猜解风险。

### 第 3 步：首次启动（自动创建 data 分支）

只需要先在自己的 Fork 中配置 `STUID`、`UISPSW`（建议另外设置 `DB_PASSWORD`），**不需要提前知道课程 ID，也不需要创建 `data` 分支**。

进入 **Actions → iCourse Check → Run workflow**，正常运行一次。工作流会在查询课程之前，自动创建一个与 `main` 独立的 `data` 分支，并写入：

```json
{
  "course_ids": []
}
```

没有课程时，检查任务会成功结束，不会启动耗时的 ASR/OCR，也不会要求数据库预先存在。随后直接在 GitHub 切换到自己仓库的 `data` 分支，编辑 `data/subscriptions.json`，填入课程 ID；下一次定时或手动运行 **iCourse Check** 就会抓取并创建加密数据库。**首次只有配置文件，没有加密数据库，因此网页查看器要等第一次实际抓取成功后才能连接。**

也可以直接运行 **Single Run**：第一次填写课程 ID 时，工作流会自动将它们作为初始订阅；第一次留空则只创建空的 `data` 分支。若 `data` 已存在，Single Run 填写的课程仅用于本次运行，不会覆盖已有的公开订阅清单。

如果是刚 Fork 的仓库，GitHub 可能默认禁用 Actions，需要先进入 Actions 页面启用工作流。自动创建分支需要工作流成功取得 `contents: write` 权限；若出现 403，请检查仓库 **Settings → Actions → General → Workflow permissions** 的写入授权或组织策略。

### 第 4 步：获取并添加课程 ID

登录 [iCourse 网页版](https://icourse.fudan.edu.cn)，进入你要监控的课程页面，URL 中的数字就是课程 ID：

![课程id如图所示](docs/courseid.png)

在自己仓库的 `data` 分支编辑 `data/subscriptions.json`，把课程 ID 写在 `course_ids` 数组中，例如：`["35472", "30251", "40123"]`。课程 ID 不属于秘密信息，会明文保存在 `data` 分支。

### 可选：获取 API Key（当前自动摘要功能未启用）

选择一个或多个模型服务商：

| 服务商 | 获取方式 | 免费额度 |
|---|---|---|
| **ModelScope**（`DASHSCOPE_API_KEY`） | [API 密钥管理](https://modelscope.cn/my/myaccesstoken) | 每天 2000 次免费调用，推荐 |
| **DeepSeek**（`DEEPSEEK_API_KEY`） | [DeepSeek Platform](https://platform.deepseek.com/) | 注册赠额度 |
| **Gemini**（`GEMINI_API_KEY`） | [Google AI Studio](https://aistudio.google.com/) | flash模型每日免费额度 |

### 可选：配置邮件 SMTP（当前自动发信功能未启用）

- **QQ 邮箱**：保持默认 `smtp.qq.com:465`，在账户与安全设置中开启 SMTP 服务，将授权码填入 `SMTP_PASSWORD`。
- **Gmail**：设置 `SMTP_HOST=smtp.gmail.com`、`SMTP_PORT=465`，开启两步验证并将 Google 应用专用密码填入 `SMTP_PASSWORD`。

### 第 5 步：开始抓取

- **首次运行**：完成第 3 步自动创建 `data`、并在第 4 步填写课程后，再运行一次 **iCourse Check**，或者直接在首次 **Single Run** 里填写课程 ID。
- **确认初始化**：第一次抓取成功后，`data` 分支将同时包含 `data/icourse-index.enc`、加密分片和 `data/subscriptions.json`。
- **定时检查**：默认北京时间 06:00、12:00、18:00、24:00；也可手动运行 **iCourse Check**

首次实际抓取会处理有权限访问的已有录播，后续只处理新增课次。空订阅时，工作流初始化 `data` 后直接跳过抓取；以后可以通过网页的**订阅编辑器**添加或移除课程，点击「保存订阅到 data 分支」即可；不会修改 GitHub Secrets。单次运行仍可以通过输入课程 ID 临时处理别的课程，不改变已存在的定时订阅。

旧用户升级时，如果 `data/subscriptions.json` 尚不存在，工作流会优先从原有加密数据库的 `subscribed_course_ids` 元数据迁移并保存它。因此可以在确认迁移成功后删除旧 `COURSE_IDS` Secret。如果旧数据库没有记录订阅清单，请通过网页订阅编辑器保存一次，或者首次在 Single Run 中输入课程 ID。

### 第 6 步：部署与连接网页

进入 **Settings → Pages → Source → GitHub Actions**，再触发 **Deploy Frontend** 工作流。访问你自己的 `https://用户名.github.io/Fudan_iCourse_Subscriber/`，检查 Repo Owner 是否为你的账号。

网页的 Connect 不是复旦 UIS 在线登录，而是**解密你自己的 `data` 分支**。首次连接必须先完成上面的初始化；设置了 `DB_PASSWORD` 时，只需填写该密码和用于 GitHub API 的 PAT，学号/UIS 密码可以留空。不设置独立密码时，沿用学号和 UIS 密码解密。

网页不会将凭据长期保存在 localStorage；凭据仅在当前浏览器标签页会话保留，IndexedDB 仅缓存加密数据。

### 已有数据库更换为独立密码

1. 在仓库 Actions Secrets 新增 `DB_PASSWORD`，不要删除 `STUID` / `UISPSW`（学校登录仍需要它们）。
2. 手动运行一次 **iCourse Check**（不要选择 `probe_only`）；程序会用旧学号密码读取原数据库，并用新密码重加密推送到 `data`。
3. 工作流成功后，刷新网页，改用新的 `DB_PASSWORD` 连接。
4. 日后更换已有独立密码时，先将旧密码放在 `DB_PASSWORD_PREVIOUS`，新密码放在 `DB_PASSWORD`，重复运行；成功后删除 `DB_PASSWORD_PREVIOUS`。

**注意：** 如果旧密码丢失且无法使用旧学号/UIS 密码解密，程序不会清空旧数据库，而会失败并提示错误，以免数据意外丢失。本地 Windows 下载器若要解密云端字幕数据库，也需设置相同的 `DB_PASSWORD` 环境变量。

## 前端页面（索引与查看）

![alt text](docs/frontend.png)

本项目自带一个浏览器端加密数据库查看器，部署在 GitHub Pages：

访问 `https://你的用户名.github.io/Fudan_iCourse_Subscriber/`

功能介绍：
- **浏览器端解密**：使用独立数据库密码（可选）或旧学号密码方案，浏览器用 WebCrypto 解密 sql.js 读取 shard 数据库
- **按课程/课次浏览**：查看每节课的转录和摘要内容
- **导出 PDF**：通过 GitHub Actions 触发导出工作流，生成格式化课程笔记 PDF 并邮件发送

> 注意：仓库里的加密数据属于各个 Fork 自己的 `data` 分支。进入原作者的 GitHub Pages，无法使用你的密码查看你自己 Fork 中的数据。

> [!TIP]
>
> ## V2 更新说明
>
> - 重构了代码架构，清晰的分层化设计。
>
> - 更新了 ASR 系统，引入插件化后端机制，目前支持 SenseVoice（默认）、FireRed 与 Zipformer 三种后端，并新增统一的跨后端后处理流程。
>
> - 引入了 PPT OCR 流水线和清洗机制，通过 PPT 信息引导模型生成更丰富的课程总结。
>
> - 引入新的调度系统，以改善 GitHub Actions 低核数环境下的吞吐与稳定性。
>
> - 更新了数据库结构，从原本的单文件数据库演进为按课程约 10MB 的分片结构，支持前端增量加载与按需读取，降低课程加载开销。
>
> - 新增 GitHub Pages 前端查看器，支持加密数据库浏览、订阅编辑器与 PDF 导出等功能。
>
> - 更新了 LLM 调度逻辑，将原本的单一 provider 调用改为多 provider 列表式自动回退机制。
>
> - 设计了完善的版本过渡机制，V1 可以直接升级为 V2，程序会自动处理所有兼容性问题。


> [!CAUTION]
> **⚠️ 合规使用声明**
>
> 本项目的设计初衷仅为辅助本校学生进行**个人的日常学习与复习**与进行技术交流。程序采用"封闭容器、流式处理、阅后即焚"的架构，默认不保存任何视频文件。任何人在部署和使用本项目时，必须严格遵守《复旦大学智慧教学资源平台使用规范》及相关校纪校规。**严禁使用者利用本程序进行以下违规操作，一切因滥用导致的账号封禁或纪律处分（如通报批评、限制平台权限等），均由使用者自行承担，与本仓库及作者无关：**
>
> * **严禁二次分发与传播**：《规范》第二部分明确指出，平台教学资源属于职务作品，未经许可不得传播。**禁止**将推送到你邮箱的课程摘要、转录文本或笔记转发给他人，或发布到任何公共网络平台。
> * **严禁修改代码非法下载视频**：《规范》严禁未经许可对平台资源进行复制和下载。基于此，本项目并不留存视频，**严禁**任何人修改源代码将受版权保护的课程录播违规下载、保存到任何本地或云端存储介质。
> * **严禁解密或泄露数据库**：仓库中的 `icourse.db.enc` 仅用于程序追踪课次进度避免重复计算。**严禁**手动解密该数据库以提取、滥用或公开其中的转录和摘要文本信息。
> * **注意账号环境安全**：本程序会使用你的 UIS 凭证进行云端 WebVPN 自动化登录，有触发异地登录风控的可能。请妥善保管个人 Secret，因使用云端自动化服务导致的账号异常风险由使用者自行评估。
>
> **当你 Fork 并配置 Secret 运行本项目时，即代表你已知晓上述风险，并承诺仅在授权范围内为个人学习目的使用本工具，遵守相关校纪校规。**


---

## 技术说明

> 以下部分是对本项目技术细节和设计的讨论，欢迎感兴趣的技术读者阅读。

### 调度器：CPU 反馈闭环

OCR 和 ASR 是两个 CPU-bound 工作负载，在 4 核 GitHub Actions runner 上需要共享算力。RapidOCR 每处理一页 PPT 图片约需 1 秒，保持单核 100% 占用；sherpa-onnx ASR 使用 4 线程 ONNX 推理，需要多核。ASR 的优先级高于 OCR——转录延迟会导致音频流中断。

动态信号量：标准库 BoundedSemaphore 不支持在运行时调整并发上限。DynamicSemaphore 在线程安全的基础上增加了 `set_target(n)` 方法，允许在运行时调高/调低并发目标。正在执行的 worker 不受影响（自然结束后不再补充），等待中的 worker 在 target 上调时被唤醒。

资源监控：ResourceMonitor 每秒采样 `psutil.cpu_percent()`，执行迟滞判断（hysteresis control）：当 CPU > 95% 且 target 尚未到达下限时递减 OCR 并发；当 CPU < 75% 且 target 尚未到达上限时递增。双阈值（95%/75%）制造了一个 20% 宽的死区（deadband），避免系统在单个阈值附近震荡。这套逻辑本质上是一个 bang-bang 控制器。

```mermaid
flowchart TB
    subgraph Pools["并发池"]
        IP["图片下载池<br>20 workers (IO-bound)"]
        OP["OCR 池<br>8 workers (CPU-bound)"]
        AP["音频下载<br>BoundedSemaphore(2)"]
    end

    subgraph Control["控制层"]
        RM["ResourceMonitor<br>每秒采样 CPU%"]
        DS["DynamicSemaphore<br>当前 target: 1-2"]
    end

    subgraph Signal["ASR 阶段信号"]
        SA["set_asr_active(True/False)"]
    end

    RM -->|CPU > 95% ↓| DS
    RM -->|CPU < 75% ↑| DS
    SA -->|限制上限| DS
    DS -->|门控| OP

    style Control fill:#fff0f0,stroke:#d03030
```

OCR_MAX_TARGET 设为 2 而非 8 的原因是：实际运行数据表明，RapidOCR 在 4 核机器上从未超过 2 个并发 worker——其余核心被 ASR 的 4 线程 ONNX 推理占满。更高的 target 仅导致 ResourceMonitor 频繁调整目标值，对吞吐无贡献。

ASR 阶段通过 `set_asr_active(True/False)` 向调度器主动声明状态。这是一个简单的布尔标志位，不需要细粒度的上下文切换，因为 ASR 和 OCR 是两个完全独立的阶段——ASR 运行时没有 OCR 依赖，反之亦然。

音频下载器使用 `BoundedSemaphore(2)` 限制并发 ffmpeg 数量。2 是理论最小值：当前转录课次需要一路，预取课次需要另一路。在 runner 的网络带宽下，两路 ffmpeg 公平共享带宽，各获得约 10 MB/s，远高于 ASR 消费速率。

### 语音识别：后处理优于更好的模型

该模块经历了 SenseVoice → FireRed → SenseVoice 的三次选择。FireRed 的转录文本更"干净"（纯中文 + 英文，无跨语种污染），但 SenseVoice 的实时倍率约 25x，FireRed 仅约 6x。在 348 节课的批量场景中，FireRed 的 ASR 总时长为 2h41m，SenseVoice 降至约 37m。当将两种模型的输出分别输入 DeepSeek-V4-Pro 生成摘要时，LLM 的摘要质量差异不显著——LLM 自动忽略了 SenseVoice 混入的日语假名和韩语谚文。

最终选择 SenseVoice 并附加后处理。后处理函数在每条 ASR segment 加入 segments 列表前执行多级清洗：删除日语假名和平假名/片假名 Unicode 区块、删除韩语谚文 Unicode 区块、删除英文 filler word 白名单（yeah, okay, uh, um, hmm 等）、删除 `<sil>` 和 `<|zh|>` 等 bracket token。技术英文（CNN, YOLO, Transformer）通过 `\b` 单词边界匹配不受影响。

每条清洗规则都经过 7 节课 × 5 门课的真实 OCR 数据验证。选择保留"well"——"well-defined"、"well-known"在技术英文中合法。

VAD 参数调优：Silero VAD 的默认 `min_silence_duration=0.25s` 在课堂场景中将老师的换气、翻页、停顿都切分为独立片段。每个片段需要一次 ASR decode，且 SenseVoice 在短片段（2-3s）上的语言检测倾向于误判为日语（因为缺乏上下文）。将参数调至 0.8s，并将 `max_speech_duration` 设为 30.0s（匹配 SenseVoice 训练感受野）。片段数量减少约 60%，日语误判率大幅下降。

### PPT 流水线：计算成本驱动的去重策略

iCourse 录播系统每 20-30 秒截取桌面截图。90 分钟课程产生约 200-300 张图片，其中大量是同一张幻灯片的重复截图。直接 OCR 全部图片将浪费大量计算时间和 LLM prompt token 预算。

去重采用两阶段策略：先以 dHash 感知哈希做粗筛，再以 OCR 文本分类做精筛。dHash 的计算成本约每张几毫秒，而 OCR 约每张 1 秒——因此在 OCR 之前执行。

```mermaid
flowchart LR
    A["PPT 图片"] --> B["dHash 感知哈希<br>每张 ~5ms"]
    B --> C["滑动窗口去重<br>窗口=5, 阈值=2bit"]
    C -->|丢弃 50-80%| D["OCR 识别<br>每张 ~1s"]
    C -->|保留| D
    D --> E["invalid 页面检测<br>特征子串匹配"]
    E -->|噪声屏| F["丢弃"]
    E -->|合法内容| G["UI 噪声清洗<br>停用词按行匹配"]
    G --> H["送入 LLM prompt"]

    style B fill:#e8f5e9
    style D fill:#fff9c4
```

滑动窗口去重有一个关键实现细节：已丢弃的页面不成为锚点。防止级联效应——如果第 1 页与第 3 页相似（第 3 页被丢弃），第 2 页与第 4 页相似但第 1 页与第 4 页无关，我们不希望第 1 页引发第 3 页被丢弃后，第 3 页又作为锚点引发第 4 页被丢弃。

OCR 之后执行 invalid 页面检测：通过特征子串匹配（约 20 条模式，如"请不要关闭设备""cfdfudaneducn""智慧教学资源平台使用规范"）识别教室桌面壁纸和 iCourse 资源平台启动页。归一化去掉所有非字母数字字符以容忍 OCR 轻微变异。

PPT 功能区 UI 噪声清洗：PowerPoint 功能区标签（"文件""开始""插入""设计"……）每次截图都被 OCR 识别，占用了 8-18% 的 LLM prompt token。清洗采用按行精确匹配策略，而非子串匹配——例如"选择"在功能区是按钮，在生物学"自然选择"中是正常文本。功能区标签在截图中独占一行，而同一词汇出现在课程内容中时周围有其他文字。100+ 条停用词在 7 节课 × 5 门课数据中零误删。

### 数据库持久化：三环境兼容的加密 + 内容寻址分片

GitHub Actions 每次在全新容器中运行，无法依赖本地文件系统持久化。解决方案是独立的 `data` 分支，每次运行结束时加密推送数据库，下次运行时拉取解密。

AES-256-CBC + PBKDF2 加密方案需要在三种环境中同时兼容：GitHub Actions shell（openssl CLI）、Python（pycryptodome 库）、浏览器前端（Web Crypto API）。`crypto_box.py` 和 `frontend/js/crypto.js` 保持精确对应——相同的 Salted__ 头部格式、相同的 PBKDF2 迭代次数、相同的 AES-256-CBC 模式。密钥由 `sha256("ICSv2:" + stuid + ":" + uispsw)` 派生。

分片的动机是增量传输。数据库约 20MB，通过 GitHub API 完整拉取会显著增加前端加载时间。按课程分组切割为 ~10MB 的 shard，每个独立加密。前端使用 git blob SHA 作为缓存键存储于 IndexedDB，未变化的 shard 自动跳过网络下载、解密、解压。

并发合并策略：两个 workflow 可能并行执行并同时写入数据库。`merge_db.py` 采用 field-level COALESCE——非空覆盖空、版本号取 MAX、错误字段在成功处理后清零。此策略是 CRDT（Conflict-Free Replicated Data Type）的简化版本，不能解决所有冲突（例如两个 workflow 对同一字段的并发写入），但在实际场景中，同一 lecture 不会被两个 workflow 同时处理，因此冲突概率足够低。

Schema 迁移：新增列时，旧的 shard 与新的 schema 之间存在列数不匹配的兼容性问题。`_migrate_shard_schema()` 在 INSERT 之前对每个 attached shard 执行 PRAGMA table_info 差集检查并通过 ALTER TABLE ADD COLUMN 补齐，将 schema 迁移与 shard 管理解耦。

### 前端：在静态页面中解密远程数据库

前端是运行在 GitHub Pages 上的纯静态单页应用，无后端服务器。它通过 GitHub raw API 拉取位于 `data` 分支的加密 shard，在浏览器中使用 Web Crypto API 解密，并利用 sql.js（SQLite WebAssembly 编译）在内存中构建数据库。

解密凭证（STUID + UISPSW）通过 PBKDF2 派生密钥，不经过网络传输，在浏览器本地内存中完成解密。

订阅编辑器直接读写当前 Fork 的 `data/subscriptions.json`。列表可读取、可修改，且即使未产生新录播，新增的课程也会在下一次定时巡检中被检查。旧版本的加密数据库元数据只作为一次性迁移来源；浏览器不再依赖 localStorage 猜测 Secret 的当前内容。由于后台更新数据库时会重建数据分支，发布脚本会在推送前读取并保留最新的订阅 JSON，并检查分支版本以防覆盖同时发生的网页编辑。

### 技术方法总结

- **控制理论**：ResourceMonitor 的双阈值迟滞比较器（deadband control），防止在单个阈值附近震荡。
- **排队论**：DynamicSemaphore 的可调整并发池，系统过载时减少服务窗口，负载下降后恢复。不影响正在服务的 worker，只影响等待队列。
- **CRDT 思想**：merge_db.py 的 field-level COALESCE，最终一致的并发合并策略。
- **内容寻址存储**：前端以 git blob SHA 为 shard 缓存键，相同内容产生相同 SHA 的特性直接复用。
