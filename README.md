# hub

一个单页 dashboard,把几个每天更新的 GitHub Pages 站点和一批书/教程汇到一起,方便一眼看到今天有没有新内容。

线上地址:https://yingwang.github.io/hub/

## 它做什么

- **每日更新区**:把 `paper-reads`、`news-reads`、`trade` 三个站做成"活"卡片,在构建时通过 GitHub API 抓各自仓库的最新文件,直接显示最新一条(论文标题加日期 / 最新 brief 日期 / 最新组合与日期),不用点进去就知道有没有新东西。
- **分组入口区**:其余的书与教程按类目(AI/技术、投资、旅行、文化生活、博客)排成链接卡片,直达对应站点。

## 怎么刷新

`build.py` 在构建时拉取最新内容,生成 `docs/index.html`。GitHub Action(`.github/workflows/build.yml`)在:

- 每天 07:25 UTC(夏令时 09:25 CEST,排在早间论文/新闻自动任务之后)
- 手动 `workflow_dispatch`
- 任何推到 `main` 的提交

三种情况下重建并部署到 Pages。页面本身是纯静态的,加载快,不在浏览器里调任何接口。

## 本地预览

```bash
# 用 gh 的 token 避免 GitHub API 限流(可选)
export GITHUB_TOKEN="$(gh auth token)"
python3 build.py
open docs/index.html
```

只用 Python 标准库,无第三方依赖。

## 加 / 改一个站

编辑 `build.py`:

- **日更站**:在 `DAILY` 列表里加一项,并写一个 `latest_*()` 抓取函数,返回 `{"date": ..., "lines": [...]}`。
- **普通链接站**:在 `GROUPS` 里对应分组下加一行 `("显示名", "URL")`。

私有仓库若没有公开 Pages 页面就不要放进来(会 404)。

## 注意

- `trade` 站当前的组合数据停在较早日期,卡片会如实显示其最后一次更新时间,不做掩饰。该站恢复每日更新后卡片会自动跟上。
