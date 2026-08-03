# 核心路由

## 目录

1. 路由目标
2. 模式判断
3. 最小输入
4. 失败与降级
5. 通用输出顺序

## 1. 路由目标

先判断用户真正需要的是“测量”“双方对话”“象征反思”“传统命理”还是“已有报告解释”。不要把所有含“测、算、合、运势”的请求都送进同一套生成式回答。

路由结果必须包含：

```json
{
  "mode": "personality | relationship-reflection | oracle-reflection | chart-interpretation | report-followup",
  "entry_point": "test | birth-data | uploaded-report | specific-question",
  "depth": "quick | deep",
  "safety_decision": "allow | allow_with_boundary | redirect | refuse",
  "reason": "一句可审计的原因",
  "missing_inputs": [],
  "next_action": "ask | run | interpret | redirect | refuse"
}
```

## 2. 模式判断

| 用户意图 | 主模式 | 不要做 |
|---|---|---|
| “简单测测”“测 MBTI”“我是 INFP 吗” | `personality` | 开场说明“非官方简单测试”，用原创 A/B 四向快照输出四字母偏好，不复制官方题库 |
| “我和 TA 合不合”“我们总因钱吵架” | `relationship-reflection` | 不用姓名/生日算匹配率 |
| “抽张牌看看我该怎么想” | `oracle-reflection` | 不预测事件必然发生 |
| “排八字”“看星盘/印占/流年” | `chart-interpretation` | 只运行已内置且当前范围支持的事实层；无合格引擎时不手算 |
| “这份报告说的是什么意思”“帮我看这份印占报告” | `report-followup` | 不越出报告补造盘面或验证其准确性 |

出现多个意图时，按顺序处理：

1. 高风险现实问题优先转向现实支持；
2. 用户明确指定的主问题优先；
3. 已有报告优先走 `report-followup`；
4. 仍无法判断时只问：“这次你更想做性格快测、关系对话、抽牌反思，还是八字/星历排盘？”

阅读深度：

- 未指定时默认 `quick`；
- 用户要求“详细、完整、技术依据、深度报告”时选 `deep`；
- `deep` 必须复用 quick 首屏结论，再展开证据与限制，不能靠新增猜测凑长。

## 3. 最小输入

### Personality

- 已知晓这是自我报告、非诊断；
- 四向快照：12 题全部为 A/B 单选，提交时规范化为 `A=1、B=-1`；四轴各 3 题不会平局，完成后输出四字母代码、四轴选择占比和派生功能偏好线索；
- Mini-IPIP：20 题全部为 1—5 的整数答案；
- 语言版本；
- 不需要姓名、生日、性别或手机号。

### Relationship reflection

- 双方分别明确同意；
- 双方各自完成同一套 12 题；
- 用 `A`、`B` 或随机代号，不收真实姓名；
- 不需要生日、星座、性别或关系身份标签。

### Oracle reflection

- 一个低风险、可由用户行动影响的具体问题；
- `REFLECTION_ONLY` 功能控制当前有效；宿主熔断时返回 `E_FEATURE_DISABLED`；
- 一个由用户自行给出的 `client_seed`；
- 不需要出生信息。

### Chart interpretation

- 若只有既有报告：报告文件或可见字段、用户具体疑问；
- 若是传统文化报告：先检查 `traditional-report-interpretation` 控制策略；
- 若要求新排盘：先检查 `chart-generation` 控制策略和引擎精确 allowlist，再收当地日期时间、地点、IANA 时区、历法和时间精度；
- 内置八字、西洋基础星历可直接运行；印度占星轻体验还必须检查 `vedic-lite-generation`，并明确其只含 D1、Lagna、整宫制、古典七曜、平均交点和月宿；
- 印占的 D9、Dasha、行运、瑜伽、强弱、择时、出生时间校准，以及紫微等未内置能力返回 `E_ENGINE_UNAVAILABLE`；
- 用户上传印度占星报告时改走 `report-followup`，可解释报告已有的 D1/D9、Dasha、Nakshatra、宫位等字段，但不重新计算未内置字段、不背书准确性；
- 时间不确定就保留区间，不承诺“校准到某一分钟”。

## 4. 失败与降级

| 情况 | 错误码 | 处理 |
|---|---|---|
| 高影响预测 | `E_HIGH_IMPACT` | 拒绝预测，转为现实信息和可控行动 |
| 心理危机或自伤风险 | `E_CRISIS` | 停止测试，进入安全支持流程 |
| 未成年人且请求高风险/敏感命理 | `E_MINOR_SENSITIVE` | 不运行，建议监护或可信成年人支持 |
| 题目未答完或答案越界 | `E_INVALID_ANSWERS` | 指出题号，不出分 |
| 关系一方未同意 | `E_PARTNER_CONSENT` | 不接受代填，不出结果 |
| 关系安全关键题触发 | `E_RELATIONSHIP_SAFETY` | 抑制共同结果，分别做私下安全核对 |
| 功能被宿主控制面关闭、策略过期或版本不匹配 | `E_FEATURE_DISABLED` | 停止并提供现实反思替代 |
| 命理引擎未配置或未验收 | `E_ENGINE_UNAVAILABLE` | 可解释已有报告，不生成新盘 |
| 命理引擎未命中 allowlist | `E_ENGINE_NOT_APPROVED` | 拒绝适配与转换 |
| 引擎元数据/边界检查不全 | `E_ENGINE_EVIDENCE` | 退回引擎层，不生成报告 |
| 抽牌状态已用或承诺不匹配 | `E_DRAW_STATE` | 停止，不重抽 |

脚本错误不能由语言模型“合理补全”。保留错误码、缺失字段和建议的修复动作。

## 5. 通用输出顺序

1. 一句话说明本次模式、`quick|deep` 和边界；
2. 首屏结论；
3. 输入、来源与脚本/引擎事实；
4. 谨慎解释、支持信号与反证；
5. 不确定性与不能推出的结论；
6. 1—3 个低风险、可逆行动；
7. 2—4 个可继续追问的方向；
8. 数据是否保存及如何删除。
