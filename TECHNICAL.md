# dsh-deep-reading 技术说明

当前插件版本为 **0.3.11**。本轮已使用安装版 DeepSeek Harness **0.2.2-rc.5** 检查消息构造、附件引用、真实 Cordis 注入、目录事务和卸载；产品版本取安装目录 `resources/runtime/primary-runtime/runtime.json` 的 `desktopVersion`。历史验证见 `verification/desktop-0.3.4.md`，本次结果见 `verification/visual-cards-0.3.11.md`。

## 组件与职责

| 组件 | 职责 |
| --- | --- |
| `index.js` | 注册宿主路由、技能和设置入口，拥有资料目录切换及服务替换过程 |
| `service.js` | 拥有 Python 子进程、就绪等待、模型轮询、取消监控与关闭 |
| `bridge.js` | 构造宿主消息，接入图片附件，收集可见输出和真实 usage |
| `panel-proxy.js` | 校验宿主 admission，代理业务请求，隔离 Cookie 与内部后台令牌 |
| `client.js` | 复用宿主 React、slot 和 locale，提供外层插件设置及同源工作台 iframe |
| `scripts/server.py` | 资料库、单 worker 队列、模型交接、HTTP 接口和实例锁 |
| `scripts/pdf_source.py` | 用 PyMuPDF 读取原始页、词框和页面图片 |
| `scripts/pdf_cards.py` | 文本选段、批量/合并制卡、题录快照、编辑及 Markdown 导出 |
| `scripts/pdf_visual.py` | 核验框选、保存裁剪 PNG、图片识别及识别缓存 |
| `scripts/note_files.py` | 生成笔记文件、复制图片、维护保存目录和外部编辑冲突记录 |
| `web/pdf.*`、`web/card.*` | PDF 阅读、标记、制卡、识别结果和独立卡片预览编辑页 |

插件不修改 Harness 的 `packages/` 或 `app.asar`，不启动旧 Web 项目、不增加 API Key 输入页面，也不安装 OCR 模型或 PyTorch。旧项目的卡片提示词和导出思路按其 Apache-2.0 许可复用，归属见 `THIRD_PARTY.md`。

## 宿主集成与访问控制

插件声明 `skills`、`llm`、`agentDefaultModel`、`directoryPicker` 和 `attachments` 注入。每次模型请求读取宿主当前默认选择，显式插件配置仍可覆盖 provider、model、reasoningEffort 和 maxTokens；未显式设置 maxTokens 时由宿主提供商决定上限。原生目录选择使用 `directoryPicker.capability().kind === 'native'` 的 `pick(signal)`；其他宿主可手工填写路径。

主工作台通过同源 `/deep-reading/` 加载。Node 首先执行 `connection.admit(req)`，随后只代理明确的静态资源与 `/api/*`。它不转发浏览器 Cookie，也不开放 `/bridge/*`。Python 内部令牌只由 Node 注入；模型轮询与服务管理使用该令牌访问随机 loopback 端口。POST 请求在 Node 中按实际字节数收集、限制为 100 MiB，并设置准确的 Content-Length，兼容缺少长度头的分块请求；GET 不转发请求体。

“查看原文”先打开同源 PDF iframe。“在浏览器打开”创建单文献临时连接，令牌放在 URL 片段，页面读取后转存 sessionStorage 并清理地址栏。该令牌与内部令牌不同，有效期 8 小时，最多保留 64 个，随后台退出失效。受限请求只允许当前 entry_id 的 PDF、标记、卡片和视觉结果接口，POST 也检查文献归属；它不能访问任意文件、全库状态、其他论文、目录设置或内部 bridge。没有 CORS 放行。

页面保持同源 CSP。Markdown 预览复用离线 Markdown/nh3 清理；公式用本地 KaTeX、`trust:false` 和 MathML 输出，不增加内联脚本或放宽 CSP。KaTeX 路由只接受明确的脚本、样式和字体文件名。

## PDF 文字、标记与框选

PyMuPDF 逐页渲染原始页面并返回词框，浏览器在图片上叠加可选文字层。页图和词框按文件时间戳及渲染参数有限缓存，不长期保留 PDF 句柄。缩放只改变显示尺寸；来源位置以 PDF 物理页和归一化坐标保存，原 PDF 只读。

文字选区记录物理页、词序号及首尾字符位置，后端重新读取词框，重建引文、前后文、矩形和实际文件 SHA256。单段最多 20 个连续页面、20000 字符，不使用 Markdown 字符偏移替代 PDF 位置。原生 PDF 文字顺序可能影响多栏选择，需要用户核对；无文字层的扫描页可以通过框选视觉识别处理。

标记位于 `workspace/annotations/<entry_id>.json`，使用 workspace 锁与原子替换，类型、颜色、页码、区域和长度在写入时检查。新高亮保存文件哈希和词/字符位置，备注修改保留这些字段；旧高亮制卡必须同时满足唯一文字匹配和区域覆盖。新框选保存当前文件哈希；没有历史哈希的旧框选按当前 PDF 区域创建识别来源，须对照原图核对。

框选松开后仅形成草稿，点击“保存框选”才写入标记。Esc、取消按钮、工具切换、pointercancel、lostpointercapture 和拖动中 blur 清除临时区域，后续 pointerup 不会保存已取消的框。保存中禁止重复提交，失败时保留草稿；成功后返回选择工具。已保存框可用右上角 × 或侧栏按钮删除。

## 文字制卡与合并

选择工具的文字选区稳定 1 秒后自动提交，拖动中不触发；Esc 和关闭自动制卡可以取消待提交选段。高亮列表支持勾选、全选与取消全选，`generation_mode` 为 `separate` 或 `combined`，默认分别生成，单批最多 200 条。

分别生成逐条返回任务或错误，成功项取消勾选。合并生成先核验全部条目，任一失败都不创建合并任务；成功时只创建一个任务。`selection_parts` 保留独立选段，允许同页多个区域及不相邻页面，按原文位置排序并去除完全相同的选段，合计正文不超过 20000 字符。合并层不放宽单选段校验，也不把间隔原文拼成连续引文。

`selection_key` 唯一约束与 mutex 使重复提交复用原任务；合并与分别制卡使用不同的键，可以同时保留。模型输出验证标题、摘要、2–6 个短标签以及核心观点、依据/证据、阅读笔记、启发或用途四节正文。卡片保存生成时的题录快照；旧卡片读取时补充当前题录并注明来源，首次编辑保存为 `legacy_backfill`，不编造缺失题录。

## 框选视觉识别

框选按 PDF 实际哈希、物理页和规范化区域建立稳定标识，每个区域渲染为 `workspace/visuals/<sha256>.png`。裁剪上限为单边 4096 像素、总计 800 万像素；这些文件是 PDF 原始页面的渲染裁剪，不是重新绘制的框架图。

每个区域先识别一次，再按分别/合并模式生成卡片。识别 JSON 保存 kind、Markdown、uncertainties、原图哈希、位置和 `machine_unverified` 状态。提示要求公式使用 LaTeX，表格保留表头、单位、行列及 Markdown 结构，图形说明节点与箭头，无法辨认处明确标注。所有原始裁剪图均保留，识别结果不能当作已逐字确认的论文引文。

Store.model_call 将图片字节写入 calls.payload。Node 解析当前模型一次，必须确认 `resolveModelInfo().inputModalities` 包含 image，再通过 `ctx.attachments.saveImages()` 保存真实附件引用，附到最后一条 user 消息。纯文本模型会收到明确失败，避免宿主图片占位逻辑产生伪识别结果。认证、路由、推理强度和 usage 沿用原模型桥接。

识别结果逐区保存，制卡失败或任务重试会复用已完成识别；合并卡片保留全部区域及图片。识别前、缓存前及最终写卡前检查取消和文件哈希；来源变化时拒绝继续，取消后的迟到识别不进入缓存。原图读取要求识别记录属于当前文献，并校验内容哈希。

## 卡片预览与文件保存

“预览卡片”打开专用卡片页，可在阅读页内展示，也可使用同篇受限连接另开窗口。页面提供标题、摘要、标签、Markdown 正文编辑和预览，展示题录、物理页、来源哈希、选段上下文、识别结果及原图。保存携带 `expected_updated`，拒绝旧窗口覆盖新修改；未保存关闭有提醒。父页只接受同源且来源为指定 iframe 的状态消息。导出只使用已保存内容。

所有 PDF 卡片自动写入默认 `home/card-notes/card-<id>.md`，图片写入其 `images/` 子目录，使用 `![[./images/<sha256>.png]]` 相对嵌入。文件含题录、来源版本、哈希、页码、位置、原文、上下文及识别不确定项。卡片在插件中编辑后更新文件；外部编辑不会自动导回数据库。

“插件设置 → 卡片笔记保存目录”支持原生选择器和绝对路径。目录配置属于当前资料库，重启保留；更换目录要求没有运行或排队任务，成功复制现有卡片及图片后才启用新位置，旧目录保留。设置中提供重新同步入口。

SQLite 是卡片主记录。文件写入使用稳定文件名、图片内容哈希和原子替换，记录每个保存位置上次生成的内容哈希；外部改动或未知同名文件会阻止覆盖。新卡片文件同步失败时保留主记录与识别缓存，任务显式失败；重试只补写文件。编辑时同步失败仍保留数据库修改，并在接口、卡片列表及设置中显示错误。

## 数据存储与恢复

| 位置或表 | 内容 |
| --- | --- |
| `topics.sqlite3`：topics、topic_documents、tasks、calls | 主题、关联、队列、模型交接及真实响应 |
| `pdf_cards_meta`、`pdf_cards` | 卡片数据版本、唯一选段键、来源和正文 payload |
| `pdf_visuals` | 逐区识别缓存、位置、原图和不确定项 |
| `card_note_settings`、`card_note_files` | 笔记目录、已生成文件哈希和同步错误 |
| `workspace/annotations/`、`workspace/visuals/` | 标记 JSON 与原始裁剪 PNG |
| `workspace/` 其余目录 | 统一文献、附件、提示词覆盖、检查点与研究产物 |

SQLite 主 `user_version` 保持 1，PDF 卡片独立版本为 1，新增功能使用附加表和可选 payload 字段。首次添加卡片表前保存 `backups/before-pdf-cards.sqlite3`；本机升级另保留版本对应的源码、配置和数据库备份。ZIP 备份包含资料库内表及 workspace；选择在资料库外保存的 Markdown 文件是派生副本，可从数据库和原始裁剪图重新同步。恢复到新目录后应检查笔记保存位置，避免误用旧机器路径。

## 生命周期、取消与目录事务

每个 ReadingService 拥有独立子进程、令牌、描述符、定时器和 AbortController。`ctx.effect()` 返回 async disposer：卸载先停止入口与模型工作，再请求 Python 正常关闭并等待进程退出；超时仅清理本实例拥有的进程树，Windows 包含 venv 启动器子进程。旧实例只清理令牌仍匹配自己的 connection.json，不操作新实例资源。

Python 单 worker 为每次执行建立持续有效的取消 Event；立即续办不清除旧执行信号。模型交接使用 lease，取消使旧调用 abandoned，迟到响应拒绝写入。重启将未完成任务标为 interrupted，保留已完成检查点；未知 usage 保留为空，不填零。插件直接使用 ctx.llm，不创建聊天 Session，也不把用量声称为桌面聊天统计。

资料目录选择优先于 config.dataDir，持久化在 DSH_HOME/deep-reading-settings.json。切换先验证绝对路径、实例占用、数据库完整性和版本、工作区格式及可写性，再在 mutex 下确认无任务和活动 worker，停止旧后台、启动新后台并持久化设置。失败时恢复旧后台，恢复也失败则显示实际错误。切换不搬迁、合并或删除旧资料，业务 Python/OCR 机器设置继续复用。

## 本机安装与版本管理

桌面自带 `resources/runtime/cli/bin/dsh.cmd` 使用安装版运行时、内置 pnpm 和 desktop profile 管理权限；普通 npm CLI 仍拒绝该保留 profile。更新前结束活动任务并退出桌面，避免 Python 当前工作目录占用插件路径。也可通过插件自身正常关闭接口确认后台退出，再安装；不终止不明 Python 进程，不手工覆盖 node_modules。

```powershell
& 'D:\Program Files\DeepSeekharness\resources\runtime\cli\bin\dsh.cmd' plugin --profile desktop add file:D:/code/dsh-deep-reading/dsh-deep-reading-0.3.11.tgz
```

安装后重启桌面、重新打开 PDF，并核对安装版本与关键源码哈希。Git 仓库保留源码、测试和文档；本地 tgz、日志、数据库、连接令牌、论文和生成笔记不提交。源码可通过 `npm pack` 生成安装包，包清单限制于声明的运行文件和上游资源。

## 验证及限制

0.3.11 的 Python 回归为 71 项，Node 回归为 17 项；最后的笔记文件并发防护修改另以 18 项相关 Python 检查验证。安装版 rc.5 的实际消息构造器验证保留图片引用，真实 Cordis 控制器覆盖附件注入、笔记目录设置/同步、忙碌拒绝、目录切换、回滚、重载和卸载。浏览器脚本通过语法检查，图片清单、Markdown 结构及本地 MathML 输出已检查。

本机已安装 0.3.11，16 个关键文件与当时源码一致；已有 5 张 PDF 卡片补写为 Markdown，0 条同步错误。识别结果测试使用受控 JSON，没有调用真实图片模型；本轮界面与真实公式、表格、框架图识别效果由用户验收。接口通过、插件 active 或文件存在不能代替识别准确性和界面验收。逐版本记录位于 `verification/`，升级行为见 `UPGRADE.md`。
