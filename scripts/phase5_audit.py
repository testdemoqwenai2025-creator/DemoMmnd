#!/usr/bin/env python3
"""Phase 5 Audit: comprehensive static checks on the Mmnd Observatory.
Run: python3 scripts/phase5_audit.py

Checks (each prints OK/FAIL + details):
  A. File inventory: every expected file exists, no orphans
  B. JSON validity: all .json files parse, _meta present where expected
  C. JS syntax: every inline + external .js file passes `node --check`
  D. Internal links: every href/src in every HTML page resolves to a real file
  E. Anchor resolution: every #anchor in citations/search-index/timeline links to an id on the target page
  F. Cite-key integrity: every data-cite key + every timeline.json citations[] key resolves in citations.json
  G. search-index integrity: every entry's page+anchor resolves to a real page+id
  H. Registry cross-references: tags.json entries point to real cards/pages; timeline links resolve
  I. Animation/interaction audit: CSS keyframes/JS transitions are well-formed; theme toggle present;
     mobile nav present; no JS that references undefined functions
  J. Phase 5 wiring: search-cite.js loaded on every page; data-cite spans have matching keys
"""
import json, os, re, subprocess, sys, html.parser
from collections import defaultdict, Counter

SRC = "/home/z/my-project/download/DemoMmnd-public"
PASS, FAIL, WARN = 0, 0, 0
results = []  # (status, label, detail)

def ok(label, detail=""):
    global PASS; PASS += 1
    results.append(("OK", label, detail))
def fail(label, detail=""):
    global FAIL; FAIL += 1
    results.append(("FAIL", label, detail))
def warn(label, detail=""):
    global WARN; WARN += 1
    results.append(("WARN", label, detail))

# ============ A. File inventory ============
EXPECTED_FILES = [
    # registries
    "citations.json", "search-index.json", "tags.json", "timeline.json",
    "code-data.json", "molecules.json", "manifest.json",
    # shared assets
    "search-cite.js",  # CSS is inline per-page, no separate styles.css
    # pages
    "index.html", "sources.html", "playgrounds.html", "tags.html", "timeline.html",
    "convergence.html", "deep-dive.html", "rl-deep-dive.html", "chem-math.html",
    "physics-ml.html", "math-ml.html", "demos.html", "about.html", "blog.html",
    "dashboard.html", "spotlight.html", "structured-output.html",
]
print("=" * 70)
print("A. File inventory")
print("=" * 70)
for f in EXPECTED_FILES:
    p = os.path.join(SRC, f)
    if os.path.exists(p):
        sz = os.path.getsize(p)
        ok(f"exists", f"{f} ({sz} bytes)")
    else:
        fail(f"missing", f)
# orphan check: any .html/.json/.js/.css not in expected list
all_files = [f for f in os.listdir(SRC) if f.endswith((".html",".json",".js",".css"))]
orphans = [f for f in all_files if f not in EXPECTED_FILES]
if orphans:
    for o in orphans: warn("orphan file", o)
else:
    ok("no orphan files")

# ============ B. JSON validity ============
print("\n" + "=" * 70)
print("B. JSON validity")
print("=" * 70)
JSON_FILES = ["citations.json","search-index.json","tags.json","timeline.json",
              "code-data.json","molecules.json","manifest.json"]
for jf in JSON_FILES:
    p = os.path.join(SRC, jf)
    try:
        with open(p, encoding="utf-8") as f: d = json.load(f)
        if isinstance(d, dict) and "_meta" in d:
            ok(f"valid JSON + _meta", f"{jf} ({len(d)-1} top-level keys)")
        else:
            ok(f"valid JSON (no _meta)", jf)
    except Exception as e:
        fail(f"invalid JSON", f"{jf}: {e}")

# ============ C. JS syntax ============
print("\n" + "=" * 70)
print("C. JS syntax (node --check)")
print("=" * 70)
# external JS files
JS_FILES = [f for f in all_files if f.endswith(".js")]
for js in JS_FILES:
    r = subprocess.run(["node","--check",os.path.join(SRC,js)], capture_output=True, text=True)
    if r.returncode == 0: ok(f"node --check", js)
    else: fail(f"JS syntax error", f"{js}: {r.stderr.strip()[:120]}")
# inline <script> blocks without src=
for hf in EXPECTED_FILES:
    if not hf.endswith(".html"): continue
    p = os.path.join(SRC, hf)
    with open(p, encoding="utf-8") as f: html_text = f.read()
    # extract inline scripts (no src attribute)
    inline_blocks = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html_text, re.DOTALL)
    for i, code in enumerate(inline_blocks):
        if not code.strip(): continue
        # write to temp file and check
        tmp = f"/tmp/_audit_inline_{hf}_{i}.js"
        with open(tmp,"w") as tf: tf.write(code)
        r = subprocess.run(["node","--check",tmp], capture_output=True, text=True)
        if r.returncode != 0:
            fail(f"inline JS syntax error", f"{hf} script#{i}: {r.stderr.strip()[:120]}")
        else:
            ok(f"inline JS OK", f"{hf} script#{i} ({len(code)} chars)")
        os.path.exists(tmp) and os.unlink(tmp)

# ============ D. Internal link resolution ============
print("\n" + "=" * 70)
print("D. Internal link resolution (href/src)")
print("=" * 70)
# Build the set of "dynamic anchors" — IDs that exist at runtime but not in static HTML:
#   - sources.html#<key> for every key in code-data.json (cards render from registry)
#   - timeline.html#<thread> for every thread in timeline.json _meta.threads (hash filter)
#   - playgrounds.html#<n> for n in 1..20 (playgrounds are numbered)
#   - tags.html#<tag> for every tag key in tags.json
code_data = json.load(open(os.path.join(SRC,"code-data.json")))
code_keys = set(code_data.keys())
tl_meta = json.load(open(os.path.join(SRC,"timeline.json")))["_meta"]
tl_threads = set(tl_meta["threads"].keys())
tags_data = json.load(open(os.path.join(SRC,"tags.json")))
tag_keys = set(tags_data["tags"].keys())
dynamic_anchors = {
    "sources.html": code_keys,
    "timeline.html": tl_threads,
    "tags.html": tag_keys,
    "playgrounds.html": {str(i) for i in range(1, 21)},
}

# Regex for REAL HTML attributes only: href="..." or src="..." where the value
# does NOT contain a single-quote or + (which would indicate it's inside a JS
# string concatenation like href="'+e.page+'#'+e.anchor+'").
ATTR_RE = re.compile(r'(?:href|src)="([^"\'+]*)"')

# ============ D. Internal link resolution ============
print("\n" + "=" * 70)
print("D. Internal link resolution (href/src)")
print("=" * 70)
# Build the set of "dynamic anchors" — IDs that exist at runtime but not in static HTML:
#   - sources.html#<key> for every key in code-data.json (cards render from registry)
#   - timeline.html#<thread> for every thread in timeline.json _meta.threads (hash filter)
#   - playgrounds.html#<n> for n in 1..20 (playgrounds are numbered)
#   - tags.html#<tag> for every tag key in tags.json
code_data = json.load(open(os.path.join(SRC,"code-data.json")))
code_keys = set(code_data.keys())
tl_meta = json.load(open(os.path.join(SRC,"timeline.json")))["_meta"]
tl_threads = set(tl_meta["threads"].keys())
tags_data = json.load(open(os.path.join(SRC,"tags.json")))
tag_keys = set(tags_data["tags"].keys())
dynamic_anchors = {
    "sources.html": code_keys,
    "timeline.html": tl_threads,
    "tags.html": tag_keys,
    "playgrounds.html": {str(i) for i in range(1, 21)},
}

broken_links = []
for hf in EXPECTED_FILES:
    if not hf.endswith(".html"): continue
    p = os.path.join(SRC, hf)
    with open(p, encoding="utf-8") as f: html_text = f.read()
    for m in ATTR_RE.finditer(html_text):
        link = m.group(1)
        if link.startswith(("http://","https://","mailto:","tel:","data:","javascript:")):
            continue
        # strip query string and anchor
        path_part = link.split("#")[0].split("?")[0]
        if not path_part: continue  # pure anchor
        target = os.path.join(SRC, path_part)
        if not os.path.exists(target):
            broken_links.append((hf, link))
if broken_links:
    for hf, link in broken_links:
        fail("broken link", f"{hf} → {link}")
else:
    ok("all internal links resolve", f"(checked all href/src in {len([f for f in EXPECTED_FILES if f.endswith('.html')])} pages)")

# ============ E. Anchor resolution ============
print("\n" + "=" * 70)
print("E. Anchor resolution (every #anchor has a matching id)")
print("=" * 70)
# build id map per page (static ids in HTML + dynamic anchors from registries)
page_ids = {}
for hf in EXPECTED_FILES:
    if not hf.endswith(".html"): continue
    with open(os.path.join(SRC, hf), encoding="utf-8") as f: ht = f.read()
    ids = set(re.findall(r'\bid="([^"]+)"', ht))
    ids |= set(re.findall(r'<a[^>]*name="([^"]+)"', ht))
    ids |= dynamic_anchors.get(hf, set())
    page_ids[hf] = ids

broken_anchors = []
for hf in EXPECTED_FILES:
    if not hf.endswith(".html"): continue
    with open(os.path.join(SRC, hf), encoding="utf-8") as f: ht = f.read()
    for m in ATTR_RE.finditer(ht):
        link = m.group(1)
        m2 = re.match(r'^([^"#?]+)#([^"]+)$', link)
        if not m2: continue
        path_part, anchor = m2.group(1), m2.group(2)
        if path_part not in page_ids:
            broken_anchors.append((hf, link, "page not found"))
            continue
        if anchor not in page_ids[path_part]:
            broken_anchors.append((hf, link, f"anchor not found (page has {len(page_ids[path_part])} ids)"))
if broken_anchors:
    for hf, link, reason in broken_anchors[:20]:
        fail("broken anchor", f"{hf} → {link} ({reason})")
    if len(broken_anchors) > 20:
        fail(f"... and {len(broken_anchors)-20} more broken anchors", "")
else:
    ok("all cross-page anchors resolve")

# ============ F. Cite-key integrity ============
print("\n" + "=" * 70)
print("F. Cite-key integrity")
print("=" * 70)
citations = json.load(open(os.path.join(SRC,"citations.json")))["citations"]
cite_keys = set(citations.keys())
ok("citations.json keys", f"{len(cite_keys)} keys")

# data-cite in HTML — only match REAL attributes (value has no ' or +, which would
# indicate JS string concatenation like data-cite="'+e.citations.join(',')+'")
DCITE_RE = re.compile(r'data-cite="([^"\'+]*)"')
all_html_cite_keys = set()
for hf in EXPECTED_FILES:
    if not hf.endswith(".html"): continue
    with open(os.path.join(SRC, hf), encoding="utf-8") as f: ht = f.read()
    for m in DCITE_RE.finditer(ht):
        for k in m.group(1).split(","):
            all_html_cite_keys.add(k.strip())
ok("data-cite keys in HTML", f"{len(all_html_cite_keys)} unique keys")
unresolved = all_html_cite_keys - cite_keys
if unresolved: fail("unresolved HTML cite-keys", ", ".join(sorted(unresolved)))
else: ok("all HTML cite-keys resolve")

# timeline.json citations
tl = json.load(open(os.path.join(SRC,"timeline.json")))
tl_keys = set()
for e in tl["entries"]:
    for k in e.get("citations", []): tl_keys.add(k)
ok("timeline.json cite-keys", f"{len(tl_keys)} unique keys")
unresolved_tl = tl_keys - cite_keys
if unresolved_tl: fail("unresolved timeline cite-keys", ", ".join(sorted(unresolved_tl)))
else: ok("all timeline cite-keys resolve")

# ============ G. search-index integrity ============
print("\n" + "=" * 70)
print("G. search-index integrity")
print("=" * 70)
si = json.load(open(os.path.join(SRC,"search-index.json")))
ok("search-index entries", f"{len(si['entries'])} entries")
si_bad = []
for e in si["entries"]:
    page = e.get("page","")
    anchor = e.get("anchor","")
    if page not in page_ids and page != "":
        si_bad.append((e["id"], f"page '{page}' not found"))
        continue
    if anchor and page in page_ids and anchor not in page_ids[page]:
        si_bad.append((e["id"], f"anchor '{page}#{anchor}' not found"))
if si_bad:
    for eid, reason in si_bad: fail("search-index entry", f"{eid}: {reason}")
else:
    ok("all search-index entries resolve to page+anchor")

# ============ H. Registry cross-references ============
print("\n" + "=" * 70)
print("H. Registry cross-references (tags → cards, timeline → pages)")
print("=" * 70)
tags = json.load(open(os.path.join(SRC,"tags.json")))
tag_bad = []
for tag_key, tag in tags["tags"].items():
    for entry in tag.get("entries", []):
        page = entry.get("page","")
        anchor = entry.get("anchor","")
        if page not in page_ids:
            tag_bad.append((tag_key, f"page '{page}' not found"))
            continue
        if anchor and anchor not in page_ids[page]:
            tag_bad.append((tag_key, f"anchor '{page}#{anchor}' not found"))
if tag_bad:
    for tk, reason in tag_bad: fail("tag entry", f"{tk}: {reason}")
else:
    ok(f"all tag entries resolve", f"({sum(len(t.get('entries',[])) for t in tags['tags'].values())} entries)")

tl_bad = []
for i, e in enumerate(tl["entries"]):
    link = e.get("link", {})
    page = link.get("page","")
    anchor = link.get("anchor","")
    if not page: continue
    if page not in page_ids:
        tl_bad.append((i, f"page '{page}' not found"))
        continue
    if anchor and anchor not in page_ids[page]:
        tl_bad.append((i, f"anchor '{page}#{anchor}' not found"))
if tl_bad:
    for i, reason in tl_bad: fail("timeline link", f"entry {i}: {reason}")
else:
    ok("all timeline links resolve", f"({len(tl['entries'])} entries)")

# ============ I. Animation / interaction audit ============
print("\n" + "=" * 70)
print("I. Animation / interaction audit")
print("=" * 70)
# CSS keyframes — count per file, check balanced braces
for hf in EXPECTED_FILES:
    if not hf.endswith(".html"): continue
    with open(os.path.join(SRC, hf), encoding="utf-8") as f: ht = f.read()
    # inline <style>
    for m in re.findall(r'<style[^>]*>(.*?)</style>', ht, re.DOTALL):
        kfs = re.findall(r'@keyframes\s+([^\s{]+)', m)
        if kfs:
            # check balanced braces in keyframes definitions
            for kf in kfs:
                pattern = r'@keyframes\s+' + re.escape(kf) + r'\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}'
                if re.search(pattern, m):
                    pass  # well-formed enough
                else:
                    warn("malformed keyframes", f"{hf}: @{kf}")
    # transition/animation references
    transitions = len(re.findall(r'transition\s*:', ht))
    animations = len(re.findall(r'animation\s*:', ht))
    if transitions or animations:
        ok(f"CSS animations", f"{hf}: {transitions} transitions, {animations} animations")

# JS interaction patterns — check theme toggle, mobile nav present on each page
for hf in EXPECTED_FILES:
    if not hf.endswith(".html"): continue
    if hf in ("blog.html","dashboard.html"): continue  # may be simpler pages
    with open(os.path.join(SRC, hf), encoding="utf-8") as f: ht = f.read()
    # theme toggle
    if 'theme-toggle' in ht or 'toggleTheme' in ht or 'data-theme' in ht:
        ok("theme toggle", hf)
    else:
        warn("no theme toggle", hf)
    # mobile nav (hamburger)
    if 'nav-toggle' in ht or 'hamburger' in ht or 'mobile-nav' in ht or 'menu-toggle' in ht:
        ok("mobile nav", hf)
    elif hf in ("index.html","sources.html","convergence.html"):
        warn("no explicit mobile nav toggle", hf)

# check for undefined function calls in inline JS
print("\n--- checking inline JS for undefined function calls ---")
# collect all function definitions across all files + external JS
all_funcs = set()
for hf in EXPECTED_FILES:
    if not hf.endswith(".html"): continue
    with open(os.path.join(SRC, hf), encoding="utf-8") as f: ht = f.read()
    all_funcs |= set(re.findall(r'function\s+([a-zA-Z_$][\w$]*)', ht))
    all_funcs |= set(re.findall(r'(?:const|let|var)\s+([a-zA-Z_$][\w$]*)\s*=\s*(?:function|\([^)]*\)\s*=>)', ht))
# add external JS
for js in JS_FILES:
    with open(os.path.join(SRC, js), encoding="utf-8") as f: js_text = f.read()
    all_funcs |= set(re.findall(r'function\s+([a-zA-Z_$][\w$]*)', js_text))
# built-in / browser globals to ignore
BUILTINS = {"setTimeout","setInterval","clearTimeout","clearInterval","fetch","console",
            "document","window","navigator","location","history","localStorage","fetch",
            "requestAnimationFrame","cancelAnimationFrame","parseInt","parseFloat","isNaN",
            "JSON","Math","Date","Array","Object","String","Number","Boolean","RegExp",
            "Promise","Error","Map","Set","Symbol","encodeURIComponent","decodeURIComponent",
            "alert","confirm","prompt","addColorStop","createLinearGradient","createRadialGradient",
            "getContext","getImageData","putImageData","drawImage","fillRect","clearRect",
            "beginPath","moveTo","lineTo","arc","fill","stroke","closePath","save","restore",
            "translate","rotate","scale","getBoundingClientRect","scrollIntoView","scrollTo",
            "querySelector","querySelectorAll","getElementById","getElementsByClassName",
            "getElementsByTagName","createElement","createTextNode","appendChild","removeChild",
            "insertBefore","replaceChild","setAttribute","getAttribute","removeAttribute",
            "addEventListener","removeEventListener","dispatchEvent","classList","dataset",
            "innerHTML","textContent","style","className","id","href","value","checked",
            "focus","blur","click","select","submit","reset","preventDefault","stopPropagation",
            "open","close","back","forward","reload","print","alert","confirm","prompt",
            "URL","URLSearchParams","FormData","Headers","Request","Response","Blob","File",
            "FileReader","Image","Audio","Video","Canvas","CanvasRenderingContext2D",
            "WebSocket","EventSource","XMLHttpRequest","fetch","AbortController",
            "IntersectionObserver","MutationObserver","ResizeObserver",
            "customElements","customElementRegistry","shadowRoot","attachShadow",
            "requestFullscreen","exitFullscreen","fullscreenElement"}
for hf in EXPECTED_FILES:
    if not hf.endswith(".html"): continue
    with open(os.path.join(SRC, hf), encoding="utf-8") as f: ht = f.read()
    inline_blocks = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', ht, re.DOTALL)
    for i, code in enumerate(inline_blocks):
        if not code.strip(): continue
        # find TOP-LEVEL function calls only: identifier( NOT preceded by . (method call)
        # use lookbehind to exclude method calls
        calls = set()
        for m in re.finditer(r'(?<![.\w$])([a-zA-Z_$][\w$]*)\s*\(', code):
            calls.add(m.group(1))
        # filter out keywords and builtins
        keywords = {"if","for","while","switch","catch","function","return","typeof","instanceof",
                    "new","delete","void","in","of","do","else","try","throw","class","extends",
                    "super","import","export","default","await","async","yield"}
        unknown = calls - all_funcs - BUILTINS - keywords
        # filter out constructors (capitalized) and single-letter vars
        unknown = {u for u in unknown if not u[0].isupper()}
        unknown = {u for u in unknown if len(u) > 1}
        if unknown:
            warn("possibly undefined function", f"{hf} script#{i}: {', '.join(sorted(unknown))[:80]}")

# ============ J. Phase 5 wiring ============
print("\n" + "=" * 70)
print("J. Phase 5 wiring (search-cite.js + data-cite)")
print("=" * 70)
pages_without_script = []
for hf in EXPECTED_FILES:
    if not hf.endswith(".html"): continue
    with open(os.path.join(SRC, hf), encoding="utf-8") as f: ht = f.read()
    if 'src="search-cite.js"' not in ht:
        pages_without_script.append(hf)
if pages_without_script:
    for p in pages_without_script: fail("missing search-cite.js", p)
else:
    ok("search-cite.js loaded on all pages", f"({len([f for f in EXPECTED_FILES if f.endswith('.html')])} pages)")

# data-cite spans without keys (empty data-cite="")
for hf in EXPECTED_FILES:
    if not hf.endswith(".html"): continue
    with open(os.path.join(SRC, hf), encoding="utf-8") as f: ht = f.read()
    empty = re.findall(r'data-cite="\s*"', ht)
    if empty: fail("empty data-cite", f"{hf}: {len(empty)} empty data-cite attributes")

# citations.json: check every entry has required fields
required_cite_fields = ["key","title","authors","year","type","provenance"]
for k, v in citations.items():
    missing = [f for f in required_cite_fields if f not in v]
    if missing: fail("citation missing fields", f"{k}: missing {missing}")
    else: ok(f"citation fields", k)

# ============ Summary ============
print("\n" + "=" * 70)
print(f"AUDIT SUMMARY:  {PASS} OK  /  {FAIL} FAIL  /  {WARN} WARN")
print("=" * 70)
if FAIL:
    print("\n❌ FAILURES:")
    for s, l, d in results:
        if s == "FAIL": print(f"  [{s}] {l}: {d}")
if WARN:
    print("\n⚠️  WARNINGS:")
    for s, l, d in results:
        if s == "WARN": print(f"  [{s}] {l}: {d}")
print()
sys.exit(1 if FAIL else 0)
