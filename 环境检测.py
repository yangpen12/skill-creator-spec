#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
沙箱环境检测脚本

用途：在 Agent 平台的沙箱里运行一次，弄清楚 Python 环境能做什么、不能做什么。
用法：python 环境检测.py
输出：先逐项打印检测结果，最后输出一段“平台事实”，把它整块粘贴进提示词模板的空位。

说明：
- 每一项检测互不影响，一项失败不会中断后面的检测。
- 只在检测过程中写入少量测试文件，检测结束后删除。
- 脚本只能测出 Python 环境的能力。技能的文件格式、产物能否下载等问题，见《环境检测-使用说明》。
"""

import datetime
import importlib
import os
import platform
import shutil
import sys
import tempfile

RAW = []
FACT = {}

WATCH = [
    ("reportlab", "reportlab"), ("lxml", "lxml"), ("pillow", "Pillow"),
    ("numpy", "numpy"), ("pandas", "pandas"), ("openpyxl", "openpyxl"),
    ("xlsxwriter", "XlsxWriter"), ("python-docx", "python-docx"),
    ("python-pptx", "python-pptx"), ("pymupdf", "PyMuPDF"), ("pypdf", "pypdf"),
    ("pdfplumber", "pdfplumber"), ("matplotlib", "matplotlib"), ("fpdf2", "fpdf2"),
]

FONT_KEYS = ("cjk", "sourcehan", "wqy", "wenquanyi", "simhei", "simsun", "msyh",
             "yahei", "droid", "arphic", "ukai", "uming", "pingfang", "heiti",
             "songti", "kaiti", "fangsong")


def brief(e, n=200):
    """把异常压成一行短文本。"""
    return "%s: %s" % (type(e).__name__, str(e).replace("\n", " ")[:n])


def run(name, fn):
    """运行一项检测并立即打印。fn 返回 (状态, 说明)，状态为 True / False / None。"""
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, brief(e)
    status = "通过" if ok is True else ("不确定" if ok is None else "失败")
    print("[%s] %s：%s" % (status, name, detail), flush=True)
    RAW.append((status, name, detail))
    return ok


# ---------- 基本信息 ----------

def t_basic():
    FACT["py"] = "Python %s，%s %s" % (platform.python_version(), platform.system(), platform.machine())
    FACT["cwd"] = os.getcwd()
    FACT["script_dir"] = os.path.dirname(os.path.abspath(__file__))
    return True, FACT["py"]


def t_dirs():
    return True, "工作目录 %s；脚本所在目录 %s" % (FACT["cwd"], FACT["script_dir"])


# ---------- 已安装的包 ----------

def installed_packages():
    import importlib.metadata as md
    out = {}
    for d in md.distributions():
        try:
            name = d.metadata["Name"]
            if name:
                out[name.lower().replace("_", "-")] = d.version
        except Exception:
            pass
    return out


def t_packages():
    pk = installed_packages()
    FACT["packages"] = pk
    names = sorted(pk)
    shown = ", ".join(names[:300]) + ("…" if len(names) > 300 else "")
    return True, "共 %d 个：%s" % (len(names), shown)


def t_watch():
    pk = FACT.get("packages", {})
    parts = ["%s %s" % (label, pk[dist]) if dist in pk else "%s 未安装" % label
             for label, dist in WATCH]
    return True, "；".join(parts)


# ---------- C 扩展 ----------

def t_stdlib_c():
    mods = ["zlib", "bz2", "_lzma", "_ctypes", "_ssl", "_hashlib", "_decimal",
            "_sqlite3", "pyexpat", "_socket", "_json"]
    bad = []
    for m in mods:
        try:
            importlib.import_module(m)
        except Exception as e:
            bad.append("%s（%s）" % (m, brief(e, 80)))
    FACT["stdlib_c_bad"] = bad
    return (True, "全部可导入") if not bad else (False, "不可导入：" + "，".join(bad))


def t_dlopen():
    import ctypes
    if sys.platform.startswith("linux"):
        cands = ["libc.so.6", "libm.so.6", "libz.so.1", "librt.so.1"]
    elif sys.platform == "darwin":
        cands = ["libSystem.B.dylib", "libm.dylib"]
    else:
        FACT["dlopen"] = None
        return None, "不是 Linux 或 macOS，本项不适用"
    errs = []
    for c in cands:
        try:
            ctypes.CDLL(c)
            FACT["dlopen"] = True
            return True, "成功加载 %s" % c
        except OSError as e:
            errs.append("%s（%s）" % (c, str(e)[:120]))
    if all("cannot open shared object" in x for x in errs):
        FACT["dlopen"] = None
        return None, "系统库里找不到这些动态库，结果不确定：%s" % "；".join(errs)
    FACT["dlopen"] = False
    return False, "；".join(errs)


def t_third_c():
    pk = FACT.get("packages", {})
    targets = [("lxml", "lxml.etree"), ("pillow", "PIL._imaging"), ("numpy", "numpy"),
               ("pandas", "pandas"), ("pymupdf", "fitz")]
    parts, ok_any, bad_any = [], False, False
    for dist, mod in targets:
        if dist not in pk:
            parts.append("%s 未安装" % dist)
            continue
        try:
            importlib.import_module(mod)
            parts.append("%s 可导入" % dist)
            ok_any = True
        except Exception as e:
            parts.append("%s 导入失败（%s）" % (dist, brief(e, 100)))
            bad_any = True
    FACT["third_c"] = "ok" if ok_any and not bad_any else (
        "fail" if bad_any and not ok_any else ("mixed" if ok_any else "none"))
    return True, "；".join(parts)


# ---------- ReportLab 与中文字体 ----------

def t_reportlab_import():
    if "reportlab" not in FACT.get("packages", {}):
        FACT["reportlab"] = "missing"
        return None, "未安装"
    import reportlab
    FACT["reportlab_version"] = getattr(reportlab, "Version", "未知")
    try:
        import _rl_accel  # noqa: F401
        acc = "C 加速模块可用"
    except Exception:
        acc = "C 加速模块不可用，会退回纯 Python 实现（速度慢一些，但能用）"
    return True, "版本 %s，%s" % (FACT["reportlab_version"], acc)


def t_reportlab_pdf():
    if FACT.get("reportlab") == "missing":
        return None, "未安装，跳过"
    from reportlab.pdfgen import canvas
    path = os.path.join(tempfile.gettempdir(), "probe_reportlab_%d.pdf" % os.getpid())
    c = canvas.Canvas(path)
    c.setFont("Helvetica", 12)
    c.drawString(72, 720, "probe 123")
    c.save()
    size = os.path.getsize(path)
    os.remove(path)
    FACT["reportlab"] = "ok" if size > 500 else "fail"
    return FACT["reportlab"] == "ok", "生成了一页 PDF，%d 字节" % size


def find_fonts():
    dirs = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
            os.path.expanduser("~/.local/share/fonts"), "/System/Library/Fonts",
            "/Library/Fonts", r"C:\Windows\Fonts"]
    fonts = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith((".ttf", ".otf", ".ttc")):
                    fonts.append(os.path.join(root, f))
            if len(fonts) > 3000:
                break
    return fonts


def t_cjk_font():
    if FACT.get("reportlab") == "missing":
        return None, "ReportLab 未安装，跳过"
    fonts = find_fonts()
    FACT["font_count"] = len(fonts)
    cands = [f for f in fonts if any(k in os.path.basename(f).lower() for k in FONT_KEYS)]
    if not cands:
        FACT["cjk_font"] = None
        return None, "系统字体目录共 %d 个字体文件，没有认出中文字体（不一定真没有）" % len(fonts)
    from reportlab.pdfbase.ttfonts import TTFont
    last = ""
    for f in cands[:20]:
        try:
            TTFont("ProbeCJK", f, subfontIndex=0)
            FACT["cjk_font"] = f
            return True, "ReportLab 可以注册：%s（中文候选共 %d 个）" % (f, len(cands))
        except Exception as e:
            last = brief(e, 120)
    FACT["cjk_font"] = None
    return False, "找到 %d 个中文候选字体，ReportLab 都注册不了。%s" % (len(cands), last)


def t_cjk_pdf():
    font = FACT.get("cjk_font")
    if not font:
        return None, "没有可注册的中文字体，跳过"
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    pdfmetrics.registerFont(TTFont("ProbeCJK2", font, subfontIndex=0))
    path = os.path.join(tempfile.gettempdir(), "probe_cjk_%d.pdf" % os.getpid())
    c = canvas.Canvas(path)
    c.setFont("ProbeCJK2", 14)
    c.drawString(72, 720, "中文测试 ABC 123")
    c.save()
    size = os.path.getsize(path)
    os.remove(path)
    FACT["cjk_pdf"] = size > 500
    return FACT["cjk_pdf"], "生成了含中文的一页 PDF，%d 字节（是否为方框需要打开确认）" % size


# ---------- 子进程 ----------

def t_subprocess():
    import subprocess
    r = subprocess.run([sys.executable, "-c", "print(123)"], capture_output=True,
                       text=True, timeout=15)
    ok = r.returncode == 0 and "123" in r.stdout
    extra = "，错误输出：%s" % r.stderr.strip()[:200] if r.stderr.strip() else ""
    FACT["subprocess"] = ok
    return ok, "返回码 %s，输出 %r%s" % (r.returncode, r.stdout.strip()[:50], extra)


def t_os_system():
    rc = os.system("echo 456 > %s 2>&1" % os.devnull)
    return rc == 0, "返回码 %s" % rc


def t_fork():
    if not hasattr(os, "fork"):
        return None, "本系统不支持 fork，跳过"
    pid = os.fork()
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
    return True, "可以创建子进程"


# ---------- 网络 ----------

def http_status(url):
    import urllib.request
    with urllib.request.urlopen(url, timeout=8) as resp:
        return resp.status


def t_net_pypi():
    try:
        s = http_status("https://pypi.org/simple/pip/")
        FACT["net"] = True
        return True, "HTTP %s" % s
    except Exception as e:
        FACT["net"] = False
        return False, brief(e)


def t_net_github():
    try:
        s = http_status("https://raw.githubusercontent.com/anthropics/skills/main/README.md")
        FACT["net_github"] = True
        return True, "HTTP %s" % s
    except Exception as e:
        FACT["net_github"] = False
        return False, brief(e)


# ---------- 文件读写 ----------

def write_test(d):
    p = os.path.join(d, "probe_%d.txt" % os.getpid())
    with open(p, "w", encoding="utf-8") as f:
        f.write("probe")
    with open(p, encoding="utf-8") as f:
        ok = f.read() == "probe"
    os.remove(p)
    return ok


def t_write():
    targets = [("工作目录", os.getcwd()), ("脚本所在目录", FACT["script_dir"]),
               ("系统临时目录", tempfile.gettempdir()), ("/tmp", "/tmp"),
               ("用户主目录", os.path.expanduser("~"))]
    good, bad = [], []
    for label, d in targets:
        try:
            (good if write_test(d) else bad).append("%s（%s）" % (label, d))
        except Exception as e:
            bad.append("%s（%s），原因 %s" % (label, d, brief(e, 80)))
    FACT["writable"], FACT["unwritable"] = good, bad
    try:
        free = "；临时目录剩余 %.1f GB" % (shutil.disk_usage(tempfile.gettempdir()).free / 2 ** 30)
    except Exception:
        free = ""
    return bool(good), "可写：" + "、".join(good) + "。不可写：" + "、".join(bad) + free


def t_read_self():
    with open(os.path.abspath(__file__), "rb") as f:
        return True, "技能目录里的文件可以读取（读了本脚本的前 %d 字节）" % len(f.read(16))


# ---------- libs 目录加载 ----------

def t_libs_dir():
    base = tempfile.mkdtemp(prefix="probe_libs_")
    libs = os.path.join(base, "libs")
    os.makedirs(libs)
    with open(os.path.join(libs, "probe_mod.py"), "w") as f:
        f.write("VALUE = 7\n")
    sys.path.insert(0, libs)
    try:
        ok = importlib.import_module("probe_mod").VALUE == 7
    finally:
        sys.path.remove(libs)
        sys.modules.pop("probe_mod", None)
        shutil.rmtree(base, ignore_errors=True)
    FACT["libs_dir"] = ok
    return ok, "把一个目录加入 sys.path 后，成功导入其中的 .py 模块" if ok else "导入失败"


def t_whl():
    import zipfile
    base = tempfile.mkdtemp(prefix="probe_whl_")
    whl = os.path.join(base, "probe_whl_pkg-1.0-py3-none-any.whl")
    with zipfile.ZipFile(whl, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("probe_whl_mod.py", "VALUE = 9\n")
        z.writestr("probe_whl_pkg-1.0.dist-info/METADATA",
                   "Metadata-Version: 2.1\nName: probe-whl-pkg\nVersion: 1.0\n")
    sys.path.insert(0, whl)
    try:
        ok = importlib.import_module("probe_whl_mod").VALUE == 9
    finally:
        sys.path.remove(whl)
        sys.modules.pop("probe_whl_mod", None)
        shutil.rmtree(base, ignore_errors=True)
    FACT["whl"] = ok
    return ok, "把纯 Python 的 whl 文件直接加入 sys.path 后导入成功" if ok else "导入失败"


# ---------- 资源限制与外部程序 ----------

def t_rlimit():
    try:
        import resource
    except ImportError:
        return None, "本系统没有 resource 模块，跳过"
    items = [("RLIMIT_AS", "虚拟内存"), ("RLIMIT_NOFILE", "打开文件数"), ("RLIMIT_NPROC", "进程数"),
             ("RLIMIT_CPU", "CPU 时间（秒）"), ("RLIMIT_FSIZE", "单文件大小（字节）"),
             ("RLIMIT_STACK", "栈大小（字节）")]
    parts = []
    for n, label in items:
        if hasattr(resource, n):
            soft, hard = resource.getrlimit(getattr(resource, n))
            fmt = lambda v: "无限制" if v == resource.RLIM_INFINITY else str(v)
            parts.append("%s %s/%s" % (label, fmt(soft), fmt(hard)))
    FACT["rlimit"] = "；".join(parts)
    return True, FACT["rlimit"]


def t_tools():
    tools = ["soffice", "libreoffice", "pandoc", "wkhtmltopdf", "node", "zip", "unzip", "fc-list"]
    found = [t for t in tools if shutil.which(t)]
    FACT["tools"] = found
    return True, ("找到：" + "、".join(found)) if found else "一个都没找到"


# ---------- 汇总 ----------

def yn(v):
    return {True: "可以", False: "不能", None: "不确定"}[v]


def c_ext_text():
    if FACT.get("dlopen") is False or FACT.get("stdlib_c_bad"):
        return "不能使用（加载动态库被拦截，或标准库的 C 扩展导入失败）"
    if FACT.get("dlopen") is True:
        return "可以使用（加载动态库没有被拦截）"
    return "不确定（标准库的 C 扩展能导入，但额外动态库的加载没有测出来）"


def c_ext_state():
    return "no" if (FACT.get("dlopen") is False or FACT.get("stdlib_c_bad")) else (
        "yes" if FACT.get("dlopen") is True else "unknown")


def pdf_text():
    st = FACT.get("reportlab")
    if st == "missing":
        return "ReportLab 未安装。先把 reportlab 的 whl 放进 libs 目录，再验证。"
    if st == "fail":
        return "ReportLab 已安装但生成 PDF 失败，暂时不要依赖它。"
    if st == "ok":
        if FACT.get("cjk_pdf"):
            return ("可以用 ReportLab 生成 PDF，本环境实测通过，中文字体可注册并嵌入"
                    "（用的是系统字体 %s）。换成技能目录里自带的 TTF 时需要再验证一次。" % FACT.get("cjk_font"))
        if FACT.get("cjk_font") is None:
            return "可以用 ReportLab 生成 PDF，本环境实测通过；但系统里没找到能注册的中文字体，需要把 TTF 放进技能目录。"
        return "ReportLab 能生成英文 PDF，但生成中文 PDF 的测试没有通过。"
    return "不确定"


def ppt_text():
    pk = FACT.get("packages", {})
    if c_ext_state() == "no":
        return "python-pptx 不可用。用标准库 zipfile 往固定版式的 .pptx 模板里填文字，这条路线需要做一次小样验证。"
    if c_ext_state() == "unknown":
        return "C 扩展能否加载没有测出来，python-pptx 能否使用也不确定；用一个小样验证，或者改用 zipfile 填固定模板。"
    if pk.get("python-pptx"):
        return "python-pptx 已安装，且 C 扩展可以使用，值得用一个小样验证后采用。"
    if pk.get("lxml"):
        return "lxml 已安装且可导入，可以把 python-pptx 的 whl 放进 libs 目录后验证。"
    return "C 扩展可用，但 lxml 和 python-pptx 都没安装；放进 libs 后验证。"


def build_facts():
    pk = FACT.get("packages", {})
    L = []
    add = L.append
    n = [0]

    def item(text, indent=None):
        n[0] += 1
        add("%d. %s" % (n[0], text))
        if indent:
            for line in indent:
                add("   " + line)

    add("==================== 平台事实（开始） ====================")
    add("检测时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    add("运行环境：%s；工作目录 %s" % (FACT.get("py"), FACT.get("cwd")))
    add("")
    item("联网：访问 pypi.org %s；访问 raw.githubusercontent.com %s" % (
        yn(FACT.get("net")), yn(FACT.get("net_github"))))
    notes = ["注意：相对路径 ./libs 以工作目录为基准，写脚本时优先用基于脚本所在目录的绝对路径。"]
    if not FACT.get("whl"):
        notes.insert(0, "注意：whl 不能直接导入时，要先解压再放进 libs 目录。")
    item("第三方包：只能用已安装的包，或把包放进 libs 目录。目录加入 sys.path 后导入 %s；"
         "纯 Python 的 whl 直接加入 sys.path 导入 %s。" % (yn(FACT.get("libs_dir")), yn(FACT.get("whl"))),
         notes)
    item("带 C 扩展的包：%s" % c_ext_text())
    item("生成 PDF：%s" % pdf_text())
    item("生成可编辑 PPT：%s" % ppt_text())
    item("启动子进程：%s" % yn(FACT.get("subprocess")))
    item("可写目录：%s" % ("、".join(FACT.get("writable", [])) or "无"),
         ["不可写：%s" % "、".join(FACT["unwritable"])] if FACT.get("unwritable") else None)
    if FACT.get("rlimit"):
        item("资源限制：%s" % FACT["rlimit"])
    if FACT.get("tools"):
        item("系统里有的外部程序：%s（能否调用取决于能否启动子进程）" % "、".join(FACT["tools"]))
    item("与文档生成相关的已安装包：",
         ["- %s：%s" % (label, pk[dist] if dist in pk else "未安装") for label, dist in WATCH])
    add("")
    add("【脚本测不了、需要人工确认的】技能的文件格式、产物能否返回前端下载、技能目录能上传的文件类型和大小、"
        "Creator 能使用哪些工具和 MCP。确认结果补在下面：")
    add("- ")
    add("==================== 平台事实（结束） ====================")
    return "\n".join(L)


def main():
    for name in ("stdout", "stderr"):
        try:
            getattr(sys, name).reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("沙箱环境检测，开始于 %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    print("-" * 60, flush=True)
    run("基本信息", t_basic)
    run("目录", t_dirs)
    run("已安装的包", t_packages)
    run("文档生成相关的包", t_watch)
    run("标准库的 C 扩展", t_stdlib_c)
    run("加载动态库（dlopen）", t_dlopen)
    run("第三方的 C 扩展", t_third_c)
    run("ReportLab 导入", t_reportlab_import)
    run("ReportLab 生成 PDF", t_reportlab_pdf)
    run("中文字体", t_cjk_font)
    run("中文 PDF", t_cjk_pdf)
    run("subprocess", t_subprocess)
    run("os.system", t_os_system)
    run("fork", t_fork)
    run("网络：pypi.org", t_net_pypi)
    run("网络：raw.githubusercontent.com", t_net_github)
    run("文件写入", t_write)
    run("读取技能目录里的文件", t_read_self)
    run("libs 目录加载", t_libs_dir)
    run("whl 文件加载", t_whl)
    run("资源限制", t_rlimit)
    run("外部程序", t_tools)

    print("-" * 60, flush=True)
    counts = {s: sum(1 for r in RAW if r[0] == s) for s in ("通过", "失败", "不确定")}
    print("共 %d 项：通过 %d，失败 %d，不确定 %d" % (
        len(RAW), counts["通过"], counts["失败"], counts["不确定"]), flush=True)
    print(flush=True)
    print(build_facts(), flush=True)


if __name__ == "__main__":
    main()
