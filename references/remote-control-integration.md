# 宿主远程控制面接入

## 定位

Skill 不直接联网读取某个配置中心。它提供两层能力：

1. 本地原型：随包策略默认开放受限模式，可用安全的本地 JSON 覆盖；
2. 生产运行：元宝服务端从自己的远程控制面取回短期快照，原子挂载给 Skill；`feature_gate.py` 负责验签、TTL、范围、版本和最低 revision。

因此，“远程”来自宿主服务端，Skill 不能单独创造一个远程控制后台。

## 生产环境变量

```text
DIVINATION_CONTROL_PROFILE=production
DIVINATION_FEATURE_CONTROLS_FILE=/absolute/host-mounted/controls.json
DIVINATION_FEATURE_CONTROLS_HMAC_KEY=<至少 32 字节的服务端密钥>
DIVINATION_FEATURE_CONTROLS_MIN_REVISION=<宿主已接受的最低整数 revision>
```

生产模式没有控制文件、使用随包默认文件、签名错误、过期、TTL 超过 15 分钟或 revision 回滚时，统一返回 `E_FEATURE_DISABLED`。

## 快照格式

```json
{
  "schema_version": "2.0.0",
  "revision": "prod-1042",
  "revision_number": 1042,
  "control_plane_id": "yuanbao-divination-prod",
  "issued_at": "2026-07-30T05:00:00+00:00",
  "expires_at": "2026-07-30T05:10:00+00:00",
  "features": {
    "oracle-reflection": {
      "enabled": false,
      "mode": "REFLECTION_ONLY",
      "feature_version": "1.0.0",
      "scopes": ["yuanbao-public-cn"],
      "reason": "运营熔断"
    },
    "chart-generation": {
      "enabled": true,
      "mode": "FACTS_ONLY",
      "feature_version": "1.0.0",
      "scopes": ["yuanbao-public-cn"],
      "reason": "只开放 allowlist 盘面事实"
    },
    "vedic-lite-generation": {
      "enabled": false,
      "mode": "VEDIC_LITE_FACTS_ONLY",
      "feature_version": "1.0.0",
      "scopes": ["yuanbao-public-cn"],
      "reason": "印度占星轻体验独立熔断"
    },
    "traditional-report-interpretation": {
      "enabled": true,
      "mode": "SOURCE_BOUND",
      "feature_version": "1.0.0",
      "scopes": ["yuanbao-public-cn"],
      "reason": "只解释用户提供或可追溯材料"
    }
  },
  "signature": "hmac-sha256:<64 位小写十六进制>"
}
```

实际快照必须同时包含上述四个功能记录。`vedic-lite-generation` 只能进一步关闭印度占星轻体验；它不能绕过 `chart-generation` 总开关。签名对象是移除 `signature` 后，按 UTF-8、键排序、无多余空格序列化的完整 JSON：

```python
canonical = json.dumps(
    unsigned_payload,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
signature = "hmac-sha256:" + hmac.new(
    signing_key,
    canonical,
    hashlib.sha256,
).hexdigest()
```

签名应在控制面完成。不要把签名密钥写入仓库、前端包或控制快照；通过服务端密钥管理系统注入运行环境。

## 宿主 SOP

1. 控制面维护单调递增的 `revision_number`。
2. 服务端签发不超过 15 分钟的完整快照。
3. 拉取进程先验签，再写入同目录临时文件，设置为仅服务账号可读写，最后原子替换正式路径。
4. 每个请求开始、引擎调用前、最终渲染和分享导出前都调用功能门。
5. 网络失联时不延长旧快照；旧快照到期后自动关闭。
6. 支付、分享、推送另设服务端开关，默认关闭。
7. `enabled=true` 只能打开相应受限模式，不能放宽医疗、法律、投资、生育、死亡、赌博、录取录用、第三方隐私或恐吓付费等硬阻断。

HMAC 只验证快照真实性，不替代服务端访问控制、密钥轮换、审计日志和平台审核。
