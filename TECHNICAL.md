# dsh-deep-reading 技术说明

当前修复版为 0.3.4，目标宿主为桌面运行时 0.2.2-rc.3。宿主版本读取 runtime.json 的 desktopVersion；Electron 的 version 文件不代表产品版本。

## 实现与数据所有权

index.js 注册宿主代理和技能并管理资料目录；service.js 拥有一个 Python 子进程、就绪等待、模型桥接和关闭过程。bridge.js 使用安装运行时的 createSystemMessage、createUserMessage 和 createAssistantMessage；用户消息带 source.kind=user，助手 source 由提供商、模型与构造器生成。reasoningEffort 来自当前默认选择；maxTokens 未显式配置时不传递，提供商负责默认值。

client.js 通过宿主共享 React 与 slot 注册主面板、侧栏。设置控件位于 iframe 外层，使用宿主 locale 字典和 t；主业务仍通过同源 /deep-reading/ iframe 显示。原生选择器声明 directoryPicker 注入，调用 capability().kind=native 的 pick(signal)。无需修改宿主 packages 或 app.asar。

同源控制 /deep-reading/control/* 与业务代理共用 connection.admit 的 Host/Origin 与身份校验。控制请求仅接受指定 GET/POST 和有大小上限的 JSON；后台令牌仅由 Node 注入代理请求，Cookie 不进入 Python。工作台不能访问 /bridge/*。内部模型交接仍由随机 loopback 端口的 Python 后台接收认证请求。

## 取消、续办与用量

Python 单 worker 为每次执行建立独立 Event，取消持有 mutex 设置该 Event，同时将当前调用置为 abandoned。续办仅把业务任务重新排队，不清除旧 Event。model_call 和 BridgeClient 在取回或保存结果前检查当前执行实例，旧 lease 的迟到响应被拒绝。worker 只有当前执行未取消才更新终态；旧实例退出后才领取续办任务。已有文件、精读步骤和 Wiki 分段检查点继续复用。

calls.response 保存真实模型响应与 usage，任务状态和完成结果返回 model_calls；NativeClient 保留 usage 到步骤检查点，未知值保持 null 或字段缺失。插件不伪造 Session 事件，不把任务用量声称为聊天统计。模型来源是宿主报告，未作独立提供商身份认证。

## 生命周期

清理由 ctx.effect 返回的 async disposer 执行；ctx.on('dispose') 在此安装运行时不承担资源清理。卸载先关闭入口、停止新工作、中断模型与监控，再请求 Python shutdown，等待模型流和进程 close。超时仅终止本实例拥有的进程树并等待结果；Windows 必须包含 venv 启动器的子进程。正常 Python 关闭设置 stop、终止其 OCR 子进程并 join worker。未 ready 卸载、启动失败、异常退出和重载都有明确清理路径。

每个 ReadingService 独立持有子进程、令牌、定时器和 descriptor。退出清除 base 并只删除令牌仍匹配自己的 connection.json；旧实例的事件不会访问新实例字段。启动、失败、切换、就绪、停止在外层设置栏显示。没有无上限自动恢复。

## 目录事务

设置选择优先于 config.dataDir，再次才是默认目录。机器设置位于 DSH_HOME/deep-reading-settings.json；未设置 DSH_HOME 时在 ~/.dsh。新包的 bundle patch 只插入插件，不含本机路径。本机升级前保留原路径与 Python/OCR 字段，详见 UPGRADE.md。

server.py --validate-home 在构造 Store 前验证绝对路径、文件夹、单实例占用、数据库版本与完整性、必要表字段、工作区版本和索引，并以唯一探针检查写入能力。检查不覆盖研究文件。只有 PID 已结束时才清理遗留服务锁；锁内容不完整或进程仍活跃时拒绝。格式兼容检查要求现有 user_version=1，不升级或降级其他版本。

切换时先验证候选，在后端 mutex 下确认没有运行/排队任务和活动 worker，停止接收新任务；等待旧实例退出，再验证并启动新实例、确认状态、原子保存机器设置。失败时停止候选实例并重启旧目录；旧目录恢复也失败时展示实际失败。候选空目录可能已初始化，保留供用户检查。原库不迁移、合并或删除；再次启用原库会读取已有内容。成功后 iframe 重新挂载，清除当前主题缓存和文献选择。

机器 Python/OCR 字段从旧 runtime.json 保留到机器设置，传入 Python 的环境只包含这组非凭据设置。OCR 执行使用新库 runtime.json 显式字段覆盖机器默认，切换不修改任一旧库 runtime.json。

## 验证与证据

Node 测试覆盖消息参数、代理身份校验与 bridge 隔离、进程关闭、早期卸载、异常退出和生成中关闭。Python 测试覆盖队列、取消立即续办、迟到结果、失败续办、已有检查点、Wiki 来源校验和目录格式。安装版 Electron/Node 可运行 verification/runtime-check.cjs 与 verification/controller-check.cjs：使用安装包内真实消息构造器和 Cordis，验证实际注入约束、目录事务、保存失败恢复、重载持久化和卸载等待，不以自制 Context 替代运行时。

真实桌面与用户指定论文的结果记录于 verification/desktop-0.3.4.md。已有旧 Web 验证记录保留为历史材料，不作为本次桌面验收证据。命令通过、插件 active 或文件存在均不足以证明界面、模型输出及文献精度已通过。

## 本机故障记录的解释

0.3.1 的清理事件与等待存在缺口；本次真实 Cordis 回归确认资源清理必须改用 effect disposer。旧桌面进程驻留时本地安装曾报 EPERM；退出该实例后同一安装命令成功。这能证明该次目录占用影响安装，不能据此认定所有历史 EPERM 都是同一个原因。历史关于 profile patch 必然失效、必须把本机路径放入分发包、自动计入聊天额度统计的说法已移除。

## PDF 换行与 Wiki 引文

真实 PDF 测试复现模型去掉换行与排版空格、原文保留空白时，严格子串校验拒绝引文。抽取预处理复用 dra_core.quality.locate_quote，仅接受当前分段内唯一的纯空白差异；回填原始字符区间与原文 quote，另外保存 model_quote 和 match_method=whitespace_only。之后仍执行原来的来源版本、哈希、逐字区间和页码校验。非空白改写、标点差异、歧义和错误显式位置不接受。引文匹配不验证模型解释，研究候选仍须人工确认。

Wiki 抽取的固定校验修正阶段最多追加一次带原响应与具体错误的模型请求。JSON、关系与引文继续通过同一 validate_chunk 校验，失败不写分段检查点。该阶段处理跨页脚注等非空白插入时的引文选择问题，不用模糊匹配绕过校验。
