# 涨停雷达 V4 网页收费版

这是一个可部署的 Flask 网页版 MVP，包含：
- 注册 / 登录
- 免费 / 付费分级查看
- 套餐页（周卡 / 月卡 / 年卡）
- 微信 / 支付宝扫码页（先用占位图，替换成你的真实二维码）
- 管理后台：核对付款后手动开通权限
- 样例数据页：data/latest_signals.json

## 本地运行
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python init_db.py
python app.py
```
打开 http://127.0.0.1:5000

默认管理员：
- 用户名：admin
- 密码：admin123

## 替换收款码
把 `static/wechat_qr_placeholder.svg` 和 `static/alipay_qr_placeholder.svg`
替换成你的真实二维码图片，文件名保持不变即可，或同步修改 pay.html 中的文件名。

## 替换真实选股数据
把你的选股脚本输出到 `data/latest_signals.json`

## 部署
- Railway 官方 Flask 指南说明支持一键从模板、CLI、GitHub 仓库或 Dockerfile 部署。
- Render 官方 Flask 文档说明可以把 Flask 作为 Web Service 从 GitHub 仓库直接部署。


## V4.1 修复说明
- 已将密码哈希方式改为 `pbkdf2:sha256`，避免部分 Python 3.9 / macOS 环境缺少 `hashlib.scrypt` 导致初始化失败。


## V4.2 修复说明
- 新增独立管理员登录页：`/admin-login`
- 非管理员访问 `/admin` 时会强制跳转到管理员登录页
- 后台页面明确显示“开通权限”按钮


## V4.3 修复说明
- 修复支付申请提交时报 `NoneType` 的问题：当浏览器 session 还在、但数据库用户不存在时，会自动清理登录状态并要求重新登录。
- `data/latest_signals.json` 仍然是演示数据，不是 V1/V2 的实时抓取结果；如要一致，请把 V1/V2 生成的 JSON 覆盖到这里。


## V4.4 新增功能
- 后台支持直接上传 `latest_signals.json`
- 上传成功后，前台数据页立即显示新的真实选股结果
- 适合把 V1/V2 的输出无缝接进收费网页版
