# 桌面 0.3.4 修复验收

日期：2026-11-18。目标宿主：安装版 DeepSeek Harness 0.2.2-rc.3；插件本地修复版 0.3.4。源码、安装包与桌面安装文件哈希已核对。宿主源码没有修改，没有 Git 提交、推送或远程发布。

## 用户可见结果

“文献研究”顶部新增“资料目录”和“重试连接”。用户在真实桌面原生目录选择器中选中了中文与空格目录，保存后界面、机器设置和后台一致；后续重启继续读取同一目录。取消、无效目录、忙碌任务、失败恢复由真实安装版 Cordis 集成回归验证。

当前实际目录：`D:\code\deepseek-harness-runtime\plugin-repair\桌面 验证库`。这是独立测试库，保留 12 篇论文、单篇精读成果和 Wiki 候选，方便检查结果。原正式目录仍为 `D:\code\deepseek-harness-runtime\data\deep-reading`，未搬迁、合并或删除；可通过资料目录按钮切回。保留测试库是为了交付验证结果。

机器设置文件：`C:\Users\langx\.dsh\deep-reading-settings.json`。业务 Python 与 OCR 路径从旧库保留，空库仍获得同一机器配置。本次没有下载或修改 OCR、PyTorch、模型和 Python 环境。

## 真实文献验证

输入目录为用户指定的“生态产品价值实现文献补全”。12 篇 PDF 均有文字层，本次使用 pymupdf，自动题录整理通过真实桌面 `ctx.llm`，使用宿主当时默认的 `deepseek-account/deepseek-flash`。12 篇正文非空且题录已产生，原始 13 个文件 SHA256 全部未变。

另有 1 个 0 字节 TXT，后台明确报告“Unsupported bibliography format; expected native CNKI/WoS text”。批量任务因此显示 failed，12 篇有效 PDF 的已完成结果保留；它不是一篇未能读出的有效论文。没有重试空文件或把它计为成功。

精读与 Wiki 只选择同一篇：生态产品价值实现收益分配的模式选择、制约要素与政策优化——基于长三角地区典型实例的考察。题录抽查的作者杨博文、2026 年、第 2 期、53–65 页及 DOI `10.19563/j.cnki.sdzs.2026.02.006` 与 PDF 首页一致。未对另外 11 篇的全部字段进行人工逐项校对。

精读完成理论框架、识别策略、变量度量 3 个维度；30 条引文中定位 26 条，剩余 4 条保留待核对警告。质量状态为 `requires_source_and_user_review`，不声称所有模型解释已证实。

Wiki 完成 3/3 个正文分段，保存 37 条研究使用记录、135 处证据，39 处记录了仅空白差异的原始模型引文。已逐条验证保存的正文证据与实际源文本区间及 SHA256 一致。候选保持待核对状态，没有替用户批准学术结论。

Wiki 首次真实测试分别暴露 PDF 空白差异和跨页脚注拼接问题，前者仅在唯一匹配时恢复实际原文，后者进入一次严格校验修正阶段；改写、位置歧义和无法支持的引文继续拒绝。最终桌面续办完成。先前失败调用保留在同一任务的交接记录中。

任务记录共有 21 次返回真实 usage 的模型请求，未知用量 0 次。Node → calls.response → NativeClient → 精读步骤保存链路已检查，任务 API 返回 model_calls。插件用量独立保存，不伪造 Session 事件，不自动计入聊天统计。

## 自动与运行时验证

- `node --test test/*.test.js`：8 项通过。
- 业务 Python 执行 `-m unittest discover -s test -p 'test_*.py'`：48 项通过。
- `verification/runtime-check.cjs`：在安装版 Electron/Node 下使用真实消息构造器，检查角色、id、source、不可变性、推理强度和继承的 token 上限。
- `verification/controller-check.cjs`：真实安装版 Cordis 校验服务注入，覆盖原生选择器调用与取消、未认证拒绝、有任务禁止切换、无效非空目录、中文空目录、已有库、保存失败恢复、恢复也失败的状态、重试、持久化重载、未 ready 卸载和等待原生选择请求取消。用受控模型等待消除忙碌检测的时间竞态。
- 服务测试覆盖空闲关闭、生成中关闭、异常退出、启动未 ready 卸载和旧实例不影响新实例；Python 覆盖取消立即续办、连续取消、失败续办、迟到响应、后续队列推进及检查点复用。
- 未知进程状态不删除遗留锁、写入权限失败不改变已有库、无效 schema 与损坏来源检查已覆盖。无权限写入由确定性的 PermissionError 回归验证，未更改系统目录 ACL。
- 代理验证继续拒绝未认证请求，工作台不能访问内部 bridge；Cookie 不转发给 Python，后台令牌没有进入浏览器或本报告。
- `node --check` 检查 index.js、service.js、client.js、panel-proxy.js，通过；`git diff --check` 通过。

## 原资料与恢复

正式库相对于安装前 SQLite 备份的逻辑导出完全一致；workspace 文件与 runtime.json 哈希一致。输入原论文全部哈希一致。旧包、原桌面 profile、数据库、workspace、runtime.json 和原源码文件保留于 `D:\code\deepseek-harness-runtime\plugin-repair\backup-before-0.3.2`。

最终安装包：`D:\code\dsh-deep-reading\dsh-deep-reading-0.3.4.tgz`，SHA256 `2ed919a29c3582646920aad002c287fcb04cdacfb2543297c2900dd1f9c1c065`。主要修改：index.js、service.js、bridge.js、client.js、panel-proxy.js、scripts/server.py、scripts/research_wiki.py 和 upstream/scripts/dra_core/native.py。README、TECHNICAL、UPGRADE 与回归测试已同步。

回退先结束任务并退出当前实例，安装备份中的 0.3.1 包，再恢复备份的 profile 配置；原正式库仍在原位置。0.3.1 不读取新的机器设置文件，使用原先 bundle 的 dataDir。详见 UPGRADE.md。

## 验证边界

本机自动点击未能可靠触发界面，原生选择、保存由用户协助完成，随后由界面状态、机器设置、真实后台与重启结果核实。没有把用户协助的步骤声称为全自动。没有重跑昂贵 OCR、完整宿主仓库测试或对所有研究任务进行模型准确率评测。

原始验收数据位于 `D:\code\deepseek-harness-runtime\plugin-repair\desktop-evidence.json`；其中没有认证 token 或 API Key。只有最终桌面实例继续运行，临时回归进程已检查退出。
