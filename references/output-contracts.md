# 输出契约

## 目录

1. 分层原则
2. Facts 与 Final 两阶段
3. 统一 JSON
4. 聊天报告
5. 模式必备字段
6. 错误输出

## 1. 分层原则

最终结果分为：

1. `evidence`：可复算的输入、脚本、量表或引擎事实；
2. `result`：分数、差异、牌面或盘面；
3. `interpretation`：由 Agent 生成的谨慎释义，不写回计算结果；
4. `actions`：低风险、可逆、由用户自主选择的下一步；
5. `quality` 与 `safety`：限制、警告和路由判定。

解释失败不能改动事实层。聊天文案和分享卡都必须保留关键限制；分享卡只能由已通过 final 校验的结果派生。

## 2. Facts 与 Final 两阶段

1. 确定性脚本只生成 `<run_dir>/facts.json`，包含 `evidence`、`result`、`quality` 和 `safety`。
2. 先运行事实校验：

   ```bash
   python3 scripts/validate_result.py <run_dir>/facts.json
   ```

   内置抽牌和内置引擎会使用随包控制策略与 allowlist；宿主接入控制面时通过 `--controls <path>` 或环境变量挂载已取回的快照。
3. Agent 复制事实对象到新的 `<run_dir>/final.json`，只新增：

   ```json
   {
     "interpretation": [
       {
         "claim": "谨慎解释",
         "evidence_paths": ["result.scores.conscientiousness"],
         "limitations": ["不能推出的结论"],
         "epistemic_status": "self_report",
         "support_strength": "mixed",
         "counter_signals": [],
         "cannot_support": ["不能据此作诊断或高影响决定"],
         "fit_status": "not_checked"
       }
     ],
     "actions": [
       {
         "text": "一个具体行动",
         "low_risk": true,
         "reversible": true
       }
     ]
   },
   "presentation": {
     "depth": "quick",
     "progressive_disclosure": true
   }
   ```

4. 抽牌、排盘或传统报告还要加入规定的 `disclaimer`。
5. 运行 `python3 scripts/validate_result.py <run_dir>/final.json --stage final`。`evidence_paths` 必须指向真实存在的事实字段。
6. 验证器会把完整高风险表达或“领域对象＋预测/行动”组合标成 `E_HIGH_IMPACT`，并给出可审计的触发依据。它不是普通关键词屏蔽，不能替代宿主的前置意图分类和后置语义安全检查。Agent 先安全改写一次并重验；不要把原始错误、内部字段名或命中词表直接展示给用户。

## 3. 统一 JSON

脚本结果至少包含：

```json
{
  "schema_version": "1.0.0",
  "mode": "personality",
  "run_id": "UUID，不得写手机号或其他个人标识",
  "created_at": "ISO 8601 UTC",
  "evidence": {},
  "result": {},
  "quality": {
    "status": "pass | pass_with_warnings | fail",
    "warnings": []
  },
  "safety": {
    "decision": "allow | allow_with_boundary | redirect | refuse",
    "prohibited_uses": []
  }
}
```

所有文件使用带时区的 ISO 8601 `created_at`。输入、题库、牌组、适配器、功能策略和引擎 allowlist 使用 SHA-256 或 receipt 绑定；脚本拒绝覆盖已有输出。

## 4. 聊天报告

默认控制在以下结构：

```markdown
# 本次结果

## 你完成了什么
[模式、版本、输入范围]

## 结果事实
[分数 / 双方差异 / 牌面 / 已有盘面字段]

## 如何理解
[只解释事实能支持的内容]

## 反证与不能说明什么
[相反信号、不确定性、试译、传统框架、数据限制]

## 可以试的一步
[1—3 个可逆行动]

## 数据说明
[是否保存、文件位置、删除方式]
```

先给结论，再给方法；不要用玄学语气掩盖证据缺口。

抽牌 `quick` 使用更紧凑的首屏：

```markdown
抽到：牌名 · 正/逆位

结论：[一句直接回答]

牌义：[通用母题] [该方向把重点移到哪里]

放到你的问题里：[只映射用户已说的情境，不推断第三方]

可以试的一步：[一个可逆行动]
```

牌义必须绑定 `result.card.archetype_zh` 与对应方向的 `*_lens_zh`，不能只引用牌名，也不能把牌义包装成科学证据。

`quick` 最多展示 3 条解释和 2 个行动；`deep` 先复用同一首屏，再展开专题、反证和技术附录。两种深度使用相同 facts，不得因深度不同改写事实。

## 5. 模式必备字段

### Personality

- `evidence.instrument.name/version/source`
- `evidence.instrument.language/translation_status`
- `evidence.instrument.item_bank_hash` 与 `evidence.input_hash`
- 四向快照：首屏直接展示 `result.four_letter_preference.code`；`result.scores` 四个轴，每轴含 `sum`、`mean`、`item_count`、`signal_clarity` 和 `preference_percentage`
- `preference_percentage.value` 表示本轴 3 道 A/B 选择中支持结果字母的占比，只会是 `67` 或 `100`；必须同时保留 `not_population_percentile=true`
- `result.derived_function_preferences` 必须与四字母代码对应，含四项 stack、`plain_summary_zh`、`plain_sequence_zh`、`sequence_explanation_zh` 和 `independently_measured=false`；每个 stack 项必须含可直接展示的 `plain_name_zh` 与 `plain_explanation_zh`
- 用户界面不得只展示 `Ti/Fi/Ne/Si` 缩写；首屏优先展示 `plain_sequence_zh`，缩写只作为括号内补充
- 开场或结果脚注只需简洁展示一次 `result.four_letter_preference.display_disclaimer_zh`；不得称为官方 MBTI® 结果
- Mini-IPIP：`result.scores` 五个维度，每维含 `sum`、`mean`、`item_count`
- `quality.response_pattern`
- 禁止把题内选择占比说成人口百分位、准确率或统计置信区间，禁止诊断、官方等价或固定本质人格表述

### Relationship reflection

- `evidence.instrument.name/version`
- `evidence.consent.partner_a/partner_b`
- 正常流程：`result.dimensions` 的双方均值、绝对差异和对话提示
- 安全关键题：原始 facts 记录 `safety.reason_code=E_RELATIONSHIP_SAFETY`、`combined_reflection_suppressed=true`，不得含 `dimensions`；它会被普通 `validate_result.py` 拒绝，必须改走 `safety_response.py build/validate` 的独立安全响应，不能包装成正常结果
- 明确 `not_a_compatibility_score: true`

### Oracle reflection

- `evidence.deck_version`
- `evidence.deck_hash`
- v2 牌组包含 `evidence.meaning_basis_zh`，说明牌义是固定、原创的当代中文释义
- `evidence.commitment`
- `evidence.client_seed`
- `evidence.server_seed_reveal`
- `evidence.verification_formula`
- `evidence.feature_control`
- `result.card` 与 `result.orientation`
- v2 的 `result.card` 必须含 `archetype_zh`、`keywords_zh`、`upright_lens_zh`、`reversed_lens_zh` 和 `visual_symbols_zh`；解释只引用本次方向对应的 lens
- 明确 `not_a_prediction: true`

### Chart interpretation

- `evidence.adapter_payload`：完整引擎结果；当前可直接放行的是三个能够本地复算的内置引擎
- `evidence.adapter_receipt`：chart hash、功能控制、引擎 allowlist receipt 和内置引擎本地复算 attestation
- `result.chart` 必须与 adapter payload 完全一致
- `quality.warnings`
- 不得省略计算内核和输入精度

### Report follow-up

- `evidence.report_source`：kind、category、title、provider、instrument/system、version、provided_by、是否独立验证
- 印度占星报告额外记录 `traditional_system=vedic-astrology`、报告中实际出现的 `chart_components_present` 与 `input_precision`；未知就写 `unknown`
- `result.answers[]`：用户问题、至少一个页码/章节 + 字段 + 原文片段、解释、限制、行动
- `category=traditional` 时必须通过 `SOURCE_BOUND` 功能门，并在 final 加规定免责声明

### Final interpretation ledger

- `presentation.depth`：`quick | deep`
- `presentation.progressive_disclosure`：必须为 `true`
- `interpretation[].support_strength`：`strong | mixed | weak`，只表示当前结果内部的证据强弱
- `interpretation[].counter_signals`：可为空数组，但必须存在
- `interpretation[].cannot_support`：至少一项
- `interpretation[].fit_status`：`not_checked | consistent | mixed | inconsistent`

## 6. 错误输出

错误也应结构化：

```json
{
  "ok": false,
  "error": {
    "code": "E_INVALID_ANSWERS",
    "message": "答案必须包含 1—20 题且为 1—5 的整数",
    "fields": ["answers.7"]
  }
}
```

错误时不输出部分人格画像、关系结论、牌面替代品或模型手算盘面。

每次运行使用唯一私有目录和输出路径。若脚本失败，旧文件即使仍存在也不属于本次运行，禁止继续交付；`E_OUTPUT_EXISTS` 表示必须换一个新的运行目录。

分享卡不是新的事实对象，不写回 facts/final。生成时只使用 [share-card.md](share-card.md) 允许的字段；`share-card.json` 只是公开字段 spec，`share-card.svg` 是其确定性展示。二者必须保存在本次私有运行目录、通过独立校验，并与 accompanying text 一起交付；完整边界仍以 final 报告为准。
