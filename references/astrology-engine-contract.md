# 历法与星历引擎契约

## 目录

1. 已内置能力
2. 输入与命令
3. 输出和验证
4. 时间与流派策略
5. 印度占星轻体验交互 SOP
6. 生产升级路线
7. 黄金测试

## 1. 已内置能力

| 引擎 | 能力 | 不包含 |
|---|---|---|
| `builtin-lunar-python-bazi` `1.4.8+wrapper.1` | 公历/农历转换、节令月柱、四柱、五行、纳音、前后节令 | 真太阳时、紫微、印度占星、人生预测 |
| `builtin-astronomy-engine-basic` `2.1.19+wrapper.1` | 热带黄道十个天体的地心位置、星座、主要相位 | 宫位、上升点、Chiron、小行星、印度占星 |
| `builtin-astronomy-engine-vedic-lite` `2.1.19+vedic-lite-beta.1` | 恒星黄道 D1、Lagna、整宫制、古典七曜、平均 Rahu/Ketu、月宿/Pada | D9 等分盘、Dasha、行运、瑜伽、强弱、择时、出生时间校准 |

三者共享的第三方源码和 MIT 许可证已放在 `scripts/vendor/`，Vedic Lite 的岁差、Lagna、整宫制、月宿和交点包装代码为本项目独立实现。运行时只用 Python 标准库和随包源码，不联网、不临时安装依赖。`scripts/engine_allowlist.json` 精确绑定名称、版本、artifact SHA-256 和许可结论。

这是一套可运行 MVP，不是“万年绝对准确”声明。公开生产前仍要完成本文件的边界差分和合规验收。

## 2. 输入与命令

### 公历八字 / 西洋基础星历 / 印度占星轻体验

```json
{
  "calendar": "gregorian",
  "local_datetime": "1992-09-15T14:30:00",
  "timezone": "Asia/Shanghai",
  "fold": 0,
  "location": {
    "label": "江苏省苏州市",
    "latitude": 31.2989,
    "longitude": 120.5853,
    "source": "用户确认或有版本的地理编码器",
    "precision": "city"
  },
  "time_precision": {
    "kind": "exact",
    "minutes": 0
  },
  "day_boundary_policy": "civil-midnight",
  "solar_time_policy": "civil"
}
```

`fold` 只在夏令时回拨造成同一当地时间出现两次时提供。不存在的当地时间直接报错，不猜测。

当前 MVP 只在 `time_precision.kind=exact` 且 `minutes=0` 时输出单一盘面。`approximate`、`range`、`unknown` 或非零误差返回 `E_TIME_UNCERTAINTY`；宿主若要支持模糊时间，必须先实现候选盘与边界差分，不能把一个时间点冒充整个范围。

1949 年前输入默认返回 `E_HISTORICAL_TIMEZONE_OFFSET_REQUIRED`。只有用户依据可复核来源显式给出 `historical_utc_offset`（如 `+08:00`）时才运行，并在结果中同时保存请求的 IANA 时区、固定偏移和“未采用 IANA 历史规则”的来源说明。

### 农历八字

```json
{
  "calendar": "lunar",
  "lunar_datetime": "1992-08-19T14:30:00",
  "lunar_is_leap_month": false,
  "timezone": "Asia/Shanghai",
  "location": {},
  "time_precision": {}
}
```

地点和精度字段仍须完整。闰月必须显式提供，不能只凭同名月份猜测。

### 运行

```bash
python3 scripts/bazi_engine.py \
  <run_dir>/chart-input.json \
  --output <run_dir>/chart.json

python3 scripts/western_engine.py \
  <run_dir>/chart-input.json \
  --output <run_dir>/chart.json

python3 scripts/vedic_lite_engine.py \
  <run_dir>/chart-input.json \
  --output <run_dir>/chart.json
```

八字接受 `calendar=gregorian|lunar`；西洋基础星历只接受公历，产品验收范围为 1800—2200。印度占星轻体验只接受公历、1950—2100 年、绝对纬度不高于 65° 且出生时间精确到 `0` 分钟误差；还需 `chart-generation` 与 `vedic-lite-generation` 两个开关同时开启。

## 3. 输出和验证

引擎输出统一 adapter JSON：

```json
{
  "schema_version": "1.0.0",
  "engine": {
    "name": "精确名称",
    "version": "精确版本",
    "artifact_hash": "sha256:...",
    "license": "许可结论"
  },
  "input": {},
  "chart_system": "bazi | western | vedic",
  "chart": {},
  "boundary_checks": [],
  "provenance": {},
  "warnings": []
}
```

公共必备检查：

- `timezone-resolved`
- `location-resolved`
- `time-precision-propagated`

八字还要：

- `solar-term-boundary`
- `day-boundary-policy`

西洋基础星历还要：

- `ephemeris-engine-verified`
- `ephemeris-range`

印度占星轻体验还要：

- `ephemeris-engine-verified`
- `ephemeris-range`
- `ayanamsa-model-declared`
- `sidereal-boundary-margin`
- `ascendant-latitude-range`

继续运行：

```bash
python3 scripts/validate_chart_adapter.py <run_dir>/chart.json
python3 scripts/convert_chart_result.py \
  <run_dir>/chart.json \
  --output <run_dir>/facts.json
python3 scripts/validate_result.py <run_dir>/facts.json
```

内置引擎校验器会从标准化 `input` 本地重算，并比较盘面、边界检查、警告和除生成时间外的 provenance；仅自报引擎名称与 hash 不足以通过。外部引擎在宿主尚未实现可验证 attestation receipt 时失败关闭。

任一检查失败、本地复算不一致、引擎 hash 不匹配、控制面关闭或时区无法解析，都不生成报告。

## 4. 时间与流派策略

- 先保留出生证墙钟时间、IANA 时区、解析后的 UTC offset、`fold`、tzdb 版本和解析来源；不能把中国用户一律当作固定 UTC+8，中国大陆 1986—1991 年存在夏令时记录。
- 新疆出生须询问记录采用北京时间还是新疆时间；不要静默选择。
- 1949 年前时区数据和地方时制不完整；当前引擎要求人工提供有来源的 `historical_utc_offset`，否则拒绝。
- 八字默认 `day_boundary_policy=civil-midnight`；用户明确选择“晚子时换日”时才用 `late-zi-next-day`。
- 当前 `solar_time_policy` 只允许 `civil`。传入真太阳时会返回 `E_UNSUPPORTED_SOLAR_TIME`，不会做粗糙经度修正。
- 不同钟制、时间误差或节气边界可能改变结果时，应输出多解或停止解释，不能选一个看起来更“准”的盘。
- 西洋基础盘用 `GeoVector(..., aberration=True)` 再接 `Ecliptic()` 得到地心真黄道坐标；不要误用日心 `EclipticLongitude()`。
- Vedic Lite 先用相同 Astronomy Engine ECT 热带经度，再减去 `lahiri-linear-beta-1950-1990`。该模型只用官方文档公开的 1950/1990 Lahiri 数值构造线性斜率，不是 Swiss Ephemeris 算法或兼容声明。
- Lagna 用当地恒星时、真黄赤交角、纬度求东方地平与黄道交点；宫位采用整宫制。绝对纬度高于 65° 直接拒绝。
- 月宿按 27 等分、每宿 13°20′，Pada 每段 3°20′；Rahu/Ketu 为平均月交点。任何关键星座/月宿/Pada 距边界不足 0.05° 时返回 `E_SIDEREAL_BOUNDARY_UNCERTAINTY`。
- 完整公式、锚点和审计边界见 [vedic-lite-algorithm.md](vedic-lite-algorithm.md)。

## 5. 印度占星轻体验交互 SOP

1. 先说明这是传统文化轻体验，只生成 D1 事实，不是完整专业印占或未来预测。
2. 一轮合并询问：公历出生日期、尽量精确到分钟的当地出生时间、出生城市；从上下文能确定的不要重复问。
3. 若用户不能确认时间精确，停止单盘并说明 Lagna、宫位和月宿边界可能变化；不要替用户猜一个整点。
4. 根据城市解析 IANA 时区和城市级经纬度，回显让用户确认；新疆时间、DST 回拨或城市同名时必须额外确认。
5. 创建私有运行目录，依次运行 `vedic_lite_engine.py`、`validate_chart_adapter.py`、`convert_chart_result.py` 和 `validate_result.py`。
6. `quick` 首屏只展示：Lagna、月亮星座/月宿、太阳星座、3 条带事实路径的谨慎主题、缺失模块和免责声明。
7. `deep` 在 quick 基础上展开九个天体/交点的星座与整宫宫位、支持信号、反证、不确定性和 1—3 个现实可验证的低风险行动；不能用生成式语言补造 D9/Dasha。
8. 用户要求可分享文件时，先完成 final JSON 校验，再用 `render_report_html.py` 输出本地 HTML。

典型开场：

> 可以做一次印度占星轻体验 Beta。我需要你的公历出生日期、当地出生时间（最好来自出生证明并精确到分钟）和出生城市。它会给出 D1、上升、月宿和整宫位置，不含 D9、大运或未来事件预测。

## 6. 生产升级路线

### 闭源、许可证风险较低的高精度路线

1. `zoneinfo` + 固定 `tzdata` 作为唯一时间层；
2. 构建期用 MIT Skyfield + 本地 JPL DE440/DE440s 生成 1901—2100 节气、朔和农历边界冻结表；
3. 自有版本化八字薄规则层；
4. 运行时继续使用 MIT Astronomy Engine 处理基础行星位置；
5. 把 kernel、冻结表、库、时区数据的版本和 SHA-256 写入结果与 SBOM。

### 完整西洋占星

需要 Placidus/Koch 等宫制、完整交点和专业兼容性时，采购 Swiss Ephemeris Professional License，并直接包装有权使用的官方 C 核心。Swiss 免费路径是 AGPL；公开闭源服务不能只因为“pip 能安装”就接入。第三方 Python/JS wrapper 还要单独审查许可证。

### 完整印度占星

当前轻体验可以用于小流量产品验证，但不能冒充专业排盘。若要兼容主流 Lahiri、D9/Varga、Vimshottari Dasha、行运、Ashtakavarga 或专业软件结果，应采购 Swiss Ephemeris Professional 或选用另一个明确允许闭源网络服务的商业内核，并做跨引擎黄金差分。不要把 PyJHora/Swiss 的 AGPL 代码复制进当前包。

### 国内部署

- 固定 wheel/tarball/hash，随包保留 LICENSE/NOTICE；
- 禁用运行时自动下载、CDN 字体和在线地理编码；
- 地点使用经审核的本地城市表并允许用户修正；
- 在断网 CI 中运行黄金用例。

## 7. 黄金测试

八字至少覆盖：

- 立春和十二“节”的 `t−1s / t / t+1s`；
- 白露回归；
- 22:59:59、23:00、23:59:59、00:00；
- 闰年、闰月和公农历互转；
- 1986—1991 中国 DST、新疆两种钟制；
- 未知地点失败、海外地点和历史时区；
- 多进程重复运行一致。

星历至少覆盖：

- 十个天体与 JPL Horizons 或选定基准的差分；
- 0° 星座边界和相位容许度边界；
- 1800 与 2200 年范围边界；
- 输入时间不确定性对月亮位置的传播；
- 同输入多次、多进程结果一致。

Vedic Lite 还要覆盖：

- 1950、1990 两个 Lahiri 锚点和 2019 官方文档对照点；
- Lagna 与至少一个独立高精度商业/授权引擎的差分；
- 12 个星座、27 个月宿、4 个 Pada 的边界前后；
- 平均 Rahu/Ketu 恰好相差 180°；
- `0.05°` 模型边界拒绝、±65° 纬度和 1950/2100 年范围；
- 双开关熔断、artifact 篡改、本地复算与离线并发一致。

不要宣传“秒级节气”“±1 分钟出生时间校准”“命中率”或“科学证明”，除非已有实现、数据集、容差、失败率和可复核报告。
