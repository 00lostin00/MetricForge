from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]


def main():
    processor = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc", "sane_lists"],
        extension_configs={"toc": {"toc_depth": "2-3"}},
    )
    source = ROOT / "docs/guide.md"
    body = processor.convert(source.read_text(encoding="utf-8"))
    style = """
body{margin:0;background:#edf3f8;color:#193147;font:16px/1.85 'Microsoft YaHei',sans-serif}
.layout{display:grid;grid-template-columns:300px minmax(0,1040px);max-width:1400px;margin:auto}
nav{position:sticky;top:0;height:100vh;overflow:auto;padding:24px 18px;box-sizing:border-box}
nav ul{padding-left:16px}nav li{font-size:13px;line-height:1.5;margin:7px 0}
main{background:white;border-radius:12px;padding:38px 46px;margin:20px 10px;min-width:0}
h1{font-size:28px;color:#155a78}h2{border-top:2px solid #d1e0eb;padding-top:24px}
h3{color:#245b78}a{color:#235e84}code{font:13px/1.7 Consolas,monospace;background:#edf3f8}
pre{background:#142f44;color:#e2edf5;padding:18px;border-radius:8px;overflow:auto}
pre code{background:transparent;color:inherit;white-space:pre}
table{display:block;overflow:auto;border-collapse:collapse;font-size:14px;margin:20px 0}
td,th{border:1px solid #d1dce8;padding:9px 12px;vertical-align:top}
th{background:#e5eff6;text-align:left}tr:nth-child(even){background:#f6f8fb}
@media(max-width:1000px){.layout{display:block}nav{position:relative;height:auto}
nav .toc>ul>li>ul{display:none}main{margin:0;padding:20px}}
@media print{nav{display:none}.layout{display:block}body{font-size:10pt;background:white}
main{padding:0;margin:0}h2,h3{break-after:avoid}pre{overflow:visible}
pre code{white-space:pre-wrap}table{display:table;font-size:8pt}tr{break-inside:avoid}}
"""
    html = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>MetricForge技术指南</title><style>" + style + "</style></head><body>"
        '<div class="layout"><nav><strong>MetricForge · 技术指南</strong>'
        + processor.toc
        + "</nav><main>"
        + body
        + "</main></div></body></html>"
    )
    source.with_suffix(".html").write_text(html, encoding="utf-8")
    print(f"Rendered {len(source.read_text(encoding='utf-8'))} characters, technical guide")


if __name__ == "__main__":
    main()
