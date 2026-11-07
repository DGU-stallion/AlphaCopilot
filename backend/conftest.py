"""pytest 全局配置。

v2 换到 Pi 运行时（ADR-0010）后，原先为 dsh SDK 注入源码路径与 node carrier
的逻辑已删除——那些路径指向一个不再存在的仓库，而 Pi 走 `pi --mode rpc`
子进程，不需要 pytest 侧的任何路径准备。

默认排除 `live` 标记的测试（打真实外部端点），见 pyproject.toml 的 addopts。
"""
