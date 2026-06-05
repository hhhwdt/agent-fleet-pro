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
3. 编码 → Agent(bg) x N → 检查: result.md≥800B + bash代码块 + output.log≥10行
4. 测试 → Agent(bg) → 只给需求不給代码 → test-report.md≥1500B + bash代码块 + PASS/FAIL
5. 验收 → Agent(bg) → 逐条执行验收标准 → 交叉验证 tester 覆盖
6. 汇总 → Agent(bg) → FINAL_REPORT.md → 检查 6 项质量

铁律: 编排器不写代码/不测试/不验收 | 每阶段独立Agent | 内容检查替代格式检查 | 累进惩罚最多2次
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

返回 JSON（只返回 JSON）。acceptance_criteria 必须是具体用例，不是空洞描述：

{
  "summary": "概述",
  "acceptance_criteria": [
    {"id": "ac-1", "描述": "正常输入得到预期结果", "输入": "具体输入值", "期望": "具体期望输出"},
    {"id": "ac-2", "描述": "边界条件处理", "输入": "空值/0/-1", "期望": "明确的错误信息或处理方式"}
  ],
  "tasks": [

验收标准规则：
- 每条必须是「给定输入 → 期望输出」的具体用例
- 禁止: "代码没有错误" "功能正常" "满足需求" "代码可运行"
- 标准: 让一个不懂编程的人拿输入去调用、对照期望输出，就能判断过没过
    {"id": "coder-01", "type": "code", "name": "模块", "responsibility": "负责什么", "expected_files": [], "depends_on": []},
    {"id": "tester-01", "type": "test", "name": "测试", "responsibility": "测什么", "expected_files": [], "depends_on": ["coder-01"]},
    {"id": "acceptor-01", "type": "acceptance", "name": "验收", "responsibility": "逐项验收", "expected_files": [], "depends_on": ["tester-01"]}
  ]
}
```

3. 写角色文件 `<RUN_DIR>/roles/<id>.md`，**占位符必须替换为实际值**：
   - code: "你是 {name}，负责 {responsibility}。只写代码不写测试。写完必须用 Bash 实际运行，贴终端输出到 result.md。\n代码目录: <CODE_DIR> (新建项目需先 mkdir)\n管道目录: <RUN_DIR>/{id}/"
   - test: "你是 {name}，负责 {responsibility}。你只能拿到需求规格和接口签名，不能看实现代码。测试必须覆盖边界值/异常输入/组合场景。实际运行测试贴终端输出。\n代码目录: <CODE_DIR>\n管道目录: <RUN_DIR>/{id}/"
   - acceptance: "你是验收员。不信任 coder 也不信任 tester，只对验收标准负责。逐条独立运行验证，贴终端输出为证据。acceptance-report.md 末尾写 VERDICT: PASS/FAIL。\n验收标准:\n{criteria_text}\n代码目录: <CODE_DIR>\n管道目录: <RUN_DIR>/{id}/"

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
ls <RUN_DIR>/coder-*/{prompt.md,output.log,result.md} 2>&1  # 文件存在
wc -c <RUN_DIR>/coder-*/result.md | awk '$1<800{print "FAIL: too small"}'  # ≥800B
grep -c '```bash' <RUN_DIR>/coder-*/result.md | awk '$1==0{print "FAIL: no bash"}'  # 有终端输出
wc -l <RUN_DIR>/coder-*/output.log | awk '$1<10{print "FAIL: log too short"}'  # ≥10行
```

**Phase 3 完成后执行：**
```bash
ls <RUN_DIR>/tester-*/{prompt.md,output.log,test-report.md} 2>&1
wc -c <RUN_DIR>/tester-*/test-report.md | awk '$1<1500{print "FAIL: too small"}'
grep -c '```bash' <RUN_DIR>/tester-*/test-report.md | awk '$1==0{print "FAIL: no bash"}'
grep -cE 'PASS|FAIL|✅|❌' <RUN_DIR>/tester-*/test-report.md | awk '$1==0{print "FAIL: no verdict"}'
```

**Phase 4 完成后执行：**
```bash
ls <RUN_DIR>/acceptor-*/{prompt.md,output.log,acceptance-report.md} 2>&1
wc -c <RUN_DIR>/acceptor-*/acceptance-report.md | awk '$1<2000{print "FAIL: too small"}'
# 验收标准N条 → grep ✅/❌ 数量应≥N
```

**Phase 6 完成后执行：**
```bash
ls -la <RUN_DIR>/FINAL_REPORT.md  # 存在 + ≥500B
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
5. **自检（不可跳过）**：用 Bash 实际运行你写的代码
   - Python: python <入口文件>，Go: go run .，Node: node <入口文件>
   - 报错 → 修复 → 再运行 → 直到无报错
6. result.md 必须包含：
   - 文件清单
   - **自检运行结果**（```bash 代码块，粘贴真实终端输出，禁止总结）
   - 没有 bash 代码块 → 编排器直接打回
7. output.log: [完成] 第{round}轮: {id}
```

4. `TaskOutput` 等待完成。
5. 阶段关卡检查（硬性）：
   - `ls` 确认 prompt.md/output.log/result.md 都存在
   - `wc -c result.md` → < 800 bytes → 打回
   - `grep -c '```bash' result.md` → = 0 → 打回（没贴终端输出）
   - output.log < 10 行 → 打回

**累进惩罚**：每个 agent 最多重试 2 次：
- 第1次打回 → prompt 加「上次产出被打回。原因：{具体问题}。这次必须达标。」
- 第2次打回 → 「第二次被打回。最后机会。还不达标 → 标记 FAILED。」
- 第3次不达标 → 标记 failed，继续流程，不阻塞其他 agent

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

## 你能拿到的信息（只给这些）
需求描述：{任务描述}
接口签名：{从 plan.json 提取的函数/类名/方法签名}
验收标准：{逐条具体输入→期望输出}

## 你不能拿到的
- 任何 coder 的 result.md（你不知道实现内部做了什么）
- 你的测试依据是需求规格，不是实现代码

## 你必须测的
- 验收标准里每条用例 → 直接翻译成测试
- 边界值（0, -1, 空, 最大值）、异常输入（类型错误, None）、组合场景

{后续轮} 上一轮测试有 N 个失败。上次失败详情：（粘贴 test-report.md 中的失败用例）

## 代码目录: <CODE_DIR>
## 管道目录: <RUN_DIR>/{id}/

## 执行步骤
1. 创建目录
2. output.log: [开始] 第{round}轮: {id}
3. 根据需求规格设计测试用例 → [思考] [分析]
4. 编写测试代码 → [行动]
5. **实际运行测试** → [结果] 粘贴真实终端输出（```bash 代码块）
6. 写入 test-report.md：
   - 测试用例表（编号|场景|输入|期望|实际|结果）
   - 失败根因分析（不是「没通过」，是「为什么没通过」）
   - 完整终端输出（```bash 代码块）
7. output.log: [完成] 第{round}轮: {id}
```

3. `TaskOutput` 等待完成。
4. 阶段关卡（硬性）：
   - `ls` 确认 prompt.md/output.log/test-report.md 都存在
   - `wc -c test-report.md` → < 1500 bytes → 打回
   - `grep -c '```bash' test-report.md` → = 0 → 打回（没贴终端输出）
   - `grep -cE 'PASS|FAIL|✅|❌' test-report.md` → = 0 → 打回（没判定结果）
5. 读 test-report.md：全部通过 → Phase 4 / 有失败 → 通知对应 coder → 回到 Phase 2

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

## 你的立场
你不站在 coder 一边，也不站在 tester 一边。你只对下面的验收标准负责。

## 验收标准（逐条独立验证）
{逐条列出 plan.json 中的验收用例（id、描述、输入、期望）}

## 验收方式：逐条执行
对每条验收标准：
1. 拿到 coder 的代码，用 Bash 实际运行
2. 用验收标准里指定的输入去调用
3. 把实际输出和期望输出逐字对比
4. 记录：✅ 一致 或 ❌ 不一致 + 贴出实际输出

## 还要检查
- 代码能直接跑吗？（不能 → ❌）
- 有需求没要求但代码多做的功能吗？（过度实现）
- 有需求要求但代码完全没做的吗？（漏实现）
- tester 的 test-report.md 覆盖了所有验收标准吗？（对照计数：验收N条，test-report覆盖M条）

## 禁止
❌ 因为测试都通过就判通过 ❌ 跳过验收标准 ❌ 写模糊结论 ❌ 不实际运行就写验收

## 执行步骤
1. 创建目录
2. output.log: [开始] 第{round}轮验收: {id}
3. 读 coder 的 result.md 和 tester 的 test-report.md → [思考]
4. **逐条执行验收标准** → 每项 [行动] 和 [结果]
5. 写入 acceptance-report.md：
   格式: ac-N: {描述} | 输入: {值} | 期望: {值} | 实际: {终端输出} | ✅/❌
   末尾必须: VERDICT: PASS 或 VERDICT: FAIL + 通过N条/失败M条
6. output.log: [完成]

## 阶段关卡（硬性）
- `wc -c acceptance-report.md` → < 2000 bytes → 打回
- 验收标准N条，`grep -c '✅\|❌'` → < N → 打回（没逐条）

## 交叉验证（编排器在 Phase 4 后执行）
- 读 acceptance-report.md，提取所有 ❌ 条目
- 读 tester 的 test-report.md
- 如果 acceptor 发现 ≥ 2 个错误且 tester 完全没覆盖 → tester 也打回重跑
  理由：「acceptor 独立运行时发现 X 个错误，你的测试没有覆盖」

## 修复轮规则（编排器执行）
验收不通过时：
- 读 acceptance-report.md 的 ❌ 条目
- 追溯：是哪个 coder 的模块有问题？→ 只重置该 coder
- 对应的 tester 没测出来？→ 也重置
- 通过的模块不动
- 重跑时 prompt 注入：`你上一轮的问题: {粘贴 ❌ 条目和实际输出}`

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
