# 印度占星轻体验 Beta：算法与验收边界

## 定位

这是一个用于小流量验证的、可离线复算的 D1 事实引擎。它没有复制 Swiss Ephemeris 或 PyJHora 代码，也不声称与专业印度占星软件完全兼容。

输出范围：

- 古典七曜的恒星黄道经度、星座和整宫宫位；
- 平均 Rahu/Ketu；
- Lagna；
- 月亮 Nakshatra、Pada 和传统守护星；
- 明确的算法、输入、版本、artifact hash 与边界检查。

明确不输出：D9 等 Varga、Vimshottari Dasha、行运、瑜伽、Shadbala/强弱、Ashtakavarga、择时、出生时间校准和事件预测。

## 计算链

1. 用 Python `zoneinfo` 把当地墙钟时间解析为 UTC；拒绝不存在时间和未消解的 DST 回拨。
2. 用随包固定的 MIT Astronomy Engine `2.1.19` 计算地心真黄道（ECT）热带经度。
3. 用下述 Lahiri 线性 Beta 岁差从热带经度换成恒星黄道经度：

   ```text
   A(t) = A1950 + (TT(t) - TT1950) / 365.2425 × rate
   A1950 = 23°09′31.2539″
   A1990 = 23°43′02.6259″
   rate = (A1990 - A1950) / 40 Julian years
   sidereal_longitude = normalize(tropical_longitude - A(t))
   ```

   两个锚点来自 Swiss Ephemeris 官方文档公开的 Lahiri 测试值；当前代码只使用这些数值建立自有线性近似，没有链接、调用或复制 Swiss 代码。模型名必须完整显示为 `lahiri-linear-beta-1950-1990`，`swiss_ephemeris_compatible` 必须为 `false`。

4. 平均升交点使用 TT 世纪多项式：

   ```text
   Ω = 125.0445479
       - 1934.1362891 T
       + 0.0020754 T²
       + T³ / 467441
       - T⁴ / 60616000
   ```

   Rahu 为 `Ω` 减岁差；Ketu 为其对点。输出必须标明 `mean lunar node`，不能称为真交点。

5. Lagna 使用东方地平与黄道交点：

   ```text
   y = -cos(θL)
   x = sin(θL)cos(ε) + tan(φ)sin(ε)
   tropical_lagna = normalize(atan2(y, x) + 180°)
   sidereal_lagna = normalize(tropical_lagna - A(t))
   ```

   `θL` 为当地视恒星时，`ε` 为当日真黄赤交角，`φ` 为地理纬度。宫位采用整宫制：Lagna 星座为第 1 宫，之后每个星座依次加一宫。

6. 27 月宿等分 360°，每宿 `13°20′`；每宿四个 Pada，每段 `3°20′`。月宿守护星按 Ketu、Venus、Sun、Moon、Mars、Rahu、Jupiter、Saturn、Mercury 循环。

## 失败关闭

- 公历年份不在 1950—2100：`E_EPHEMERIS_RANGE`
- 时间不是 `exact + 0 分钟`：`E_TIME_UNCERTAINTY`
- 绝对纬度高于 65°：`E_ASCENDANT_LATITUDE_RANGE`
- 任一关键星座边界，或月亮月宿/Pada 边界距离小于 0.05°：`E_SIDEREAL_BOUNDARY_UNCERTAINTY`
- 总排盘开关或 Vedic Lite 独立开关关闭：`E_FEATURE_DISABLED`
- 引擎不在精确 allowlist、本地源码 hash 不符或复算不一致：拒绝生成统一结果

`0.05°` 不是科学精度声明，而是为近似模型设置的产品保护带。它不能替代与已授权专业引擎的系统差分。

## 许可与来源

- Astronomy Engine：MIT，源码与许可证随包。
- 时区：Python 标准库 `zoneinfo` + 宿主 IANA tzdata。
- Lahiri 公开锚点：Swiss Ephemeris 官方文档，仅作为数值对照；没有使用其 AGPL 源码。
- Lagna 公式：Jean Meeus / Duffett-Smith 系列公开天文公式的独立实现；实现代码为本项目原创包装。

公开生产前仍需法务确认数值常量使用、产品文案和目标分发方式，并以获授权专业引擎完成黄金差分。Beta 上线不等于完成专业兼容验收。
