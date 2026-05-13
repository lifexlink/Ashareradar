# V6.2 防重复提交 + 实时数据加强版

## 修复
- 前端提交后按钮立即禁用，防止用户重复点击
- 后端增加 3 分钟内同用户同套餐待审核订单去重
- `/health` 显示 signals/source/generated_at，方便确认是否实时数据

## 数据
- 云端脚本优先尝试 AKShare 实时行情接口
- 成功时 source 会显示 `live-...`
- 失败时 source 会显示 `fallback-demo`，并在 reason 里标注原因

## 部署
解压后覆盖上传 GitHub 根目录，Commit 后 Railway 自动部署。
部署后去 GitHub Actions 手动 Run workflow 一次，再访问 `/health` 检查 source。
