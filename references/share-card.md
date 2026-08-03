# 脱敏分享卡

## 适用条件

仅在 `final.json` 已通过 `validate_result.py --stage final` 且用户明确同意后生成。不要为了卡片重新测试、重抽或重排盘。

默认输出 1080×1440 的 3:4 竖卡；用户明确要求头像卡时用 1080×1080。默认不显示元宝、产品名、Logo、官方徽章或认证视觉。

## 两条生成路径

### A. 确定性模板，默认

这条路径保证四字母代码、牌名、四柱、盘面事实和边界文字不被图片模型改写：

```bash
python3 scripts/render_share_card.py \
  <run_dir>/final.json \
  --output <run_dir>/share-card.svg \
  --spec-output <run_dir>/share-card.json

python3 scripts/validate_share_card.py \
  <run_dir>/share-card.json \
  --svg <run_dir>/share-card.svg
```

- 用户明确要求 1:1 时追加 `--aspect square`。
- 用户主动提供且确认公开的昵称可追加 `--nickname "昵称"`；脚本会拦截手机号、邮箱、日期、UUID 等模式。
- 交付 SVG 和脚本返回的 `companion_text`。宿主需要 PNG/JPEG 时，在产品层光栅化已校验 SVG；不要重新生成文字。
- 私有运行目录执行 cleanup 前，宿主必须先读取并摄取 SVG 为聊天附件或受控对象。若宿主无法摄取文件，退回可复制卡面文案；不要返回即将被清理的临时路径。
- 内置主题位于 `assets/share-card-themes.json`，只含配色、图形母题和字体栈，不含 Logo、网络字体或外链。

### B. 图片模型氛围版，可选

只有用户明确想要“更有氛围、插画感更强”的版本且宿主提供 `image_generation@v1.0` 时才使用。支持两种 render pass：

- `text-free-background`：生产默认。图片模型只生成背景，关键中文由已校验 SVG/spec 排版；
- `framed-preview`：用户明确要完整塔罗牌预览时使用。图片模型可生成牌框、牌号、双语牌名和正逆位关键词，但不能取代正式确定性文字层。

1. 先生成并校验 `share-card.json` 与 `share-card.svg`；
2. 抽牌卡运行：

   ```bash
   python3 scripts/build_share_card_image_prompt.py \
     <run_dir>/final.json \
     --output <run_dir>/image-prompt.json
   ```

3. 把 `image-prompt.json.prompt` 与 `negative_prompt` 交给图片模型，只生成 `render_pass=text-free-background`；
4. 检查背景没有文字、Logo、真人身份、灾祸写实或新增结论；
5. 宿主将 `share-card.svg` 的确定性文字层叠加到背景，保持 `exact_text` 逐字不变；
6. 宿主暂不支持图层合成时，分别交付氛围背景与已校验 SVG，不让图片模型代写中文。

完整牌面预览追加：

```bash
python3 scripts/build_share_card_image_prompt.py \
  <run_dir>/final.json \
  --render-pass framed-preview \
  --output <run_dir>/framed-preview-prompt.json
```

预览严格遵循 `frame_system`：4.5% 内缩金色双线框、克制切角、单层内拱门、少量月相和星点；顶部依次放牌号、中文牌名、英文名，底部只放正逆位与两个关键词。必须逐项核对 `preview_exact_text`；任一关键字错误、重复或出现伪文字都不交付，改走默认无字背景路径。

视觉规范固定在 `assets/immersive-card-visual-system.json`：3:4 画布、顶部和底部文字安全区、深靛/月白/仪式金配色、当代编辑插画、单一核心母题、匿名人物，以及可选的完整牌框系统。22 张牌的具体场景只从已校验 `result.card.visual_symbols_zh` 与对应正逆位牌义派生。

图片模型不是排版引擎，也不能替代 SVG/spec 校验。

## 默认隐私规则

允许：

- 用户主动选择公开的昵称；
- 体系名称、版本化结果摘要；
- 最多 3 条已校验的短句；
- 一个低风险反思问题；
- AI、非官方或传统文化边界。

禁止：

- 出生日期、时刻、城市、经纬度和时区；
- 原始答案、`run_id`、seed、文件路径和 receipt；
- 真实姓名、手机号、单位、学校或关系对象身份；
- 未成年人年龄、健康、创伤、财务、法律等敏感背景；
- 第三方结论、未来事件、日期、概率、吉凶和行动指令；
- 元宝名称、Logo、官方证书、MBTI® 标志和大师批命视觉。

关系卡必须由双方分别同意；默认只用 A/B，不放真实姓名，不显示总体匹配率。

## 内置模板

| `template_id` | 内容 | 必显边界 |
|---|---|---|
| `type-preference` | 四字母、四轴选择占比、人话偏好链 | `非官方简单测试｜12 道原创题` |
| `big-five` | 五个连续维度 | `无本地常模｜不是心理诊断` |
| `relationship` | 最多四个沟通维度和一个对话问题 | `不提供匹配率` |
| `oracle` | 牌名、正逆位和一个反思动作 | `不预测外部事件` |
| `bazi` | 四柱作为一个盘面事实、最多两条补充 | `AI生成｜传统文化与自我反思` |
| `western` | 太阳、月亮和基础行星星座 | `基础星历｜无宫位` |
| `vedic` | Lagna、月亮、月宿 | `Vedic Lite Beta｜非 Swiss 专业兼容` |
| `report-followup` | 来源绑定的谨慎解释和行动 | `仅解释所提供报告` |

四字母卡不得只放 `Fi → Ne → Si → Te`，应使用 `plain_sequence_zh`。五人格卡不转成四字母。关系卡不显示总分。传统文化卡不放出生资料、财运婚期灾祸、人生定论或未实现模块。

## 交付检查

`validate_share_card.py` 必须确认：

- spec 尺寸、主题、公开字段和必显边界正确；
- SVG 不含脚本、外链、外部图片或网络字体；
- 每条 `exact_text` 都以可核对文字存在；
- 没有手机号、身份证号、邮箱、URL、日期时间、坐标或 UUID；
- 没有元宝名称、Logo、官方认证、准确率、改命或预测性措辞；
- `privacy.*` 全部为 `false`。

传统文化模式在图片旁同时发送：

`AI生成内容｜传统文化与自我反思，仅供参考，不是经科学验证的预测，也不构成医疗、法律、投资或其他专业建议。`

## 图片模型提示词骨架

```text
为一张中文抽牌反思卡生成无字背景插画。只生成背景艺术，不渲染任何文字。
视觉系统：静夜金线 Quiet Arcana。
牌面主题：[result.card.name_zh] · [正/逆位]。
核心母题：[result.card.archetype_zh]
本次方向：[result.card.upright_lens_zh 或 reversed_lens_zh]
原创场景象征：[result.card.visual_symbols_zh]
顶部 0%—19% 与底部 73%—100% 保持低细节负空间；中部只放一个主角或核心象征。
深靛蓝为主，月白与仪式金点亮；当代编辑插画、水粉、纸张纤维、柔和体积光。
严禁文字、伪文字、Logo、水印、证书、算命广告、商业牌组复刻、真人面孔和新增结论。
```
