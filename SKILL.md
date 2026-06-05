---
name: agent-fleet-pro
description: "多Agent并行任务编排引擎。仅在 /agent-fleet-pro 命令时触发。"
---

# Agent Fleet Pro — 多 Agent 并行编排

**仅在用户明确输入 `/agent-fleet-pro` 时触发。**

## 目录约定

两个目录，职责分离：

| 目录 | 值 | 用途 |
|---|---|---|
| `FLEET_DIR` | **固定**: `D:\clauld_code_work\.fleet\` | 管道数据（日志/报告/状态），Dashboard 读 |
| `CODE_DIR` | **动态**: 当前 Claude Code 会话的工作目录 | agent 写代码到这里 |

`FLEET_DIR` 只设一次，和 Dashboard 一起部署。`CODE_DIR` 随你开 Claude Code 的目录自动变化。

Dashboard: `python D:\clauld_code_work\agent-fleet-pro\run.py` → http://localhost:8765

---

## 速查卡片

```
1. 分析 → Phase 0 总是执行，扫代码结构 + 写分析报告
2. 拆分 → Agent 拆成 code/test/accept → 写 plan.json / status.json / roles/*.md
   {新建项目: CODE_DIR = workspace/<RUN_ID>/，改动已有: CODE_DIR = 当前目录}
3. 编码 → Agent(bg) x N 并发 → 检查: output.log>=5行 + [思考][分析][行动][结果]各>=1 + result.md
4. 测试 → Agent(bg) → 读 test-report.md → 失败？通知 coder → 回到 3
5. 验收 → Agent(bg) → 读 acceptance-report.md → 不通过+round<5？回到 3
6. 汇总 → Agent(bg) → FINAL_REPORT.md → 检查 6 项质量

铁律: 编排器不写代码/不测试/不验收 | 每阶段独立Agent | 每阶段完执行 ls 验证文件 | 占位符全替换
```

---

---

## 代码目录规则

**新建项目**：代码产到 `CODE_DIR/workspace/<run-id>/` 下，不污染当前工作区。
**改动已有项目**：代码直接写到 `CODE_DIR`（当前工作区）。

判断标准：任务是否包含「改/修/优化/重构」等词 → 改动已有项目；否则 → 新建项目。

## 执行流程

```
/agent-fleet-pro <任务>
        │
Phase 0: 需求分析（每次都做）
    扫代码结构 + 生成分析报告 → analysis/requirement-analysis.md
        │
Phase 1: 任务拆分 + 初始化
    基于分析报告拆分 → plan.json / status.json / progress.log / roles/*.md
        │
Phase 2: 并行编码 → Agent(background) × N
Phase 3: 并行测试 → Agent(background) × M → 失败则通知 coder 回到 Phase 2
Phase 4: 验收 → Agent(background) → 不通过则回到 Phase 2 → 最多 5 轮
Phase 5: 强制结束（达到上限）
Phase 6: 汇总 → FINAL_REPORT.md
```

## Phase 0: 需求分析（每次都执行）

**不再判断输入类型。每次 /agent-fleet-pro 都要做分析。**

如果是 URL 或文件路径：先读取文档内容。


1. **读取需求文档**（如果有）：
   - URL → 用 WebFetch 读取网页内容
   - .md/.txt 文件 → 用 Read 读取本地文件

2. **分析项目**（每次都做）：
   - 用 Glob 了解当前工作区结构（`ls` 或 `dir`）
   - 判断是新建项目还是改动已有项目
   - 新建项目 → 确定技术栈和文件结构
   - 改动已有项目 → 识别关键模块和依赖

3. **启动分析 Agent**（每次都做，哪怕是纯文本任务）：
```
你是需求分析师。分析以下任务并输出分析报告。

## 任务
{用户输入}

## 当前工作区结构
{项目结构概览}

## 项目类型
{新建项目 或 改动已有项目}

输出分析报告（用中文）：

## 需求分析报告

### 任务概述
- 要做什么

### 项目类型
- 新建 / 改动已有

### 代码输出目录
{如果是新建项目：CODE_DIR/workspace/<RUN_ID>/}
{如果是改动已有项目：CODE_DIR（当前目录）}

### 技术方案
- 推荐技术栈
- 文件结构规划

### 建议
- 推荐拆成几个编码任务
- 各任务负责范围
```

4. 保存到 `<RUN_DIR>/analysis/requirement-analysis.md`

5. Phase 1 拆分时引用分析报告

---

## Phase 1: 拆分 + 初始化

1. 创建目录（**RUN_ID 不能为空，否则会产生 run-/ 僵尸目录**）:
   ```
   RUN_ID = run-YYYYMMDD-HHMMSS（当前本地时间，如 run-20260605-143000）
   echo "RUN_ID=$RUN_ID"  # 确认不为空
   
   FLEET_DIR = D:\clauld_code_work\.fleet\    (固定，Dashboard 读这里)
   RUN_DIR   = <FLEET_DIR>/<RUN_ID>/
   ROLES_DIR = <RUN_DIR>/roles/
   
   # 代码目录：新建项目 vs 改动已有
   如果是新建项目: CODE_DIR = 当前工作目录/workspace/<RUN_ID>/
   如果是改动已有: CODE_DIR = 当前工作目录
   ```

   **防僵尸目录**：mkdir 之后立刻 `ls <FLEET_DIR>/run-/`，存在则 `rm -rf`。

2. 用 Agent 拆分任务：
```
你是任务拆分专家。将以下任务拆分为 code/test/acceptance 三类。

任务: <用户输入>

{如果有 Phase 0 的分析报告，追加:}
## 需求分析报告
{分析报告内容}
基于以上分析报告拆分。

返回 JSON（只返回 JSON）：
{
  "summary": "概述",
  "acceptance_criteria": ["可验证标准1", "标准2"],
  "tasks": [
    {"id": "coder-01", "type": "code", "name": "模块", "responsibility": "负责什么", "expected_files": [], "depends_on": []},
    {"id": "tester-01", "type": "test", "name": "测试", "responsibility": "测什么", "expected_files": [], "depends_on": ["coder-01"]},
    {"id": "acceptor-01", "type": "acceptance", "name": "验收", "responsibility": "逐项验收", "expected_files": [], "depends_on": ["tester-01"]}
  ]
}
```

3. 写角色文件 `<RUN_DIR>/roles/<id>.md`，**占位符必须替换为实际值**：
   - code: "你是 {name}，负责 {responsibility}。只写代码不写测试。所有输出用中文。\n代码目录: <CODE_DIR> (新建项目需先 mkdir)\n管道目录: <RUN_DIR>/{id}/"
   - test: "你是 {name}，负责 {responsibility}。必须实际运行测试粘贴真实输出。测试报告用中文。不修改实现代码。\n代码目录: <CODE_DIR> (新建项目需先 mkdir)\n管道目录: <RUN_DIR>/{id}/"
   - acceptance: "你是验收员。\n验收标准:\n1. {实际标准1}\n2. {实际标准2}\n...\n逐项检查必须实际运行。报告用中文。\n代码目录: <CODE_DIR> (新建项目需先 mkdir)\n管道目录: <RUN_DIR>/{id}/"

4. 写 plan.json（flat tasks 数组，每条含 id/type/name/depends_on）

5. 写 status.json：
```json
{
  "run_id": "<RUN_ID>", "task": "<任务>", "status": "executing", "phase": "coding",
  "started_at": "<ISO时间>",
  "phases": {"init": {"start": "<ISO>", "end": "<ISO>"}, "coding": {"start": "<ISO>", "end": null}, "testing": {"start": null, "end": null}, "acceptance": {"start": null, "end": null}},
  "round": {"coding": 1, "testing": 0, "acceptance": 0},
  "max_acceptance_rounds": 5,
  "agents": {"<每个id>": {"role": "...", "status": "pending", "round": 0}},
  "progress": {"done": 0, "total": <N>, "by_type": {"code": 0, "test": 0, "acceptance": 0}}
}
```

6. 写 progress.log

### 阶段关卡：必须执行验证命令，不能跳过

每个阶段完成后，**立即执行 Bash 命令验证文件存在**。这是硬步骤，不能凭感觉判断。

**Phase 2 完成后执行：**
```bash
# 列出所有 coder 目录下的产出（prompt.md 也应存在）
ls <RUN_DIR>/coder-*/{prompt.md,output.log,result.md} 2>&1
# 期望：每个 coder 都有这三个文件。有缺失 → 立即重派该 coder
```

**Phase 3 完成后执行：**
```bash
ls <RUN_DIR>/tester-*/{prompt.md,output.log,test-report.md} 2>&1
# 期望：每个 tester 都有这三个文件。有缺失 → 立即重派该 tester
```

**Phase 4 完成后执行：**
```bash
ls <RUN_DIR>/acceptor-*/{prompt.md,output.log,acceptance-report.md} 2>&1
# 期望：acceptor 有这三个文件。有缺失 → 立即重派 acceptor
```

**Phase 6 完成后执行：**
```bash
ls -la <RUN_DIR>/FINAL_REPORT.md
# 期望：文件存在且 >500 bytes
```

**验证 FAIL 的标准处理：**
```
1. 把缺失文件的 agent id 记下来
2. 重派该 agent，prompt 里加：「上次你缺少 xxx 文件，这次必须产出」
3. 再次执行验证命令
4. 同一个 agent 最多重试 2 次，2 次都 fail → 标记 failed，继续流程（不阻塞其他 agent）
```

## Phase 2: 并行编码

1. 找出 `type=code` 且 depends_on 全满足的就绪任务
2. **存档 prompt.md（不可跳过）**：每个 agent 派发前，先用 Write 工具把完整 prompt 写入 `<RUN_DIR>/<id>/prompt.md`。派发后 Agent 返回时执行 `ls <RUN_DIR>/<id>/prompt.md` 确认存在。
3. 并发 `Agent(run_in_background=true)` × N

Prompt 模板：
```
## 所有输出必须使用中文！必须实时写 output.log！
格式: [开始] [思考] [分析] [行动] [结果] [决定] [完成]
output.log 少于 5 行 = 失败！

{角色文件内容}

## 当前: 第 {round} 轮编码
{第1轮} 按角色职责完成初始实现。
{修复轮} 上一轮测试/验收发现了你的代码有以下问题，请修复：
（粘贴 test-report.md 或 acceptance-report.md 中指向你的失败项和修复建议）
注意：只修复你的问题，不要动其他模块。

## 代码目录: <CODE_DIR>
  {新建项目 → 需先 mkdir，改动已有 → 直接修改}
## 管道目录（日志/报告）: <RUN_DIR>/{id}/

## 执行步骤
1. 创建 <RUN_DIR>/{id}/ 目录
2. output.log: [开始] 第{round}轮: {id}
3. 分析需求 -> [思考] -> [分析]
4. 写代码，每步写 [行动] 和 [结果]
5. 写入 result.md
6. output.log: [完成] 第{round}轮: {id}
```

4. `TaskOutput` 等待完成。检查 output.log < 5 行 → 日志不合格

## Phase 3: 并行测试

1. 找出 `type=test` 且 depends_on 全满足的就绪任务
2. **存档 prompt.md（不可跳过）**：每个 tester 派发前，先用 Write 工具把完整 prompt 写入 `<RUN_DIR>/<id>/prompt.md`。Agent 返回后 `ls` 确认存在。
3. 并发 Agent(background)

Prompt 模板：
```
## 所有输出必须使用中文！必须实时写 output.log！
格式: [开始] [思考] [分析] [行动] [结果] [决定] [完成]
output.log 少于 5 行 = 失败！

{角色文件内容}

## 当前: 第 {round} 轮测试

## 依赖的编码模块
你必须先读取以下文件了解接口，否则不知道该怎么测：
- <RUN_DIR>/coder-01/result.md
- <RUN_DIR>/coder-02/result.md
（列出所有 depends_on 中 coder 的 result.md 完整路径）

{第1轮} 编写测试并运行。
{后续轮} 上一轮测试有 N 个失败，相关 coder 已修复。重新运行全部测试确认。
上次失败的用例和修复建议：（粘贴 test-report.md 中的失败详情）

## 代码目录: <CODE_DIR>
  {新建项目 → 需先 mkdir，改动已有 → 直接修改}
## 管道目录（日志/报告）: <RUN_DIR>/{id}/

## 执行步骤
1. 创建 <RUN_DIR>/{id}/ 目录
2. output.log: [开始] 第{round}轮: {id}
3. 读依赖模块代码了解接口 → [思考] [分析]
4. 编写测试代码 → [行动]
5. 运行测试 → [结果] 粘贴真实输出！
6. 写入 test-report.md（测试用例表、通过/失败、失败分析）
7. output.log: [完成] 第{round}轮: {id}
```

3. 用 `TaskOutput` 等待完成。检查 output.log < 5 行 → 不合格。
4. 主 agent 读 test-report.md：
   - 全部通过 → Phase 4
   - 有失败 → 通知对应 coder（传入失败详情+修复建议）→ 回到 Phase 2

## Phase 4: 验收（必须启动独立 Agent，编排器不得自己验收）

1. **第一步：存档 prompt.md（不可跳过）**
   ```bash
   # 先创建目录，再用 Write 工具写入 prompt.md
   mkdir -p <RUN_DIR>/acceptor-01/
   Write: <RUN_DIR>/acceptor-01/prompt.md   ← 把下面的 prompt 模板填好写进去
   ```

2. **第二步：启动验收 Agent**（`run_in_background: true`），编排器自己不能验收

3. **第三步：验证** — Agent 返回后执行 `ls <RUN_DIR>/acceptor-01/prompt.md`，文件不存在 → 重新存档

Prompt 模板：
```
## 所有输出必须使用中文！必须实时写 output.log！
格式: [开始] [思考] [分析] [行动] [结果] [决定] [完成]
output.log 少于 5 行 = 失败！

{角色文件内容}

## 当前: 第 {round} 轮验收（最多 5 轮）

## 验收标准（必须逐条检查）
（此处列出 plan.json 中的 acceptance_criteria 完整列表）

## 编码产出
先读取以下文件了解实现：
- <RUN_DIR>/coder-01/result.md
- <RUN_DIR>/coder-02/result.md
（列出所有 coder 的 result.md 完整路径）

## 测试报告
先读取以下文件了解测试结果：
- <RUN_DIR>/tester-01/test-report.md
（列出所有 tester 的 test-report.md 完整路径）

{第1轮} 这是第一轮验收。
{后续轮} 上一轮验收不通过项和修复建议：
（粘贴 acceptance-report.md 中的不通过项表格）
相关 agent 已完成修复，请重新逐条验收。

## 代码目录: <CODE_DIR>
  {新建项目 → 需先 mkdir，改动已有 → 直接修改}
## 管道目录（日志/报告）: <RUN_DIR>/{id}/

## 执行步骤
1. 创建 <RUN_DIR>/{id}/ 目录
2. output.log: [开始] 第{round}轮验收: {id}
3. 阅读编码产出和测试报告 → [思考] [分析]
4. 逐项对照验收标准检查 → 每项写 [行动] 和 [结果]
5. 必须实际运行项目！→ [结果] 粘贴运行输出
6. 写入 acceptance-report.md（逐条 ✅/❌ + 证据 + 修复建议）
7. output.log: [完成] 第{round}轮验收: {id}
```

3. 用 `TaskOutput` 等待完成。检查 output.log < 5 行 → 不合格。
4. 主 agent 读报告：
   - 通过 → Phase 6
   - 不通过 + round < 5 → 通知 agent 修复 → round++ → Phase 2 → Phase 3 → Phase 4
   - 不通过 + round >= 5 → Phase 5

## Phase 5: 强制结束

status.json → `force_stopped`，追加 progress.log，进入 Phase 6。

## Phase 6: 汇总（必须启动独立 Agent，编排器不得自己写报告）

**前置检查**：确认 `acceptance-report.md` 存在，否则回到 Phase 4。

**必须**启动独立的汇总 Agent（`run_in_background: true`）。编排器自己不能写报告。

Prompt 模板：
```
你是项目汇总专家。请读取所有 agent 产出，生成完整的执行报告。

你必须先读取以下所有文件：
- <RUN_DIR>/plan.json
{各 coder 的 result.md 路径列表}
{各 tester 的 test-report.md 路径列表}
- <RUN_DIR>/acceptor-01/acceptance-report.md
{如果有 Phase 0 的分析报告}
- <RUN_DIR>/analysis/requirement-analysis.md

生成 FINAL_REPORT.md，写入 <RUN_DIR>/FINAL_REPORT.md。

## 报告必须包含以下全部 7 个章节（缺一不可）：

### 1. 基本信息
- 任务描述、Run ID、开始/结束时间、最终状态（通过/未通过）

### 2. 需求分析摘要（如有分析报告）
- 需求概述、影响范围

### 3. 执行统计
- 编码轮次、测试轮次、验收轮次、总 Agent 调用次数、总耗时

### 4. 各 Agent 产出表
| Agent | 角色 | 轮次 | 产出文件 |

### 5. 验收结果
- 验收标准逐条检查结果、最终判定、通过/不通过数量

### 6. 产出文件清单
- 所有创建/修改的文件完整路径

### 7. 如何运行
- 启动命令、如何测试、环境依赖

### 已知问题（如有）
```

## 报告质量检查（编排器必须逐项验证）

Agent 返回后，读取 FINAL_REPORT.md，检查以下 6 项：

- [ ] 包含 `## 基本信息` 或 `### 1. 基本信息` 章节
- [ ] 包含 `执行统计` 或 `### 3. 执行统计` 章节（含数字，不是占位符）
- [ ] 包含 `验收结果` 或 `### 5. 验收结果` 章节
- [ ] 包含 `产出文件清单` 或 `### 6. 产出文件清单` 章节
- [ ] 包含 `如何运行` 或 `### 7. 如何运行` 章节（含具体命令，不是空话）
- [ ] 总字数 ≥ 500

**任何一项不通过 → 重新调用汇总 Agent**，prompt 里注明上次缺少了哪个章节。

status.json → `done`，追加 progress.log。

## 铁律：编排器不得自己干活

**编排器（你，当前 Claude Code 会话）只做四件事**：
1. 拆分任务
2. 派发 Agent
3. 读结果、做决策
4. 生成汇总报告

**你绝对不能**：
- ❌ 自己写代码（那是 coder 的工作）
- ❌ 自己跑测试（那是 tester 的工作）
- ❌ 自己验收（那是 acceptor 的工作）
- ❌ 跳过某个阶段直接写报告

**每个阶段必须启动独立的 Agent（`run_in_background: true`）**，Agent 返回后检查产出文件是否存在。文件不存在 = 阶段无效 = 不能进入下一阶段。

缺少 acceptance-report.md 就直接生成 FINAL_REPORT.md = **严重违规**。

---

## 质量保障（每个 Agent 派发时必须遵守）

### 派发前：Prompt 完整性检查

发送给 agent 的 prompt **必须逐条确认**，缺一条就不能发：

- [ ] 包含日志强制指令：`## 所有输出必须使用中文！必须实时写 output.log！`
- [ ] 包含日志格式：`[开始] [思考] [分析] [行动] [结果] [决定] [完成]`
- [ ] 包含失败后果：`output.log 少于 5 行 = 失败！`
- [ ] 包含角色文件内容（从 roles/{id}.md 读取）
- [ ] 包含当前轮次信息
- [ ] 包含明确的产出文件名（result.md / test-report.md / acceptance-report.md）
- [ ] 所有 `{占位符}` 已替换为实际值（文件路径、验收标准、失败详情等）
- [ ] 包含具体的文件路径（不是变量名，是完整路径）
- [ ] 修复轮时，包含上一轮的**完整失败信息和修复建议**（不是一句话概括）

**反例（会被拒绝的 prompt）：**
```
你是 tester，去测一下。
```
**正例（合格的 prompt）：**
```
## 所有输出必须使用中文！必须实时写 output.log！
格式: [开始] [思考] [分析] [行动] [结果] [决定] [完成]
output.log 少于 5 行 = 失败！

# Role: 登录功能测试
...
## 依赖的编码模块
你必须先读取以下文件：
- .fleet/run-xxx/coder-01/result.md
- .fleet/run-xxx/coder-02/result.md
...
```

### 完成后：产出物检查

agent 返回后，主 agent **必须**逐一验证：

| 检查项 | coder | tester | acceptor | 修复轮 |
|---|---|---|---|---|
| output.log 存在 | ✅ | ✅ | ✅ | ✅ |
| output.log ≥ 5 行 | ✅ | ✅ | ✅ | ✅ |
| 含 ≥1 条 [思考] | ✅ | ✅ | ✅ | ✅ |
| 含 ≥1 条 [分析] | ✅ | ✅ | ✅ | ✅ |
| 含 ≥1 条 [行动] | ✅ | ✅ | ✅ | ✅ |
| 含 ≥1 条 [结果] | ✅ | ✅ | ✅ | ✅ |
| 含 [完成] | ✅ | ✅ | ✅ | ✅ |
| result.md 存在 | ✅ | - | - | ✅ |
| test-report.md 存在 | - | ✅ | - | - |
| acceptance-report.md 存在 | - | - | ✅ | - |

**任何一项不通过 → 立即重试该 agent**。修复轮 agent 同样必须产出 result.md。

### 日志不合格的标准处理

如果 output.log 只有 `[开始]` 和 `[完成]` 两行（没有思考/分析/行动）：

```
你上次的 output.log 只有开始和结束标记，中间没有任何思考过程。
这次必须每做一件事就写一行日志！格式: [思考] → [分析] → [行动] → [结果]
如果还是没有中间日志，你的工作会被再次拒绝。
```

---

## 超时监控

主 agent 每 60-90s 检查后台 agent：
1. `TaskOutput(task_id, block=true, timeout=90000)`
2. 超时 → 读 output.log，行数增长否？
3. 行数不变 → 卡住 → 读日志判断 → 重试或跳过
4. 单个 agent 最多等 5 分钟

## 耗时记录

每个阶段进入/退出时更新 status.json.phases 时间戳。进入 Phase 6 时写 finished_at。

## 运行 Dashboard

```bash
python D:\clauld_code_work\agent-fleet-pro\run.py
```

## 示例

```
/agent-fleet-pro 做一个待办事项应用，Vue3 + Flask
/agent-fleet-pro 写一个Python爬虫
```
