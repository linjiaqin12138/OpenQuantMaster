# AGENTS.md

## 项目概览

面向量化场景的服务化积木库（OHLCV、Ticker、Indicator、NewsFetcher、BinancePerp、Notification 等）。优先保持分层清晰、契约可测、代码易 review；不要把一次性脚本或交易决策固化进骨架。

## 需求与变更

遵循项目 skill [`.cursor/skills/product-delivery`](.cursor/skills/product-delivery/SKILL.md)。文档语言与结构约定见 [`docs/conventions/documentation.md`](docs/conventions/documentation.md)；协作入口见 [README](README.md)。

接到改行为的任务时先判档（S/M/L）；L/M 未确认前不写业务实现。

- 现行产品：`docs/product/`（有内容后）
- 现行架构：`docs/architecture/`（有内容后）；工程分层细则仍以 [`docs/conventions/architecture.md`](docs/conventions/architecture.md) 为准
- 服务契约说明：`docs/services/`
- 非 HTTP 现行契约：`docs/contracts/current/`（有内容后）
- 变更包：`docs/changes/NNNN-slug/`（落地后 Frozen，不回写正文，也不作为现行契约入口）
- 行为流水：根目录 `CHANGELOG.md`（有内容后）

## 编码

确认可写码之后，遵循项目 skill [`.cursor/skills/layered-codebase`](.cursor/skills/layered-codebase/SKILL.md)。需要完整规则时阅读其 `references/architecture.md`、`complexity-ladder.md`、`testing.md`、`agent-rules.md`；本仓库细则见 [`docs/conventions/`](docs/conventions/)。

依赖方向：`Protocol → Service → UseCase → Provider / Repository`，只向内。Engine（可独立发布、无领域知识）放 `src/engines/<name>/`，不进 `utils/`。查询代码图用 `graphify query`（先 `graphify extract . --code-only`，不对文档跑模型）；跨层 import 由 `lint-imports` 失败，Graphify 不是门禁。

当前目标复杂度：**Level 3（含 Provider；已有 UseCase）**。升级触发条件见 [`docs/conventions/architecture.md`](docs/conventions/architecture.md) 与 layered-codebase 的 complexity ladder。出现真实持久化再引入 Repository；同一能力第二种实现再引入 Port。

最容易被违反的三条：

1. Protocol（CLI）中不写业务规则，只做协议转换并调用 Service。
2. Provider 不读配置、不选账号、不做长轮询编排；不跨 Provider 互调。
3. 不提前创建空壳层、通用 `run()` 分派，或只被使用一次的「通用」抽象。

## 环境准备

优先使用 VS Code Dev Containers 打开仓库（见 `.devcontainer/`）。本地：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

可选：复制 `config.yaml.example` / `.env.example` 以接入实盘凭证。单测默认 fake SDK，不需要真实密钥。

## 常用命令

```bash
ruff check .
lint-imports
mypy src
pytest
pytest tests/services -q
pytest -m unit
qm-cli list
qm-cli run ohlcv --symbol BTCUSDT --market crypto --interval 1h --limit 10
```

不得把 build 或 typecheck 当作行为测试。配置加载顺序：`--config PATH` → `./config.yaml` → `~/.qm/config.yaml`。

## 收尾指南（代码完成且用户 Approve 后）

代码完成并获得用户 Approve 后，按以下顺序执行。若收尾中再次改变产品行为，返回对应闸门重新确认，不用文档更新代替确认。

1. **同步契约与活文档源文件**
   - 服务对外形状变化：更新对应 `docs/services/<service>.md`。
   - 按需更新 `docs/product/`、`docs/architecture/`、`docs/contracts/current/` 与 ADR；长期模块关系变化必须进入 architecture / conventions。
   - 命令、文档入口或协作边界变化：同步 README 与本文件。
2. **验证与验收**：实际运行 `ruff check .`、`lint-imports`、`mypy src`（若已接入）、`pytest`；按变更档位完成行为测试，不能用类型检查代替行为验证。
3. **行为流水与变更寿命**：用户可见行为或对外契约变化更新 `CHANGELOG.md`，纯内部 refactor 可省略；M/L 完成验收后更新 brief 状态并 Frozen，不回写其它 Frozen 变更包正文。
4. **交付说明**：列出实际验证命令与结果、更新过的活文档及未做项；未明确获授权时不提交或推送。

## 提交规范

Conventional Commits：`<type>(<scope>): <description>`

- type：`feat` `fix` `refactor` `test` `docs` `build` `chore` `perf`
- scope：`ohlcv`、`indicator`、`protocols/cli`、`providers`、`docs` 等
- 破坏性变更加 `!`，正文说明 `BREAKING CHANGE`

不要代替用户提交，除非用户明确要求。

## 测试约定

细则见 [`docs/conventions/testing.md`](docs/conventions/testing.md)。摘要：

- Service 证业务规则；patch 具体 Provider。
- Protocol 证 CLI 参数、输出与退出码映射。
- Provider 证外部传输与响应解析；patch SDK/HTTP。
- 同一规则只设一个主要测试归属。
- 持久化用临时 SQLite 等真库路径，不 mock session 生命周期来「假装通过」。

## 目录约定

- 长期能力放入对应层源码，不堆进 `scripts/`。
- 一次性迁移或运维脚本才放 `scripts/`；不要漂在仓库根目录。
- `utils/` 不许 import 应用层；不许建 `common` / `framework` 垃圾桶。
- 机制型效应工具放 `utils/<capability>`；引擎类组件放 `src/engines/<name>/`。
- Service 文件按能力命名（如 `services/ohlcv.py`），不要 `*_service` 后缀。
- 领域 skill（如 `skills/cn-portfolio-advisor`）与工程协作 skill（`.cursor/skills/`）分开：前者描述产品操作，后者约束交付流程与分层。

## 禁区

- 新增顶层目录、引入新依赖、改变公开接口：先问再做。
- 不顺手重构、格式化全仓库或升级依赖。
- 不删除、跳过测试来让检查通过。
- 不提交凭据、token、账号；配置走环境变量 / `config.yaml`（已 gitignore）。
- 不使用模块级可变全局保存 client、缓存或「当前会话」。
- 调用会产生真实下单、划转或付费副作用的接口前，必须先展示完整参数并得到明确确认。

## 完成定义

- [ ] 用户 Approve 后已按「收尾指南」完成验证与文档收尾
- [ ] 档位与闸门符合 product-delivery（该过的已确认）
- [ ] lint、类型检查、测试均已实际运行并通过；尚未接入时明确说明
- [ ] 分层落位正确，无反向依赖或空壳层（layered-codebase）
- [ ] 新行为有测试，且测试归属不重复
- [ ] 新错误码有明确归属，并逐层映射
- [ ] 新依赖、顶层目录、公开接口变化已获确认并记录
- [ ] 架构决策写入约定位置；活文档（product/architecture/contracts/CHANGELOG/services）已按需更新
- [ ] 最终回复包含实际验证命令与结果
