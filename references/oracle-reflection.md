# Commit–Reveal 抽牌反思

## 目录

1. 定位
2. 为什么分两步
3. 功能门
4. 执行 SOP
5. 并发与恢复
6. 验证
7. 解释边界

## 1. 定位

抽牌只提供一个不可按结果重抽的象征提示，用来打破思维惯性。它不预测未来，也不证明超自然因果。

## 2. 为什么分两步

单纯在出牌后展示哈希，只能证明文件没被修改，不能证明平台没有挑选想要的结果。两步 commit–reveal 先锁定服务器随机种子，再加入用户提供的 `client_seed` 派生结果，减少事后操纵空间。

它仍不是密码学意义上的公共随机信标：服务器在 commit 前仍可选择种子。结果中必须如实称为“可复核的承诺—揭示流程”，不写“绝对公平”。

## 3. 功能控制

`REFLECTION_ONLY` 默认可用。宿主需要复查或熔断时运行：

```bash
python3 scripts/feature_gate.py \
  oracle-reflection \
  --controls <host_feature_controls>
```

原型没有显式路径时使用 `scripts/feature_controls.default.json`。宿主控制文件关闭、过期、版本或范围不匹配时返回 `E_FEATURE_DISABLED`，不要继续。生产环境按 [remote-control-integration.md](remote-control-integration.md) 接入：宿主负责远程拉取和原子挂载，Skill 验签、检查短 TTL 并失败关闭；本地 JSON 本身不是安全边界。

## 4. 执行 SOP

1. 把问题改成低风险、可反思、可行动的形式，例如：
   - “我该如何保证投资必赚？”应拒绝预测并转为风险清单；
   - “面对这个选择，我忽略了什么信息？”可以运行。
2. 创建权限为 0700 的私有单次运行目录，把命令返回的绝对路径记为 `<run_dir>`：

   ```bash
   python3 scripts/secure_run_dir.py create
   ```

3. 创建承诺：

   ```bash
   python3 scripts/reflection_draw.py commit \
     --state <run_dir>/draw-state.json
   ```

4. 只有命令成功后，才把 stdout 中的 `commitment`、`deck_version`、`deck_hash` 和 `control_revision` 展示给用户。绝不虚构一个看起来像哈希的值。
5. 请用户任意给出一段非敏感 `client_seed`，例如一个词或随机数字；不要替用户挑。使用安全文件写入能力保存为权限 0600 的 `<run_dir>/client-seed.txt`，不要把用户文本拼进 shell 命令。
6. 揭示：

   ```bash
   python3 scripts/reflection_draw.py reveal \
     --state <run_dir>/draw-state.json \
     --client-seed-file <run_dir>/client-seed.txt \
     --output <run_dir>/facts.json
   ```

7. 运行：

   ```bash
   python3 scripts/validate_result.py <run_dir>/facts.json
   ```

8. 输出牌名、正逆位、验证字段、2—4 个开放问题和一个可逆行动，再按 [output-contracts.md](output-contracts.md) 生成并校验 final JSON。
9. 在完成、取消或失败后的 `finally` 中运行 `secure_run_dir.py create` 返回的精确 cleanup 命令。宿主仍需处理聊天记录、备份和日志生命周期。

## 5. 并发与恢复

- 脚本用跨进程排他锁保护状态。两个不同 seed 并发揭示时，只允许一个成功。
- 首次成功揭示后，状态原子保存唯一 `revealed_result`。
- 使用同一 seed 重试只返回已经保存的同一个结果，不重新计算。
- 使用不同 seed 重试返回 `E_DRAW_STATE`。
- 导出文件失败时，已揭示结果仍保存在私有状态。用下列命令重导出，不重抽：

  ```bash
  python3 scripts/reflection_draw.py export \
    --state <run_dir>/draw-state.json \
    --output <run_dir>/recovered-facts.json
  ```

状态文件包含尚未揭示的服务器随机种子和揭示后的完整结果，只能短暂保留在私有运行目录，不得上传到公共位置。

## 6. 验证

先把 `oracle_deck.json` 按 UTF-8、JSON key 排序、无多余空白规范化，然后：

```text
deck_hash = SHA256(canonical_json(oracle_deck.json))
```

承诺：

```text
commitment = SHA256("divination-assessment|commit|"
                    + deck_version + "|" + deck_hash + "|" + server_seed)
```

抽取：

```text
digest = HMAC-SHA256(
  key = bytes.fromhex(server_seed),
  message = "divination-assessment|draw|" + deck_version + "|" + deck_hash
            + "|" + client_seed
)
card_index = digest 的前 8 字节按无符号大端整数 mod 22
orientation = digest 的第 9 字节最低位；0 为正位，1 为逆位
```

揭示结果包含 `server_seed_reveal`，用户可复算 deck hash、commitment 和 digest。修改牌名、顺序或其他牌组内容会改变 deck hash，从而使验证失败。

## 7. 解释边界

合格：

- “抽到‘隐者·正位’。把它当成一个提问镜头：这件事里，哪些答案需要你先独处核对，而不是继续收集他人的意见？”

不合格：

- “隐者说明 TA 一定会离开。”
- “逆位代表你会生病。”
- “再付费抽三张才能化解。”

不根据用户期待重抽，不把逆位说成坏运，不制造依赖或稀缺感。

final 结果还必须包含 [safety-and-compliance.md](safety-and-compliance.md) 规定的 AI 生成和用途边界声明。
