# 全平台新歌发现器

这是一个基于 Streamlit 的小工具，用来批量抓取指定艺人的候选新歌，并生成适合导出到 Spotify、网易云音乐、QQ 音乐、酷狗音乐等多个平台的歌单文本。它不再限定某个特定流派，适合用来追踪任何风格、任何艺人池。

## 功能

- 支持一次监控多位艺人
- 只保留最近 N 天内发布的歌曲
- 结果表格支持直接点击试听预览
- 支持封面、流派、时长、商店链接展示
- 支持按艺人筛选和排序查看
- 支持手动勾选候选歌曲，整理最终歌单
- 支持按目标平台切换导出文案、文件名与后续入口
- 支持更贴近 Spotify 工作流的深色界面和结果浏览体验
- 支持艺人模板，可一键载入常见流派/风格的艺人名单
- 支持保存、载入、删除你自己的艺人预设
- 支持从页面直接跳转到 TuneMyMusic 导入页面
- 配置 Supabase 后，可跨设备长期保存预设
- 配置 Supabase Auth 后，支持邮箱注册、登录与个人预设
- 自动生成可复制的歌单文本
- 支持导出为 `.txt`
- 支持导出完整结果为 `.csv`
- 支持导出最终选中歌曲的 `.csv`

## 项目结构

```text
Spotify finder/
├─ app.py
├─ requirements.txt
├─ README.md
└─ .streamlit/
   └─ config.toml
```

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

如果你不想手动输入命令，也可以直接双击：

`start_spotify_finder.bat`

它会自动用本机已配置的 Python 运行这个项目，并在窗口里保留启动日志。

启动后，浏览器里会打开本地页面，你可以：

1. 在文本框里填入艺人名单，一行一个
2. 在左侧边栏设置时间范围和抓取数量
3. 点击“抓取新歌”
4. 复制或下载生成的歌单文本

## 发布成网页应用

这个项目很适合直接部署到 Streamlit Community Cloud。

最简流程是：

1. 把项目上传到 GitHub
2. 登录 [Streamlit Community Cloud](https://share.streamlit.io/)
3. 新建应用并选择仓库
4. 主文件填写 `app.py`
5. 点击部署

更详细的步骤见：

`DEPLOY_STREAMLIT_CLOUD.md`

## 依赖

- `streamlit`
- `pandas`
- `requests`

## 说明

当前数据来源是 iTunes Search API，适合做“新歌候选列表”的快速筛选，不保证和 Spotify 上架节奏完全一致。
