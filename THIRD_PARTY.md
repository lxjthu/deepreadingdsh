# 资源与来源

- `upstream/` 来自本机 `deep-reading-agent/skill-packages/deep-reading-agent` 的独立业务资源，源项目为 `lxjthu/deep-reading-agent`；遵循源项目 Apache-2.0，保留根目录 LICENSE 与上游 THIRD_PARTY.md。未复制 `.env`、本机配置、用户工作区、论文、数据库、测试缓存或虚拟环境。
- `scripts/idea_lab.py` 来自同一项目 `backend/services/research_idea_lab.py`，迁入构念、六类缺口与选题纯函数；保持证据边界。本次开始时原项目对应功能已由另一聊天提交。
- Unlimited OCR 2 及其权重不随插件分发。OCR 适配器调用用户已有本地 Transformers 环境和官方 Markdown 转换函数；其代码与模型按各自上游许可使用。
- DeepSeek Harness、Cordis 与其模型/技能服务作为宿主依赖，不复制到插件；认证与模型传输由宿主负责。
- Python 可选依赖及前端 Markdown 清理使用原独立业务包声明的依赖，不将第三方二进制随插件发布。
