# AdGuard-Rules

将第三方过滤器 **anti-AD** 与 AdGuard 官方内置过滤器做**去重**后的订阅列表，通过 GitHub Actions 每日自动更新。

## 订阅地址（在 AdGuard App 中添加自定义过滤器时填写）

```
https://raw.githubusercontent.com/Alizesa/AdGuard-Rules/main/antiad-deduped.txt
```

国内访问建议走 CDN：

```
https://cdn.jsdelivr.net/gh/Alizesa/AdGuard-Rules@main/antiad-deduped.txt
```

> 在 AdGuard App 里：请先**停用**原始的 `anti-ad.net/adguard.txt`（或 easylist）订阅，
> 改为订阅上面这个生成列表，避免重复叠加。

## 这是什么

`anti-AD`（[anti-ad.net](https://anti-ad.net/)）本质上是一个域名黑名单（全部是 `||域名^`
无修饰符规则）。如果你同时启用了 AdGuard 官方过滤器（基础、防跟踪、移动广告、中文等），
其中约 **46%** 的域名其实已经被 AdGuard 官方过滤器覆盖了，属于冗余规则。

本项目通过 GitHub Actions 每天自动：

1. 拉取最新 `https://anti-ad.net/adguard.txt`（anti-AD 的 AdGuard 专用版本）；
2. 拉取 7 个 AdGuard 官方优化过滤器（与 App 内启用集保持一致）；
3. 保守去重，生成 `antiad-deduped.txt`；
4. 有变化时自动提交回本仓库。

去重后列表从 ~99,000 条降到 ~53,000 条，下载 / 编译 / 内存占用明显减小。

## ⚠️ 重要：必须保持这些 AdGuard 官方过滤器启用

去重是基于"AdGuard 官方已拦截该域名"的前提。请在你的 AdGuard App 中**始终启用**以下过滤器，
否则生成列表里被去掉的规则会失去覆盖、出现漏拦：

| ID | 过滤器 |
|----|--------|
| 2  | AdGuard 基础过滤器 |
| 3  | AdGuard 防跟踪保护过滤器 |
| 11 | AdGuard 移动广告过滤器 |
| 19 | AdGuard 弹窗过滤器 |
| 20 | AdGuard 移动拦截程序横幅广告过滤器 |
| 21 | AdGuard 其他恼人广告过滤器 |
| 224 | AdGuard 中文过滤器 |

如果你想调整去重基准集，修改 `scripts/dedupe.py` 里的 `ADGUARD_FILTERS` 列表，并同步更新
`.github/workflows/dedupe.yml` 的下载循环。

## 去重逻辑（保守，保证不漏拦）

- 只对**无修饰符**的 `||域名^` 规则做去重（有 `$domain=`、`$third-party` 等修饰符的规则
  覆盖范围不完整，一律视为不可覆盖）；
- 父域名覆盖（如 AdGuard 拦截 `||example.com^` 时，去掉 anti-AD 的 `||sub.example.com^`）
  仅在 **没有** 全域名 `@@` 例外指向该域名或其父域名时生效；
- anti-AD 自身的 `@@` 放行规则与含通配符的规则**原样保留**，去重不会丢失 anti-AD 明确添加的行为。

## 手动运行

```bash
# 需要 Python 3.8+
mkdir -p lists
curl -fsSL -o lists/anti-ad.txt https://anti-ad.net/adguard.txt
for id in 2 3 11 19 20 21 224; do
  curl -fsSL -o "lists/adguard_${id}.txt" \
    "https://filters.adtidy.org/android/filters/${id}_optimized.txt"
done
python scripts/dedupe.py
```

脚本选项：

```bash
python scripts/dedupe.py --no-parent   # 关闭父域名覆盖，只做精确匹配去重（更保守）
```

## 许可

- anti-AD：MIT（[privacy-protection-tools/anti-AD](https://github.com/privacy-protection-tools/anti-AD)）
- AdGuard 官方过滤器：GPLv3（[adguard.com](https://adguard.com/)）

本仓库生成的列表是上述两者的派生数据，仅供个人使用，请保留相应出处。
