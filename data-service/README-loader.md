# loader.py 使用说明（M3-V3）

把 `vendor/a-stock-data/SKILL.md` 的 91 个 python 块加载成可调用能力。

```python
import sys; sys.path.insert(0, "src")
import loader

ns = loader.load()                    # 加载全部能力（0.4 秒，不联网）
fn = loader.callables(ns)             # 101 个 vendor 自定义公开函数
caps = loader.list_capabilities()     # 104 个带文档说明的（给 agent 的清单）
```

## 三条硬纪律

1. **不联网**。加载只做「解析 + exec 定义」，任何顶层示例调用都会被剥掉。
   实测过：不剥会真的取数，某块卡 16.7 秒。`test_loads_without_network` 用
   socket 拦截钉住这条。
2. **不复制代码**。vendor 是唯一真源，升级只替换文件，不产生第二套实现。
3. **单块失败不中断**。已知三类：`mootdx` 缺依赖（有意不装）、前向引用
   （SKILL.md 不按依赖排序）、非 python 片段。跳过即可，调用时才报错更准确。

## 为什么不把 87/101 的数字写死

文档的 87 是「能力入口」口径（README 有 88−1−1+1 的说明），与「函数个数」不是一回事。
测试用区间（80~130）而不是等号，避免上游小改动就红；同时用
`test_excludes_third_party_imports` 防止把 `HTTPAdapter`/`Path` 这类 import 混进能力清单。
