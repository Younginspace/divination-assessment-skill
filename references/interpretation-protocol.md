# 解释与渐进披露协议

## 1. 选择阅读深度

在不增加敏感输入的前提下，让用户选择：

- `quick`：30 秒结论，最多 3 条解释、2 个行动；
- `deep`：先给同样的首屏结论，再展开证据、反证、专题和技术限制。

用户没选时默认 `quick`。不要因选择 `deep` 而生成更多未经事实支持的内容。

最终结果记录：

```json
{
  "presentation": {
    "depth": "quick",
    "progressive_disclosure": true
  }
}
```

## 2. 事实优先，背景后置

对人格、关系、盘面和已有报告都执行：

1. 仅根据已校验的 `evidence` 与 `result` 写第一版解释；
2. 不读取或利用用户传记来制造“命中”；
3. 第一版完成后，才用用户主动提供的背景检查贴合度；
4. 只把背景用于标记 `consistent | mixed | inconsistent`，不改写事实、分数、牌面或盘面；
5. 没有背景时标记 `not_checked`，不要求用户补交疾病、创伤、财务或家庭隐私。

这是一项生成流程约束，不是科学验证或准确率证明。

## 3. 解释账本

每条 final `interpretation` 必须包含：

```json
{
  "claim": "带边界的解释",
  "evidence_paths": ["result.scores.conscientiousness"],
  "limitations": ["数据或方法限制"],
  "epistemic_status": "self_report",
  "support_strength": "strong | mixed | weak",
  "counter_signals": [],
  "cannot_support": ["不能推出的结论"],
  "fit_status": "not_checked | consistent | mixed | inconsistent"
}
```

字段含义：

- `support_strength` 只表示当前结果内部的解释证据强弱，不代表科学置信度、发生概率或准确率；
- `counter_signals` 写入削弱该解释的已知事实路径或简短说明；没有时用空数组；
- `cannot_support` 至少一项，明确该解释不能推出什么；
- `fit_status` 只记录用户背景核对结果，不能用于回改事实。

不要把多个冲突信号平均成一句模糊的“你有时 A、有时 B”。优先写清：

1. 哪个事实支持；
2. 哪个事实削弱；
3. 在什么条件下解释可能成立；
4. 什么观察会推翻它。

## 4. 输出顺序

### Quick

1. 一句话边界；
2. 1—3 条结论卡；
3. 每条的一个证据和一个限制；
4. 1—2 个可逆行动；
5. 可继续深入的 2—4 个方向。

### Deep

1. 复用 Quick 首屏，不改结论；
2. 展开全部事实、反证和矛盾；
3. 按用户选择展开一个专题；
4. 展示输入精度、版本、来源和不能支持的结论；
5. 提供技术附录或本地 HTML 报告。

## 5. 连续追问

- 在当前单次运行中复用同一 `run_id` 和已校验 facts；
- 追问只能新增解释和行动，不能改写 facts；
- 只有用户主动要求保存时才交给宿主的保存流程；
- Skill 本身不承诺跨会话记忆，不建立持续追加的个人传记；
- 每次追问仍重新经过安全路由。

