# PDF 打开修复 0.3.7

日期：2026-11-19。用户确认已安装 0.3.6 后，点击查看原文出现“请求大小需小于 100 MiB”。本次检查安装副本 package.json，确认为 0.3.6；宿主仍为 0.2.2-rc.5。

## 原因与改动

Node 代理直接 pipe POST 请求，没有 Content-Length 时会以分块传输发送；Python BaseHTTPRequestHandler 只按 Content-Length 读取，将这类小请求误判为空请求，返回误导性的大小提示。新增回归在旧实现上复现同样的 HTTP 400 与错误原文。修复按收到的字节累计请求体，设置正确长度后转发，保留原有 100 MiB 上限。鉴权、Cookie 隔离和 bridge 拒绝保持原逻辑。

查看原文改为同步打开同源内嵌阅读页，不再先等待创建浏览器连接；在浏览器打开作为显式选项，保留直接链接和窗口内错误提示，避免浏览器拦截后无反馈。迟到的旧文献浏览器连接不会覆盖当前文献的链接。

## 验证

- Node 10 项通过，包括新增中文 JSON 字节长度与分块传输测试；修复前对应检查失败，修复后通过。
- 新增真实 Python 集成检查：生成并导入一页测试 PDF，经过代理发送分块 /api/pdf/session 请求，得到受限阅读连接；/pdf、/pdf.js、/pdf.css、PDF 元数据和 PNG 页面资源均返回成功。
- node --check web/app.js 与 panel-proxy.js 通过。
- Python 业务逻辑未改动，沿用上一轮 57 项通过的证据，没有重复运行整组 Python 检查。
- 安装包清单检查不得包含 PDF、数据库、connection.json、日志和 Python 缓存。

## 交付及用户测试

源码与本地包已更新；旧源码文件备份到 plugin-repair/backup-before-0.3.7。desktop profile 由新版 Electron 专管，本次不直接改写安装目录。请通过桌面插件管理器卸载旧插件并安装 file:D:/code/dsh-deep-reading/dsh-deep-reading-0.3.7.tgz。资料目录保持原位。

升级后点击查看原文应立即出现内嵌 PDF 窗口，再验证显示页面、文字选择和自动制卡。若需要默认浏览器，点击“在浏览器打开”；没有弹出时点击“打开阅读页”。界面及真实模型验收依用户要求由用户执行。
