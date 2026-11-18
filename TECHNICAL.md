# dsh-deep-reading 技术文档

> 面向后续接手或协作审阅的 agent 与维护者。记录本插件是什么、本次为接入桌面版所做的适配改动、部署方式、数据与 OCR 配置，以及已知遗留问题。

## 1. 概览

`dsh-deep-reading` 是一个 DeepSeek Harness（下称 dsh）的第三方文献研究插件。它以「按研究主题管理的文献库」为核心，提供文献精读、全文翻译、证据问答、跨文献比较、主题综述、经济管理创意实验室，以及本地 OCR（Unlimited OCR 二代）与跨论文研究 Wiki 等功能。

插件安装到 dsh 后，在**左侧栏**出现「文献研究」入口，点击后在主面板内嵌一个 Web 工作台（iframe 指向同源路由 `/deep-reading/`），所有文献管理、精读、创意实验室都在该工作台内操作。

### 1.1 关键标识

| 项 | 值 |
| --- | --- |
| 包名 | `dsh-deep-reading` |
| 版本 | `0.3.1` |
| 源码目录 | `D:\code\dsh-deep-reading` |
| git | 本地仓库，提交 `b95cfb5` |
| 目标宿主 | dsh 桌面版（Electron），运行时版本 `0.2.2-rc.3` |
| 许可证 | Apache-2.0 |

### 1.2 定位澄清

本插件**不是**官方 dsh 仓库的一部分，也**不是** `lit-review` 技能的直接产物。它最初是为 dsh `0.2.0-rc.2`（官方 npm Web 版）开发的独立插件，本次工作是把它**适配**到 dsh `0.2.2-rc.3` 桌面版。

> 注：本次会话早期还做过一个临时的 `deepreadingagent` 插件（仅 5 个简单工具 + 静态引导面板），已被 `dsh-deep-reading` 取代并卸载。不要混淆两者。

## 2. 架构

插件是「单包、三入口」结构：

```
dsh-deep-reading/
├── index.js          # 宿主入口（Node 侧）：apply(ctx, config)
├── bridge.js         # 模型消息转换 + 流式生成辅助
├── panel-proxy.js    # 同源 HTTP 反向代理（/deep-reading/ → Python 后台）
├── client.js         # 浏览器入口：__ModuleLoader__.load 注册侧栏图标 + 主面板
├── cordis.patch.yml  # bundle patch：insert 宿主行（带 dataDir config）
├── scripts/          # Python 后台（server.py + 精读/OCR/Wiki 模块）
├── upstream/         # 上游脚本、提示词、资产、技能 SKILL.md
└── web/              # 内嵌 Web 工作台前端（app.js / wiki.js / index.html）
```

### 2.1 数据流

```
dsh 宿主 (Node)
  ├─ apply(ctx, config)
  │   ├─ 读 dataDir → 读 runtime.json（OCR/Python 路径）
  │   ├─ spawn Python server.py（子进程，监听随机本地端口）
  │   ├─ 注册 /deep-reading/ 同源代理（panel-proxy.js）
  │   ├─ 注册 deep-reading-workbench 技能（ctx.skills.register）
  │   └─ 轮询 Python 后台的 /bridge/next，把模型请求转发给 dsh 的 ctx.llm
  │
  └─ Python 后台 server.py
      ├─ topics.sqlite3（主题、文献、任务、Wiki 表）
      └─ workspace/（文献原文、产物、检查点）

浏览器 (client.js)
  ├─ 侧栏图标「文献研究」→ sidebar.panellist
  └─ 主面板 iframe → /deep-reading/（同源，经 panel-proxy 转发到 Python 后台）
```

### 2.2 模型桥接

插件不直接调用外部模型 API，而是复用 dsh 的默认模型与既有认证：Python 后台把需要模型处理的任务（精读、翻译、综述等）通过 `/bridge/next` 交给宿主，宿主用 `ctx.llm.stream()` 生成，再把结果 `/bridge/respond` 回 Python 后台。这样复用 dsh 的模型路由、凭据和额度统计。

## 3. 本次适配改动

本次工作的目标是让原本面向 dsh `0.2.0-rc.2` 的插件，在 dsh `0.2.2-rc.3` 桌面版上正确激活并复用原有数据。

### 3.1 改动清单

只改了 3 个文件，均为跨版本 API 适配：

#### ① `bridge.js`（关键，不改必崩）

`@deepseek-ai/dsh-llm` 的 `createAssistantMessage` 在 0.2.2 中签名变化：`provider` / `model` 从顶层字段移入 `source` 子对象。

- 旧（0.2.0）：
  ```js
  createAssistantMessage({ content, provider: config.provider, model: config.model })
  ```
- 新（0.2.2）：
  ```js
  createAssistantMessage({ content, source: { provider: config.provider, model: config.model } })
  ```

新版 `createAssistantMessage` 的 `source` 形如 `{ kind: 'model', provider, model }`，其中 `kind: 'model'` 由函数内部补齐。

#### ② `package.json`（版本对齐）

- `engines.dsh`：`0.2.0-rc.2` → `0.2.2-rc.3`
- `peerDependencies`：
  - 移除 `@deepseek-ai/dsh-skill: 0.2.0-rc.2`、`@deepseek-ai/dsh-llm: 0.2.0-rc.2`
  - 保留并更新 `@deepseek-ai/cordis: ~4.0.4` → `4.1.0`

原因：npm 官方源上 `dsh-skill` / `dsh-llm` 最高只到 `0.1.2-alpha.5`，**不存在** `0.2.0-rc.2` 版本；这些服务由 dsh 运行时（asar 内）提供，桌面版 profile 的 `autoInstallPeers: false` 使 peer 依赖不校验 npm 版本。保留 `cordis@4.1.0` 即可满足运行时。

#### ③ `cordis.patch.yml`（dataDir 配置）

给 insert 的 `deep-reading` 行加上 `config.dataDir`，指向原 runtime 的文献数据目录：

```yaml
- insert:
    - id: deep-reading
      name: dsh-deep-reading
      config:
        dataDir: "D:/code/deepseek-harness-runtime/data/deep-reading"
```

### 3.2 关键经验教训

- **config 覆盖要写进 bundle 自己的 patch，不要靠 profile patch 覆盖。** 曾尝试在桌面版 profile 的 `cordis.patch.yml` 里用 `- id: deep-reading` 覆盖 config，结果**未生效**（插件仍走默认路径 `$DSH_HOME/deep-reading`）。改成 bundle `insert` 时直接携带 config 后一次成功。推测原因是 profile patch 对「已安装 bundle 的 row」的覆盖时机/匹配有问题（未深入排查，留待后续）。
- **卸载重装时注意残留 Python 子进程。** 插件 `apply` 会 spawn `server.py` 子进程。卸载时若子进程未及时退出，会锁住 `node_modules/dsh-deep-reading` 目录，导致重装报 `EPERM: rename` 失败。解决：先 `Stop-Process` 杀掉残留的 `server.py` 进程，再重装。

## 4. 部署方式

### 4.1 打包

在源码目录执行：

```powershell
cd D:\code\dsh-deep-reading
npm pack --ignore-scripts
```

产物：`dsh-deep-reading-0.3.1.tgz`（约 1.1 MB，含 Python 脚本与 web 资源）。

### 4.2 安装到桌面版

通过 dsh 的插件管理器（`plugin_manager`）安装本地 tarball：

```
install_bundle  target: file:D:/code/dsh-deep-reading/dsh-deep-reading-0.3.1.tgz
```

安装后插件会自动激活（`application: "applied"`），左侧栏出现「文献研究」图标。

### 4.3 卸载

```
remove_bundle  target: dsh-deep-reading
```

卸载后若需重装，先确认无残留 `server.py` 进程（见 3.2）。

## 5. 数据与 OCR 配置

### 5.1 数据目录（dataDir）

插件数据目录由 `config.dataDir` 决定，默认 `$DSH_HOME/deep-reading`（桌面版即 `C:\Users\langx\.dsh\deep-reading`）。

本次已通过 bundle patch 将 `dataDir` 固定为：

```
D:\code\deepseek-harness-runtime\data\deep-reading
```

该目录复用原 runtime 的文献数据，包含：

- `topics.sqlite3` — 主题、文献、任务、Wiki 表（核心数据库）
- `workspace/` — 文献原文、产物、检查点
- `runtime.json` — Python 与 OCR 路径配置
- `backups/` — 备份
- `connection.json` / `.service.lock` — 运行期连接描述与单实例锁

### 5.2 OCR 环境（runtime.json）

插件启动时读 `dataDir/runtime.json` 获取本机环境路径。当前内容：

```json
{
  "python": "D:/code/dsh-deep-reading-runtime/.venv/Scripts/python.exe",
  "ocrRoot": "D:/code/paddleocr",
  "ocrPython": "D:/code/paddleocr/Unlimited-OCR-env/Scripts/python.exe"
}
```

- `python`：普通业务 Python（需 3.10+，依赖 `upstream/requirements.txt`）
- `ocrRoot` / `ocrPython`：Unlimited OCR 二代环境（GPU），模型在 `D:/code/paddleocr/Unlimited-OCR-model`

OCR 路径在安装包外，不随插件分发；换机器需重新配置 `runtime.json`。

### 5.3 配置合并逻辑（index.js）

```js
const home = config.dataDir || join(process.env.DSH_HOME || homedir()/'.dsh', 'deep-reading');
const local = existsSync(home + '/runtime.json') ? JSON.parse(...) : {};
const settings = { ...local, ...config };  // config 覆盖 runtime.json
```

即：`cordis.patch.yml` 里的 config 优先级**高于** `runtime.json`。当前 config 只设了 `dataDir`，OCR 路径仍来自 `runtime.json`。

## 6. 运行时 API 依赖

插件 `apply` 声明依赖以下 dsh 服务（`inject`）：

| 服务 | 用途 |
| --- | --- |
| `skills` | 注册 `deep-reading-workbench` 技能 |
| `llm` | 模型桥接（`ctx.llm.stream`） |
| `agentDefaultModel` | 读取当前默认模型选择 |
| `webServer` | 注册 `/deep-reading/` 同源路由 |
| `connection` | 同源代理的身份校验 |

`@deepseek-ai/dsh-llm` 模块导出依赖：`createAssistantMessage`、`createSystemMessage`（经 bridge.js 使用）。

## 7. 已验证项与遗留问题

### 7.1 已验证

- 插件在 dsh 0.2.2-rc.3 桌面版正确激活（`fiberPhase: active`）
- 左侧栏出现「文献研究」图标（`sidebar.panellist` 中 id `deep-reading`，order 20）
- 主面板 `main` slot 注册成功（key `deep-reading`）
- `deep-reading-workbench` 技能注册成功
- dataDir 指向原数据目录生效（`connection.json` 写入原目录，默认目录不再被写）
- Python 后台 `server.py` 正常启动并建立连接

### 7.2 遗留问题（尚未实现）

1. **「设置按钮」未实现。** 用户曾希望有一个图形界面按钮来指定文献数据库路径。当前 `dataDir` 是写死在 bundle patch 里的，改路径需手动编辑 `cordis.patch.yml` 并重新打包。要做图形设置，需要：给插件加 `Config` schema（schemastery）+ 接入 dsh 的 `configForms`/设置 UI 机制（对纯 JS 第三方插件的完整支持路径尚未完全摸清）。**列为后续工作。**

2. **profile patch 覆盖失效的根因未定位。** 见 3.2 第一条，现象明确但根因未深挖。

3. **版本兼容边界。** 插件声明 `engines.dsh: 0.2.2-rc.3`，是精确版本匹配。dsh 升级到更高版本时需重新核对 API（尤其 `createAssistantMessage` 等 message 构造函数的签名）。

## 8. 测试

```powershell
cd D:\code\dsh-deep-reading
npm test                        # node --test test/*.test.js
python -m unittest discover -s test -p 'test_*.py'
```

## 9. 备份

原始 0.2.0 文件备份在源码目录（已被 .gitignore 排除，不进入 git）：

- `package.json.bak-0.2.0`
- `bridge.js.bak-0.2.0`
