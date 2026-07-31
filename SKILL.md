---
name: divination-assessment
description: 面向中国用户，将原创四字母性格偏好快测、Mini-IPIP 大五人格、关系反思、抽牌式联想、八字排盘、西洋基础星历、印度占星轻体验和已有报告追问，路由到可运行、可复核且有边界的快速或深度流程，并可在结果校验后生成脱敏分享卡。用于用户想测 INFP、ENTJ 等四字母偏好、通过几道情境题探索性格、做大五人格或关系沟通测试、进行塔罗/抽签反思、八字排盘、星座行星相位、生成 D1/Lagna/月宿轻量印占盘、传统文化解读、上传既有报告连续追问，或把测试/占卜结果生成朋友圈、小红书分享卡时。不做完整专业印度占星、心理诊断，不复制受保护的商业量表，不把传统文化内容用于高影响决策，也不分析生物特征。
---

# 占卜与人格测试

把“测一测、抽一张、排个盘”转成三层结果：确定性事实、带边界的解释、低风险可逆建议。默认提供受限娱乐体验；不把语言模型联想冒充量表分数、历法计算或未来事实。

## 执行流程

1. **选择一个主模式**
   - 始终读取 [core-routing.md](references/core-routing.md)。
   - `personality`：原创四向偏好快照、Mini-IPIP 五人格。
   - `relationship-reflection`：双方沟通、边界、修复与共同期待。
   - `oracle-reflection`：单次抽牌或抽签式自我反思。
   - `chart-interpretation`：内置八字、西洋基础星历或印度占星轻体验 Beta。
   - `report-followup`：只围绕用户提供的报告解释和追问。
   - 多模式请求先处理用户最关心的一项；仍不明确时只追问一次主目标。
   - 用户没指定阅读深度时默认 `quick`；明确要完整报告、技术细节或深入专题时使用 `deep`。

2. **先过安全门**
   - 始终读取 [safety-and-compliance.md](references/safety-and-compliance.md)。
   - 判断 `allow`、`allow_with_boundary`、`redirect` 或 `refuse` 后才收集信息。
   - 医疗、心理危机、生育、死亡、人身安全、违法、诉讼、投资、借贷、保险、赌博、录取录用等问题，不给日期、概率、吉凶或行动指令；改做可核验信息和现实决策梳理。
   - 不推断第三方出轨、犯罪、精神状态、性取向或秘密；不做“有灾—付费化解”、重抽到满意、转运商品或依赖性设计。
   - “AI 生成，仅供参考”必须展示，但不能让本来禁止的内容变得可做。

3. **读取模式规则**
   - 始终读取 [output-contracts.md](references/output-contracts.md)。
   - 始终读取 [interpretation-protocol.md](references/interpretation-protocol.md)，执行事实优先、背景后置、反证账本和渐进披露。
   - 人格：读取 [personality-assessment.md](references/personality-assessment.md)。
   - 关系：读取 [relationship-reflection.md](references/relationship-reflection.md)。
   - 抽牌：读取 [oracle-reflection.md](references/oracle-reflection.md)。
   - 排盘：读取 [astrology-engine-contract.md](references/astrology-engine-contract.md)。
   - 印度占星轻体验：额外读取 [vedic-lite-interpretation.md](references/vedic-lite-interpretation.md)；只解释盘面中真实存在的字段。
   - 报告追问：读取 [report-followup.md](references/report-followup.md)。
   - 用户要生成、分享或保存结果卡片时：读取 [share-card.md](references/share-card.md)。
   - [source-attribution.md](references/source-attribution.md) 只在维护、审计、升级依赖时读取。

4. **补齐最少输入**
   - 复用当前对话和用户已提供材料，不重复索取。
   - 每轮合并询问 1—4 个必要问题；有结构化 `ask_user_question` 能力时优先使用。
   - 不收真实姓名、手机号、身份证号、精确住址或单位等无关标识。
   - 原创四向快照开场只说明一次“这是一个非官方简单测试”；每题只让用户选 A 或 B，不询问强弱、不提供中立项。每轮问 2—4 题，答完 12 题后直接输出 INFP、ENTJ 等四字母偏好、四轴选择占比和进一步偏好线索。
   - 关系数据必须由双方分别知情提交，不能代填另一方。
   - 排盘只收当地日期时间、IANA 时区、城市级地点/经纬度来源、历法和时间精度；不要收与计算无关的人生隐私。
   - 不满 14 周岁时，宿主未确认监护人同意就不收出生资料、不运行个性化传统文化流程。

5. **创建私有运行目录**
   - 从 Skill 根目录运行：`python3 scripts/secure_run_dir.py create`。
   - 把输入、状态和结果写入返回的 0700 临时目录，不写入 Skill 安装目录。
   - 完成或取消时，在 `finally` 中运行脚本返回的精确 cleanup 命令。
   - 不把用户文字直接拼接进 shell；为每次结果使用新输出路径，脚本拒绝覆盖旧文件。

6. **运行确定性脚本**
   - 原创四向题目：`python3 scripts/score_type_preference.py questions`
   - 原创四向计分：`python3 scripts/score_type_preference.py score <run_dir>/answers.json --output <run_dir>/facts.json`
   - Mini-IPIP 题目：`python3 scripts/score_mini_ipip.py questions --language zh-CN`
   - Mini-IPIP 计分：`python3 scripts/score_mini_ipip.py score <run_dir>/answers.json --output <run_dir>/facts.json`
   - 关系反思：`python3 scripts/score_relationship_reflection.py <run_dir>/answers.json --output <run_dir>/facts.json`
     - 若输出 `E_RELATIONSHIP_SAFETY`，普通结果校验必须失败；按 [relationship-reflection.md](references/relationship-reflection.md) 改用 `safety_response.py build/validate`，只展示独立固定安全响应。
   - 抽牌承诺：`python3 scripts/reflection_draw.py commit --state <run_dir>/draw-state.json`
   - 将用户自选、非敏感的 seed 安全写入 0600 文本文件，再揭示：

     ```bash
     python3 scripts/reflection_draw.py reveal \
       --state <run_dir>/draw-state.json \
       --client-seed-file <run_dir>/client-seed.txt \
       --output <run_dir>/facts.json
     ```

   - 内置八字：先写符合 [astrology-engine-contract.md](references/astrology-engine-contract.md) 的 `chart-input.json`，再运行：

     ```bash
     python3 scripts/bazi_engine.py \
       <run_dir>/chart-input.json \
       --output <run_dir>/chart.json
     ```

   - 内置西洋基础星历：

     ```bash
     python3 scripts/western_engine.py \
       <run_dir>/chart-input.json \
       --output <run_dir>/chart.json
     ```

   - 印度占星轻体验 Beta：

     ```bash
     python3 scripts/vedic_lite_engine.py \
       <run_dir>/chart-input.json \
       --output <run_dir>/chart.json
     ```

     仅在 `chart-generation` 和独立的 `vedic-lite-generation` 均开启时放行；只生成 D1 事实层、Lagna、整宫制、古典七曜、平均 Rahu/Ketu 与月宿，不生成 D9、Dasha、行运或择时。

   - 将已验证盘面转成统一事实：

     ```bash
     python3 scripts/validate_chart_adapter.py <run_dir>/chart.json
     python3 scripts/convert_chart_result.py \
       <run_dir>/chart.json \
       --output <run_dir>/facts.json
     ```

   - 校验事实层：`python3 scripts/validate_result.py <run_dir>/facts.json`
   - 不手算、不改分、不为迎合用户重抽；只有命令真实成功后才能引用其输出。

7. **解释并校验**
   - 严格分开：
     1. **事实层**：答案、脚本分数、牌面、四柱、行星位置、版本和输入精度；
     2. **解释层**：用“可能、可以留意、若贴合”表达的暂定解释，并绑定事实字段；
     3. **行动层**：低成本、可逆、用户可拒绝的观察或沟通建议。
   - 人格结果首屏直接展示四字母偏好代码和四轴选择占比，例如 `INFP｜I 67% · N 67% · F 67% · P 67%`。百分比只表示本轴 3 道 A/B 选择的占比，不是人口百分位、准确率或统计置信度。
   - 进一步偏好不能只展示 `Fi → Ne → Si → Te`。先展示脚本返回的 `plain_sequence_zh`，例如“确认自己是否真心认可 → 探索还有哪些可能 → 用过往经验核对细节 → 用计划和标准推动落地”；再按需把缩写放在括号中，并用 `stack[].plain_explanation_zh` 逐项解释。紧邻说明“由四字母偏好代号推导，未单独测量”。
   - 抽牌先展示 `result.card.archetype_zh` 的通用母题，再展示与正逆位对应的 `upright_lens_zh|reversed_lens_zh`，最后才结合用户问题说明“为什么可能有关”。不得只报牌名就跳到行动建议。`quick` 给一句结论、一段 60—140 字牌义映射、至多一个自检问题和一个可逆行动；`deep` 才展开 2—4 个反思问题。
   - 八字与星历解释必须显示引擎、版本、时区、精度和边界；印度占星还要显式显示 `lahiri-linear-beta-1950-1990` 近似模型与缺失模块，不把传统框架说成科学事实。
   - 把人话层写入新的 `<run_dir>/final.json`；每条 `interpretation` 绑定现有 `evidence.*` 或 `result.*` 字段，每个 `action` 标为 `low_risk: true`、`reversible: true`。
   - 先在不读取用户传记的情况下写事实绑定解释，再用用户主动提供的背景标记贴合、冲突或未核对；背景不能回改 facts。
   - 每条 `interpretation` 必须记录 `support_strength`、`counter_signals`、`cannot_support` 和 `fit_status`；强弱只表示当前结果内部的解释证据，不得称为科学置信度。
   - final 顶层必须记录 `presentation.depth=quick|deep` 和 `progressive_disclosure=true`。
   - 抽牌、排盘或传统报告 final 必须逐字包含：

     `AI生成内容｜传统文化与自我反思，仅供参考，不是经科学验证的预测，也不构成医疗、法律、投资或其他专业建议。`

   - 运行 `python3 scripts/validate_result.py <run_dir>/final.json --stage final`；校验通过后才能展示。若只因 `E_HIGH_IMPACT` 失败，不把原始校验错误或“关键词屏蔽”抛给用户；先按错误给出的领域和触发组合安全改写一次并重验，仍失败才用人话说明边界和可继续的问法。
   - 用户主动要求文件报告时，在 final 校验通过后生成无外链、默认不含原始结果的本地 HTML：

     ```bash
     python3 scripts/render_report_html.py \
       <run_dir>/final.json \
       --output <run_dir>/report.html
     ```

8. **可选生成分享卡**
   - 只在 `<run_dir>/final.json` 已通过 final 校验后询问一次：“要生成一张脱敏分享卡吗？”
   - 用户同意后，优先运行 `render_share_card.py` 生成确定性 SVG 与公开字段 spec，再运行 `validate_share_card.py`；这条路径不依赖图片模型，文字、隐私和边界可复核。
   - 默认生成 1080×1440 的 3:4 竖版；用户明确要求头像卡时传 `--aspect square`。宿主需要 PNG/JPEG 时，在产品层把已校验 SVG 光栅化，不让图片模型重写文字。
   - 在清理私有运行目录前，先让宿主读取并摄取已校验 SVG 为聊天附件或受控对象；不能摄取时只交付 `companion_text` 和可复制卡面文案，不能先清理再声称文件仍可下载。
   - 用户明确想要更强插画感且宿主提供 `image_generation@v1.0` 时，运行 `build_share_card_image_prompt.py`：生产默认使用 `text-free-background`，再由宿主叠加已校验 SVG；用户明确要“像一张完整塔罗牌”的预览时可传 `--render-pass framed-preview`，只生成牌号、双语牌名和正逆位关键词。逐字核对预览文字，错误时回退到无字背景加确定性文字层。
   - 分享卡是 final 的衍生展示，不能改分、重抽、重排盘或新增事实。

9. **处理追问**
   - 先指出报告字段或用户原话，再解释，再给行动。
   - 用户把话题扩展到高影响决定、第三方隐私或另一模式时，重新执行安全路由。
   - 不承诺跨会话记忆、自动更新、持续追踪或未来主动推送。
   - 当前单次运行内可复用同一 `run_id` 与已校验 facts；追问只新增解释和行动，不修改事实。

## 功能开关

- 默认可用，但只开放受限事实/反思模式：
  - 抽牌：`REFLECTION_ONLY`
  - 排盘：`FACTS_ONLY`
  - 印度占星轻体验：`VEDIC_LITE_FACTS_ONLY`，并受排盘总开关约束
  - 传统报告：`SOURCE_BOUND`
- 本地默认策略在 `scripts/feature_controls.default.json`。
- 本地原型可用绝对路径环境变量 `DIVINATION_FEATURE_CONTROLS_FILE`，或在命令中传 `--controls <path>`，关闭单项功能；任何 `enabled: false`、过期、版本/范围不匹配或文件不安全都返回 `E_FEATURE_DISABLED`。这叫“宿主控制快照覆盖”，本身不会联网拉取远程配置。
- 接入生产控制面时设置 `DIVINATION_CONTROL_PROFILE=production`。此时禁止回落到随包默认文件，并要求宿主挂载 HMAC-SHA256 签名、TTL 不超过 15 分钟、带整数 `revision_number` 的控制快照，同时注入 `DIVINATION_FEATURE_CONTROLS_HMAC_KEY`；缺失、过期、验签失败或低于 `DIVINATION_FEATURE_CONTROLS_MIN_REVISION` 都关闭。远程拉取、密钥托管与原子挂载由元宝服务端负责。
- 具体快照格式、签名算法和宿主 SOP 见 [remote-control-integration.md](references/remote-control-integration.md)。
- 高影响硬阻断独立于功能开关，不能被控制面放宽。
- 引擎 allowlist 独立存在，功能开启不代表任意引擎可运行。

## 运行边界

- `lunar-python 1.4.8` 和 Astronomy Engine `2.1.19` 已随 Skill 固定版本、源码和 MIT 许可证，可完全离线运行；无需国内用户访问 PyPI、GitHub 或境外 API。
- 八字当前支持公历与显式闰月的农历输入、节令月柱和两种子时换日规则；只支持 `civil` 民用时，不会把经度修正冒充真太阳时。
- 当前内置排盘只接受 `exact + 0 分钟误差` 的单一时间；不精确时间返回 `E_TIME_UNCERTAINTY`。1949 年前必须显式提供有来源的固定 UTC offset，否则拒绝。
- 西洋基础版只提供热带黄道十个天体、星座与主要相位；不提供宫位、上升点、紫微或出生时间校准。
- 印度占星轻体验 Beta 只支持 1950—2100、绝对纬度不高于 65°、`exact + 0 分钟误差` 的公历出生时间；提供 D1、Lagna、整宫制、古典七曜、平均 Rahu/Ketu 和月宿。Lahiri 为 1950/1990 公开锚点的线性近似，边界不足 0.05° 时拒绝硬判；不等同 Swiss Ephemeris，不提供 D9、Dasha、行运、瑜伽、强弱、择时或出生时间校准。
- 用户上传既有印度占星报告时仍走来源绑定解释；只解释报告实际存在的 D1/D9、Dasha 等字段，不声称验证原报告排盘准确性。
- 若需要宫位/高精度商业服务，另行实现并验证，或采购 Swiss Ephemeris Professional；不能把其 AGPL 免费路径直接嵌入闭源公开服务。
- Mini-IPIP 中文题是未完成本地心理测量验证的试译，只用于原型自我反思。
- “四向偏好快照”是 12 道原创中文 A/B 题，不属于任何商业人格量表，不复制其题目、计分、常模或报告；它会输出独立推导的四字母偏好代码和功能偏好线索，但不得包装成官方 MBTI® 测评或确定人格结论。
- 不分析面相、手相、人脸、声音或其他生物特征来推断人格、健康、财富或命运。

## 质量检查

- 是否只选了一个主模式，并收集最少必要信息？
- 是否先完成安全路由，高影响请求已拒绝或转为现实决策梳理？
- 所有分数、牌面和盘面是否真实来自脚本或 allowlist 引擎？
- 是否记录版本、来源、时区、时间精度、警告和错误码？
- 是否区分事实、解释和行动，避免绝对断言与第三方推断？
- 是否先完成事实绑定解释，再核对用户背景；是否列出反证、不能支持的结论和贴合状态？
- 是否按 `quick|deep` 渐进披露，而不是用未经支持的内容填充长报告？
- 是否只在开场或结果脚注简洁说明一次“非官方简单测试”，同时避免匹配率、诊断、概率或“最佳时机”承诺？
- 是否优先用人话解释功能偏好，而不是默认用户理解 `Ti/Fi/Ne/Si` 等缩写？
- 是否使用唯一私有运行目录并在结束时清理？
- facts 与 final JSON 是否分别通过 `validate_result.py`？
- 传统文化 final 是否包含规定的 AI 标识与用途边界？
- 分享卡是否先通过 spec 与 SVG 校验、完成脱敏与文字核对，并避免 Logo、官方 MBTI®、预测和匹配率误导？
