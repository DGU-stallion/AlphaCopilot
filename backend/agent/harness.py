"""（已下沉）dsh 适配实现迁至 ``agent.providers.dsh.DshProvider``（ADR-0007 决策 2）。

原 HarnessSession / HarnessSettings / StreamEvent 的 dsh 私有形状不再对外暴露；
业务层只依赖 ``agent.provider`` 的中立契约（AgentProvider / AgentEvent / ProviderSpec）。
本文件保留仅为标记迁移轨迹，不含实现。
"""
