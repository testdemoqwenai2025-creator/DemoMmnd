/* Phase 5: shared search + citation module.
 * Loaded by every page via <script src="search-cite.js"></script>.
 * Does three things:
 *   1. Injects a search box into the header nav.
 *   2. Loads search-index.json and powers client-side fuzzy match with a results dropdown.
 *   3. Loads citations.json and renders inline citation superscripts from data-cite="key1,key2" attributes.
 *
 * Citation usage in HTML: <span data-cite="riemann1859,hadamard1896">some claim</span>
 *   → renders as "some claim [1][2]" with superscript links to the source.
 */
(function () {
  'use strict';

  var SEARCH_INDEX = null;
  var CITATIONS = null;
  var SEARCH_BOX = null;
  var RESULTS_DROPDOWN = null;
  var debounceTimer = null;

  /* ---------- Citation rendering ---------- */
  function renderCitations() {
    if (!CITATIONS) return;
    var nodes = document.querySelectorAll('[data-cite]');
    nodes.forEach(function (node) {
      if (node.dataset.citeRendered) return;
      var keys = node.dataset.cite.split(',').map(function (s) { return s.trim(); });
      var supers = document.createElement('sup');
      supers.className = 'cite-supers';
      keys.forEach(function (key, idx) {
        var cite = CITATIONS[key];
        if (!cite) {
          console.warn('[citations] unknown cite-key:', key);
          return;
        }
        var a = document.createElement('a');
        a.className = 'cite-link cite-' + (cite.provenance || 'unknown');
        a.href = cite.url || cite.code_url || '#';
        a.target = '_blank';
        a.rel = 'noopener';
        a.textContent = '[' + (idx + 1) + ']';
        a.title = cite.authors + ' (' + cite.year + '). ' + cite.title + '. ' + (cite.venue || '') +
          (cite.arxiv ? ' arXiv:' + cite.arxiv : '') +
          (cite.doi ? ' doi:' + cite.doi : '') +
          (cite.provenance === 'classical' ? ' [classical, pre-digital]' : '') +
          (cite.provenance === 'observatory-internal' ? ' [observatory-internal]' : '');
        if (idx > 0) supers.appendChild(document.createTextNode(' '));
        supers.appendChild(a);
      });
      node.appendChild(document.createTextNode(' '));
      node.appendChild(supers);
      node.dataset.citeRendered = '1';
    });
  }

  function loadCitations() {
    if (CITATIONS) { renderCitations(); return; }
    fetch('citations.json?v=' + (window.MMND_CACHE_BUST || Date.now()))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        CITATIONS = d.citations || {};
        renderCitations();
      })
      .catch(function (e) {
        // silent fail — citations are an enhancement, not load-bearing
        if (window.console) console.warn('[citations] load failed:', e.message);
      });
  }

  /* ---------- Search ---------- */
  function fuzzyMatch(query, text) {
    query = query.toLowerCase();
    text = text.toLowerCase();
    if (text.indexOf(query) !== -1) return query.length * 2; // substring match scores high
    // character-by-character subsequence match
    var qi = 0, score = 0, consecutive = 0;
    for (var ti = 0; ti < text.length && qi < query.length; ti++) {
      if (text[ti] === query[qi]) {
        qi++;
        consecutive++;
        score += consecutive; // reward consecutive matches
      } else {
        consecutive = 0;
      }
    }
    return qi === query.length ? score : 0;
  }

  function search(query) {
    if (!SEARCH_INDEX) return [];
    query = query.trim();
    if (!query) return [];
    var results = [];
    for (var i = 0; i < SEARCH_INDEX.entries.length; i++) {
      var e = SEARCH_INDEX.entries[i];
      var titleScore = fuzzyMatch(query, e.title) * 3;
      var textScore = fuzzyMatch(query, e.text);
      var score = titleScore + textScore;
      if (score > 0) results.push({ entry: e, score: score });
    }
    results.sort(function (a, b) { return b.score - a.score; });
    return results.slice(0, 8).map(function (r) { return r.entry; });
  }

  function renderResults(results, query) {
    if (!RESULTS_DROPDOWN) return;
    if (!results.length) {
      RESULTS_DROPDOWN.innerHTML = '<div class="search-empty">No matches for "' + escapeHtml(query) + '"</div>';
      RESULTS_DROPDOWN.classList.add('open');
      return;
    }
    var html = results.map(function (e) {
      var href = e.page + (e.anchor ? '#' + e.anchor : '');
      return '<a class="search-result" href="' + href + '">' +
        '<span class="search-result-kind kind-' + e.kind + '">' + e.kindLabel + '</span>' +
        '<span class="search-result-title">' + highlightMatch(e.title, query) + '</span>' +
        '<span class="search-result-snippet">' + escapeHtml(e.snippet) + '</span>' +
        '</a>';
    }).join('');
    RESULTS_DROPDOWN.innerHTML = html;
    RESULTS_DROPDOWN.classList.add('open');
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function highlightMatch(title, query) {
    var safe = escapeHtml(title);
    var q = escapeHtml(query);
    var re = new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    return safe.replace(re, '<mark>$1</mark>');
  }

  function handleInput() {
    var query = SEARCH_BOX.value;
    if (!query.trim()) {
      if (RESULTS_DROPDOWN) RESULTS_DROPDOWN.classList.remove('open');
      return;
    }
    if (!SEARCH_INDEX) return; // still loading
    renderResults(search(query), query);
  }

  function injectSearchBox() {
    var nav = document.querySelector('header nav');
    if (!nav) return;
    if (document.getElementById('searchBoxWrap')) return; // already injected

    var wrap = document.createElement('div');
    wrap.id = 'searchBoxWrap';
    wrap.className = 'search-box-wrap';
    wrap.innerHTML =
      '<input type="search" id="searchBox" class="search-box" placeholder="Search the observatory…" autocomplete="off" aria-label="Search">' +
      '<div id="resultsDropdown" class="results-dropdown"></div>';
    // insert before the theme toggle
    var themeToggle = nav.querySelector('.theme-toggle');
    if (themeToggle) nav.insertBefore(wrap, themeToggle);
    else nav.appendChild(wrap);

    SEARCH_BOX = document.getElementById('searchBox');
    RESULTS_DROPDOWN = document.getElementById('resultsDropdown');

    SEARCH_BOX.addEventListener('input', function () {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(handleInput, 120);
    });
    SEARCH_BOX.addEventListener('focus', handleInput);
    SEARCH_BOX.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        SEARCH_BOX.value = '';
        RESULTS_DROPDOWN.classList.remove('open');
        SEARCH_BOX.blur();
      } else if (e.key === 'Enter') {
        var first = RESULTS_DROPDOWN.querySelector('.search-result');
        if (first) window.location.href = first.getAttribute('href');
      }
    });

    // close dropdown on outside click
    document.addEventListener('click', function (e) {
      if (!wrap.contains(e.target)) RESULTS_DROPDOWN.classList.remove('open');
    });
  }

  function injectSearchStyles() {
    if (document.getElementById('searchCiteStyles')) return;
    var style = document.createElement('style');
    style.id = 'searchCiteStyles';
    style.textContent = [
      '/* search box */',
      '.search-box-wrap{position:relative;margin-left:.5rem;}',
      '.search-box{width:clamp(140px,18vw,220px);padding:.5rem .75rem;border:1px solid var(--border,#e5e0d8);border-radius:1.5rem;background:var(--bg,#faf7f2);color:var(--fg,#1a1a1a);font-size:.8125rem;font-family:inherit;outline:none;transition:border-color .15s,box-shadow .15s;}',
      '.search-box:focus{border-color:var(--primary,#c2410c);box-shadow:0 0 0 3px rgba(194,65,12,.12);}',
      '.search-box::placeholder{color:var(--muted,#736a5e);}',
      '.results-dropdown{position:absolute;top:calc(100% + .25rem);right:0;left:0;min-width:280px;max-height:60vh;overflow-y:auto;background:var(--card,#fefcf8);border:1px solid var(--border,#e5e0d8);border-radius:.5rem;box-shadow:0 12px 32px rgba(0,0,0,.12);z-index:200;display:none;}',
      '.results-dropdown.open{display:block;}',
      '.search-result{display:flex;flex-direction:column;gap:.125rem;padding:.625rem .875rem;text-decoration:none;color:var(--fg,#1a1a1a);border-bottom:1px solid var(--border,#e5e0d8);transition:background .1s;}',
      '.search-result:last-child{border-bottom:none;}',
      '.search-result:hover,.search-result.active{background:var(--accent-bg,rgba(194,65,12,.08));}',
      '.search-result-kind{font-size:.625rem;text-transform:uppercase;letter-spacing:.1em;font-weight:600;padding:.0625rem .375rem;border-radius:.25rem;align-self:flex-start;}',
      '.kind-card{background:rgba(194,65,12,.15);color:#c2410c;}',
      '.kind-tag{background:rgba(14,116,160,.15);color:#0e7490;}',
      '.kind-timeline{background:rgba(124,58,237,.15);color:#7c3aed;}',
      '.kind-stage{background:rgba(8,145,178,.15);color:#0891b2;}',
      '.kind-page{background:rgba(190,24,93,.15);color:#be185d;}',
      '.search-result-title{font-size:.875rem;font-weight:600;line-height:1.3;}',
      '.search-result-title mark{background:rgba(194,65,12,.25);color:inherit;border-radius:2px;padding:0 1px;}',
      '.search-result-snippet{font-size:.75rem;color:var(--muted,#736a5e);line-height:1.4;overflow:hidden;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;}',
      '.search-empty{padding:1rem .875rem;text-align:center;color:var(--muted,#736a5e);font-size:.8125rem;}',
      '/* citation superscripts */',
      '.cite-supers{font-size:.7em;vertical-align:super;line-height:0;margin-left:.1em;}',
      '.cite-link{color:var(--primary,#c2410c);text-decoration:none;font-weight:600;border-bottom:1px dotted var(--primary,#c2410c);padding:0 .1em;}',
      '.cite-link:hover{text-decoration:none;border-bottom-style:solid;}',
      '.cite-classical{color:var(--muted,#736a5e);border-bottom-color:var(--muted,#736a5e);}',
      '.cite-observatory-internal{color:#0891b2;border-bottom-color:#0891b2;}',
      '.cite-canonical-blog{color:#0e7490;border-bottom-color:#0e7490;}',
      '/* responsive: shrink search on narrow screens */',
      '@media (max-width:640px){.search-box-wrap{margin-left:0;flex:1;max-width:140px;}.search-box{width:100%;}.results-dropdown{position:fixed;left:1rem;right:1rem;min-width:0;}}'
    ].join('\n');
    document.head.appendChild(style);
  }

  function loadSearchIndex() {
    if (SEARCH_INDEX) { return; }
    fetch('search-index.json?v=' + (window.MMND_CACHE_BUST || Date.now()))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        SEARCH_INDEX = d;
        // if the user already typed before index loaded, re-run
        if (SEARCH_BOX && SEARCH_BOX.value.trim()) handleInput();
      })
      .catch(function (e) {
        if (window.console) console.warn('[search] load failed:', e.message);
      });
  }

  function init() {
    injectSearchStyles();
    injectSearchBox();
    loadCitations();
    loadSearchIndex();
  }

  // boot on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  // also re-render citations after dynamic content loads (e.g., timeline.json fetch)
  window.addEventListener('load', function () { setTimeout(loadCitations, 300); });
  // re-render when pages signal their dynamic content changed (timeline filter, sources popup, etc.)
  window.addEventListener('mmnd-content-changed', function () { loadCitations(); });
})();
