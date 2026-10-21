"""vendor 调用的 worker（M3-V5）。在 data-service 的 venv 里跑。

协议：stdin 一行 JSON → stdout 一行 JSON。**stdout 必须只有 JSON**。

⚠️ 这是本文件存在的第二个理由：vendor 的代码块里有大量 `print(...)`
（示例块的打印语句）。如果不把 stdout 重定向走，它们会混进协议输出，
后端 `json.loads` 就炸 —— 而且报错信息会是一堆用户数据，很难看出根因。
所以这里在加载 vendor 之前就把 sys.stdout 换成 sys.stderr，
最后只把结果打到真正的 stdout 上。
"""

from __future__ import annotations

import io
import json
import sys
import traceback
from pathlib import Path


def main() -> int:
    raw = sys.stdin.read()

    # ---- 把真 stdout 存下来，然后立刻劫持 stdout 到 stderr ----
    real_stdout = sys.stdout
    sys.stdout = sys.stderr

    def emit(payload: dict) -> None:
        real_stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        real_stdout.flush()

    try:
        req = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        emit({"ok": False, "error": f"输入不是合法 JSON: {e}"})
        return 1

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import loader
    except Exception as e:  # noqa: BLE001
        emit({"ok": False, "error": f"loader 导入失败: {e}"})
        return 1

    action = req.get("action", "invoke")

    if action == "list":
        try:
            emit({"ok": True, "result": loader.list_capabilities()})
        except Exception as e:  # noqa: BLE001
            emit({"ok": False, "error": f"列举能力失败: {e}"})
            return 1
        return 0

    if action != "invoke":
        emit({"ok": False, "error": f"未知 action: {action!r}（只支持 list / invoke）"})
        return 1

    name = req.get("name")
    if not isinstance(name, str) or not name:
        emit({"ok": False, "error": "缺少 name"})
        return 1
    if name.startswith("_"):
        # 私有函数不是能力入口。暴露它们等于把 vendor 的内部实现变成 API，
        # 上游一改就断，而我们承诺不了它的稳定性。
        emit({"ok": False, "error": f"不暴露私有函数: {name}（以 _ 开头）"})
        return 1

    try:
        ns = loader.load()
    except Exception as e:  # noqa: BLE001
        emit({"ok": False, "error": f"vendor 加载失败: {e}"})
        return 1

    fn = ns.get(name)
    if fn is None or not callable(fn):
        emit({"ok": False, "error": f"vendor 里没有可调用能力: {name}"})
        return 1

    args = req.get("args") or []
    kwargs = req.get("kwargs") or {}
    if not isinstance(args, list) or not isinstance(kwargs, dict):
        emit({"ok": False, "error": "args 必须是数组、kwargs 必须是对象"})
        return 1

    # 参数类型预检：vendor 大量函数用 `dict[str, ...]` 注解，但**传错类型时
    # 往往静默返回空 dict**（实测 tencent_quote(codes="600519") → {}）。
    # 静默空结果是最危险的失败模式：调用方（尤其是 agent）会把它理解成
    # 「这只票没有数据」，然后自己编一个数出来。本项目已经栽过一次。
    # 所以这里在调用前用签名注解做一次轻量检查，把「类型错了」明确说出来。
    try:
        import inspect as _inspect
        sig = _inspect.signature(fn)
        sig.bind(*args, **kwargs)          # 参数个数/名字不对 → TypeError
    except TypeError as e:
        emit({"ok": False, "error": f"参数不匹配 {name}: {e}"})
        return 1
    except (ValueError, AttributeError):
        pass                               # 没有签名（C 扩展等）就跳过检查

    try:
        result = fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        # 调用失败要带类型与栈尾部：缺依赖（mootdx）与参数错要能区分开。
        # 只回 str(e) 的话，「ModuleNotFoundError」和「TypeError」看起来一样。
        emit({
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc()[-1500:],
        })
        return 1

    emit({"ok": True, "result": _serialize(result)})
    return 0


def _serialize(obj: object) -> object:
    """把 pandas DataFrame / numpy 标量之类转成 JSON 友好结构。

    vendor 大量返回 DataFrame —— 直接 json.dumps 会失败。
    这里转成 `{columns, rows}`，与页面 spec 的 table 形状一致，
    前后端都不用为每个端点写转换。
    """
    # pandas 不一定装得上（data-service 装了，但要防御）
    try:
        import pandas as pd
    except ImportError:
        pd = None

    if pd is not None:
        if isinstance(obj, pd.DataFrame):
            return {
                "columns": [str(c) for c in obj.columns],
                "rows": obj.astype(object).where(obj.notna(), None).values.tolist(),
            }
        if isinstance(obj, pd.Series):
            return {
                "columns": ["index", "value"],
                "rows": [[str(i), None if pd.isna(v) else v] for i, v in obj.items()],
            }

    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_serialize(v) for v in obj]

    # numpy 标量等：有 item() 就取标量值
    item = getattr(obj, "item", None)
    if callable(item):
        try:
            return item()
        except (ValueError, AttributeError):
            pass
    return str(obj)


if __name__ == "__main__":
    sys.exit(main())
