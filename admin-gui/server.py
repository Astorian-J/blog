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
import urllib.parse
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
            {"name": "tag", "label": "分类标签", "type": "select", "options": ["公告", "教程", "分析", "杂谈"]},
            {"name": "excerpt", "label": "文章摘要", "type": "textarea"},
            {"name": "body", "label": "正文内容", "type": "markdown", "required": True},
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
}

# ==================== 工具函数 ====================


def slugify(text):
    """生成 URL 友好的 slug"""
    text = text.strip().lower()
    text = re.sub(r'[^\w\u4e00-\u9fff\-]', '-', text)
    text = re.sub(r'-{2,}', '-', text).strip('-')
    return text


def generate_slug(collection_name, title, date_str):
    """根据分类规则生成文件名"""
    col = COLLECTIONS[collection_name]
    fmt = col["slug_format"]
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d") if date_str else datetime.now()
    s = slugify(title) if title else "untitled"
    result = fmt.replace("{year}", str(dt.year))
    result = result.replace("{month}", f"{dt.month:02d}")
    result = result.replace("{day}", f"{dt.day:02d}")
    result = result.replace("{slug}", s)
    return result


def parse_frontmatter(content):
    """解析 Markdown 文件的 frontmatter"""
    if content.startswith('---'):
        end = content.find('---', 3)
        if end > 0:
            fm_text = content[3:end].strip()
            body = content[end+3:].strip()
            fm = {}
            for line in fm_text.split('\n'):
                if ':' in line:
                    key, val = line.split(':', 1)
                    val = val.strip().strip('"').strip("'")
                    if val.lower() == 'true':
                        val = True
                    elif val.lower() == 'false':
                        val = False
                    elif val.isdigit():
                        val = int(val)
                    fm[key.strip()] = val
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
    """保存/更新一个 Markdown 文件"""
    folder = os.path.join(CONTENT_DIR, COLLECTIONS[collection_name]["folder"])
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)
    
    fm_data = {}
    for field in COLLECTIONS[collection_name]["fields"]:
        fname = field["name"]
        if fname in data and data[fname] is not None:
            fm_data[fname] = data[fname]
    
    content = make_frontmatter(fm_data) + '\n\n' + (body or '')
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


def git_push(commit_msg="update content"):
    """执行 Git 提交和推送操作"""
    try:
        # git add -A
        subprocess.run(
            [GIT_EXE, "add", "-A"],
            cwd=str(BLOG_DIR),
            capture_output=True,
            check=True,
        )
        
        # 检查是否有变更
        status = subprocess.run(
            [GIT_EXE, "status", "--porcelain"],
            cwd=str(BLOG_DIR),
            capture_output=True,
            text=True,
        )
        if not status.stdout.strip():
            return {"success": True, "message": "没有变更需要提交"}
        
        # 先拉取远程最新（rebase 模式避免合并提交）
        pull_result = subprocess.run(
            [GIT_EXE, "pull", "--rebase"],
            cwd=str(BLOG_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        # 如果 pull 失败（冲突），放弃 rebase 并提示用户
        if pull_result.returncode != 0:
            # 尝试自动解决：用远程版本覆盖冲突文件
            subprocess.run(
                [GIT_EXE, "rebase", "--abort"],
                cwd=str(BLOG_DIR),
                capture_output=True,
                timeout=10,
            )
            # 重新用 merge 方式拉取
            merge_result = subprocess.run(
                [GIT_EXE, "pull", "--no-rebase", "-X", "theirs"],
                cwd=str(BLOG_DIR),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if merge_result.returncode != 0:
                return {"success": False, "message": f"同步远程变更失败，请手动在 blog 目录执行 git pull 后重试: {merge_result.stderr}"}
        
        # git commit
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = f"cms: {commit_msg} ({now})"
        subprocess.run(
            [GIT_EXE, "commit", "-m", msg],
            cwd=str(BLOG_DIR),
            capture_output=True,
            check=True,
        )
        
        # git push
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
        length = int(self.headers.get('Content-Length', 0))
        raw_data = self.rfile.read(length)
        
        try:
            data = json.loads(raw_data) if raw_data else {}
        except:
            data = {}
        
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        # API: 新增内容
        if path == '/api/add':
            col_name = data.get('collection')
            title = data.get('title', '')
            date_str = data.get('date', datetime.now().strftime('%Y-%m-%d'))
            
            if not col_name or col_name not in COLLECTIONS:
                self.send_json({'error': '无效的分类'}, status=400)
                return
            
            filename = generate_slug(col_name, title, date_str) + '.md'
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
                if os.path.isfile(old_full):
                    # 删除旧文件，用新名字创建
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
        
        # API: 一键发布
        if path == '/api/publish':
            # 先更新 manifest
            update_manifest()
            # 再 git push
            result = git_push(data.get('message', '发布内容更新'))
            self.send_json(result)
            return
        
        self.send_error(404)

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
