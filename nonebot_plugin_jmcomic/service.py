import os
import re
import asyncio
import zipfile
import shutil
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

import jmcomic
from jmcomic import (
    JmOption,
    JmAlbumDetail,
    JmPhotoDetail,
    JmSearchPage,
    JmcomicException,
    MissingAlbumPhotoException,
    RequestRetryAllFailException,
)
from nonebot import get_plugin_config
from nonebot.log import logger

from .config import Config

def _get_config() -> Config:
    try:
        return get_plugin_config(Config)
    except Exception:
        return Config()

config = _get_config()


class JMService:
    def __init__(self):
        self._option: Optional[JmOption] = None
        self._cache_dir = Path(config.jm_cache_dir)
        self._download_dir = Path(config.jm_download_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._download_dir.mkdir(parents=True, exist_ok=True)

    def get_option(self) -> JmOption:
        """获取并构建 JmOption 配置对象"""
        if self._option is not None:
            return self._option

        # 构造 YAML 配置字典
        proxy_val = config.jm_proxy if config.jm_proxy else "system"
        # 允许禁用代理
        if config.jm_proxy and config.jm_proxy.lower() in ("null", "none", "disable", "false"):
            proxy_val = "null"

        client_impl = config.jm_client_impl or "api"

        yaml_lines = [
            "log: false",
            "client:",
            f"  impl: {client_impl}",
            "  retry_times: 3",
            "  postman:",
            "    meta_data:",
            f"      proxies: {proxy_val}",
        ]

        # 写入 Cookies
        if config.jm_cookies_avs:
            yaml_lines.extend([
                "      cookies:",
                f"        AVS: {config.jm_cookies_avs}",
            ])

        # 下载路径与解码设置
        abs_download = str(self._download_dir.resolve()).replace("\\", "/")
        yaml_lines.extend([
            "download:",
            "  cache: true",
            "  image:",
            "    decode: true",
            "    suffix: .jpg",
            "dir_rule:",
            f"  base_dir: {abs_download}",
            "  rule: Bd / Aid / Pindex",
        ])

        # 插件设置（若配置了账号密码）
        if config.jm_username and config.jm_password:
            yaml_lines.extend([
                "plugins:",
                "  after_init:",
                "    - plugin: login",
                "      kwargs:",
                f"        username: {config.jm_username}",
                f"        password: {config.jm_password}",
            ])

        yaml_content = "\n".join(yaml_lines)
        logger.debug(f"[JMComic] 构建 Option 配置:\n{yaml_content}")
        self._option = jmcomic.create_option_by_str(yaml_content)
        return self._option

    def get_client(self):
        """获取 JmClient 实例"""
        return self.get_option().new_jm_client()

    # ================= 业务方法（内部同步） =================

    def _sync_get_album_detail(self, album_id: str) -> Tuple[JmAlbumDetail, Optional[Path]]:
        """获取本子详情并下载封面"""
        client = self.get_client()
        album: JmAlbumDetail = client.get_album_detail(album_id)

        # 下载封面到缓存目录
        cover_file = self._cache_dir / f"cover_{album.id}.jpg"
        if not cover_file.exists() or cover_file.stat().st_size == 0:
            try:
                client.download_album_cover(album.id, str(cover_file))
            except Exception as e:
                logger.warning(f"[JMComic] 下载封面失败: {e}")
                cover_file = None

        return album, (cover_file if cover_file and cover_file.exists() else None)

    def _sync_search_albums(self, keyword: str, page: int = 1) -> Tuple[int, int, List[Tuple[str, str, List[str]]]]:
        """搜索本子，返回 (总数, 总页数, [(车号, 标题, 标签列表)])"""
        client = self.get_client()
        search_page: JmSearchPage = client.search_site(search_query=keyword, page=page)
        total = search_page.total
        page_count = search_page.page_count
        results = []
        for aid, title, tags in search_page.iter_id_title_tag():
            results.append((str(aid), str(title), tags if isinstance(tags, list) else []))
        return total, page_count, results

    def _sync_get_ranking(self, rank_type: str = "day", page: int = 1) -> Tuple[str, List[Tuple[str, str]]]:
        """获取排行榜数据"""
        client = self.get_client()
        rank_type = rank_type.lower()
        if rank_type in ("day", "daily", "日榜", "日"):
            title = "禁漫日榜 (今日热门)"
            cat_page = client.day_ranking(page=page)
        elif rank_type in ("week", "weekly", "周榜", "周"):
            title = "禁漫周榜 (本周热门)"
            cat_page = client.week_ranking(page=page)
        elif rank_type in ("month", "monthly", "月榜", "月"):
            title = "禁漫月榜 (本月热门)"
            cat_page = client.month_ranking(page=page)
        else:
            title = "禁漫热门"
            cat_page = client.day_ranking(page=page)

        results = []
        for aid, a_title in cat_page.iter_id_title():
            results.append((str(aid), str(a_title)))
        return title, results

    def _sync_preview_album(self, album_id: str, photo_index: int = 1, max_images: int = 5) -> Tuple[str, List[Path]]:
        """
        预览指定章节前几张图
        返回: (章节标题, 图片本地路径列表)
        """
        client = self.get_client()
        album: JmAlbumDetail = client.get_album_detail(album_id)
        if not album.episode_list:
            raise JmcomicException("该本子未找到章节信息")

        # 确定目标章节
        idx = max(1, min(photo_index, len(album.episode_list)))
        target_ep = album.episode_list[idx - 1]
        photo_id = target_ep[0]
        chapter_title = target_ep[2] if len(target_ep) > 2 else f"第 {idx} 话"

        photo: JmPhotoDetail = client.get_photo_detail(photo_id, False)

        image_paths: List[Path] = []
        # 最多取 max_images 张
        limit = min(max_images, len(photo))
        for img_idx in range(limit):
            img_detail = photo[img_idx]
            out_path = self._cache_dir / f"preview_{album_id}_{photo_id}_{img_idx + 1}.jpg"
            if not out_path.exists() or out_path.stat().st_size == 0:
                client.download_by_image_detail(img_detail, str(out_path))
            image_paths.append(out_path)

        return chapter_title, image_paths

    def _sync_download_and_zip(self, album_id: str) -> Tuple[Path, int, str]:
        """
        下载整本本子并打包为 zip 压缩包
        返回: (zip文件路径, 字节大小, 本子名称)
        """
        opt = self.get_option()
        result = opt.download_album(album_id)
        album: JmAlbumDetail = result.detail

        album_dir = Path(opt.decide_image_save_dir(album[0]))
        # 获取本子实际存放目录 (Aid 这一层)
        # rule 规则为: base_dir / Aid / Pindex
        parent_dir = album_dir.parent
        target_dir = parent_dir if parent_dir.name == str(album_id) else album_dir

        # 打包成 zip
        clean_name = "".join(c for c in album.name if c not in r'\/:*?"<>|').strip() or f"JM{album_id}"
        zip_path = self._download_dir / f"[JM{album_id}] {clean_name}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(target_dir):
                for file in files:
                    file_path = Path(root) / file
                    # 在 zip 内保留相对路径
                    rel_path = file_path.relative_to(target_dir)
                    zf.write(file_path, arcname=str(rel_path))

        file_size = zip_path.stat().st_size
        return zip_path, file_size, album.name

    def _sync_download_and_pdf(self, album_id: str) -> Tuple[Path, int, str, int]:
        """
        下载整本本子并生成全本 PDF 文档
        返回: (pdf文件路径, 字节大小, 本子名称, 总页数)
        """
        opt = self.get_option()
        result = opt.download_album(album_id)
        album: JmAlbumDetail = result.detail

        # 收集所有已下载且反混淆解码的图片
        all_image_paths = []
        for photo in album:
            for image in photo:
                img_path = Path(opt.decide_image_filepath(image))
                if img_path.exists() and img_path.stat().st_size > 0:
                    all_image_paths.append(str(img_path))

        # 兜底：如果实体类映射没取到，扫描本地对应目录
        if not all_image_paths:
            album_dir = Path(opt.decide_image_save_dir(album[0]))
            parent_dir = album_dir.parent
            target_dir = parent_dir if parent_dir.name == str(album_id) else album_dir
            for root, _, files in os.walk(target_dir):
                for file in sorted(files, key=lambda f: [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', f)]):
                    if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        all_image_paths.append(os.path.join(root, file))

        if not all_image_paths:
            raise JmcomicException("未找到可用于合成 PDF 的图片文件")

        clean_name = "".join(c for c in album.name if c not in r'\/:*?"<>|').strip() or f"JM{album_id}"
        pdf_path = self._download_dir / f"[JM{album_id}] {clean_name}.pdf"

        # 优先使用 img2pdf 进行极速无损合并
        pdf_success = False
        try:
            import img2pdf
            with open(pdf_path, "wb") as f:
                f.write(img2pdf.convert(all_image_paths))
            pdf_success = True
        except Exception as e:
            logger.warning(f"[JMComic] img2pdf 转换遇到异常 ({e})，正在尝试通过 Pillow 回退转换...")

        # 回退模式：使用 PIL.Image 合并
        if not pdf_success:
            from PIL import Image
            imgs = []
            for p in all_image_paths:
                try:
                    im = Image.open(p)
                    if im.mode != "RGB":
                        im = im.convert("RGB")
                    imgs.append(im)
                except Exception as err:
                    logger.warning(f"[JMComic] 读取图片 {p} 失败: {err}")
            if not imgs:
                raise JmcomicException("所有图片均无法正常打开以生成 PDF")
            imgs[0].save(pdf_path, save_all=True, append_images=imgs[1:])

        file_size = pdf_path.stat().st_size
        return pdf_path, file_size, album.name, len(all_image_paths)

    # ================= 异步调用封装 =================

    async def get_album_detail(self, album_id: str) -> Tuple[JmAlbumDetail, Optional[Path]]:
        return await asyncio.to_thread(self._sync_get_album_detail, album_id)

    async def search_albums(self, keyword: str, page: int = 1) -> Tuple[int, int, List[Tuple[str, str, List[str]]]]:
        return await asyncio.to_thread(self._sync_search_albums, keyword, page)

    async def get_ranking(self, rank_type: str = "day", page: int = 1) -> Tuple[str, List[Tuple[str, str]]]:
        return await asyncio.to_thread(self._sync_get_ranking, rank_type, page)

    async def preview_album(self, album_id: str, photo_index: int = 1, max_images: int = 5) -> Tuple[str, List[Path]]:
        return await asyncio.to_thread(self._sync_preview_album, album_id, photo_index, max_images)

    async def download_and_zip(self, album_id: str) -> Tuple[Path, int, str]:
        return await asyncio.to_thread(self._sync_download_and_zip, album_id)

    async def download_and_pdf(self, album_id: str) -> Tuple[Path, int, str, int]:
        return await asyncio.to_thread(self._sync_download_and_pdf, album_id)


service = JMService()
