#!/usr/bin/env python3
"""Convert Threema export to nicely formatted HTML."""

import argparse
from datetime import datetime
import html
import json
import os
import re
import shutil
import sys


# Note on Content-Security-Policy for static archives:
# TODO(security): We intentionally omit <meta http-equiv="Content-Security-Policy" content="default-src 'self'">
# because generated archives are opened directly from disk via file:// URLs, where browsers treat each file://
# path as an opaque origin and block sibling ./lib/default.css, ./media/*, and search_index.js under 'self'.
# XSS is mitigated via strict html.escape() in Python, script-safe JSON unicode escaping, and zero innerHTML in JS.

SPLIT_NAV_CSS = """
.t2h-split-nav {
\tmargin: 6px 1ex 10px 1ex;
}
.t2h-back-link {
\tdisplay: inline-block;
\tpadding: 5px 12px;
\tbackground: rgba(255, 255, 255, 0.92);
\tcolor: #1f2937;
\ttext-decoration: none;
\tborder-radius: 999px;
\tborder: 1px solid rgba(0, 0, 0, 0.15);
\tfont-size: 13px;
\tfont-weight: 600;
\tbox-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.t2h-back-link:hover {
\tbackground: #ffffff;
}
@media print {
\t.t2h-split-nav { display: none !important; }
}
"""

CHAT_SEARCH_CSS = """
.t2h-search {
\tposition: fixed;
\ttop: 12px;
\tright: 16px;
\tz-index: 9999;
\tfont-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
\tfont-size: 13px;
\tcolor: #1f2937;
}
.t2h-fab {
\twidth: 40px;
\theight: 40px;
\tborder-radius: 999px;
\tborder: 1px solid rgba(0, 0, 0, 0.16);
\tbackground: rgba(255, 255, 255, 0.94);
\tcolor: #1f2937;
\tcursor: pointer;
\tdisplay: flex;
\talign-items: center;
\tjustify-content: center;
\tbox-shadow: 0 2px 8px rgba(0, 0, 0, 0.16);
\ttransition: transform 0.12s ease, background-color 0.12s ease;
}
.t2h-fab:hover {
\tbackground: #ffffff;
\ttransform: scale(1.04);
}
.t2h-panel {
\tdisplay: none;
\talign-items: center;
\tgap: 6px;
\tflex-wrap: wrap;
\tpadding: 7px 10px;
\tborder-radius: 14px;
\tborder: 1px solid rgba(0, 0, 0, 0.16);
\tbackground: rgba(255, 255, 255, 0.96);
\tbackdrop-filter: blur(8px);
\t-webkit-backdrop-filter: blur(8px);
\tbox-shadow: 0 6px 20px rgba(0, 0, 0, 0.18);
\tmax-width: calc(100vw - 32px);
}
.t2h-search.t2h-open .t2h-fab {
\tdisplay: none;
}
.t2h-search.t2h-open .t2h-panel {
\tdisplay: flex;
}
.t2h-input {
\twidth: 210px;
\tmax-width: 52vw;
\tpadding: 5px 9px;
\tborder: 1px solid #cbd5e1;
\tborder-radius: 8px;
\tfont-size: 13px;
\toutline: none;
\tbackground: #ffffff;
\tcolor: #111827;
}
.t2h-input:focus, .t2h-select:focus {
\tborder-color: #2563eb;
\tbox-shadow: 0 0 0 2px rgba(37, 99, 235, 0.18);
}
.t2h-select {
\tmax-width: 135px;
\tpadding: 5px 7px;
\tborder: 1px solid #cbd5e1;
\tborder-radius: 8px;
\tfont-size: 12px;
\tbackground: #ffffff;
\tcolor: #111827;
\toutline: none;
}
.t2h-count {
\tmin-width: 54px;
\ttext-align: center;
\tfont-variant-numeric: tabular-nums;
\tfont-size: 12px;
\tcolor: #4b5563;
\tuser-select: none;
}
.t2h-count.t2h-zero {
\tcolor: #dc2626;
\tfont-weight: 600;
}
.t2h-btn {
\tpadding: 4px 8px;
\tborder-radius: 7px;
\tborder: 1px solid #cbd5e1;
\tbackground: #f8fafc;
\tcolor: #1f2937;
\tfont-size: 12px;
\tcursor: pointer;
\tline-height: 1.3;
\tuser-select: none;
}
.t2h-btn:hover:not(:disabled) {
\tbackground: #e2e8f0;
}
.t2h-btn:disabled {
\topacity: 0.42;
\tcursor: default;
}
.t2h-btn.t2h-active-toggle {
\tbackground: #1d4ed8;
\tborder-color: #1d4ed8;
\tcolor: #ffffff;
\tfont-weight: 600;
}
div.date > div.t2h-active-msg {
\toutline: 2px solid #f59e0b;
\toutline-offset: 2px;
}
body.t2h-filtering div.date:not(.t2h-date-hit) {
\tdisplay: none !important;
}
body.t2h-filtering div.date > div:not(.t2h-hit) {
\tdisplay: none !important;
}
body.t2h-filtering div.date > div.t2h-hit {
\tcursor: pointer;
}
mark.t2h-mark {
\tbackground-color: #fef08a;
\tcolor: inherit;
\tpadding: 0 1px;
\tborder-radius: 2px;
}
div.t2h-active-msg mark.t2h-mark {
\tbackground-color: #fb923c;
\tcolor: #111827;
}
::highlight(t2h-match) {
\tbackground-color: #fef08a;
\tcolor: #111827;
}
::highlight(t2h-active) {
\tbackground-color: #fb923c;
\tcolor: #111827;
}
@media print {
\t.t2h-search { display: none !important; }
}
"""

CHAT_SEARCH_JS = r"""
(function () {
  "use strict";

  var indexed = false;
  var dateEls = [];
  var msgEls = [];
  var msgBodyEls = [];
  var msgTsEls = [];
  var msgDateIdx = [];
  var msgSenders = [];
  var msgSearchText = [];
  var msgIdToIndex = new Map();
  var senderList = [];

  var matches = [];
  var activePos = -1;
  var filterOnly = false;
  var currentTokens = [];
  var searchGen = 0;

  var hitMsgIndices = [];
  var hitDateIndices = [];
  var prevActiveEl = null;

  var supportsCustomHighlight =
    typeof CSS !== "undefined" &&
    CSS.highlights &&
    typeof Highlight !== "undefined";
  var visibleMatched = new Set();
  var rangeCacheGen = -1;
  var rangeCache = new Map();
  var markedMsgs = new Set();
  var observer = null;
  var rafFilterId = 0;

  function createSearchIcon(size) {
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("width", String(size));
    svg.setAttribute("height", String(size));
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2.2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    var circle = document.createElementNS(ns, "circle");
    circle.setAttribute("cx", "11");
    circle.setAttribute("cy", "11");
    circle.setAttribute("r", "7");
    var line = document.createElementNS(ns, "line");
    line.setAttribute("x1", "20");
    line.setAttribute("y1", "20");
    line.setAttribute("x2", "16.2");
    line.setAttribute("y2", "16.2");
    svg.appendChild(circle);
    svg.appendChild(line);
    return svg;
  }

  function extractBasename(path) {
    if (!path) return "";
    var clean = path.split("#")[0].split("?")[0];
    var slash = clean.lastIndexOf("/");
    return slash >= 0 ? clean.slice(slash + 1) : clean;
  }

  function ensureIndex() {
    if (indexed) return;
    indexed = true;
    var senderSet = new Set();
    var dates = document.querySelectorAll("div.date");
    for (var d = 0; d < dates.length; d++) {
      var dateDiv = dates[d];
      dateEls.push(dateDiv);
      var children = dateDiv.children;
      for (var c = 0; c < children.length; c++) {
        var el = children[c];
        if (el.tagName !== "DIV") continue;
        var h3 = el.querySelector("h3");
        var msgP = el.querySelector("p.msg");
        var tsP = el.querySelector("p.timestamp");
        var sender = h3 ? h3.textContent.trim() : "";
        if (sender) senderSet.add(sender);

        var mediaNames = "";
        if (msgP) {
          var imgs = msgP.querySelectorAll("img[src]");
          for (var k = 0; k < imgs.length; k++) {
            mediaNames += " " + extractBasename(imgs[k].getAttribute("src"));
          }
          var links = msgP.querySelectorAll("a[href]");
          for (var m = 0; m < links.length; m++) {
            mediaNames += " " + extractBasename(links[m].getAttribute("href"));
          }
        }

        var idx = msgEls.length;
        msgEls.push(el);
        msgBodyEls.push(msgP);
        msgTsEls.push(tsP);
        msgDateIdx.push(d);
        msgSenders.push(sender);
        if (el.id) msgIdToIndex.set(el.id, idx);

        var bodyText = msgP ? msgP.textContent : "";
        var tsText = tsP ? tsP.textContent : "";
        msgSearchText.push((bodyText + mediaNames + "\n" + tsText).toLowerCase());
      }
    }
    senderList = Array.from(senderSet).sort();
    populateSenderSelect();
    setupObserver();
  }

  function parseQuery(raw) {
    var tokens = [];
    if (!raw) return tokens;
    var parts = raw.split('"');
    for (var i = 0; i < parts.length; i++) {
      var seg = parts[i].trim().toLowerCase();
      if (!seg) continue;
      if (i % 2 === 1) {
        tokens.push(seg);
      } else {
        var words = seg.split(/\s+/);
        for (var w = 0; w < words.length; w++) {
          if (words[w]) tokens.push(words[w]);
        }
      }
    }
    return tokens;
  }

  function findIntervals(str, tokens) {
    if (!tokens.length || !str) return null;
    var lower = str.toLowerCase();
    if (lower.length !== str.length) return null;
    var raw = [];
    for (var t = 0; t < tokens.length; t++) {
      var tok = tokens[t];
      if (!tok) continue;
      var pos = 0;
      while ((pos = lower.indexOf(tok, pos)) !== -1) {
        raw.push([pos, pos + tok.length]);
        pos += tok.length;
      }
    }
    if (!raw.length) return null;
    raw.sort(function (a, b) {
      return a[0] - b[0] || b[1] - a[1];
    });
    var merged = [raw[0]];
    for (var i = 1; i < raw.length; i++) {
      var last = merged[merged.length - 1];
      if (raw[i][0] <= last[1]) {
        if (raw[i][1] > last[1]) last[1] = raw[i][1];
      } else {
        merged.push(raw[i]);
      }
    }
    return merged;
  }

  function collectTextNodes(root) {
    var nodes = [];
    if (!root) return nodes;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var n;
    while ((n = walker.nextNode())) {
      if (n.nodeValue && n.nodeValue.trim()) nodes.push(n);
    }
    return nodes;
  }

  function getMsgRanges(msgIdx) {
    if (rangeCacheGen !== searchGen) {
      rangeCache.clear();
      rangeCacheGen = searchGen;
    }
    if (rangeCache.has(msgIdx)) return rangeCache.get(msgIdx);
    var ranges = [];
    if (!currentTokens.length) {
      rangeCache.set(msgIdx, ranges);
      return ranges;
    }
    var roots = [msgBodyEls[msgIdx], msgTsEls[msgIdx]];
    for (var r = 0; r < roots.length; r++) {
      var textNodes = collectTextNodes(roots[r]);
      for (var i = 0; i < textNodes.length; i++) {
        var node = textNodes[i];
        var intervals = findIntervals(node.nodeValue, currentTokens);
        if (!intervals) continue;
        for (var j = 0; j < intervals.length; j++) {
          var rng = document.createRange();
          rng.setStart(node, intervals[j][0]);
          rng.setEnd(node, intervals[j][1]);
          ranges.push(rng);
        }
      }
    }
    rangeCache.set(msgIdx, ranges);
    return ranges;
  }

  function clearFallbackMarks() {
    if (!markedMsgs.size) return;
    markedMsgs.forEach(function (idx) {
      var el = msgEls[idx];
      var marks = el.querySelectorAll("mark.t2h-mark");
      for (var i = 0; i < marks.length; i++) {
        var mk = marks[i];
        var parent = mk.parentNode;
        if (parent) {
          parent.replaceChild(document.createTextNode(mk.textContent), mk);
          parent.normalize();
        }
      }
    });
    markedMsgs.clear();
  }

  function applyFallbackMarksForMsg(msgIdx) {
    if (markedMsgs.has(msgIdx) || !currentTokens.length) return;
    var roots = [msgBodyEls[msgIdx], msgTsEls[msgIdx]];
    var applied = false;
    for (var r = 0; r < roots.length; r++) {
      var textNodes = collectTextNodes(roots[r]);
      for (var i = 0; i < textNodes.length; i++) {
        var node = textNodes[i];
        var val = node.nodeValue;
        var intervals = findIntervals(val, currentTokens);
        if (!intervals) continue;
        var frag = document.createDocumentFragment();
        var cursor = 0;
        for (var j = 0; j < intervals.length; j++) {
          var start = intervals[j][0];
          var end = intervals[j][1];
          if (start > cursor) {
            frag.appendChild(document.createTextNode(val.slice(cursor, start)));
          }
          var mark = document.createElement("mark");
          mark.className = "t2h-mark";
          mark.textContent = val.slice(start, end);
          frag.appendChild(mark);
          cursor = end;
        }
        if (cursor < val.length) {
          frag.appendChild(document.createTextNode(val.slice(cursor)));
        }
        if (node.parentNode) {
          node.parentNode.replaceChild(frag, node);
          applied = true;
        }
      }
    }
    if (applied) markedMsgs.add(msgIdx);
  }

  function makeHighlightFromArray(ranges) {
    var h = new Highlight();
    for (var i = 0; i < ranges.length; i++) {
      h.add(ranges[i]);
    }
    return h;
  }

  function updateCustomHighlightsSafe() {
    var activeMsgIdx = activePos >= 0 && activePos < matches.length ? matches[activePos] : -1;
    if (!supportsCustomHighlight) {
      if (!currentTokens.length || !matches.length) {
        clearFallbackMarks();
        return;
      }
      visibleMatched.forEach(function (idx) {
        applyFallbackMarksForMsg(idx);
      });
      if (activeMsgIdx !== -1) {
        applyFallbackMarksForMsg(activeMsgIdx);
      }
      return;
    }
    if (!currentTokens.length || !matches.length) {
      CSS.highlights.delete("t2h-match");
      CSS.highlights.delete("t2h-active");
      return;
    }
    var matchH = new Highlight();
    var hasMatch = false;
    visibleMatched.forEach(function (idx) {
      if (idx === activeMsgIdx) return;
      var r = getMsgRanges(idx);
      for (var i = 0; i < r.length; i++) {
        matchH.add(r[i]);
        hasMatch = true;
      }
    });
    if (hasMatch) {
      CSS.highlights.set("t2h-match", matchH);
    } else {
      CSS.highlights.delete("t2h-match");
    }
    if (activeMsgIdx !== -1) {
      var ar = getMsgRanges(activeMsgIdx);
      if (ar.length) {
        CSS.highlights.set("t2h-active", makeHighlightFromArray(ar));
      } else {
        CSS.highlights.delete("t2h-active");
      }
    } else {
      CSS.highlights.delete("t2h-active");
    }
  }

  function setupObserver() {
    if (typeof IntersectionObserver === "undefined") return;
    observer = new IntersectionObserver(
      function (entries) {
        var changed = false;
        for (var i = 0; i < entries.length; i++) {
          var entry = entries[i];
          var idx = msgIdToIndex.get(entry.target.id);
          if (idx === undefined) continue;
          if (entry.isIntersecting) {
            visibleMatched.add(idx);
            changed = true;
          } else if (visibleMatched.delete(idx)) {
            changed = true;
          }
        }
        if (changed) updateCustomHighlightsSafe();
      },
      { rootMargin: "350px 0px" }
    );
  }

  function clearHitClasses() {
    for (var i = 0; i < hitMsgIndices.length; i++) {
      msgEls[hitMsgIndices[i]].classList.remove("t2h-hit");
    }
    for (var d = 0; d < hitDateIndices.length; d++) {
      dateEls[hitDateIndices[d]].classList.remove("t2h-date-hit");
    }
    hitMsgIndices = [];
    hitDateIndices = [];
  }

  function applyFilterState(isQueryActive) {
    if (rafFilterId) cancelAnimationFrame(rafFilterId);
    rafFilterId = requestAnimationFrame(function () {
      rafFilterId = 0;
      clearHitClasses();
      if (!filterOnly || !isQueryActive) {
        document.body.classList.remove("t2h-filtering");
        return;
      }
      var dateSeen = new Uint8Array(dateEls.length);
      for (var i = 0; i < matches.length; i++) {
        var mIdx = matches[i];
        msgEls[mIdx].classList.add("t2h-hit");
        hitMsgIndices.push(mIdx);
        var dIdx = msgDateIdx[mIdx];
        if (!dateSeen[dIdx]) {
          dateSeen[dIdx] = 1;
          dateEls[dIdx].classList.add("t2h-date-hit");
          hitDateIndices.push(dIdx);
        }
      }
      document.body.classList.add("t2h-filtering");
    });
  }

  // Build UI via safe DOM APIs
  var container = document.createElement("div");
  container.className = "t2h-search";
  container.setAttribute("role", "search");

  var fab = document.createElement("button");
  fab.type = "button";
  fab.className = "t2h-fab";
  fab.title = "Search chat (/ or Ctrl+K)";
  fab.setAttribute("aria-label", "Search chat");
  fab.appendChild(createSearchIcon(18));

  var panel = document.createElement("div");
  panel.className = "t2h-panel";

  var input = document.createElement("input");
  input.type = "search";
  input.className = "t2h-input";
  input.placeholder = "Search messages\u2026";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.setAttribute("aria-label", "Search messages");

  var senderSelect = document.createElement("select");
  senderSelect.className = "t2h-select";
  senderSelect.setAttribute("aria-label", "Filter by sender");
  var allOpt = document.createElement("option");
  allOpt.value = "";
  allOpt.textContent = "All senders";
  senderSelect.appendChild(allOpt);

  var countEl = document.createElement("span");
  countEl.className = "t2h-count";
  countEl.textContent = "";

  var prevBtn = document.createElement("button");
  prevBtn.type = "button";
  prevBtn.className = "t2h-btn";
  prevBtn.textContent = "\u2191";
  prevBtn.title = "Older match (Enter)";
  prevBtn.disabled = true;

  var nextBtn = document.createElement("button");
  nextBtn.type = "button";
  nextBtn.className = "t2h-btn";
  nextBtn.textContent = "\u2193";
  nextBtn.title = "Newer match (Shift+Enter)";
  nextBtn.disabled = true;

  var filterBtn = document.createElement("button");
  filterBtn.type = "button";
  filterBtn.className = "t2h-btn";
  filterBtn.textContent = "Filter";
  filterBtn.title = "Show only matching messages (toggle off to view active match in context)";
  filterBtn.setAttribute("aria-pressed", "false");

  var closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "t2h-btn";
  closeBtn.textContent = "\u2715";
  closeBtn.title = "Clear and close (Esc)";
  closeBtn.setAttribute("aria-label", "Close search");

  panel.appendChild(input);
  panel.appendChild(senderSelect);
  panel.appendChild(countEl);
  panel.appendChild(prevBtn);
  panel.appendChild(nextBtn);
  panel.appendChild(filterBtn);
  panel.appendChild(closeBtn);

  container.appendChild(fab);
  container.appendChild(panel);
  document.body.appendChild(container);

  function populateSenderSelect() {
    senderSelect.replaceChildren();
    var def = document.createElement("option");
    def.value = "";
    def.textContent = "All senders";
    senderSelect.appendChild(def);
    for (var i = 0; i < senderList.length; i++) {
      var opt = document.createElement("option");
      opt.value = senderList[i];
      opt.textContent = senderList[i];
      senderSelect.appendChild(opt);
    }
  }

  function setActiveMatch(pos, shouldScroll) {
    if (prevActiveEl) {
      prevActiveEl.classList.remove("t2h-active-msg");
      prevActiveEl = null;
    }
    if (!matches.length || pos < 0 || pos >= matches.length) {
      activePos = -1;
      updateCounterUI(isQueryActiveNow());
      updateCustomHighlightsSafe();
      return;
    }
    activePos = pos;
    var el = msgEls[matches[activePos]];
    el.classList.add("t2h-active-msg");
    prevActiveEl = el;
    updateCounterUI(true);
    updateCustomHighlightsSafe();
    if (shouldScroll) {
      el.scrollIntoView({ behavior: "auto", block: "center" });
    }
  }

  function isQueryActiveNow() {
    return currentTokens.length > 0 || senderSelect.value !== "";
  }

  function updateCounterUI(active) {
    if (!active) {
      countEl.textContent = "";
      countEl.classList.remove("t2h-zero");
      prevBtn.disabled = true;
      nextBtn.disabled = true;
      return;
    }
    if (!matches.length) {
      countEl.textContent = "0 / 0";
      countEl.classList.add("t2h-zero");
      prevBtn.disabled = true;
      nextBtn.disabled = true;
      return;
    }
    countEl.classList.remove("t2h-zero");
    countEl.textContent = String(activePos + 1) + " / " + String(matches.length);
    var disableNav = matches.length <= 1;
    prevBtn.disabled = disableNav;
    nextBtn.disabled = disableNav;
  }

  function executeSearch(preferredMsgId, scrollOnMatch) {
    ensureIndex();
    searchGen++;
    if (observer) observer.disconnect();
    visibleMatched.clear();
    if (!supportsCustomHighlight) clearFallbackMarks();

    currentTokens = parseQuery(input.value);
    var matchTokens = currentTokens.slice().sort(function (a, b) {
      return b.length - a.length;
    });
    var sender = senderSelect.value;
    var active = matchTokens.length > 0 || sender !== "";

    matches = [];
    if (active) {
      var tLen = matchTokens.length;
      for (var i = 0; i < msgEls.length; i++) {
        if (sender && msgSenders[i] !== sender) continue;
        var hay = msgSearchText[i];
        var ok = true;
        for (var t = 0; t < tLen; t++) {
          if (hay.indexOf(matchTokens[t]) === -1) {
            ok = false;
            break;
          }
        }
        if (ok) matches.push(i);
      }
    }

    if (observer && currentTokens.length > 0) {
      for (var k = 0; k < matches.length; k++) {
        observer.observe(msgEls[matches[k]]);
      }
    } else if (!observer && currentTokens.length > 0) {
      var cap = Math.min(matches.length, 200);
      for (var c = 0; c < cap; c++) visibleMatched.add(matches[c]);
    }

    applyFilterState(active);

    if (!matches.length) {
      setActiveMatch(-1, false);
      return;
    }

    var targetPos = matches.length - 1; // Newest match first
    if (preferredMsgId && msgIdToIndex.has(preferredMsgId)) {
      var targetMsgIdx = msgIdToIndex.get(preferredMsgId);
      var foundPos = matches.indexOf(targetMsgIdx);
      if (foundPos !== -1) targetPos = foundPos;
    }
    setActiveMatch(targetPos, scrollOnMatch !== false);
  }

  function openSearch() {
    ensureIndex();
    container.classList.add("t2h-open");
    input.focus();
    input.select();
  }

  function closeSearch() {
    input.value = "";
    senderSelect.value = "";
    if (filterOnly) {
      filterOnly = false;
      filterBtn.classList.remove("t2h-active-toggle");
      filterBtn.setAttribute("aria-pressed", "false");
    }
    executeSearch(null, false);
    container.classList.remove("t2h-open");
    input.blur();
  }

  function stepOlder() {
    if (!matches.length) return;
    var next = activePos <= 0 ? matches.length - 1 : activePos - 1;
    setActiveMatch(next, true);
  }

  function stepNewer() {
    if (!matches.length) return;
    var next = activePos >= matches.length - 1 ? 0 : activePos + 1;
    setActiveMatch(next, true);
  }

  fab.addEventListener("click", openSearch);
  closeBtn.addEventListener("click", closeSearch);
  prevBtn.addEventListener("click", stepOlder);
  nextBtn.addEventListener("click", stepNewer);

  filterBtn.addEventListener("click", function () {
    ensureIndex();
    filterOnly = !filterOnly;
    filterBtn.classList.toggle("t2h-active-toggle", filterOnly);
    filterBtn.setAttribute("aria-pressed", filterOnly ? "true" : "false");
    applyFilterState(isQueryActiveNow());
    if (!filterOnly && prevActiveEl) {
      requestAnimationFrame(function () {
        if (prevActiveEl) {
          prevActiveEl.scrollIntoView({ behavior: "auto", block: "center" });
        }
      });
    }
  });

  input.addEventListener("input", function () {
    executeSearch(null, true);
  });

  senderSelect.addEventListener("change", function () {
    executeSearch(null, true);
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (e.shiftKey) {
        stepNewer();
      } else {
        stepOlder();
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeSearch();
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && container.classList.contains("t2h-open")) {
      e.preventDefault();
      closeSearch();
      return;
    }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      openSearch();
      return;
    }
    if (
      e.key === "/" &&
      !e.metaKey &&
      !e.ctrlKey &&
      !e.altKey &&
      document.activeElement &&
      document.activeElement.tagName !== "INPUT" &&
      document.activeElement.tagName !== "TEXTAREA" &&
      document.activeElement.tagName !== "SELECT" &&
      !document.activeElement.isContentEditable
    ) {
      e.preventDefault();
      openSearch();
    }
  });

  // In Filter mode, clicking a matched message selects it; double-clicking reveals it in full context
  document.addEventListener("click", function (e) {
    if (!filterOnly || !matches.length) return;
    var msgDiv = e.target.closest ? e.target.closest("div.date > div.t2h-hit") : null;
    if (!msgDiv || !msgDiv.id) return;
    var mIdx = msgIdToIndex.get(msgDiv.id);
    if (mIdx === undefined) return;
    var pos = matches.indexOf(mIdx);
    if (pos !== -1) setActiveMatch(pos, false);
  });

  document.addEventListener("dblclick", function (e) {
    if (!filterOnly || !matches.length) return;
    var msgDiv = e.target.closest ? e.target.closest("div.date > div.t2h-hit") : null;
    if (!msgDiv) return;
    filterOnly = false;
    filterBtn.classList.remove("t2h-active-toggle");
    filterBtn.setAttribute("aria-pressed", "false");
    applyFilterState(isQueryActiveNow());
    requestAnimationFrame(function () {
      msgDiv.scrollIntoView({ behavior: "auto", block: "center" });
    });
  });

  function applyDeepLinkHash() {
    var hash = window.location.hash;
    if (!hash || hash.length < 2) return;
    var raw = hash.slice(1);
    var parts = raw.split("&");
    var targetId = "";
    var qParam = "";
    var sParam = "";
    for (var i = 0; i < parts.length; i++) {
      var kv = parts[i].split("=");
      var k = kv[0];
      var v = kv.slice(1).join("=");
      if (i === 0 && /^m\d+$/.test(k) && kv.length === 1) {
        targetId = k;
      } else if (k === "q") {
        try {
          qParam = decodeURIComponent(v);
        } catch (_) {
          qParam = v;
        }
      } else if (k === "s") {
        try {
          sParam = decodeURIComponent(v);
        } catch (_) {
          sParam = v;
        }
      }
    }
    if (qParam || sParam) {
      ensureIndex();
      container.classList.add("t2h-open");
      input.value = qParam;
      if (sParam && senderList.indexOf(sParam) !== -1) {
        senderSelect.value = sParam;
      }
      executeSearch(targetId || null, true);
    } else if (targetId) {
      var targetEl = document.getElementById(targetId);
      if (targetEl) {
        targetEl.classList.add("t2h-active-msg");
        prevActiveEl = targetEl;
        targetEl.scrollIntoView({ behavior: "auto", block: "center" });
      }
    }
  }

  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(function () {
      ensureIndex();
    });
  }

  applyDeepLinkHash();
  window.addEventListener("hashchange", applyDeepLinkHash);
})();
"""

INDEX_SEARCH_CSS = """
#t2h-index-search, #t2h-index-search div {
\twidth: auto;
\tmargin: 0;
\tpadding: 0;
\tborder: none;
\tborder-radius: 0;
\tbackground: transparent;
\tbox-sizing: border-box;
}
#t2h-index-search .t2h-idx-box {
\tmax-width: 780px;
\tmargin: 16px auto;
\tpadding: 14px 16px;
\tbackground: rgba(255, 255, 255, 0.95);
\tborder-radius: 16px;
\tborder: 1px solid rgba(0, 0, 0, 0.14);
\tbox-shadow: 0 3px 12px rgba(0, 0, 0, 0.1);
\tfont-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
#t2h-index-search .t2h-idx-controls {
\tdisplay: flex;
\tgap: 8px;
\tflex-wrap: wrap;
\talign-items: center;
}
#t2h-index-search .t2h-idx-input {
\tflex: 1 1 240px;
\tpadding: 8px 12px;
\tborder: 1px solid #cbd5e1;
\tborder-radius: 10px;
\tfont-size: 14px;
\toutline: none;
}
#t2h-index-search .t2h-idx-input:focus, #t2h-index-search .t2h-idx-select:focus {
\tborder-color: #2563eb;
\tbox-shadow: 0 0 0 2px rgba(37, 99, 235, 0.18);
}
#t2h-index-search .t2h-idx-select {
\tpadding: 8px 10px;
\tborder: 1px solid #cbd5e1;
\tborder-radius: 10px;
\tfont-size: 13px;
\tbackground: #ffffff;
\toutline: none;
}
#t2h-index-search .t2h-idx-clear {
\tpadding: 7px 11px;
\tborder: 1px solid #cbd5e1;
\tborder-radius: 10px;
\tbackground: #f8fafc;
\tcursor: pointer;
\tfont-size: 13px;
}
#t2h-index-search .t2h-idx-clear:hover {
\tbackground: #e2e8f0;
}
#t2h-index-search .t2h-idx-status {
\tmargin-top: 8px;
\tfont-size: 12px;
\tcolor: #4b5563;
}
#t2h-index-search .t2h-idx-results {
\tmargin-top: 10px;
\tdisplay: flex;
\tflex-direction: column;
\tgap: 8px;
}
#t2h-index-search .t2h-idx-card {
\tdisplay: block;
\tpadding: 10px 12px;
\tborder-radius: 12px;
\tborder: 1px solid #e2e8f0;
\tbackground: #ffffff;
\tcolor: #111827;
\ttext-decoration: none;
\ttransition: border-color 0.12s ease, background-color 0.12s ease;
}
#t2h-index-search .t2h-idx-card:hover {
\tborder-color: #93c5fd;
\tbackground: #f8fafc;
}
#t2h-index-search .t2h-idx-meta {
\tdisplay: flex;
\tjustify-content: space-between;
\tgap: 8px;
\tfont-size: 12px;
\tcolor: #6b7280;
\tmargin-bottom: 4px;
}
#t2h-index-search .t2h-idx-sender {
\tfont-weight: 700;
\tcolor: #1f2937;
}
#t2h-index-search .t2h-idx-snippet {
\tfont-size: 13px;
\tline-height: 1.4;
\twhite-space: pre-wrap;
\tword-break: break-word;
}
#t2h-index-search .t2h-idx-snippet mark {
\tbackground-color: #fef08a;
\tcolor: inherit;
\tpadding: 0 1px;
\tborder-radius: 2px;
}
#t2h-index-search .t2h-idx-more {
\tmargin-top: 8px;
\tpadding: 8px 14px;
\tborder-radius: 10px;
\tborder: 1px solid #cbd5e1;
\tbackground: #f8fafc;
\tcursor: pointer;
\tfont-size: 13px;
\tfont-weight: 600;
\talign-self: center;
}
#t2h-index-search .t2h-idx-more:hover {
\tbackground: #e2e8f0;
}
"""

INDEX_SEARCH_JS = r"""
(function () {
  "use strict";

  var BATCH_SIZE = 100;
  var SAFE_FILE_RE = /^chat_\d{4}(?:_\d{2})?\.html$/;

  var loading = false;
  var loaded = false;
  var loadError = false;
  var indexData = null;
  var lowerCorpus = [];
  var currentMatches = [];
  var currentTokens = [];
  var renderedCount = 0;

  var mount = document.getElementById("t2h-index-search");
  if (!mount) return;

  var box = document.createElement("div");
  box.className = "t2h-idx-box";
  box.setAttribute("role", "search");

  var controls = document.createElement("div");
  controls.className = "t2h-idx-controls";

  var input = document.createElement("input");
  input.type = "search";
  input.className = "t2h-idx-input";
  input.placeholder = "Search across all chat files\u2026 (/ or Ctrl+K)";
  input.autocomplete = "off";
  input.spellcheck = false;

  var senderSelect = document.createElement("select");
  senderSelect.className = "t2h-idx-select";
  senderSelect.setAttribute("aria-label", "Filter by sender");
  var defaultOpt = document.createElement("option");
  defaultOpt.value = "";
  defaultOpt.textContent = "All senders";
  senderSelect.appendChild(defaultOpt);

  var clearBtn = document.createElement("button");
  clearBtn.type = "button";
  clearBtn.className = "t2h-idx-clear";
  clearBtn.textContent = "Clear";

  var statusEl = document.createElement("div");
  statusEl.className = "t2h-idx-status";

  var resultsEl = document.createElement("div");
  resultsEl.className = "t2h-idx-results";

  controls.appendChild(input);
  controls.appendChild(senderSelect);
  controls.appendChild(clearBtn);
  box.appendChild(controls);
  box.appendChild(statusEl);
  box.appendChild(resultsEl);
  mount.appendChild(box);

  function parseQuery(raw) {
    var tokens = [];
    if (!raw) return tokens;
    var parts = raw.split('"');
    for (var i = 0; i < parts.length; i++) {
      var seg = parts[i].trim().toLowerCase();
      if (!seg) continue;
      if (i % 2 === 1) {
        tokens.push(seg);
      } else {
        var words = seg.split(/\s+/);
        for (var w = 0; w < words.length; w++) {
          if (words[w]) tokens.push(words[w]);
        }
      }
    }
    return tokens;
  }

  function findIntervals(str, tokens) {
    if (!tokens.length || !str) return null;
    var lower = str.toLowerCase();
    if (lower.length !== str.length) return null;
    var raw = [];
    for (var t = 0; t < tokens.length; t++) {
      var tok = tokens[t];
      if (!tok) continue;
      var pos = 0;
      while ((pos = lower.indexOf(tok, pos)) !== -1) {
        raw.push([pos, pos + tok.length]);
        pos += tok.length;
      }
    }
    if (!raw.length) return null;
    raw.sort(function (a, b) {
      return a[0] - b[0] || b[1] - a[1];
    });
    var merged = [raw[0]];
    for (var i = 1; i < raw.length; i++) {
      var last = merged[merged.length - 1];
      if (raw[i][0] <= last[1]) {
        if (raw[i][1] > last[1]) last[1] = raw[i][1];
      } else {
        merged.push(raw[i]);
      }
    }
    return merged;
  }

  function buildHighlightedSnippet(text, tokens) {
    var frag = document.createDocumentFragment();
    var display = text.length > 320 ? text.slice(0, 320) + "\u2026" : text;
    var intervals = findIntervals(display, tokens);
    if (!intervals) {
      frag.appendChild(document.createTextNode(display));
      return frag;
    }
    var cursor = 0;
    for (var i = 0; i < intervals.length; i++) {
      var start = intervals[i][0];
      var end = intervals[i][1];
      if (start > cursor) {
        frag.appendChild(document.createTextNode(display.slice(cursor, start)));
      }
      var mark = document.createElement("mark");
      mark.textContent = display.slice(start, end);
      frag.appendChild(mark);
      cursor = end;
    }
    if (cursor < display.length) {
      frag.appendChild(document.createTextNode(display.slice(cursor)));
    }
    return frag;
  }

  function hydrateIndex() {
    indexData = window.__THREEMA_SEARCH_INDEX__;
    if (!indexData || !Array.isArray(indexData.messages)) {
      loadError = true;
      statusEl.textContent = "Search index unavailable.";
      return;
    }
    loaded = true;
    loading = false;
    var msgs = indexData.messages;
    lowerCorpus = new Array(msgs.length);
    for (var i = 0; i < msgs.length; i++) {
      lowerCorpus[i] = (msgs[i][4] + "\n" + msgs[i][3]).toLowerCase();
    }
    var senders = indexData.senders || [];
    var sortedSenders = senders.slice().sort();
    senderSelect.replaceChildren();
    var allOpt = document.createElement("option");
    allOpt.value = "";
    allOpt.textContent = "All senders";
    senderSelect.appendChild(allOpt);
    for (var s = 0; s < sortedSenders.length; s++) {
      var opt = document.createElement("option");
      opt.value = sortedSenders[s];
      opt.textContent = sortedSenders[s];
      senderSelect.appendChild(opt);
    }
    runGlobalSearch();
  }

  function ensureIndexLoaded() {
    if (loaded || loading || loadError) return;
    if (window.__THREEMA_SEARCH_INDEX__) {
      hydrateIndex();
      return;
    }
    loading = true;
    statusEl.textContent = "Loading search index\u2026";
    var script = document.createElement("script");
    script.src = "search_index.js";
    script.onload = hydrateIndex;
    script.onerror = function () {
      loading = false;
      loadError = true;
      statusEl.textContent = "Could not load search_index.js.";
    };
    document.head.appendChild(script);
  }

  function renderMoreResults() {
    var existingMore = resultsEl.querySelector(".t2h-idx-more");
    if (existingMore) existingMore.remove();

    var msgs = indexData.messages;
    var files = indexData.files;
    var senders = indexData.senders;
    var rawQuery = input.value.trim();
    var selectedSender = senderSelect.value;

    var limit = Math.min(currentMatches.length, renderedCount + BATCH_SIZE);
    var frag = document.createDocumentFragment();

    for (var i = renderedCount; i < limit; i++) {
      var rec = msgs[currentMatches[i]];
      var file = files[rec[0]] || "";
      if (!SAFE_FILE_RE.test(file)) continue;
      var msgNum = rec[1];
      var senderName = senders[rec[2]] || "";
      var ts = rec[3] || "";
      var text = rec[4] || "";

      var hash = "#m" + String(msgNum);
      if (rawQuery) hash += "&q=" + encodeURIComponent(rawQuery);
      if (selectedSender) hash += "&s=" + encodeURIComponent(selectedSender);

      var card = document.createElement("a");
      card.className = "t2h-idx-card";
      card.href = file + hash;

      var meta = document.createElement("div");
      meta.className = "t2h-idx-meta";

      var senderSpan = document.createElement("span");
      senderSpan.className = "t2h-idx-sender";
      senderSpan.textContent = senderName;

      var rightMeta = document.createElement("span");
      rightMeta.textContent = ts + " \u00b7 " + file;

      meta.appendChild(senderSpan);
      meta.appendChild(rightMeta);

      var snippet = document.createElement("div");
      snippet.className = "t2h-idx-snippet";
      snippet.appendChild(buildHighlightedSnippet(text, currentTokens));

      card.appendChild(meta);
      card.appendChild(snippet);
      frag.appendChild(card);
    }

    renderedCount = limit;
    resultsEl.appendChild(frag);

    if (renderedCount < currentMatches.length) {
      var moreBtn = document.createElement("button");
      moreBtn.type = "button";
      moreBtn.className = "t2h-idx-more";
      moreBtn.textContent =
        "Show more (" + String(currentMatches.length - renderedCount) + " remaining)";
      moreBtn.addEventListener("click", renderMoreResults);
      resultsEl.appendChild(moreBtn);
    }
  }

  function runGlobalSearch() {
    if (!loaded) {
      if (input.value.trim() || senderSelect.value) ensureIndexLoaded();
      return;
    }
    resultsEl.replaceChildren();
    currentMatches = [];
    renderedCount = 0;

    currentTokens = parseQuery(input.value);
    var matchTokens = currentTokens.slice().sort(function (a, b) {
      return b.length - a.length;
    });
    var selectedSender = senderSelect.value;
    if (!matchTokens.length && !selectedSender) {
      statusEl.textContent = "";
      return;
    }

    var senderFilterIdx = -1;
    if (selectedSender) {
      senderFilterIdx = indexData.senders.indexOf(selectedSender);
      if (senderFilterIdx === -1) {
        statusEl.textContent = "0 matches.";
        return;
      }
    }

    var msgs = indexData.messages;
    var tLen = matchTokens.length;
    var matchedFiles = new Set();

    // Scan newest-first
    for (var i = msgs.length - 1; i >= 0; i--) {
      if (senderFilterIdx !== -1 && msgs[i][2] !== senderFilterIdx) continue;
      var hay = lowerCorpus[i];
      var ok = true;
      for (var t = 0; t < tLen; t++) {
        if (hay.indexOf(matchTokens[t]) === -1) {
          ok = false;
          break;
        }
      }
      if (ok) {
        currentMatches.push(i);
        matchedFiles.add(msgs[i][0]);
      }
    }

    if (!currentMatches.length) {
      statusEl.textContent = "No matching messages found.";
      return;
    }

    statusEl.textContent =
      String(currentMatches.length) +
      (currentMatches.length === 1 ? " match" : " matches") +
      " across " +
      String(matchedFiles.size) +
      (matchedFiles.size === 1 ? " file" : " files");
    renderMoreResults();
  }

  input.addEventListener("focus", ensureIndexLoaded);
  senderSelect.addEventListener("focus", ensureIndexLoaded);
  input.addEventListener("input", runGlobalSearch);
  senderSelect.addEventListener("change", runGlobalSearch);

  clearBtn.addEventListener("click", function () {
    input.value = "";
    senderSelect.value = "";
    resultsEl.replaceChildren();
    statusEl.textContent = "";
    input.focus();
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      e.preventDefault();
      input.value = "";
      senderSelect.value = "";
      resultsEl.replaceChildren();
      statusEl.textContent = "";
    }
  });

  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      ensureIndexLoaded();
      input.focus();
      input.select();
    } else if (
      e.key === "/" &&
      !e.metaKey &&
      !e.ctrlKey &&
      !e.altKey &&
      document.activeElement &&
      document.activeElement.tagName !== "INPUT" &&
      document.activeElement.tagName !== "TEXTAREA" &&
      document.activeElement.tagName !== "SELECT"
    ) {
      e.preventDefault();
      ensureIndexLoaded();
      input.focus();
      input.select();
    }
  });
})();
"""


def serialize_js_data(data):
    """Serialize data to JSON safe for embedding inside JavaScript files or <script> tags."""
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def make_links(text, media_folder, thumb_width, found_files=None):
    # Sanitize XML characters FIRST
    text = html.escape(text)
    safe_media_folder = html.escape(media_folder, quote=True)

    # Process images for inline display
    def img_repl(match):
        filename = html.unescape(match.group(1))
        safe_filename = match.group(1)
        if found_files is not None:
            found_files.append(filename)
        return f'<br/><a href="{safe_media_folder}{safe_filename}"><img src="{safe_media_folder}{safe_filename}" alt="Image" width="{thumb_width}"/></a>'

    text = re.sub(r"&lt;(.+?\.(?:jpe?g|png))&gt;", img_repl, text)

    # Process other files as links
    def file_repl(match):
        filename = html.unescape(match.group(1))
        safe_filename = match.group(1)
        if found_files is not None:
            found_files.append(filename)
        return f'<a href="{safe_media_folder}{safe_filename}">{safe_filename}</a>'

    text = re.sub(r"&lt;(.+?\.(?:mp4|pdf|vcf))&gt;", file_repl, text)

    # Process hyperlinks
    def url_repl(match):
        url = match.group(1)
        return f'<a href="{url}">{url}</a>'

    text = re.sub(r"(https?://[^ ]+)", url_repl, text)

    return text


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert Threema exports to nicely formatted HTML."
    )
    parser.add_argument(
        "-f",
        "--from-date",
        type=int,
        default=19700101,
        help="Start of date range to include (default: 19700101)",
    )
    parser.add_argument(
        "-t",
        "--to-date",
        type=int,
        default=20701231,
        help="End of date range to include (default: 20701231)",
    )
    parser.add_argument(
        "-T", "--title", default="Threema Export", help="HTML title"
    )
    parser.add_argument(
        "-n", "--name", default="", help="Name of exporter to substitute for 'Ich'"
    )
    parser.add_argument(
        "-m", "--media-folder", default="./media/", help="Media folder"
    )
    parser.add_argument(
        "-s", "--style-file", default="./lib/default.css", help="CSS style file"
    )
    parser.add_argument(
        "-w", "--width", type=int, default=480, help="Image width"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )
    parser.add_argument(
        "--split",
        choices=["year", "month"],
        help="Split output into multiple files by year or month",
    )
    parser.add_argument(
        "--no-search",
        action="store_true",
        help="Disable embedded JavaScript search functionality",
    )
    parser.add_argument("inputfile", help="Exported Threema messages file (.txt)")

    args = parser.parse_args(argv)

    input_dir = os.path.dirname(os.path.abspath(args.inputfile))
    safe_title = html.escape(args.title, quote=True)
    safe_style_file = html.escape(args.style_file, quote=True)
    enable_search = not args.no_search

    message_start_pattern = re.compile(
        r"^\[(\d{2}\.\d{2}\.\d{4}),\s*(\d{2}:\d{2}:\d{2})\]\s*(.*)"
    )

    old_date = ""
    pending_msg = False
    skip_continuation = False
    onr = 0

    created_files = set()

    # Global search index structures for --split mode
    index_files = []
    index_file_map = {}
    index_senders = []
    index_sender_map = {}
    index_messages = []
    active_index_record = None

    def flush_index_record():
        nonlocal active_index_record
        if active_index_record is not None:
            file_idx, msg_num, sender_idx, ts_str, lines = active_index_record
            index_messages.append(
                [file_idx, msg_num, sender_idx, ts_str, "\n".join(lines)]
            )
            active_index_record = None

    def write_chat_header(f):
        print("<!DOCTYPE html>", file=f)
        print("<html>", file=f)
        print("<head>", file=f)
        print('\t<meta charset="utf-8">', file=f)
        print(
            '\t<meta name="viewport" content="width=device-width, initial-scale=1">',
            file=f,
        )
        print(
            '\t<meta name="generator" content="threema2html.py (migrated from AWK)">',
            file=f,
        )
        print(f"\t<title>{safe_title}</title>", file=f)
        print(
            f'\t<link rel="stylesheet" type="text/css" href="{safe_style_file}">',
            file=f,
        )
        css_parts = []
        if args.split:
            css_parts.append(SPLIT_NAV_CSS.strip())
        if enable_search:
            css_parts.append(CHAT_SEARCH_CSS.strip())
        if css_parts:
            print("\t<style>", file=f)
            print("\n".join(css_parts), file=f)
            print("\t</style>", file=f)
        print("</head>", file=f)
        print("<body>", file=f)
        if args.split:
            print(
                '\t<div class="t2h-split-nav"><a href="index.html" class="t2h-back-link">&larr; Index</a></div>',
                file=f,
            )

    def write_chat_footer(f):
        if enable_search:
            print("<script>", file=f)
            print(CHAT_SEARCH_JS.strip(), file=f)
            print("</script>", file=f)
        print("</body>", file=f)
        print("</html>", file=f)

    def close_msg_div(date_time_str, file=sys.stdout):
        print("\t\t\t</p>", file=file)
        print('\t\t\t<p class="timestamp">', file=file)
        print(f"\t\t\t\t{html.escape(date_time_str)}", file=file)
        print("\t\t\t</p>", file=file)
        print("\t\t</div>", file=file)

    def get_target_filename(date_str):
        if not args.split:
            return None
        parts = date_str.split(".")
        day, month, year = parts[0], parts[1], parts[2]
        if args.split == "year":
            return f"chat_{year}.html"
        elif args.split == "month":
            return f"chat_{year}_{month}.html"
        return None

    def open_new_file(filename):
        f = open(filename, "w", encoding="utf-8")
        write_chat_header(f)
        return f

    def close_file(f):
        if f and f is not sys.stdout:
            write_chat_footer(f)
            f.close()

    def copy_files(files):
        for filename in files:
            safe_base = os.path.basename(filename)
            if safe_base != filename or not safe_base:
                if args.verbose:
                    print(
                        f"Skipping unsafe media path: {filename}",
                        file=sys.stderr,
                    )
                continue
            src_path = os.path.join(input_dir, safe_base)
            dst_path = os.path.join(args.media_folder, safe_base)
            if os.path.exists(src_path):
                if args.verbose:
                    print(
                        f"Copying {src_path} to {dst_path}", file=sys.stderr
                    )
                try:
                    os.makedirs(args.media_folder, exist_ok=True)
                    shutil.copy(src_path, dst_path)
                except Exception as e:
                    print(f"Error copying file: {e}", file=sys.stderr)
            else:
                if args.verbose:
                    print(f"File not found: {src_path}", file=sys.stderr)

    if not args.split:
        current_file = sys.stdout
        current_filename = None
        write_chat_header(current_file)
    else:
        current_file = None
        current_filename = None

    current_msg_timestamp = ""

    try:
        with open(args.inputfile, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                match = message_start_pattern.match(line)
                if match:
                    date_str = match.group(1)
                    time_str = match.group(2)
                    rest = match.group(3)

                    # Parse date for filtering
                    try:
                        current_date = datetime.strptime(date_str, "%d.%m.%Y")
                        date_int = int(current_date.strftime("%Y%m%d"))
                    except ValueError:
                        print(
                            f"Error parsing date: {date_str}", file=sys.stderr
                        )
                        skip_continuation = True
                        continue

                    if date_int < args.from_date or date_int > args.to_date:
                        skip_continuation = True
                        continue

                    skip_continuation = False

                    # Parse user and message
                    parts = rest.split(": ", 1)
                    if len(parts) > 1:
                        user = parts[0]
                        msg = parts[1]
                    else:
                        user = "(Unknown)"
                        msg = rest

                    flush_index_record()

                    if args.split:
                        target_filename = get_target_filename(date_str)
                        if target_filename != current_filename:
                            if current_file:
                                if pending_msg:
                                    close_msg_div(
                                        current_msg_timestamp, file=current_file
                                    )
                                    pending_msg = False
                                print(
                                    "\t</div>", file=current_file
                                )  # Close date div
                                close_file(current_file)

                            current_file = open_new_file(target_filename)
                            current_filename = target_filename
                            old_date = ""  # Reset old_date for new file
                            created_files.add(target_filename)

                    if pending_msg:
                        close_msg_div(current_msg_timestamp, file=current_file)

                    if date_str != old_date:
                        if pending_msg:
                            print("\t</div>", file=current_file)

                        print('\t<div class="date">', file=current_file)
                        print(
                            f"\t\t<h2>{html.escape(date_str)}</h2>",
                            file=current_file,
                        )
                        old_date = date_str

                    # Start new message
                    user_class = user
                    display_name = user
                    if args.name and user == "Ich":
                        user_class = f"Ich {args.name}"
                        display_name = args.name

                    onr += 1
                    msg_id = f"m{onr}"

                    print(
                        f'\t\t<div id="{msg_id}" class="{html.escape(user_class, quote=True)}">',
                        file=current_file,
                    )
                    print(
                        f"\t\t\t<h3>{html.escape(display_name)}</h3>",
                        file=current_file,
                    )

                    found_files = []
                    processed_msg = make_links(
                        msg, args.media_folder, args.width, found_files
                    )
                    copy_files(found_files)

                    print('\t\t\t<p class="msg">', file=current_file)
                    print(f"\t\t\t\t{processed_msg}", file=current_file)

                    current_msg_timestamp = f"{date_str}, {time_str}"
                    pending_msg = True

                    if args.split and enable_search:
                        if current_filename not in index_file_map:
                            index_file_map[current_filename] = len(index_files)
                            index_files.append(current_filename)
                        if display_name not in index_sender_map:
                            index_sender_map[display_name] = len(index_senders)
                            index_senders.append(display_name)
                        active_index_record = (
                            index_file_map[current_filename],
                            onr,
                            index_sender_map[display_name],
                            current_msg_timestamp,
                            [msg],
                        )
                else:
                    if pending_msg and not skip_continuation:
                        # Continuation line
                        found_files = []
                        processed_line = make_links(
                            line, args.media_folder, args.width, found_files
                        )
                        copy_files(found_files)
                        print(
                            f"\t\t\t\t<br/>{processed_line}", file=current_file
                        )
                        if active_index_record is not None:
                            active_index_record[4].append(line)
    except FileNotFoundError:
        print(f"Error: File not found: {args.inputfile}", file=sys.stderr)
        sys.exit(1)

    flush_index_record()

    if pending_msg:
        close_msg_div(current_msg_timestamp, file=current_file)
        print("\t</div>", file=current_file)  # Close date div

    if not args.split:
        write_chat_footer(current_file)
    else:
        close_file(current_file)

    if args.split and created_files:
        if enable_search:
            search_index_filename = "search_index.js"
            try:
                payload = {
                    "files": index_files,
                    "senders": index_senders,
                    "messages": index_messages,
                }
                with open(search_index_filename, "w", encoding="utf-8") as sf:
                    sf.write(
                        f"window.__THREEMA_SEARCH_INDEX__ = {serialize_js_data(payload)};\n"
                    )
                if args.verbose:
                    print(
                        f"Created search index: {search_index_filename}",
                        file=sys.stderr,
                    )
            except Exception as e:
                print(f"Error creating search index: {e}", file=sys.stderr)

        index_filename = "index.html"
        try:
            with open(index_filename, "w", encoding="utf-8") as f:
                print("<!DOCTYPE html>", file=f)
                print("<html>", file=f)
                print("<head>", file=f)
                print('\t<meta charset="utf-8">', file=f)
                print(
                    '\t<meta name="viewport" content="width=device-width, initial-scale=1">',
                    file=f,
                )
                print(
                    '\t<meta name="generator" content="threema2html.py (migrated from AWK)">',
                    file=f,
                )
                print(f"\t<title>{safe_title} - Index</title>", file=f)
                print(
                    f'\t<link rel="stylesheet" type="text/css" href="{safe_style_file}">',
                    file=f,
                )
                if enable_search:
                    print("\t<style>", file=f)
                    print(INDEX_SEARCH_CSS.strip(), file=f)
                    print("\t</style>", file=f)
                print("</head>", file=f)
                print("<body>", file=f)
                print('\t<div class="date">', file=f)
                print(f"\t\t<h2>{safe_title}</h2>", file=f)
                if enable_search:
                    print('\t\t<div id="t2h-index-search"></div>', file=f)
                print("\t\t<ul>", file=f)
                for filename in sorted(list(created_files)):
                    safe_fn = html.escape(filename, quote=True)
                    print(
                        f'\t\t\t<li><a href="{safe_fn}">{safe_fn}</a></li>',
                        file=f,
                    )
                print("\t\t</ul>", file=f)
                print("\t</div>", file=f)
                if enable_search:
                    print("<script>", file=f)
                    print(INDEX_SEARCH_JS.strip(), file=f)
                    print("</script>", file=f)
                print("</body>", file=f)
                print("</html>", file=f)
            print(f"Created index file: {index_filename}", file=sys.stderr)
        except Exception as e:
            print(f"Error creating index file: {e}", file=sys.stderr)

    print(f"{onr} output messages.", file=sys.stderr)


if __name__ == "__main__":
    main()
