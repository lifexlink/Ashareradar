# V7.1 Patch

修复：
1. 数据源页面中文化
2. 换手率 0 / 0.00 显示为 "-"
3. anti_double_submit.js 只作用于支付页，避免后台变灰/卡住
4. /health 增加 version: v7.1-patch 和 source_label

部署后：
1. 覆盖上传 GitHub 根目录
2. Commit
3. 等 Railway Online
4. GitHub Actions 手动 Run workflow 一次
5. 检查 /health
