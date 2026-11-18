# 文件夹导入与文献库验证

本机插件版本：0.2.2。2026-11-16 完成安装与运行验证。

## 验证结果

- Python：`D:/code/dsh-deep-reading-runtime/.venv/Scripts/python.exe -m unittest discover -s test -p 'test_*.py'`，18 项通过。
- 插件：`npm test`，4 项通过；`node --check web/app.js` 通过。
- 行为覆盖：中文与空格目录递归扫描、原文件不变、重复内容去重、题录字段提取、PDF/Markdown 附件关联、DOI/年份冲突保留独立条目、逐文件失败与重试、固定扫描清单、模型桥接并发、自动整理失败标记、已有文件名题录再次整理、分阶段文件夹上传、HTTP 文献库读写、阅读状态、标签笔记置顶与备份恢复。
- 独立样例工作台经真实浏览器验证：目录导入后显示一个去重条目、作者、年份、期刊、摘要、关键词、附件路径及可编辑详情。
- 已通过宿主插件管理命令安装到 web profile，并启动本机服务；已安装的服务端、文献库模块、前端与来源匹配文件逐字节核对一致。
- 已在实际宿主的“文献研究”面板打开导入窗口，确认“选择整个文件夹”、本机文件或目录、PDF 解析方式及默认自动整理选项均已生效；启动错误日志为空。
- 运行检查时正式工作台保留 1 个原有主题、0 篇文献、0 个活跃任务；未向正式资料库导入样例。

## 范围与限制

参考在线 Deep Reading Agent 的 BibEntry、附件与研究时间线业务结构，在既有本地 workspace 上提供相同含义的字段；未共享或改动在线数据库。自动整理复用 dsh 已有模型桥接，测试使用模拟模型响应，本次未发生付费模型调用。原有 Unlimited OCR 二代路径保持不变，PDF/Markdown 归并测试使用文字层 PDF；未重新执行 GPU OCR 全流程。

原代码及安装配置备份保存在 `D:/code/deepseek-harness-runtime/backups/folder-library-*` 与 `folder-library-install-*`；旧版安装包保留，便于恢复。
