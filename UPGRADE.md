# 从 0.3.1 升级至 0.3.4

## 变更

分发包不再内置本机 dataDir。通过“资料目录”保存的路径优先于插件 config.dataDir，持久化于 DSH_HOME/deep-reading-settings.json，未设置 DSH_HOME 时使用 ~/.dsh。模型请求继承当前默认模型与推理强度；未显式 maxTokens 时使用宿主提供商默认上限。SQLite 和工作区格式保持兼容。

## 迁移

1. 确认没有活动或排队任务，备份旧包、桌面 profile 配置和资料库。保留旧目录内容。
2. 安装前在机器设置文件中保存原 dataDir，以及已有 runtime.json 中的 python、ocrRoot、ocrPython；或在自己的 profile 中显式配置原 dataDir，首次启动会保存机器设置。不要把个人路径加回通用包。
3. 使用 dsh plugin --profile desktop add file:<本地0.3.4包绝对路径> 安装，再重启桌面应用。若旧版后台占用插件目录，先正常退出对应桌面/Web 实例；不要终止不明 Python 进程。
4. 打开“文献研究 → 资料目录”，核对实际路径与原主题。切换目录只启用所选库，不搬迁资料；空目录创建新库。有任务时先结束任务。
5. 回退时关闭当前实例，重新安装备份的 0.3.1 包并恢复备份的 profile 配置；原库保持原位。本机有独立的 backup-before-0.3.2 备份目录。0.3.1 不读取新的机器设置文件，必须保留它原先使用的 dataDir。
