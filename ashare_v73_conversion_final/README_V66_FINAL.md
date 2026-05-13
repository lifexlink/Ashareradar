# V6.6 + 复盘增强版

## 新增功能
- /backtest 历史表现页
- /review 每日复盘页
- /feedback 用户反馈页
- /admin/feedback 反馈审核管理
- /methodology 算法说明页
- GitHub Actions 自动保存 data/history/YYYY-MM-DD.json
- 首页展示历史表现摘要与已审核用户反馈

## 算法/产品定位
当前版本定位为“市场观察与数据筛选工具”，不是荐股服务。
算法主要基于：
- 当日涨跌幅
- 成交额
- 成交量
- 换手率
- 涨速/振幅
- ST/退市过滤

## 部署后操作
1. 覆盖上传 GitHub 根目录
2. Commit
3. Railway 自动部署
4. GitHub Actions 手动 Run workflow 一次
5. 打开 /health，确认 history_files >= 1
6. 测试 /backtest /review /feedback
