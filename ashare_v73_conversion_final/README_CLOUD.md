# 云端自动赚钱版说明

## 这版实现了什么
- 网页站点长期在线
- GitHub Actions 定时自动运行 `cloud_update/generate_signals_cloud.py`
- 自动更新 `data/latest_signals.json`
- 你的 Flask 网站自动读取最新 JSON
- 你电脑不用开着

## 推荐部署架构
### 方案 A（最推荐）
1. GitHub 仓库托管代码
2. GitHub Actions 定时更新 JSON
3. Railway 或 Render 部署网页
4. 平台跟随 GitHub 提交自动部署

## 本地测试
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python init_db.py
PORT=5001 python app.py
```

## 云端上线步骤
### 1. 上传到 GitHub
把整个项目推到 GitHub 仓库。

### 2. 启用 GitHub Actions
仓库里已经有：
`.github/workflows/update_signals.yml`

它支持：
- 定时运行
- 手动运行

### 3. 部署到 Railway 或 Render
- Railway：连接 GitHub 仓库，使用 `Procfile` 启动
- Render：创建 Web Service，构建命令 `pip install -r requirements.txt`，启动命令 `gunicorn app:app`

### 4. 设置环境变量
至少设置：
- `SECRET_KEY`

## 收第一单建议
- 周卡先低价试卖
- 先卖“研究工具”和“候选池”
- 不要宣传“稳赚”或“必涨”

## 注意
`cloud_update/generate_signals_cloud.py` 里当前是“简化版自动评分 + 演示回退”。
如果你要完全沿用 V1/V2 的逻辑，可以把 V1/V2 的核心评分逻辑替换进这个脚本。


## V5.1 修复说明
- 修复 Railway/Render 云端注册时报 Internal Server Error 的问题。
- 原因：云端使用 `gunicorn app:app` 启动时不会执行 `python init_db.py`。
- 解决：在 `app.py` 被 gunicorn 加载时自动执行 `init_db()`。
- 新增 `/health` 检查入口，用于确认数据库是否正常初始化。
