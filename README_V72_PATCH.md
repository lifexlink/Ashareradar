# V7.2 Final Patch

修复：
1. 换手率等字段为 0/0.00 时，模板层强制显示为 "-"
2. 完全移除 anti_double_submit.js 的页面引用，避免后台按钮变灰/卡住
3. 保留后端 3 分钟订单去重，支付不会重复生成过多订单
4. /health 版本号更新为 v7.2-final-patch

部署后请：
1. 覆盖上传 GitHub 根目录
2. Commit
3. 等 Railway redeploy
4. 强制刷新浏览器缓存：Cmd+Shift+R
5. 检查 /health 是否为 v7.2-final-patch
