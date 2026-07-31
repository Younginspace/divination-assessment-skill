# 来源、竞品与维护审计

> 本文件只在维护 Skill、评估依赖或更新产品决策时读取。正常执行测试时不要加载。

## 目录

1. 一手来源
2. 中国规则证据
3. 竞品与社区 Skill
4. 已审计技术结论
5. 依赖选型原则
6. 复核节奏

## 1. 一手来源

### Mini-IPIP / IPIP

- IPIP 官方首页：<https://ipip.ori.org/index.htm>
  - 官方说明题项和量表属于 public domain，可复制、编辑、翻译和使用。
- Mini-IPIP 官方计分键：<https://ipip.ori.org/MiniIPIPKey.htm>
  - 列出五个维度的正反向题项。
  - 官方页面同时提醒：Mini-IPIP 基于词汇 Big Five，原论文对部分构念的命名并不完全准确；其 Neuroticism 是对原 Emotional Stability 的反向计分。产品解释保留该历史 caveat。
- IPIP 计分说明：<https://ipip.ori.org/newScoringInstructions.htm>
  - 正向题按 1—5，反向题按 5—1，再求和。
- IPIP 个体分数解释：<https://ipip.ori.org/InterpretingIndividualIPIPScaleScores.htm>
  - 建议基于自己的样本建立常模，避免把连续分数武断分型。
- Donnellan et al. (2006), PubMed：<https://pubmed.ncbi.nlm.nih.gov/16768595/>
  - 20 题，每个 Big Five 维度 4 题；原论文报告五项研究。
- Myers-Briggs 官方版权政策：<https://www.themyersbriggs.com/en-US/Support/Copyright-and-Permissions>
  - 未经许可不得复制题目、计分工具和报告等受保护材料。
- Myers-Briggs 官方商标指南：<https://www.themyersbriggs.com/hubfs/MyersBriggsCompany_January2026/pdfs/Trademark_Guidelines.pdf>
  - 其他人格工具不应把 MBTI 等标志用于产品名、服务名、域名、广告或描述。
  - 该边界不等于禁止原创工具输出 INFP、ENTJ 等四字母偏好代码；必须使用原创题目与独立计分，并明确非官方、无关联、非诊断。
- OEJTS 开发与许可：<https://openpsychometrics.org/tests/OJTS/development/>
  - 这是独立开发的开放替代量表，不是官方题库；内容为 CC BY-NC-SA，不能直接用于商业产品。

### 历法与星历

- lunar-python：<https://github.com/6tail/lunar-python>
  - 当前随包版本 1.4.8，MIT；用于可运行八字 MVP，仍需产品黄金用例。
- Astronomy Engine：<https://github.com/cosinekitty/astronomy>
  - 当前随包 Python 版本 2.1.19，MIT；官方以 NOVAS/JPL Horizons 做差分，适合基础地心行星位置。
- Swiss Ephemeris 官方开发文档：<https://www.astro.com/swisseph-download/doc/swisseph.pdf>
  - 只引用其中公开的 Lahiri 1950/1990/2019 测试数值作 Beta 模型对照；当前 Skill 不链接、调用或复制 Swiss 源码。
- Ascendant 公开公式与书目索引：<https://en.wikipedia.org/wiki/Ascendant#Calculation>
  - 作为 Lagna 独立实现的公式交叉来源；产品验收仍需与获授权专业内核差分。
- Skyfield 东亚节气：<https://rhodesmill.org/skyfield/almanac.html#solar-terms>
  - MIT；建议与本地 JPL 内核用于构建期生成高精度冻结表。
- JPL/NAIF Rules：<https://naif.jpl.nasa.gov/naif/rules.html>
  - SPICE 软件和数据可用于商业产品，仍要保存内核元数据和遵守规则。
- Swiss Ephemeris 许可：<https://www.astro.com/swisseph/swephinfo_e.htm#license>
  - 公开服务上线前必须选择 AGPL 或 Professional License；闭源完整占星应采购专业许可。
- Python `zoneinfo`：<https://docs.python.org/3/library/zoneinfo.html>
  - 用 IANA 时区和 `fold` 处理历史偏移、重复及不存在的当地时间。

### 平台与交易事实

- Midjourney 收购 Co–Star 官方公告：<https://updates.midjourney.com/midjourneys-first-acquisition/>
  - 只能证明收购和官方披露的安排；不能证明占星准确性或某个产品机制必然有效。

## 2. 中国规则证据

- 2023 年“清朗·生活服务类平台信息内容整治”：<https://www.cac.gov.cn/2023-09/28/c_1697560160163531.htm>
  - 点名黄历、星座、命理风水、塔罗、年运婚运、灵签占卜和付费算命问答。
- 2025 年春节网络环境整治：<https://www.cac.gov.cn/2025-01/19/c_1738899842680885.htm>
  - 点名风水运势、改命转运、破除太岁和网上算命占卜付费服务。
- 2025 年“清朗·整治 AI 技术滥用”专项行动：<https://www.cac.gov.cn/2025-04/30/c_1747719097461951.htm>
  - 点名 AI 算命、AI 占卜误导欺骗网民。
- 2026 年“清朗·整治 AI 应用乱象”专项行动：<https://www.cac.gov.cn/2026-04/30/c_1779289298718765.htm>
  - 再次把 AI 算命等违规功能服务列为整治重点。
- 《人工智能生成合成内容标识办法》：<https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm>
  - 要求显式标识，生成文件还涉及元数据隐式标识。
- 《个人信息保护法》：<https://www.samr.gov.cn/wljys/gzzd/art/2023/art_3ef1e889c1e644d4b65b5f5c7f432386.html>
  - 不满 14 周岁未成年人个人信息属于敏感个人信息；处理前需取得父母或其他监护人同意。
- 《人工智能拟人化互动服务管理暂行办法》：<https://www.cac.gov.cn/2026-04/10/c_1777558395078289.htm>
  - 自 2026-07-15 施行。若产品构成持续性情感互动服务，涉及极端情绪、依赖、未成年人模式、AI 标识、退出及交互数据复制/删除等要求。

这些来源说明存在明确风险，不等于本 Skill 自行完成法律适用判断。法务必须为每项规则记录“适用/不适用、理由、日期和责任人”。

## 3. 竞品与社区 Skill

| 对象 | 来源 | 证据级别 | 维护备注 |
|---|---|---|---|
| 八字排盘 | <https://skillhub.cn/skills/user_1854b633/bazi-paipan> | 社区包源码审计 | 可复用 intake/报告框架，不复用计算内核 |
| 月老姻缘 | <https://skillhub.cn/skills/user_7cb4ad8c/yuelao-matchmaker> | 社区包源码审计 | 实际非八字合婚，含随机分和伪姓名笔画 |
| MBTI assessment | <https://skillhub.cn/skills/user_dedbd569/mbti-assessment> | 社区包源码审计 | 题库许可与工程问题阻断复用 |
| 小红书印占原帖 | <https://www.xiaohongshu.com/explore/6a2a49bb0000000022022631> | 原帖热度信号 | 与 SkillHub 包作者关系未获直接确认 |
| Ning’s Vedic Astrology | <https://skillhub.cn/skills/user_cb08f85f/nings-vedic-astrology> | 高置信功能映射、非作者确认 | 内容体系完整，工程/许可/精度风险高 |
| FateTell | <https://wp.fatetell.com/2025/05/27/think-ai-cant-tell-your-fortune-this-startup-tapping-eastern-metaphysics-says-otherwise/> | 厂商自述 | 适合研究报告后追问闭环，不当作效果证据 |
| Co–Star | 官方产品与收购公告 | 官方事实 + 产品推断 | 社交/品牌价值只能作为待验证假设 |

所有热度、下载量、价格和商店信息都带采集日期；不得永久写成“当前”事实。

社区包源码审计快照日期为 2026-07-29。SkillHub 页面未提供可核验的上游源码 URL、commit 或包 hash，因此审计结果只能绑定当时下载的社区快照，不能无条件外推到以后版本。复现摘要保存在外层交付包的 `研究材料/竞品与技术审计结论.md`。

## 4. 已审计技术结论

### 八字社区包

- 纯 Python 标准库，国内离线运行容易；
- 月首节气列表漏“白露”、误含“大寒”，会直接改月柱；
- 常熟与敦煌坐标互换；
- 未知地点静默回退北京；
- 缺少海外时区和历史 DST 契约；
- “VSOP87、±1 分钟”宣传没有对应实现证据。

结论：只复用交互和结构化报告思路，计算内核必须替换并通过黄金用例。

### 月老社区包

- 实际输入不含出生日期推导；
- “姓名笔画”是 Unicode 码点求和取模；
- “性格互补”使用随机数；
- 同输入结果可变化，非法星座还有异常路径。

结论：不复用。改为双方知情的原创沟通问卷，且不输出匹配率。

### MBTI 社区包

- 93 题、HTML/Node 可离线，但版本号、路径、答案校验、未完成提交和平分处理不一致；
- 测试仅覆盖极端答案；
- 官方 MBTI 题库和标识存在许可阻断。
- 这一阻断针对题库、计分、报告和品牌包装，不阻断原创四向题目生成非官方四字母偏好代码。

结论：不复用题库或标识；提供 public-domain IPIP 原型和独立原创 12 题四向快照。

### 印占社区包

- 多模块 SOP 丰富，但缺地名解析、OCR 实现和可靠锁定；
- Swiss/Moshier 可能在同一进程混合，星历文件和全局路径处理不稳定；
- “±5 分钟校准”实际只有逐分钟状态扫描，无事件评分、排序、置信区间和验证集；
- Skill、PyJHora、Swiss Ephemeris 存在多层 AGPL/商业许可风险；
- 原始安装依赖公网 PyPI、Google Fonts 和未锁定运行时安装。

结论：不集成该社区包及其 PyJHora/Swiss 代码；当前另做 MIT Astronomy Engine + 自有公式的 Vedic Lite Beta，只开放 D1/Lagna/月宿事实层。完整印占仍要在技术、许可、隐私和产品门通过后再评估。

## 5. 依赖选型原则

- 运行代码使用 Python 3.9+ 标准库和随包 vendored 源码，不在运行时联网安装；抽牌并发锁使用 POSIX `fcntl`，目标运行环境须为 Linux/macOS 类系统。
- 已内置 lunar-python 1.4.8 与 Astronomy Engine 2.1.19，并随包保留 MIT 许可证；`engine_allowlist.json` 绑定包装器与源码 artifact hash。
- 当前八字内核是可运行 MVP，不等于生产“万年历精度”验收。高精度闭源路线优先用 Skyfield + JPL 生成冻结节气/朔表和自有规则层。
- Vedic Lite 只复用 MIT Astronomy Engine 的天体位置；Lahiri 近似、Lagna、整宫制、平均交点和月宿由本项目独立实现。不得把它宣传成 Swiss/PyJHora 兼容或完整印度占星。
- `zoneinfo` 使用宿主本地 tzdata；部署制品应固定并记录时区库版本。
- 对候选库分别记录：精确版本、许可证、商业服务要求、源码/制品 hash、国内镜像、离线安装、支持 Python 版本、运行时外网、算法验证。
- 不用单一“红黄绿”混合许可证、网络、工程和科学有效性。
- 不使用 `>=` 作为生产锁定；构建制品应有 hash 与 SBOM。
- MIT、可安装和断网可运行只证明部分工程/许可条件，不自动通过算法、产品或合规门。

## 6. 复核节奏

- 平台政策、法律、许可证、依赖版本和产品价格：每次上线或重大版本前复核；
- 量表题库、计分键和中文翻译：变更即重新验证；
- 命理引擎黄金用例：每次引擎、时区库、星历或地理编码数据变更时回归；
- 竞品推断与优先级：明确区分“官方事实、厂商自述、商店描述、用户评价、分析推断”。
