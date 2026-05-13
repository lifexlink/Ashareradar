# V6 半自动增强收款版

## 新增功能
- 用户付款后生成唯一订单号
- 用户可在“我的订单”查看订单状态
- 管理员后台按订单审核
- 一键“确认到账并开通”
- 支持拒绝订单
- 上传 JSON 同时兼容列表格式和 `{"signals":[...]}` 格式
- `ADMIN_PASSWORD` 支持 Railway Variables 配置

## 部署
解压后，把里面的文件覆盖上传到 GitHub 仓库根目录，Railway 会自动 redeploy。

## 建议 Railway Variables
- SECRET_KEY=一串复杂随机字符
- ADMIN_PASSWORD=你的新管理员密码

## 注意
如果已有旧数据库，`orders` 表会自动创建，不影响原有用户。
