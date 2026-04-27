# 部署到 Streamlit Community Cloud

这个项目已经是 Streamlit 应用，部署成网页应用最简单的方式就是用 Streamlit Community Cloud。

## 你需要准备

1. 一个 GitHub 账号
2. 把这个项目上传到一个 GitHub 仓库
3. 一个 Streamlit Community Cloud 账号

## 第一步：上传到 GitHub

建议把下面这些文件放进仓库：

- `app.py`
- `requirements.txt`
- `README.md`
- `.streamlit/config.toml`
- `DEPLOY_STREAMLIT_CLOUD.md`
- `.gitignore`

不建议上传这些本地文件：

- `start_spotify_finder.bat`
- `streamlit.log`
- `streamlit-error.log`
- `user_artist_templates.json`
- `__pycache__/`

## 可选：配置长期保存的在线预设

如果你希望“我的预设”在网页应用里也能长期保存，并且跨设备同步，推荐使用免费的 Supabase 数据库。

### 1. 在 Supabase 创建项目

打开 [Supabase](https://supabase.com/) 后：

1. 新建一个项目
2. 进入 `SQL Editor`
3. 执行下面这段 SQL

```sql
create table if not exists public.artist_presets (
  namespace text not null,
  name text not null,
  artists text not null,
  updated_at timestamptz not null default now(),
  primary key (namespace, name)
);
```

### 2. 开启表的 API 访问

这个项目通过 Supabase 的 REST API 读写 `artist_presets`。

你需要在项目里拿到：

- `Project URL`
- `anon public key`

### 3. 在 Streamlit Cloud 里配置密钥

部署应用后，打开应用设置，把下面两个 Secrets 配进去：

```toml
SUPABASE_URL = "你的 Supabase Project URL"
SUPABASE_ANON_KEY = "你的 Supabase anon key"
```

配置完成后，应用里的“我的预设”就会自动切换成云端同步模式。

### 4. 怎么实现跨设备同步

页面左侧有一个“预设空间名”输入框。

只要你在不同电脑、不同浏览器里填写同一个空间名，再点击“加载这个空间”，就能看到同一组预设。

## 第二步：在 Streamlit Community Cloud 部署

1. 打开 [Streamlit Community Cloud](https://share.streamlit.io/)
2. 用 GitHub 登录
3. 点击 `New app`
4. 选择你的 GitHub 仓库
5. 主文件填：`app.py`
6. 点击 `Deploy`

部署成功后，你会得到一个公开网址，别人直接打开这个网址就能使用。

## 第三步：以后怎么更新

以后你只要：

1. 修改本地项目文件
2. 提交并推送到 GitHub
3. Streamlit Cloud 会自动重新部署

## 注意事项

### 1. 没配 Supabase 时，预设只保存在本地文件

如果你没有配置 Supabase，应用仍然可以运行，但“我的预设”只会写入本地文件：

`user_artist_templates.json`

这种方式适合本地使用，不适合正式网页部署。

### 2. 当前项目适合公开轻量使用

这个应用现在很适合：

- 你自己使用
- 给朋友或客户试用
- 作为作品集演示

如果以后访问量明显变大，再考虑迁移到 Render、Railway 或自己的服务器。

## 推荐做法

先部署到 Streamlit Community Cloud，先拿到一个能分享的网址。等你确认这个工具真的会长期使用，再决定要不要加数据库、登录或更正式的后端。
