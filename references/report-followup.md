# 已有报告追问

## 目录

1. 适用范围
2. SOP
3. 证据绑定
4. 不可越界

## 1. 适用范围

用于用户上传人格、关系、八字、星盘、印度占星或其他测试报告后，请求摘要、术语解释、矛盾检查或把报告转成现实行动。印度占星只做来源绑定解释，不重新排盘、不验证所谓精确校时。

## 2. SOP

1. 识别报告来源、日期、系统/量表、版本和输入；缺失就标记未知。
   - 印度占星报告标记 `traditional_system=vedic-astrology`；
   - 只记录实际出现的 D1/D9/D10、Dasha、Nakshatra、宫位等 `chart_components_present`；
   - 出生时间精度、时区、ayanamsa 或宫制未知时写 `unknown`，不猜。
2. 若 `category=traditional`，运行 `python3 scripts/feature_gate.py traditional-report-interpretation`；本地默认进入 `SOURCE_BOUND`，宿主挂载关闭快照时返回 `E_FEATURE_DISABLED`。心理测量或其他普通报告不使用该门。
3. 只提取报告实际出现的字段，不从版式或营销词推断计算过程。
4. 把用户问题映射到具体页码/章节、字段和最短必要原文片段。
5. 先完成不使用用户传记的来源绑定解释，再用用户主动提供的背景检查贴合、矛盾或无法判断。
6. 先复述依据，再解释传统/测量含义，再列反证、不能推出什么和限制。
7. 把结论转为一个可观察问题或低风险行动。
8. 按 [output-contracts.md](output-contracts.md) 写入结构化 `report_source`、`answers[]`、`interpretation`、`actions` 和 `presentation`，先校验 facts，再用 `--stage final` 校验。传统报告 final 必须带规定的 AI 标识和用途边界。
9. 若用户要新盘、新测试或高影响预测，重新走核心路由。

## 3. 证据绑定

每个回答使用下列简式：

```text
依据：报告第 X 页 / 字段 Y 写了……
解释：在该报告采用的框架中，这通常表示……
限制：由于缺少版本/输入精度/常模，不能推出……
行动：如果你想验证，可在未来一周观察……
```

若无法读取附件、字段模糊或截图不完整，先说明缺失，不补造内容。

结构化来源至少记录：

```json
{
  "kind": "file | text | screenshot",
  "category": "traditional | psychometric | other",
  "title": "报告名或 unknown",
  "provider": "提供方或 unknown",
  "instrument_or_system": "量表/命理体系或 unknown",
  "version": "版本或 unknown",
  "provided_by": "user",
  "independently_verified": false
}
```

印度占星报告增加：

```json
{
  "traditional_system": "vedic-astrology",
  "chart_components_present": ["D1", "D9", "vimshottari-dasha"],
  "input_precision": "exact | approximate | unknown"
}
```

这些字段仅描述报告内容，不代表 Skill 已验证报告的计算或准确率。

## 4. 不可越界

- 用户提供的报告不自动成为可信计算结果；
- 不补算印度占星分盘、Dasha、过运或出生时间，不把报告中的“±5 分钟校准”当成已验证事实；
- 不因报告声称“高精度”就沿用其精度；
- 不把人格报告转成诊断、招聘筛选或职业限制；
- 不把命理报告转成医疗、投资、法律、生育或死亡建议；
- 不对未在报告中的第三方动机、忠诚、健康或秘密作推断；
- 不以追问为理由建立长期个人档案。
