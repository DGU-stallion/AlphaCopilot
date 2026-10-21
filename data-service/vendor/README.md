# data-service/vendor — 只读区

整个 `vendor/` 目录是上游项目的**原样拷贝，只读**：

- **禁止任何手工编辑**（改一个空格都不行）——改了就会在下一次同步（M3-V6）
  时冲突，然后有人手工 merge，然后这份 vendor 就变成「我们自己维护的分支」。
  上一次 v3.3 移植就是这么烂掉的，不能重演。
- 本地适配（loader / 抽代码 / 缓存 / HTTP 暴露）全部写在 `data-service/src/` 内。
- 更新唯一路径：同步脚本 `scripts/vendor-a-stock-data.sh`（M3-V6）整目录覆盖。
- 版本钉死在 `vendor/a-stock-data/NOTICE`（commit `29b07d2e3700`，V3.10.2），
  sha256 一并记录在那里。

## CI 校验

CI 会用下面这条命令校验这个目录无本地改动（建议的 job 定义见
`data-service/README.md` 末尾；写入 `.github/workflows/ci.yml` 是后续任务）：

```bash
git diff --exit-code data-service/vendor/
```

任何对 `vendor/` 的未提交改动都会让这条命令非零退出 → CI 红。
