"""
文章静态页构建脚本
读取 content/articles/*.md → 生成 posts/*.html（独立可访问的文章详情页）
用法：python build.py [blog根目录]
"""

import os
import re
import sys
import json


# ============================================================
# 路径配置
# ============================================================

BLOG_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENT_DIR = os.path.join(BLOG_DIR, "content", "articles")
POSTS_DIR = os.path.join(BLOG_DIR, "posts")
TEMPLATE_FILE = os.path.join(POSTS_DIR, "article-template.html")
MANIFEST_FILE = os.path.join(BLOG_DIR, "content", "manifest.json")


# ============================================================
# Frontmatter 解析
# ============================================================

def parse_frontmatter(content):
    """解析 YAML frontmatter，返回 {frontmatter: dict, body: str}"""
    if not content.startswith('---'):
        return {'frontmatter': {}, 'body': content}
    end = content.find('---', 3)
    if end < 0:
        return {'frontmatter': {}, 'body': content}
    fm_text = content[3:end].strip()
    body = content[end+3:].strip()
    fm = {}
    for line in fm_text.split('\n'):
        if ':' not in line:
            continue
        key, val = line.split(':', 1)
        val = val.strip()
        # 去引号
        if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
            val = val[1:-1]
        # 布尔值
        elif val.lower() == 'true':
            val = True
        elif val.lower() == 'false':
            val = False
        # 数字
        else:
            try:
                if '.' in val:
                    val = float(val)
                else:
                    val = int(val)
            except ValueError:
                pass
        fm[key.strip().lower()] = val
    return {'frontmatter': fm, 'body': body}


# ============================================================
# Slug 生成
# ============================================================

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


# ============================================================
# Markdown → HTML 转换器（轻量级，与前端 renderMd 一致）
# ============================================================

def render_md(md_text):
    """将 Markdown 文本转换为 HTML，与前端 index.html 的 renderMd() 行为一致"""
    if not md_text:
        return ''
    html = md_text
    # 图片（必须在链接之前处理，避免 ![] 被 [] 吞掉）
    html = re.sub(r'!\[(.*?)\]\((.*?)\)', r'<img src="\2" alt="\1">', html)
    # 链接
    html = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2" target="_blank">\1</a>', html)
    # 标题
    html = re.sub(r'^### (.*)$', r'<h3>\1</h>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*)$', r'<h2>\1</h>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.*)$', r'<h1>\1</h>', html, flags=re.MULTILINE)
    # 粗体/斜体
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
    # 行内代码
    html = re.sub(r'`(.*?)`', r'<code>\1</code>', html)
    # 引用块
    html = re.sub(r'^> (.*)$', r'<blockquote>\1</blockquote>', html, flags=re.MULTILINE)
    # 列表项 → 先包裹连续的 li
    lines = html.split('\n')
    new_lines = []
    ul_buffer = []
    for line in lines:
        if re.match(r'^- ', line):
            ul_buffer.append(re.sub(r'^- (.*)$', r'<li>\1</li>', line))
        else:
            if ul_buffer:
                new_lines.append('<ul>' + '\n'.join(ul_buffer) + '</ul>')
                ul_buffer = []
            new_lines.append(line)
    if ul_buffer:
        new_lines.append('<ul>' + '\n'.join(ul_buffer) + '</ul>')
    html = '\n'.join(new_lines)
    # 段落和换行
    html = html.replace('\n\n', '</p><p>')
    html = html.replace('\n', '<br>')
    return '<p>' + html + '</p>'


# ============================================================
# 模板渲染
# ============================================================

def render_article_html(fm, body_html):
    """用模板生成完整的文章 HTML 页面"""
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        template = f.read()

    # 分类标签
    tag_map = {'故事': '故事', '教程': '教程', '分析': '分析', '杂谈': '杂谈', '平衡人物志': '平衡人物志'}
    tag = fm.get('tag', '')
    display_tag = tag_map.get(tag, tag) if tag else ''
    tag_class = ' highlight' if tag == '故事' else ''

    # 来源链接
    source_url = fm.get('source_url', '')
    source_link = ''
    if source_url and source_url != '#':
        source_link = f'<a href="{source_url}" target="_blank" rel="noopener noreferrer">🔗 查看原文</a>'

    replacements = {
        '{{title}}': fm.get('title', ''),
        '{{tag}}': display_tag,
        '{{tag_class}}': tag_class,
        '{{date}}': fm.get('date', ''),
        '{{source_link}}': source_link,
        '{{body}}': body_html,
        '{{back_text}}': '← 返回文章列表',
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)

    return template


# ============================================================
# 主构建流程
# ============================================================

def build():
    """扫描 articles 目录，为每篇 md 生成静态 HTML"""
    # 确保输出目录存在
    os.makedirs(POSTS_DIR, exist_ok=True)

    # 读取模板
    if not os.path.exists(TEMPLATE_FILE):
        print(f"[错误] 模板文件不存在：{TEMPLATE_FILE}")
        return False

    # 扫描所有文章
    if not os.path.isdir(CONTENT_DIR):
        print(f"[错误] 文章目录不存在：{CONTENT_DIR}")
        return False

    md_files = [f for f in os.listdir(CONTENT_DIR) if f.endswith('.md')]
    if not md_files:
        print("[信息] 没有找到任何文章")
        return True

    # 生成文件映射表（用于更新 manifest）
    html_mapping = {}  # md文件名 → html相对路径

    for md_file in sorted(md_files):
        md_path = os.path.join(CONTENT_DIR, md_file)
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        data = parse_frontmatter(content)
        fm = data['frontmatter']
        body_html = render_md(data['body'])

        # 从原始文件名提取日期前缀，或从 frontmatter 的 date 字段生成 slug
        # 文件名格式：2026-04-20-标题拼音-分类英文.html
        base_name = md_file[:-3]  # 去掉 .md
        title = fm.get('title', '')
        date_val = fm.get('date', '')
        tag = fm.get('tag', '')

        # 提取日期（优先用 frontmatter 的 date，否则从 md 文件名提取）
        if date_val:
            dt_part = date_val[:10].replace('-', '')
        else:
            # 从文件名前10字符提取 YYYY-MM-DD
            dt_part = base_name[:10].replace('-', '') if len(base_name) >= 10 else ''

        # 标题转拼音 slug
        title_slug = slugify(title) if title else 'untitled'

        # 分类标签 → 英文映射
        tag_map = {
            '故事': 'story', '教程': 'tutorial',
            '分析': 'analysis', '杂谈': 'essay',
            '平衡人物志': 'profile', '': '',
        }
        tag_en = tag_map.get(tag, slugify(tag)) if tag else ''

        # 拼接：日期 + 标题拼音 + 分类英文
        parts = [p for p in [dt_part, title_slug, tag_en] if p]
        html_filename = '-'.join(parts) + '.html'

        # 渲染页面
        page_html = render_article_html(fm, body_html)

        # 写入
        output_path = os.path.join(POSTS_DIR, html_filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(page_html)

        html_path_relative = 'posts/' + html_filename
        html_mapping[md_file] = html_path_relative
        print(f"  [OK] {md_file} -> {html_path_relative}")

    # 更新 manifest.json，添加 articles_html 映射
    update_manifest(html_mapping)

    print(f"\n构建完成！共生成 {len(html_mapping)} 篇文章静态页")
    return True


def update_manifest(html_mapping):
    """在 manifest.json 中添加/更新 articles_html 字段"""
    manifest = {}
    if os.path.isfile(MANIFEST_FILE):
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
            try:
                manifest = json.load(f)
            except json.JSONDecodeError:
                manifest = {}

    # 更新或创建 articles_html 映射
    manifest['articles_html'] = html_mapping

    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"  [OK] manifest.json updated (articles_html: {len(html_mapping)} entries)")


# ============================================================
if __name__ == '__main__':
    success = build()
    sys.exit(0 if success else 1)
