# 双方关系反思

## 目录

1. 定位
2. 同意与输入
3. 执行 SOP
4. 解释规则
5. 升级与停止

## 1. 定位

这是一套原创的产品原型问卷，用于发现双方自报的对话主题，不是经过心理测量验证的关系量表，也不是“姻缘匹配算法”。它不使用姓名笔画、生肖、星座、随机分或出生资料。

## 2. 同意与输入

- A、B 必须分别知道用途并同意提交；
- 双方各自完成 12 个 1—5 题；
- 1 表示“非常不符合”，5 表示“非常符合”；
- 用代号，不收真实姓名；
- 不让一方看到另一方逐题答案后再修改自己的答案；
- 任一方不同意、被强迫或答案由另一方代填，停止。

## 3. 执行 SOP

1. 分别向 A、B 展示 `relationship_items.json` 中同一版本题目。
2. 生成输入：

   ```json
   {
     "consent": {"partner_a": true, "partner_b": true},
     "partner_a": {"answers": {"1": 4}},
     "partner_b": {"answers": {"1": 3}}
   }
   ```

3. 收齐双方各 12 题后运行：

   ```bash
   python3 scripts/score_relationship_reflection.py \
     <run_dir>/answers.json \
     --output <run_dir>/facts.json
   python3 scripts/validate_result.py <run_dir>/facts.json
   ```

4. 先检查 `safety.reason_code`：
   - 若为 `E_RELATIONSHIP_SAFETY`，不要显示维度、差异或共同对话提示；分别私下询问双方当前是否感到安全、是否需要暂停共同流程，并转向宿主提供的本地支持；
   - 普通 `validate_result.py` 会按设计拒绝该 facts。改为运行：

     ```bash
     python3 scripts/safety_response.py build \
       <run_dir>/facts.json \
       --output <run_dir>/safety-response.json
     python3 scripts/safety_response.py validate \
       <run_dir>/safety-response.json \
       --source <run_dir>/facts.json
     ```

     只展示通过独立契约校验的固定安全响应；不要再生成 interpretation 或 actions；
   - 不告诉任何一方“另一方具体哪道题触发”，不诊断虐待，不安排双方共同练习；
   - 没有该错误码时，才按“共同资源—差异主题—对话问题”解释，不给总分和排名。

四个维度：

- `emotional_safety`：表达感受与被尊重；
- `repair`：冲突降温与修复；
- `boundaries`：边界、空间与自主；
- `shared_expectations`：金钱、时间与未来期待。

## 4. 解释规则

- 维度差异是双方自报均值的绝对差，不等于谁对谁错。
- 差异小也不代表关系健康；两人可能都对某项评价较低。
- 优先讨论“双方均值较低”或“差异较大”的一个主题。
- 给出可执行的对话句式，例如：
  - “这周有哪一次你觉得我听懂了你？哪一次没有？”
  - “下次争执升温时，我们各自愿意使用什么暂停信号？”
- 不输出匹配率、真爱指数、控制/操纵诊断或分手建议。

## 5. 升级与停止

出现恐惧、胁迫、暴力、跟踪、财务控制或安全风险时，不建议双方共同“沟通练习”；停止问卷，优先个人安全和本地专业支持。

第 3 题和第 9 题是安全关键题。任一方在其中任一题回答 1 或 2，脚本只输出 `E_RELATIONSHIP_SAFETY` 和合并结果抑制标记，不输出关系维度。这个标记是安全核对信号，不是对关系或任何人的诊断。

涉及婚姻法律、共同债务、生育或医疗决定时，只做问题清单，不替代律师、医生或持证咨询专业人员。
