from typing import Optional
from pydantic import BaseModel, Field


class Config(BaseModel):
    """JMComic Plugin Configuration"""

    # 网络代理设置，例如 http://127.0.0.1:7890 或 socks5://127.0.0.1:7890
    jm_proxy: Optional[str] = Field(default=None, description="HTTP/SOCKS代理地址，例如 http://127.0.0.1:7890")

    # 客户端实现模式：'api'（APP端接口，免梯稳定性高）或 'html'（网页端）
    jm_client_impl: str = Field(default="api", description="客户端实现：api 或 html，推荐 api")

    # 本子及文件下载目录
    jm_download_dir: str = Field(default="data/jmcomic/downloads", description="本子保存根目录")

    # 缓存目录（用于存放封面图、预览图缓存）
    jm_cache_dir: str = Field(default="cache/jmcomic", description="临时图片缓存目录")

    # 权限控制：是否仅允许超级用户/群管理员使用下载功能
    jm_admin_only_download: bool = Field(default=True, description="是否仅限超级用户/管理员使用下载指令")

    # 预览的最大页数（防止图片过多导致腾讯风控封禁）
    jm_max_preview_pages: int = Field(default=5, description="单次预览图片最大张数")

    # 是否允许在群聊中使用（若为False则仅允许私聊）
    jm_allow_group: bool = Field(default=True, description="是否允许在群聊中触发指令")

    # 指令冷却时间（秒，0为不限制，针对普通用户防止高频刷屏）
    jm_cd: int = Field(default=5, description="指令冷却时间（秒）")

    # 命令优先级
    jm_command_priority: int = Field(default=10, description="命令匹配优先级")

    # 账号 Cookie（AVS），用于需登录或敏感限制本子
    jm_cookies_avs: Optional[str] = Field(default=None, description="禁漫 AVS Cookie（可选）")

    # 禁漫账号密码（可选，用于自动登录）
    jm_username: Optional[str] = Field(default=None, description="禁漫账号用户名（可选）")
    jm_password: Optional[str] = Field(default=None, description="禁漫账号密码（可选）")
