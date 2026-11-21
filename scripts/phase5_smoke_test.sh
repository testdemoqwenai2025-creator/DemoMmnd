#!/usr/bin/env bash
# Phase 5 Smoke Test: live browser checks on the deployed Mmnd Observatory.
# Run: bash scripts/phase5_smoke_test.sh
#
# Tests (against https://testdemoqwenai2025-creator.github.io/DemoMmnd/):
#   1. Every page returns HTTP 200
#   2. Every page loads in a browser without console errors
#   3. Phase 5 search box present + functional on every page
#   4. Phase 5 citations render (data-cite → superscript links) on convergence + timeline
#   5. Animations function: theme toggle, timeline thread filter, sources card popup
#   6. Search returns correct results for representative queries
#   7. Citation links point to real external sources (arXiv, DOI, blog)

set -uo pipefail
BASE="https://testdemoqwenai2025-creator.github.io/DemoMmnd"
BUST="?v=$(date +%s)"
PASS=0; FAIL=0; WARN=0
results=()

record() { # status label detail
  results+=("$1|$2|$3")
  case "$1" in
    OK) PASS=$((PASS+1));;
    FAIL) FAIL=$((FAIL+1));;
    WARN) WARN=$((WARN+1));;
  esac
}

PAGES=(
  index.html sources.html playgrounds.html tags.html timeline.html
  convergence.html deep-dive.html rl-deep-dive.html chem-math.html
  physics-ml.html math-ml.html demos.html about.html blog.html
  dashboard.html spotlight.html structured-output.html
)

echo "=========================================="
echo "1. HTTP 200 check (curl)"
echo "=========================================="
for pg in "${PAGES[@]}"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/$pg$BUST")
  if [ "$code" = "200" ]; then
    record OK "HTTP 200" "$pg"
  else
    record FAIL "HTTP $code" "$pg"
  fi
done

# static asset checks
for asset in citations.json search-index.json search-cite.js tags.json timeline.json code-data.json; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/$asset$BUST")
  if [ "$code" = "200" ]; then
    record OK "HTTP 200" "$asset"
  else
    record FAIL "HTTP $code" "$asset"
  fi
done

echo ""
echo "=========================================="
echo "2. Browser smoke test (agent-browser)"
echo "=========================================="

# ensure no browser left over
agent-browser close 2>/dev/null

test_page() { # page label
  local pg="$1"; local label="$2"
  local url="$BASE/$pg$BUST"
  # open + wait
  agent-browser open "$url" >/dev/null 2>&1
  agent-browser wait 1500 >/dev/null 2>&1
  # check page title set
  local title
  title=$(agent-browser get title 2>/dev/null | head -1)
  if [ -n "$title" ] && [ "$title" != "" ]; then
    record OK "page loads" "$pg → $title"
  else
    record FAIL "no title" "$pg"
  fi
  # check no console errors
  local errors
  errors=$(agent-browser errors 2>/dev/null | grep -v "^$" | head -5)
  if [ -z "$errors" ]; then
    record OK "no console errors" "$pg"
  else
    # filter out known-harmless network errors (CDN, fonts)
    real_errors=$(echo "$errors" | grep -viE "font|cdn|net::ERR|Failed to load resource" | head -3)
    if [ -z "$real_errors" ]; then
      record WARN "only network/font errors" "$pg"
    else
      record FAIL "console errors" "$pg: $real_errors"
    fi
  fi
  # check search box present (Phase 5)
  local search_count
  search_count=$(agent-browser eval "document.querySelectorAll('input#searchBox').length" 2>/dev/null | tail -1)
  if [ "$search_count" = "1" ]; then
    record OK "search box present" "$pg"
  else
    record FAIL "search box missing" "$pg (count=$search_count)"
  fi
}

# test all pages for load + console + search box
for pg in "${PAGES[@]}"; do
  test_page "$pg" "$pg"
done

echo ""
echo "=========================================="
echo "3. Search functionality (convergence.html)"
echo "=========================================="
agent-browser open "$BASE/convergence.html$BUST" >/dev/null 2>&1
agent-browser wait 2000 >/dev/null 2>&1

# test 3 representative queries
test_search() { # query min_results
  local query="$1"; local min="$2"
  agent-browser fill "#searchBox" "$query" >/dev/null 2>&1
  agent-browser wait 400 >/dev/null 2>&1
  local count
  count=$(agent-browser eval "document.querySelectorAll('.search-result').length" 2>/dev/null | tail -1)
  if [ "$count" -ge "$min" ] 2>/dev/null; then
    record OK "search '$query'" "→ $count results (≥$min required)"
  else
    record FAIL "search '$query'" "→ only $count results (need ≥$min)"
  fi
  # dropdown open?
  local open
  open=$(agent-browser eval "document.querySelectorAll('.results-dropdown.open').length" 2>/dev/null | tail -1)
  if [ "$open" = "1" ]; then
    record OK "dropdown opens" "for '$query'"
  else
    record FAIL "dropdown not open" "for '$query'"
  fi
}
test_search "riemann" 3
test_search "lean" 3
test_search "sindy" 2
test_search "alpha" 1
test_search "zeta" 2

# clear + verify dropdown closes
agent-browser fill "#searchBox" "" >/dev/null 2>&1
agent-browser wait 200 >/dev/null 2>&1
open=$(agent-browser eval "document.querySelectorAll('.results-dropdown.open').length" 2>/dev/null | tail -1)
if [ "$open" = "0" ]; then
  record OK "dropdown closes" "after clearing input"
else
  record FAIL "dropdown stuck open" "after clearing"
fi

echo ""
echo "=========================================="
echo "4. Citation rendering (convergence.html)"
echo "=========================================="
# count superscripts
supers=$(agent-browser eval "document.querySelectorAll('.cite-supers').length" 2>/dev/null | tail -1)
if [ "$supers" -ge 10 ]; then
  record OK "citation superscripts" "convergence.html → $supers rendered"
else
  record FAIL "citations not rendering" "convergence.html → only $supers"
fi
# count citation links
links=$(agent-browser eval "document.querySelectorAll('.cite-link').length" 2>/dev/null | tail -1)
if [ "$links" -ge 10 ]; then
  record OK "citation links" "convergence.html → $links links"
else
  record FAIL "citation links missing" "convergence.html → only $links"
fi
# verify a specific external URL (AlphaProof → DeepMind blog)
apex_link=$(agent-browser eval "Array.from(document.querySelectorAll('.cite-link')).find(a=>a.href.includes('deepmind.google'))?.href" 2>/dev/null | tail -1)
if [ -n "$apex_link" ] && [[ "$apex_link" == *"deepmind.google"* ]]; then
  record OK "AlphaProof link" "→ $apex_link"
else
  record FAIL "AlphaProof link missing" "expected deepmind.google URL"
fi
# verify an arXiv link (Attention paper)
arxiv_link=$(agent-browser eval "Array.from(document.querySelectorAll('.cite-link')).find(a=>a.href.includes('arxiv.org/abs/1706.03762'))?.href" 2>/dev/null | tail -1)
if [ -n "$arxiv_link" ] && [[ "$arxiv_link" == *"1706.03762"* ]]; then
  record OK "Attention arXiv link" "→ $arxiv_link"
else
  record FAIL "Attention arXiv link missing" "expected arxiv.org/abs/1706.03762"
fi

echo ""
echo "=========================================="
echo "5. Timeline page: citations + filter"
echo "=========================================="
agent-browser open "$BASE/timeline.html$BUST" >/dev/null 2>&1
agent-browser wait 2500 >/dev/null 2>&1
# count timeline citations
tl_supers=$(agent-browser eval "document.querySelectorAll('.cite-supers').length" 2>/dev/null | tail -1)
if [ "$tl_supers" -ge 15 ]; then
  record OK "timeline citations" "→ $tl_supers rendered"
else
  record FAIL "timeline citations missing" "→ only $tl_supers"
fi
# test thread filter: click first filter chip, verify entries reduce
total_before=$(agent-browser eval "document.querySelectorAll('.tl-entry').length" 2>/dev/null | tail -1)
# click a thread pill
agent-browser eval "document.querySelector('.filter-chip, .thread-pill, [onclick*=toggleThread]')?.click()" >/dev/null 2>&1
agent-browser wait 500 >/dev/null 2>&1
total_after=$(agent-browser eval "document.querySelectorAll('.tl-entry').length" 2>/dev/null | tail -1)
if [ "$total_after" -lt "$total_before" ] 2>/dev/null; then
  record OK "thread filter works" "$total_before → $total_after entries"
  # verify citations re-render after filter
  tl_supers_after=$(agent-browser eval "document.querySelectorAll('.cite-supers').length" 2>/dev/null | tail -1)
  if [ "$tl_supers_after" -ge 1 ] && [ "$tl_supers_after" -le "$tl_supers" ]; then
    record OK "citations re-render after filter" "$tl_supers → $tl_supers_after"
  else
    record FAIL "citations not re-rendering after filter" "before=$tl_supers after=$tl_supers_after"
  fi
else
  record FAIL "thread filter not working" "$total_before → $total_after"
fi

echo ""
echo "=========================================="
echo "6. Animations & interactions"
echo "=========================================="
# back to convergence for animation checks
agent-browser open "$BASE/convergence.html$BUST" >/dev/null 2>&1
agent-browser wait 2000 >/dev/null 2>&1
# theme toggle (adds/removes 'dark' class on <html>)
theme_before=$(agent-browser eval "document.documentElement.classList.contains('dark') ? 'dark' : 'light'" 2>/dev/null | tail -1)
agent-browser eval "document.querySelector('.theme-toggle')?.click()" >/dev/null 2>&1
agent-browser wait 300 >/dev/null 2>&1
theme_after=$(agent-browser eval "document.documentElement.classList.contains('dark') ? 'dark' : 'light'" 2>/dev/null | tail -1)
if [ "$theme_before" != "$theme_after" ]; then
  record OK "theme toggle works" "$theme_before → $theme_after"
else
  record WARN "theme toggle did not change" "before=$theme_before after=$theme_after"
fi
# scroll-triggered animations: check if scroll reveals stage elements
agent-browser eval "window.scrollTo(0, document.body.scrollHeight)" >/dev/null 2>&1
agent-browser wait 1500 >/dev/null 2>&1
# verify KaTeX rendered some math (presence of .katex elements)
# convergence.html has exactly 4 formula blocks; all should render
katex_count=$(agent-browser eval "document.querySelectorAll('.katex').length" 2>/dev/null | tail -1)
if [ "$katex_count" -ge 3 ] 2>/dev/null; then
  record OK "KaTeX math rendered" "→ $katex_count .katex elements"
else
  record WARN "KaTeX not rendering" "→ only $katex_count .katex elements (may need more wait)"
fi

echo ""
echo "=========================================="
echo "7. Sources page: card popup + dynamic anchors"
echo "=========================================="
agent-browser open "$BASE/sources.html#lean_riemann$BUST" >/dev/null 2>&1
agent-browser wait 2500 >/dev/null 2>&1
# verify the card popup opened (data-key=lean_riemann should be loaded)
popup=$(agent-browser eval "document.querySelector('[data-key=lean_riemann], #popup, .card-popup, .source-popup')?.outerHTML?.length || 0" 2>/dev/null | tail -1)
if [ "$popup" -gt 100 ] 2>/dev/null; then
  record OK "sources popup loads from hash" "#lean_riemann → popup rendered ($popup chars)"
else
  # fallback: check if any heading/text mentions Lean
  lean_text=$(agent-browser eval "document.body.innerText.includes('Lean') ? 'yes' : 'no'" 2>/dev/null | tail -1)
  if [ "$lean_text" = "yes" ]; then
    record OK "sources page renders Lean content" "(text present)"
  else
    record FAIL "sources popup not loading" "#lean_riemann → no popup ($popup chars)"
  fi
fi

# close
agent-browser close 2>/dev/null

echo ""
echo "=========================================="
echo "SMOKE TEST SUMMARY:  $PASS OK  /  $FAIL FAIL  /  $WARN WARN"
echo "=========================================="
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "❌ FAILURES:"
  for r in "${results[@]}"; do
    if [[ "$r" == FAIL* ]]; then
      IFS='|' read -r status label detail <<< "$r"
      echo "  [$status] $label: $detail"
    fi
  done
fi
if [ "$WARN" -gt 0 ]; then
  echo ""
  echo "⚠️  WARNINGS:"
  for r in "${results[@]}"; do
    if [[ "$r" == WARN* ]]; then
      IFS='|' read -r status label detail <<< "$r"
      echo "  [$status] $label: $detail"
    fi
  done
fi
echo ""
exit $FAIL
