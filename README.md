<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="https://github.com/nonebot/nonebot2/raw/master/docs/guide/images/logo.png" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://github.com/nonebot/nonebot2/raw/master/docs/guide/images/NoneBot.svg" width="240" alt="NoneBotPluginText"></p>
</div>

<div align="center">

# nonebot-plugin-jmcomic

_✨ 基于 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python) 的 NoneBot2 禁漫天堂插件 ✨_

<p align="center">
  <a href="https://raw.githubusercontent.com/YourUsername/nonebot-plugin-jmcomic/master/LICENSE">
    <img src="https://img.shields.io/github/license/YourUsername/nonebot-plugin-jmcomic.svg" alt="license">
  </a>
  <a href="https://pypi.python.org/pypi/nonebot-plugin-jmcomic">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-jmcomic.svg" alt="pypi">
  </a>
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="python">
  <a href="https://nonebot.dev/">
    <img src="https://img.shields.io/badge/nonebot-2.2.0+-red.svg" alt="NoneBot">
  </a>
  <a href="https://onebot.adapters.nonebot.dev/">
    <img src="https://img.shields.io/badge/adapter-OneBot%20V11-orange.svg" alt="OneBot V11">
  </a>
</p>

</div>

---

## 📖 介绍

`nonebot-plugin-jmcomic` 是一款专为 **NoneBot2 (OneBot V11 适配器)** 打造的禁漫天堂助手插件。

底层接入并适配了社区优秀的爬虫框架 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)，具备**智能图片切片反混淆还原**、**动态 API 域名更新**与**高并发无损合成 PDF** 等强大特性。

### 🌟 核心特色
- 📄 **车号直出全本 PDF**：输入车号直接在后台并发下载、自动解密反混淆，并利用 `img2pdf` 无损合并为单份高质量 PDF 电子书直接发送给用户。
- 🤫 **零冗余清爽交互**：无任何前置等待提示与生成成功长文本刷屏，纯净直传文件。
- 🔍 **站内精准搜索**：支持关键词站内搜索与分页浏览。
- 🛡️ **安全合并转发预览**：章节预览通过 OneBot V11 自定义转发节点（Forward Node）发出，卡片收拢不刷屏、大幅降低 QQ 风控概率。
- 📦 **整本 ZIP 打包**：支持将本子打包为标准 ZIP 文件推送。
- 🏆 **全站排行榜**：随时掌握禁漫日榜、周榜、月榜热门动态。
- ⏱️ **频率冷却防护**：内置普通群友 CD 防刷屏保护，管理员免 CD。

---

## 💿 快速安装

### 方式一：使用 nb-cli 安装（推荐）
在 NoneBot2 项目根目录下执行：
```bash
nb plugin install nonebot-plugin-jmcomic
```

### 方式二：使用包管理器安装
```bash
# 使用 pip
pip install nonebot-plugin-jmcomic

# 若网络较慢可使用清华镜像
pip install nonebot-plugin-jmcomic -i https://pypi.tuna.tsinghua.edu.cn/simple
```
随后在 NoneBot2 项目的 `pyproject.toml` 的 `plugins` 列表中加入：
```toml
plugins = ["nonebot_plugin_jmcomic"]
```

### 方式三：源码直接引入
克隆或下载本项目至机器人工程的自定义插件目录（例如 `plugins/nonebot_plugin_jmcomic`），并在对应配置中加载即可。

---

## ⚙️ 配置说明

在机器人根目录下的 `.env`（或 `.env.dev` / `.env.prod`）中添加以下可选配置：

| 配置项 | 类型 | 默认值 | 详细说明 |
| :--- | :--- | :--- | :--- |
| `JM_PROXY` | `str` | `None` (跟随系统) | 网络代理地址。例如本地开有代理，填 `http://127.0.0.1:7890`。若需直连填 `null` 或留空。 |
| `JM_CLIENT_IMPL` | `str` | `api` | 客户端实现：`api`（APP端接口）或 `html`（网页端）。**推荐保留 `api`**，APP 端不限 IP 地区，免翻直连率极高。 |
| `JM_DOWNLOAD_DIR` | `str` | `data/jmcomic/downloads` | 本子、PDF 及 ZIP 文件的本地保存目录。 |
| `JM_CACHE_DIR` | `str` | `cache/jmcomic` | 临时图片与封面图的本地缓存目录。 |
| `JM_MAX_PREVIEW_PAGES` | `int` | `5` | 章节单次预览的最大图片张数（建议 3~5 张，防止风控）。 |
| `JM_ADMIN_ONLY_DOWNLOAD` | `bool` | `true` | 整本 ZIP 下载功能是否仅限群管理/超级用户使用。 |
| `JM_ALLOW_GROUP` | `bool` | `true` | 是否允许在群聊中触发指令（为 `false` 则仅允许私聊）。 |
| `JM_CD` | `int` | `5` | 普通用户触发指令的冷却时间（秒，超级用户免 CD）。 |
| `JM_COOKIES_AVS` | `str` | `None` | 禁漫网页端 AVS Cookie（可选，用于解锁需登录的敏感限制本子）。 |

### 配置范例 (.env)
```ini
# JMComic 插件配置
JM_PROXY=http://127.0.0.1:7890
JM_CLIENT_IMPL=api
JM_MAX_PREVIEW_PAGES=5
JM_CD=5
```

---

## 🎮 指令说明

> 💡 **提示**：指令前缀取决于你机器人的 `COMMAND_START` 配置（例如 `/` 或空前缀）。

| 指令 | 别名 | 权限 | 详细说明与示例 |
| :--- | :--- | :--- | :--- |
| `jm <车号>` | `车牌`、`禁漫`、`jmpdf` | 所有人 | **下载并直接发送全本 PDF 文档**。<br>示例：`jm 427413`、`车牌 JM427413`、`jm https://18comic.vip/album/427413` |
| `jmcard <车号>` | `jm详情`、`jminfo`、`jm卡片` | 所有人 | 仅查看本子封面、作者、标签与章节列表（不下载大文件）。<br>示例：`jmcard 427413` |
| `jmsearch <关键词> [页码]` | `搜本子`、`搜车牌`、`jm搜索` | 所有人 | 站内关键词模糊搜索与翻页。<br>示例：`jmsearch 碧蓝航线`、`jmsearch 东方 2` |
| `jmpreview <车号> [话数] [张数]` | `jm预览`、`看本子` | 所有人 | 反混淆解码并以**合并转发卡片**形式发送预览图。<br>示例：`jmpreview 427413 1 5` |
| `jmdownload <车号>` | `jm下载`、`下载本子` | 管理员 | 下载整本并打包为 `.zip` 压缩文件推送。<br>示例：`jmdownload 427413` |
| `jmrank [日/周/月]` | `jm排行`、`禁漫排行` | 所有人 | 获取禁漫今日日榜、本周周榜或本月月榜。<br>示例：`jmrank`、`jmrank 周` |
| `jmhelp` | `jm帮助` | 所有人 | 查看插件全部指令说明菜单。 |

---

## 🛡️ QQ 运营与防风控建议

1. **坚持使用合并转发**：连续在群内直接发图是腾讯风控的最常见拦截点。本插件的 `jmpreview` 采用合并转发节点聚合，极大降低了违规风险。
2. **控制预览张数**：建议保持默认的 3~5 张预览，不要随意在群里大批量请求图片。
3. **大文件下载限制**：整本 ZIP 下载（`jmdownload`）默认限制为管理员可用，避免群友无节制并发调用耗尽服务器带宽。
4. **网络代理配置**：若服务器位于国内，推荐搭配本地 Clash 或 v2ray 代理端口（`JM_PROXY`）使用，确保请求禁漫稳定不掉线。

---

## 🙏 致谢与声明

- 核心爬虫能力来自于开源项目 [hect0x7/JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)，感谢原作者的持续维护！
- 机器人框架依赖于 [NoneBot2](https://github.com/nonebot/nonebot2) 与 [OneBot V11](https://github.com/botuniverse/onebot-11)。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 协议开源。
