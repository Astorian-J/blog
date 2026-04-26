"""
静态页构建脚本
读取 content/articles/*.md → 生成 posts/*.html（文章详情页）
读取 content/glossary/*.md → 生成 glossary/*.html（词条独立页 + 索引页）
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
GLOSSARY_CONTENT_DIR = os.path.join(BLOG_DIR, "content", "glossary")
POSTS_DIR = os.path.join(BLOG_DIR, "posts")
GLOSSARY_OUTPUT_DIR = os.path.join(BLOG_DIR, "glossary")
TEMPLATE_FILE = os.path.join(POSTS_DIR, "article-template.html")
GLOSSARY_TERM_TEMPLATE = os.path.join(POSTS_DIR, "glossary-term-template.html")
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
    # posts/*.html 需要相对路径 ../content/...
    html = re.sub(r'!\[(.*?)\]\((content/[^\)]+)\)', r'<img src="../\2" alt="\1">', html)
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
# Manifest 更新
# ============================================================

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
# 术语词典构建（glossary）
# ============================================================

def build_glossary_term_registry():
    """
    扫描所有 glossary .md 文件，构建「术语名称 → slug」映射表。
    返回: {
        'by_cn': { '平衡委员会': 'balance-council', ... },
        'by_en': { 'Balance Council': 'balance-council', ... },
        'all_data': [ {slug, cn_name, en_name, category, description}, ... ]
    }
    用于在词条描述中自动将已知术语名替换为超链接。
    """
    registry = {'by_cn': {}, 'by_en': {}, 'all_data': []}
    if not os.path.isdir(GLOSSARY_CONTENT_DIR):
        return registry
    for md_file in os.listdir(GLOSSARY_CONTENT_DIR):
        if not md_file.endswith('.md'):
            continue
        slug = md_file[:-3]
        md_path = os.path.join(GLOSSARY_CONTENT_DIR, md_file)
        with open(md_path, 'r', encoding='utf-8') as f:
            data = parse_frontmatter(f.read())
        fm = data['frontmatter']
        cn = fm.get('cn_name', '')
        en = fm.get('en_name', '')
        # 英文名可能包含多个别名（用 ; 或 , 分割），取第一个作为主键
        en_primary = en.split(';')[0].strip().split(',')[0].strip() if en else ''
        if cn:
            registry['by_cn'][cn] = slug
        if en_primary:
            registry['by_en'][en_primary] = slug
            # 也注册完整英文名（含括号备注）
            if en != en_primary:
                registry['by_en'][en] = slug
        registry['all_data'].append({
            'slug': slug,
            'cn_name': cn,
            'en_name': en,
            'category': fm.get('category', ''),
            'description': fm.get('description', ''),
        })
    return registry


def link_glossary_terms(text, registry, current_slug=None):
    """
    在文本中自动检测已知的术语名称并替换为超链接。
    
    规则：
    - 匹配中文全名（如"平衡委员会"）和英文全名（如"Balance Council"）
    - 不链接到当前词条自身（避免自引用）
    - 使用 glossary-link CSS class 标记以便特殊样式
    - 按词长降序匹配（避免短词先误匹配长词的一部分）
    """
    if not text or not (registry['by_cn'] or registry['by_en']):
        return text
    
    # 构建有序的替换列表：(term_name, slug, display_text)，按词长降序
    replacements = []
    for name, slug in registry['by_cn'].items():
        if slug != current_slug:
            replacements.append((name, slug, name))
    for name, slug in registry['by_en'].items():
        if slug != current_slug:
            replacements.append((name, slug, name))
    
    # 按长度降序：先替换长的，避免 "Nerf" 先于 "Nerf Bat" 被错误匹配
    replacements.sort(key=lambda x: len(x[0]), reverse=True)
    
    result = text
    for term_name, slug, display in replacements:
        # 使用单词边界或中文边界来精确匹配
        # 中文术语直接匹配；英文术语需要防止部分匹配（如 "Meta" 不应匹配 "Metagame" 中的前缀）
        if any('\u4e00' <= ch <= '\u9fff' for ch in term_name):
            # 中文：直接全文匹配（不使用 \b 因为中文没有 word boundary）
            pattern = re.escape(term_name)
        else:
            # 英文：使用 \b 确保是独立词汇
            pattern = r'\b' + re.escape(term_name) + r'\b'
        
        link_html = f'<a href="{slug}.html" class="glossary-link">{display}</a>'
        result = re.sub(pattern, link_html, result)
    
    return result


def render_glossary_description(description_text, registry, current_slug=None):
    """渲染词条描述：先转 HTML，再自动插入术语超链接"""
    html = render_md(description_text)
    html = link_glossary_terms(html, registry, current_slug=current_slug)
    return html


def render_glossary_term_html(fm, body_html, registry):
    """用模板生成完整的词条详情页"""
    with open(GLOSSARY_TERM_TEMPLATE, 'r', encoding='utf-8') as f:
        template = f.read()
    
    # 生成相关词条推荐（同分类 + 描述中提到的其他词条）
    current_category = fm.get('category', '')
    current_slug = fm.get('_slug', '')
    related = []
    seen_slugs = {current_slug}
    
    # 同分类的其他词条优先
    for item in registry['all_data']:
        if item['slug'] in seen_slugs:
            continue
        if item['category'] == current_category and item['slug'] != current_slug:
            related.append(item)
            seen_slugs.add(item['slug'])
    
    # 补充其他分类词条（最多显示 8 个相关）
    for item in registry['all_data']:
        if len(related) >= 8:
            break
        if item['slug'] in seen_slugs:
            continue
        related.append(item)
        seen_slugs.add(item['slug'])
    
    # 渲染相关词条链接 HTML
    related_links = ''
    for r in related:
        label = r['cn_name'] or r['en_name']
        related_links += f'        <a href="{r["slug"]}.html" class="related-tag">{label}<span class="arrow">→</span></a>\n'
    
    related_display = '' if not related else ''
    
    replacements = {
        '{{cn_name}}': fm.get('cn_name', ''),
        '{{en_name}}': fm.get('en_name', ''),
        '{{category}}': fm.get('category', ''),
        '{{body}}': body_html,
        '{{related_links}}': related_links,
        '{{related_display}}': related_display,
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    
    return template


def generate_glossary_index(registry):
    """
    生成独立的术语词典索引页 glossary/index.html。
    这是一个纯静态页面，自带搜索/筛选功能（与前台 index.html 的面板逻辑一致但完全独立）。
    """
    all_terms = sorted(registry['all_data'], key=lambda x: x['cn_name'])
    
    # 构建 JS 数据数组
    terms_js_data = []
    for t in all_terms:
        terms_js_data.append({
            'slug': t['slug'],
            'cn_name': t['cn_name'],
            'en_name': t['en_name'],
            'category': t['category'],
        })
    
    page = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>昆特牌术语词典 | 中国社区昆特平衡数据库</title>
    <style>
        *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
        :root {{
            --bg: #fafafa; --card-bg: #ffffff;
            --text-primary: #1a1a1a; --text-secondary: #666666;
            --text-muted: #999999; --accent: #2563eb; --border: #e5e5e5;
            --nav-bg: rgba(255,255,255,0.92); --tag-bg: #f0f0f0;
        }}
        html {{ scroll-behavior: smooth; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            background: var(--bg); color: var(--text-primary); line-height: 1.7; min-height: 100vh;
        }}
        a {{ color: inherit; text-decoration: none; }}
        a:hover {{ color: var(--accent); }}

        /* 导航栏 */
        .navbar {{
            position: fixed; top: 0; left: 0; right: 0; height: 60px;
            background: var(--nav-bg); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border); display: flex; align-items: center;
            justify-content: space-between; padding: 0 40px; z-index: 1000;
        }}
        .logo a {{ font-size: 20px; font-weight: 700; letter-spacing: -0.5px; color: var(--text-primary); text-decoration: none !important; }}
        .logo a span {{ color: var(--accent); }}
        .nav-home {{ font-size: 13px; color: var(--accent); font-weight: 500; }}
        .nav-home:hover {{ text-decoration: underline; }}

        /* 主内容 */
        .main-content {{ max-width: 880px; margin: 0 auto; padding: 90px 24px 60px; }}

        /* 页面标题 */
        .page-header {{ text-align: center; margin-bottom: 36px; padding: 32px 20px; background: linear-gradient(135deg,#2a2a2a 0%,#111 100%); border-radius: 12px; color: #fff; position: relative; overflow: hidden; }}
        .page-header::before {{ content:'';position:absolute;inset:0;background:radial-gradient(circle at 30% 50%,rgba(37,99,235,.08),transparent 55%);pointer-events:none; }}
        .page-header h1 {{ font-size: 28px; font-weight: 800; letter-spacing: 1px; margin-bottom: 8px; position: relative; }}
        .page-header p {{ font-size: 14px; opacity: 0.6; position: relative; }}
        .page-header .count-badge {{ display: inline-block; margin-top: 10px; font-size: 13px; background: rgba(255,255,255,.1); padding: 4px 14px; border-radius: 20px; position: relative; }}

        /* 搜索 */
        .search-bar {{ margin: 24px auto 16px; max-width: 560px; }}
        .search-bar input {{
            width: 100%; padding: 14px 20px; font-size: 15.5px; border: 2px solid var(--border);
            border-radius: 12px; outline: none; transition: border-color .25s;
            background: var(--card-bg); color: var(--text-primary);
        }}
        .search-bar input:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px rgba(37,99,235,.12); }}

        /* 筛选 */
        .filters {{ display: flex; gap: 8px; margin-bottom: 22px; justify-content: center; flex-wrap: wrap; }}
        .filter-btn {{
            padding: 6px 18px; border-radius: 20px; font-size: 13.5px; font-weight: 500;
            background: var(--tag-bg); color: var(--text-secondary); border: 1px solid transparent;
            cursor: pointer; transition: all .2s; user-select: none;
        }}
        .filter-btn:hover {{ border-color: var(--border); }}
        .filter-btn.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

        /* 词条列表 */
        .term-list {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; min-height: 120px; }}
        .term-card {{
            background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px;
            padding: 18px 22px; transition: all .2s ease; display: flex; align-items: center; gap: 16px;
            text-decoration: none !important;
        }}
        .term-card:hover {{ border-color: var(--accent); box-shadow: 0 4px 16px rgba(37,99,235,.10); transform: translateY(-2px); }}
        .term-cat {{ font-size: 11px; color: #fff; background: var(--accent); padding: 2px 8px; border-radius: 6px; white-space: nowrap; flex-shrink: 0; }}
        .term-info {{ flex: 1; min-width: 0; }}
        .term-cn-name {{ font-size: 17px; font-weight: 700; color: var(--text-primary); white-space: nowrap; }}
        .term-en-name {{ font-size: 13px; color: var(--text-secondary); opacity: .85; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 160px; }}
        .empty-state {{ grid-column: 1/-1; text-align: center; padding: 48px 20px; color: var(--text-muted); font-size: 15px; }}

        /* 页脚 */
        footer {{ text-align: center; padding: 28px 24px; font-size: 12.5px; color: var(--text-muted); border-top: 1px solid var(--border); }}
        footer a {{ color: var(--text-secondary); }}

        @media (max-width: 640px) {{
            .navbar {{ padding: 0 20px; }}
            .main-content {{ padding: 74px 14px 36px; }}
            .page-header h1 {{ font-size: 21px; }}
            .term-list {{ grid-template-columns: 1fr; }}
            .term-card {{ flex-direction: column; align-items: flex-start !important; gap: 10px; }}
            .filters {{ gap: 6px; }} .filter-btn {{ padding: 7px 12px; font-size: 13px; }}
        }}
    </style>
</head>
<body>

<nav class="navbar">
    <div class="logo"><a href="../"><span>昆特</span>平衡数据库</a></div>
    <a href="../" class="nav-home">← 返回首页</a>
</nav>

<main class="main-content">

    <div class="page-header">
        <h1>📖 昆特牌术语词典</h1>
        <p>Gwent Terminology Dictionary — 中英文对照 · 可点击跳转查看详情</p>
        <span class="count-badge">共 {len(all_terms)} 个术语</span>
    </div>

    <div class="search-bar">
        <input type="text" id="searchInput" placeholder="🔍 输入中文或英文搜索术语..." autocomplete="off" oninput="renderList()">
    </div>

    <div class="filters" id="filters">
        <button class="filter-btn active" data-cat="all" onclick="setFilter(this)">全部</button>
        <button class="filter-btn" data-cat="机制" onclick="setFilter(this)">机制</button>
        <button class="filter-btn" data-cat="卡牌效果" onclick="setFilter(this)">卡牌效果</button>
        <button class="filter-btn" data-cat="派系术语" onclick="setFilter(this)">派系术语</button>
        <button class="filter-btn" data-cat="赛事术语" onclick="setFilter(this)">赛事术语</button>
        <button class="filter-btn" data-cat="社区用语" onclick="setFilter(this)">社区用语</button>
        <button class="filter-btn" data-cat="其他" onclick="setFilter(this)">其他</button>
    </div>

    <div class="term-list" id="termList"></div>

</main>

<footer><p>&copy; 2026 中国社区昆特平衡数据库</p></footer>

<script>
const TERMS = {json.dumps(terms_js_data, ensure_ascii=False)};
let currentFilter = 'all';

function setFilter(btn) {{
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.cat;
    renderList();
}}

function renderList() {{
    const query = (document.getElementById('searchInput').value || '').trim().toLowerCase();
    let items = TERMS.filter(t => {{
        if (currentFilter !== 'all' && t.category !== currentFilter) return false;
        if (!query) return true;
        return (t.cn_name && t.cn_name.toLowerCase().includes(query)) ||
               (t.en_name && t.en_name.toLowerCase().includes(query));
    }});
    // 按中文拼音排序
    items.sort((a,b) => (a.cn_name||'').localeCompare(b.cn_name||'', 'zh'));

    const container = document.getElementById('termList');
    if (!items.length) {{
        container.innerHTML = '<div class="empty-state">📖 没有找到匹配的术语</div>';
        return;
    }}
    container.innerHTML = items.map(t =>
        `<a href="${{t.slug}}.html" class="term-card">
            <span class="term-cat">${{t.category}}</span>
            <div class="term-info">
                <div class="term-cn-name">${{t.cn_name}}</div>
                <div class="term-en-name">${{t.en_name}}</div>
            </div>
            <span style="color:var(--text-muted);flex-shrink:0;">›</span>
        </a>`
    ).join('');
}}

// 初始化
renderList();
</script>

</body>
</html>'''
    
    index_path = os.path.join(GLOSSARY_OUTPUT_DIR, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(page)
    print(f"  [OK] glossary/index.html ({len(all_terms)} terms)")
    return len(all_terms)


def build_glossary():
    """扫描 glossary 目录，为每个词条生成独立 HTML 页面 + 索引页"""
    os.makedirs(GLOSSARY_OUTPUT_DIR, exist_ok=True)
    
    if not os.path.isdir(GLOSSARY_CONTENT_DIR):
        print("[信息] 术语词典目录不存在")
        return True
    
    if not os.path.exists(GLOSSARY_TERM_TEMPLATE):
        print(f"[错误] 词条模板文件不存在：{GLOSSARY_TERM_TEMPLATE}")
        return False
    
    md_files = [f for f in os.listdir(GLOSSARY_CONTENT_DIR) if f.endswith('.md')]
    if not md_files:
        print("[信息] 术语词典为空")
        return True
    
    # 第一步：构建全局术语注册表（用于跨词条超链接）
    registry = build_glossary_term_registry()
    print(f"[词典] 加载了 {len(registry['all_data'])} 个术语到注册表")
    
    # 第二步：生成每个词条的独立页面
    html_mapping = {}  # content/glossary/xxx.md → glossary/yyy.html
    
    for md_file in sorted(md_files):
        slug = md_file[:-3]
        md_rel_path = f'content/glossary/{md_file}'
        md_path = os.path.join(GLOSSARY_CONTENT_DIR, md_file)
        
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        data = parse_frontmatter(content)
        fm = data['frontmatter']
        fm['_slug'] = slug  # 临时字段供模板使用
        
        # 渲染描述（含自动超链接）
        desc_html = render_glossary_description(fm.get('description', ''), registry, current_slug=slug)
        
        # 渲染完整页面
        page_html = render_glossary_term_html(fm, desc_html, registry)
        
        output_path = os.path.join(GLOSSARY_OUTPUT_DIR, slug + '.html')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(page_html)
        
        html_mapping[md_rel_path] = f'glossary/{slug}.html'
        print(f"  [OK] {md_file} -> glossary/{slug}.html")
    
    # 第三步：生成索引页
    term_count = generate_glossary_index(registry)
    
    # 第四步：更新 manifest.json
    update_manifest_glossary(html_mapping)
    
    print(f"\n[词典] 构建完成！共生成 {len(html_mapping)} 个词条页 + 1 个索引页")
    return True


def update_manifest_glossary(html_mapping):
    """在 manifest.json 中添加/更新 glossary_html 字段"""
    manifest = {}
    if os.path.isfile(MANIFEST_FILE):
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
            try:
                manifest = json.load(f)
            except json.JSONDecodeError:
                manifest = {}
    
    manifest['glossary_html'] = html_mapping
    
    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    print(f"  [OK] manifest.json updated (glossary_html: {len(html_mapping)} entries)")


# ============================================================
# 主构建流程
# ============================================================

def build():
    """扫描 articles 目录，为每篇 md 生成静态 HTML；同时构建术语词典"""
    # 确保输出目录存在
    os.makedirs(POSTS_DIR, exist_ok=True)

    # 读取模板
    if not os.path.exists(TEMPLATE_FILE):
        print(f"[错误] 模板文件不存在：{TEMPLATE_FILE}")
        return False

    # 扫描所有文章
    if not os.path.isdir(CONTENT_DIR):
        print(f"[警告] 文章目录不存在：{CONTENT_DIR}，跳过文章构建")

    md_files = [f for f in os.listdir(CONTENT_DIR)] if os.path.isdir(CONTENT_DIR) else []
    md_files = [f for f in md_files if f.endswith('.md')]
    
    if not md_files:
        print("[信息] 没有找到任何文章")
        html_mapping = {}
    else:
        # 生成文件映射表（用于更新 manifest）
        # key 用完整相对路径（与 manifest.articles 一致，确保前台 goToArticle() 直接命中）
        html_mapping = {}  # content/articles/xxx.md → posts/yyy.html

        for md_file in sorted(md_files):
            md_path = os.path.join(CONTENT_DIR, md_file)
            md_rel_path = os.path.relpath(md_path, BLOG_DIR).replace('\\', '/')  # 完整相对路径作为 key
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
            html_mapping[md_rel_path] = html_path_relative  # 用完整相对路径作为 key
            print(f"  [OK] {md_file} -> {html_path_relative}")

    # 更新 manifest.json，添加 articles_html 映射
    update_manifest(html_mapping)

    print(f"\n[文章] 构建完成！共生成 {len(html_mapping)} 篇文章静态页")

    # 同时构建术语词典
    build_glossary()

    return True


# ============================================================
if __name__ == '__main__':
    success = build()
    sys.exit(0 if success else 1)
