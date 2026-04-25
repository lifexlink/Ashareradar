# V7 迁移/换服务器指南

1. 旧站后台 → 导出数据，保存 `ashare_v7_backup.json`
2. 新服务器部署 V7 代码
3. 配置环境变量：SECRET_KEY、ADMIN_PASSWORD
4. 打开 /health 确认系统正常
5. 后台 → 导入数据 → 上传备份 JSON
6. 检查用户、订单、到期时间是否恢复

真实收款码放：
- static/wechat_qr.jpg
- static/alipay_qr.jpg
