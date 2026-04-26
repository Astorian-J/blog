#!/usr/bin/env python3
"""
博客本地可视化管理后台 — 后端服务
功能：文件读写、Git 操作、一键发布
双击 start.bat 启动，浏览器自动打开管理界面
"""

import os
import sys
import json
import re
import subprocess
import shutil
import urllib.parse
import uuid
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器，每个请求独立处理不阻塞"""
    allow_reuse_address = True
    daemon_threads = True

# ==================== 配置 ====================
BLOG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # blog/ 目录
CONTENT_DIR = os.path.join(BLOG_DIR, "content")
IMAGES_DIR = os.path.join(CONTENT_DIR, "images")
MANIFEST_FILE = os.path.join(CONTENT_DIR, "manifest.json")
GIT_EXE = r"C:\Program Files\Git\cmd\git.exe"

# 端口和地址
PORT = 8765
HOST = "localhost"

# 分类配置（对应 config.yml 的 collections）
COLLECTIONS = {
    "news": {
        "label": "📰 最新平衡资讯",
        "folder": "news",
        "slug_format": "{year}-{month}-{day}-{slug}",
        "fields": [
            {"name": "title", "label": "标题", "type": "text", "required": True},
            {"name": "date", "label": "日期", "type": "date", "required": True},
            {"name": "hot", "label": "是否热门", "type": "checkbox"},
            {"name": "excerpt", "label": "内容摘要", "type": "textarea"},
        ],
    },
    "articles": {
        "label": "📝 文章发布",
        "folder": "articles",
        "slug_format": "{year}-{month}-{day}-{slug}",
        "fields": [
            {"name": "title", "label": "标题", "type": "text", "required": True},
            {"name": "date", "label": "日期", "type": "date", "required": True},
            {"name": "tag", "label": "分类标签", "type": "select", "options": ["故事", "教程", "分析", "杂谈", "平衡人物志"]},
            {"name": "excerpt", "label": "文章摘要", "type": "textarea"},
            {"name": "source_url", "label": "原文链接", "type": "text", "hint": "原文出处链接，可选，前台会显示「查看原文」按钮"},
            {"name": "body", "label": "正文内容（支持 Markdown 图片语法）", "type": "markdown", "required": True, "hint": "支持图片: ![描述](图片路径) | 可用下方按钮插入本地图片"},
        ],
    },
    "survey-data": {
        "label": "📊 每月问卷数据",
        "folder": "survey-data",
        "slug_format": "{year}-{month}",
        "fields": [
            {"name": "title", "label": "月份标题", "type": "text", "required": True},
            {"name": "year", "label": "年份", "type": "number", "required": True},
            {"name": "month", "label": "月份", "type": "number", "required": True},
            {"name": "vote_count", "label": "投票人次", "type": "number"},
            {"name": "raw_url", "label": "原始问卷表格", "type": "text"},
            {"name": "stat_url", "label": "问卷统计结果", "type": "text"},
            {"name": "video_url", "label": "相关视频链接", "type": "text"},
            {"name": "description", "label": "备注说明", "type": "textarea"},
        ],
    },
    "videos": {
        "label": "▶️ 平衡推荐视频",
        "folder": "videos",
        "slug_format": "{year}-{month}",
        "fields": [
            {"name": "title", "label": "视频标题", "type": "text", "required": True},
            {"name": "date", "label": "发布日期", "type": "date", "required": True},
            {"name": "source", "label": "来源平台", "type": "select", "options": ["哔哩哔哩", "YouTube", "其他"]},
            {"name": "url", "label": "视频链接", "type": "text", "required": True},
        ],
    },
    "bc-recommendations": {
        "label": "🎯 平衡推荐汇总",
        "folder": "bc-recommendations",
        "slug_format": "{year}-{month}-{day}",
        "fields": [
            {"name": "image", "label": "推荐截图", "type": "image"},
        ],
    },
    "streamers": {
        "label": "🎙 中国社区昆特主播",
        "folder": "streamers",
        "slug_format": "{year}-{month}-{day}-{slug}",
        "fields": [
            {"name": "title", "label": "标题", "type": "text", "required": True},
            {"name": "date", "label": "日期", "type": "date", "required": True},
            {"name": "excerpt", "label": "文章摘要", "type": "textarea"},
            {"name": "source_url", "label": "原文链接", "type": "text", "hint": "原文出处链接，可选，前台会显示「查看原文」按钮"},
            {"name": "body", "label": "正文内容（支持 Markdown 图片语法）", "type": "markdown", "required": True, "hint": "支持图片: ![描述](图片路径) | 可用下方按钮插入本地图片"},
        ],
    },
    "survey-link": {
        "label": "📋 问卷链接设置",
        "folder": "survey-link",
        "slug_format": "link",
        "fields": [
            {"name": "url", "label": "问卷网址", "type": "text", "required": True, "hint": "平衡民意问卷调查的外部链接地址"},
        ],
    },
    "glossary": {
        "label": "📖 昆特术语词典",
        "folder": "glossary",
        "slug_format": "{slug}",
        "fields": [
            {"name": "cn_name", "label": "中文名称", "type": "text", "required": True, "hint": "中文术语名称，如：平衡委员会"},
            {"name": "en_name", "label": "英文名称", "type": "text", "required": True, "hint": "英文术语名称，如：Balance Council (BC)"},
            {"name": "category", "label": "分类", "type": "select", "options": ["机制", "卡牌效果", "派系术语", "赛事术语", "社区用语", "其他"]},
            {"name": "description", "label": "含义与解释", "type": "textarea", "required": True, "hint": "详细解释该术语的含义、用法、来源等"},
        ],
    },
}

# ==================== 工具函数 ====================


def slugify(text):
    """生成纯英文 URL 友好的 slug（中文自动转拼音）"""
    text = text.strip()
    # 尝试中文转拼音
    try:
        from pypinyin import lazy_pinyin
        parts = []
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff':
                py = lazy_pinyin(ch)
                parts.append(py[0] if py else '')
            elif ch.isalnum():
                parts.append(ch.lower())
            elif ch in '-_ ':
                parts.append('-')
        text = ''.join(parts)
    except ImportError:
        # 未安装 pypinyin 时去掉非 ASCII 字符
        text = re.sub(r'[^\w\-]', '-', text)

    text = re.sub(r'-{2,}', '-', text).strip('-')
    return text or 'untitled'


def generate_slug(collection_name, data, date_str):
    """根据分类规则生成文件名，支持所有字段占位符"""
    col = COLLECTIONS[collection_name]
    fmt = col["slug_format"]
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d") if date_str else datetime.now()

    # 先替换日期相关占位符
    result = fmt.replace("{year}", str(dt.year))
    result = result.replace("{month}", f"{dt.month:02d}")
    result = result.replace("{day}", f"{dt.day:02d}")

    # 替换 slug（用 title 或首个文本字段）
    title_text = data.get('title', '') or ''
    if not title_text:
        # 找第一个有值的文本类字段作为 fallback
        for f in col.get("fields", []):
            v = data.get(f["name"], '')
            if v and f["type"] in ("text", "select"):
                title_text = str(v)
                break
    s = slugify(title_text) if title_text else "untitled"
    result = result.replace("{slug}", s)

    # 替换其他字段占位符（如 {author}）
    for f in col.get("fields", []):
        placeholder = "{" + f["name"] + "}"
        if placeholder in result:
            val = data.get(f["name"], "")
            result = result.replace(placeholder, slugify(str(val)) if val else "unknown")

    return result


def parse_frontmatter(content):
    """解析 Markdown 文件的 frontmatter（支持多行引号值）"""
    if content.startswith('---'):
        end = content.find('---', 3)
        if end > 0:
            fm_text = content[3:end].strip()
            body = content[end+3:].strip()
            fm = {}
            i = 0
            lines = fm_text.split('\n')
            while i < len(lines):
                line = lines[i]
                # 跳过空行
                if not line.strip():
                    i += 1
                    continue
                if ':' in line:
                    key, val = line.split(':', 1)
                    key = key.strip()
                    val_stripped = val.strip()
                    # 检测是否是双引号开头的多行值
                    if val_stripped.startswith('"') and not val_stripped.endswith('"'):
                        # 多行字符串：收集直到找到结尾的 "
                        parts = [val_stripped]  # 保留开头的引号
                        i += 1
                        while i < len(lines):
                            parts.append(lines[i])
                            if lines[i].rstrip().endswith('"'):
                                break
                            i += 1
                        full_val = '\n'.join(parts)
                        # 去掉首尾引号
                        val = full_val[1:-1].strip() if full_val.endswith('"') else full_val[1:].strip()
                    elif val_stripped.startswith("'") and not val_stripped.endswith("'"):
                        # 单引号多行值（同理）
                        parts = [val_stripped]
                        i += 1
                        while i < len(lines):
                            parts.append(lines[i])
                            if lines[i].rstrip().endswith("'"):
                                break
                            i += 1
                        full_val = '\n'.join(parts)
                        val = full_val[1:-1].strip() if full_val.endswith("'") else full_val[1:].strip()
                    else:
                        # 普通单行值
                        val = val_stripped.strip('"').strip("'")
                    
                    # 类型转换
                    if isinstance(val, str) and val.lower() == 'true':
                        val = True
                    elif isinstance(val, str) and val.lower() == 'false':
                        val = False
                    elif isinstance(val, str) and val.isdigit():
                        val = int(val)
                    fm[key] = val
                i += 1
            return fm, body
    # 无 frontmatter 的旧格式兼容
    return {}, content.strip()


def make_frontmatter(data):
    """将字典转为 YAML frontmatter 字符串"""
    lines = ['---']
    for key, value in data.items():
        if value is None:
            continue
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, str):
            # 处理包含特殊字符的值
            if ':' in value or '"' in value or '\n' in value:
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f'{key}: {value}')
        else:
            lines.append(f"{key}: {value}")
    lines.append('---')
    return '\n'.join(lines)


def get_files_in_collection(collection_name):
    """获取某个分类下的所有 .md 文件"""
    folder = os.path.join(CONTENT_DIR, COLLECTIONS[collection_name]["folder"])
    files = []
    if os.path.isdir(folder):
        for f in sorted(os.listdir(folder), reverse=True):
            if f.endswith('.md'):
                full = os.path.join(folder, f)
                content = open(full, 'r', encoding='utf-8').read()
                fm, body = parse_frontmatter(content)
                files.append({
                    "filename": f,
                    "path": os.path.relpath(full, BLOG_DIR).replace('\\', '/'),
                    "frontmatter": fm,
                    "body": body,
                    "size": os.path.getsize(full),
                    "modified": datetime.fromtimestamp(os.path.getmtime(full)).strftime("%Y-%m-%d %H:%M"),
                })
    return files


def save_file(collection_name, filename, data, body=""):
    """保存/更新一个 Markdown 文件（保存前自动创建 .bak 备份）"""
    folder = os.path.join(CONTENT_DIR, COLLECTIONS[collection_name]["folder"])
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)
    
    # 安全措施：保存前先备份现有文件（防止内容意外丢失）
    if os.path.exists(filepath):
        bak_path = filepath + '.bak'
        shutil.copy2(filepath, bak_path)
    
    fm_data = {}
    for field in COLLECTIONS[collection_name]["fields"]:
        fname = field["name"]
        # body 字段只写入正文，不写入 frontmatter 避免重复渲染
        if fname == "body":
            continue
        if fname in data and data[fname] is not None:
            fm_data[fname] = data[fname]
    
    # 确保使用传入的 body 参数（前端传来的最新正文内容）
    final_body = body or data.get('body', '') or ''
    content = make_frontmatter(fm_data) + '\n\n' + final_body
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return os.path.relpath(filepath, BLOG_DIR)


def delete_file(file_path_str):
    """删除一个文件"""
    full_path = os.path.join(BLOG_DIR, file_path_str)
    if os.path.isfile(full_path):
        os.remove(full_path)
        return True
    return False


def update_manifest():
    """自动扫描 content 目录，重新生成 manifest.json"""
    manifest = {}
    for col_name, col_config in COLLECTIONS.items():
        folder = os.path.join(CONTENT_DIR, col_config["folder"])
        files = []
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder), reverse=True):
                if f.endswith('.md'):
                    full = os.path.join(folder, f)
                    files.append(os.path.relpath(full, BLOG_DIR).replace('\\', '/'))
        manifest[col_name] = files
    
    os.makedirs(os.path.dirname(MANIFEST_FILE), exist_ok=True)
    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
        f.write(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def build_articles():
    """调用 build.py 生成文章静态页（.md → posts/*.html）"""
    import subprocess as sp
    try:
        result = sp.run(
            [sys.executable, os.path.join(BLOG_DIR, "build.py")],
            capture_output=True, text=True, timeout=30,
            cwd=BLOG_DIR
        )
        if result.returncode == 0:
            # 构建完成后重新读取 manifest（build.py 会更新 articles_html 字段）
            with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            count = len(manifest.get('articles_html', {}))
            print(f"[构建] 文章静态页已生成 {count} 篇")
            return {'ok': True, 'msg': f'generated {count} pages'}
        else:
            return {'ok': False, 'msg': result.stderr or result.stdout}
    except Exception as e:
        return {'ok': False, 'msg': str(e)}


def git_push(commit_msg="update content"):
    """执行 Git 提交和推送操作"""
    try:
        # 检查是否有变更
        status = subprocess.run(
            [GIT_EXE, "status", "--porcelain"],
            cwd=str(BLOG_DIR),
            capture_output=True,
            text=True,
        )
        if not status.stdout.strip():
            return {"success": True, "message": "没有变更需要提交"}

        # 1️⃣ 先 git add -A（暂存所有改动）
        subprocess.run(
            [GIT_EXE, "add", "-A"],
            cwd=str(BLOG_DIR),
            capture_output=True,
            check=True,
        )

        # 2️⃣ 提交本地改动
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = f"cms: {commit_msg} ({now})"
        subprocess.run(
            [GIT_EXE, "commit", "-m", msg],
            cwd=str(BLOG_DIR),
            capture_output=True,
            check=True,
        )

        # 2.5️⃣ 自动打 tag（用于回滚：git checkout <tag> 恢复到发布前状态）
        tag_name = f"pre-publish-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        subprocess.run(
            [GIT_EXE, "tag", "-f", tag_name],
            cwd=str(BLOG_DIR),
            capture_output=True,
        )
        print(f"[发布] 已打标签: {tag_name}")

        # 3️⃣ 拉取远程最新（rebase 模式，保持提交历史整洁）
        pull_result = subprocess.run(
            [GIT_EXE, "pull", "--rebase"],
            cwd=str(BLOG_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if pull_result.returncode != 0:
            # rebase 失败 → 放弃 rebase
            subprocess.run([GIT_EXE, "rebase", "--abort"], cwd=str(BLOG_DIR), capture_output=True, timeout=10)
            # 用普通 merge 拉取，自动用本地版本覆盖冲突文件（因为我们刚提交过）
            merge_result = subprocess.run(
                [GIT_EXE, "pull", "--no-rebase", "-X", "ours"],
                cwd=str(BLOG_DIR),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if merge_result.returncode != 0:
                # 最后手段：强制用本地版本重置
                subprocess.run(
                    [GIT_EXE, "reset", "--hard", "HEAD"],
                    cwd=str(BLOG_DIR), capture_output=True, timeout=10,
                )

        # 4️⃣ 推送到远程
        result = subprocess.run(
            [GIT_EXE, "push"],
            cwd=str(BLOG_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode == 0:
            return {"success": True, "message": "发布成功！已推送到 GitHub"}
        else:
            return {"success": False, "message": f"推送失败: {result.stderr}"}
            
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "推送超时（可能网络问题）"}
    except Exception as e:
        return {"success": False, "message": f"错误: {str(e)}"}


# ==================== API 路由处理器 ====================

class AdminHandler(SimpleHTTPRequestHandler):
    """自定义请求处理器：静态文件 + API"""

    def __init__(self, *args, **kwargs):
        # 切换工作目录到 admin-gui 以便提供静态文件
        self.directory = os.path.dirname(os.path.abspath(__file__))
        super().__init__(*args, directory=self.directory, **kwargs)

    def do_GET(self):
        """处理 GET 请求"""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        # API: 获取所有分类的内容列表
        if path.startswith('/api/collections'):
            self.send_json({"collections": {k: v["label"] for k, v in COLLECTIONS.items()}})
            return
        
        # API: 获取某分类的所有文件
        match = re.match(r'^/api/([\w-]+)/files$', path)
        if match:
            col_name = match.group(1)
            if col_name in COLLECTIONS:
                files = get_files_in_collection(col_name)
                self.send_json({col_name: files})
                return
        
        # API: 获取单个文件内容
        match = re.match(r'^/api/file\?path=(.+)$', path)
        if not match:
            match = re.match(r'^/api/file/(.+)$', path)
        if match:
            file_path = urllib.parse.unquote(match.group(1))
            full_path = os.path.join(BLOG_DIR, file_path)
            if os.path.isfile(full_path):
                content = open(full_path, 'r', encoding='utf-8').read()
                fm, body = parse_frontmatter(content)
                self.send_json({"frontmatter": fm, "body": body})
            else:
                self.send_json({"error": f"文件不存在: {file_path}"}, status=404)
            return
        
        # API: 获取分类字段定义
        match = re.match(r'^/api/([\w-]+)/fields$', path)
        if match:
            col_name = match.group(1)
            if col_name in COLLECTIONS:
                self.send_json(COLLECTIONS[col_name])
                return
        
        # API: 获取 manifest
        if path == '/api/manifest':
            if os.path.isfile(MANIFEST_FILE):
                manifest = json.loads(open(MANIFEST_FILE, 'r', encoding='utf-8').read())
                self.send_json(manifest)
            else:
                self.send_json(update_manifest())
            return
        
        # 默认：返回静态文件（index.html）
        if path == '/' or path == '/index.html':
            self.serve_static('index.html', 'text/html; charset=utf-8')
            return
        
        # 其他静态资源
        static_file = os.path.join(self.directory, path.lstrip('/'))
        if os.path.isfile(static_file):
            ext = static_file.suffix.lower()
            ct = {
                '.html': 'text/html; charset=utf-8',
                '.css': 'text/css; charset=utf-8',
                '.js': 'application/javascript; charset=utf-8',
                '.json': 'application/json; charset=utf-8',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.svg': 'image/svg+xml',
                '.ico': 'image/x-icon',
            }.get(ext, 'application/octet-stream')
            self.serve_static(path.lstrip('/'), ct)
            return
        
        self.send_error(404)

    def do_POST(self):
        """处理 POST 请求"""
        try:
            self._do_post()
        except Exception as e:
            self.send_json({'error': f'服务器内部错误: {str(e)}'}, status=500)

    def _do_post(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # API: 图片上传（必须在读取 body 前处理，因为它是 multipart 而非 JSON）
        if path == '/api/upload-image':
            self._handle_image_upload()
            return

        length = int(self.headers.get('Content-Length', 0))
        raw_data = self.rfile.read(length)
        
        try:
            data = json.loads(raw_data) if raw_data else {}
        except:
            data = {}
        
        # API: 新增内容
        if path == '/api/add':
            col_name = data.get('collection')
            date_str = data.get('date', datetime.now().strftime('%Y-%m-%d'))
            
            if not col_name or col_name not in COLLECTIONS:
                self.send_json({'error': '无效的分类'}, status=400)
                return
            
            filename = generate_slug(col_name, data, date_str) + '.md'
            body = data.get('body', '')
            file_path = save_file(col_name, filename, data, body)
            self.send_json({'success': True, 'file': file_path, 'message': f'已创建 {filename}'})
            return
        
        # API: 编辑内容
        if path == '/api/edit':
            file_path = data.get('path')
            col_name = data.get('collection')
            new_filename = data.get('filename')
            body = data.get('body', '')
            
            if not file_path:
                self.send_json({'error': '缺少路径'}, status=400)
                return
            
            # 如果文件名变了（比如标题改了），需要重命名
            old_full = os.path.join(BLOG_DIR, file_path)
            if new_filename and os.path.basename(old_full) != new_filename:
                col_folder = os.path.join(CONTENT_DIR, COLLECTIONS[col_name]["folder"]) if col_name else os.path.dirname(old_full)
                new_full = os.path.join(col_folder, new_filename)
                
                # 🔒 防覆盖保护：如果目标文件名已存在且不是当前文件本身，拒绝操作
                if os.path.isfile(new_full) and os.path.abspath(new_full) != os.path.abspath(old_full):
                    self.send_json({
                        'error': f'文件 "{new_filename}" 已存在！请先删除或重命名现有文件，或将月份改回原值。',
                        'conflict': True,
                        'existing_file': new_filename
                    }, status=409)
                    return
                
                if os.path.isfile(old_full):
                    # 先备份旧文件（防止重命名后找不到原始数据）
                    bak_path = old_full + '.bak'
                    shutil.copy2(old_full, bak_path)
                    os.remove(old_full)
                    file_path = save_file(col_name, new_filename, data, body)
                else:
                    file_path = save_file(col_name, new_filename, data, body)
            else:
                # 直接覆盖原文件
                old_name = os.path.basename(old_full)
                if col_name:
                    save_file(col_name, old_name, data, body)
                else:
                    # 不知道分类时尝试从路径推断
                    parts = file_path.replace('\\', '/').split('/')
                    for cn, cc in COLLECTIONS.items():
                        if cc['folder'] in parts:
                            save_file(cn, old_name, data, body)
                            break
            
            self.send_json({'success': True, 'message': '更新成功'})
            return
        
        # API: 删除内容
        if path == '/api/delete':
            file_path = data.get('path')
            if not file_path:
                self.send_json({'error': '缺少路径'}, status=400)
                return
            
            ok = delete_file(file_path)
            if ok:
                self.send_json({'success': True, 'message': '已删除'})
            else:
                self.send_json({'error': '删除失败或文件不存在'}, status=404)
            return
        
        # API: 从备份恢复（.bak → 原文件）
        if path == '/api/restore-backup':
            file_path = data.get('path')
            if not file_path:
                self.send_json({'error': '缺少路径'}, status=400)
                return
            
            full_path = os.path.join(BLOG_DIR, file_path)
            bak_path = full_path + '.bak'
            
            if os.path.exists(bak_path):
                shutil.copy2(bak_path, full_path)
                self.send_json({'success': True, 'message': f'已从备份恢复 {file_path}'})
            else:
                self.send_json({'error': '备份文件不存在'}, status=404)
            return
        
        # API: 一键发布（发布前自动打 git tag）
        if path == '/api/publish':
            # 先更新 manifest
            update_manifest()
            # 执行文章静态页构建（.md → posts/*.html）
            build_result = build_articles()
            if not build_result['ok']:
                # 构建失败不阻断发布，但记录警告
                print(f"[警告] 文章构建失败：{build_result.get('msg', '未知错误')}")
            # 再 git push
            result = git_push(data.get('message', '发布内容更新'))
            self.send_json(result)
            return

        self.send_error(404)

    def _handle_image_upload(self):
        """处理图片上传（multipart/form-data），保存到 content/images/"""
        try:
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self.send_json({'error': '需要 multipart/form-data 格式'}, status=400)
                return

            # 解析 boundary
            boundary = content_type.split('boundary=')[-1].encode()
            body_bytes = self.rfile.read(int(self.headers.get('Content-Length', 0)))

            # 简单解析 multipart，找到文件数据
            parts = body_bytes.split(b'--' + boundary)
            file_data = None
            filename = None

            for part in parts:
                if b'filename=' not in part:
                    continue
                header_end = part.find(b'\r\n\r\n')
                if header_end == -1:
                    continue
                headers_part = part[:header_end].decode('utf-8', errors='ignore')
                fn_match = re.search(r'filename="(.+)"', headers_part)
                if fn_match:
                    filename = fn_match.group(1)
                    file_data = part[header_end + 4:].rstrip(b'\r\n--').rstrip(b'\r\n')
                    break

            if not file_data or not filename:
                self.send_json({'error': '未找到上传的文件'}, status=400)
                return

            # 安全化文件名：只保留 ASCII 字母数字、连字符和点（禁止中文）
            safe_name = re.sub(r'[^\w\.\-]', '', os.path.splitext(filename)[0], flags=re.ASCII)
            ext = os.path.splitext(filename)[1].lower() or '.png'
            allowed_exts = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
            if ext not in allowed_exts:
                self.send_json({'error': f'不支持的文件格式: {ext}，允许 {allowed_exts}'}, status=400)
                return

            # 不限制图片大小（本地存储，按月替换）

            # 生成唯一文件名
            unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}{ext}"
            os.makedirs(IMAGES_DIR, exist_ok=True)
            filepath = os.path.join(IMAGES_DIR, unique_name)

            with open(filepath, 'wb') as f:
                f.write(file_data)

            # 返回相对于 blog 根目录的路径（用于 Markdown 图片引用）
            rel_path = f"content/images/{unique_name}"
            self.send_json({
                'success': True,
                'url': rel_path,
                'message': f'图片已保存: {unique_name}'
            })

        except Exception as e:
            self.send_json({'error': f'上传失败: {str(e)}'}, status=500)

    def send_json(self, data, status=200):
        """发送 JSON 响应"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))

    def serve_static(self, rel_path, content_type):
        """发送静态文件"""
        full_path = os.path.join(self.directory, rel_path)
        try:
            content = open(full_path, 'rb').read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            print(f"Error serving {rel_path}: {e}")
            self.send_error(500)

    def log_message(self, format, *args):
        """简化日志输出"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")


# ==================== 启动 ====================

def main():
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    print("=" * 50)
    print("  博客可视化管理后台")
    print("=" * 50)
    print(f"  博客目录: {BLOG_DIR}")
    print(f"  地址:     http://{HOST}:{PORT}")
    print(f"  时间:     {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)
    print("\n按 Ctrl+C 停止服务\n")
    
    # 验证博客目录
    if not os.path.isdir(BLOG_DIR):
        print(f"错误: 找不到博客目录 {BLOG_DIR}")
        input("按回车退出...")
        return
    
    if not GIT_EXE or not os.path.isfile(GIT_EXE):
        print(f"警告: 未找到 Git ({GIT_EXE})")
        print("   发布功能将不可用，但浏览/编辑功能正常\n")

    server = ThreadedHTTPServer((HOST, PORT), AdminHandler)
    
    # 尝试自动打开浏览器
    import webbrowser
    webbrowser.open(f'http://{HOST}:{PORT}')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n服务已停止")
        server.server_close()


if __name__ == '__main__':
    main()
