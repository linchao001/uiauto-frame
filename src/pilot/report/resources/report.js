/* Pilot enhanced HTML report UI (injected by polish_report_html). */
(function () {
  "use strict";

  var RESULT_ORDER = [
    "failed",
    "error",
    "passed",
    "skipped",
    "xfailed",
    "xpassed",
    "rerun",
    "retried",
  ];

  var RESULT_LABEL = {
    failed: "失败 Failed",
    error: "错误 Error",
    passed: "通过 Passed",
    skipped: "跳过 Skipped",
    xfailed: "预期失败 xFailed",
    xpassed: "意外通过 xPassed",
    rerun: "重跑 Rerun",
    retried: "重试 Retried",
  };

  var STAT_META = [
    { key: "failed", label: "失败", icon: "✕" },
    { key: "error", label: "错误", icon: "!" },
    { key: "passed", label: "通过", icon: "✓" },
    { key: "skipped", label: "跳过", icon: "–" },
    { key: "total", label: "总计", icon: "Σ" },
  ];

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function resultKey(result) {
    return String(result || "").toLowerCase();
  }

  function decodeBlob(raw) {
    if (!raw) return null;
    // getAttribute() already returns entity-decoded text. Do NOT pass the JSON
    // through innerHTML — caseTitle embeds HTML and would corrupt the payload.
    try {
      return JSON.parse(raw);
    } catch (err) {
      console.error("pilot report: bad data-jsonblob", err);
      return null;
    }
  }

  function flattenTests(blob) {
    var tests = (blob && blob.tests) || {};
    var out = [];
    Object.keys(tests).forEach(function (key) {
      var rows = tests[key] || [];
      rows.forEach(function (row, idx) {
        out.push(
          Object.assign({}, row, {
            _uid: key + "::" + idx,
            _result: resultKey(row.result),
          })
        );
      });
    });
    return out;
  }

  function countByResult(tests) {
    var counts = { total: tests.length };
    RESULT_ORDER.forEach(function (k) {
      counts[k] = 0;
    });
    tests.forEach(function (t) {
      var k = t._result;
      if (counts[k] === undefined) counts[k] = 0;
      counts[k] += 1;
    });
    return counts;
  }

  function stripParamId(name) {
    // test_foo[E2E001] / test_foo[T001] → test_foo
    return String(name || "").replace(/\[[^\]]*\]$/g, "");
  }

  function parseNodeId(testId) {
    var id = String(testId || "");
    var parts = id.split("::").filter(function (p) {
      return p.length > 0;
    });
    // Drop file path (first segment).
    var rest = parts.slice(1);
    if (rest.length && /^(setup|call|teardown)$/i.test(rest[rest.length - 1])) {
      rest.pop();
    }
    if (rest.length >= 2) {
      return {
        className: rest[0],
        caseName: stripParamId(rest.slice(1).join("::")),
      };
    }
    if (rest.length === 1) {
      return { className: "", caseName: stripParamId(rest[0]) };
    }
    return { className: "", caseName: stripParamId(id) || "(unnamed)" };
  }

  function treeCaseLabel(test) {
    var parsed = parseNodeId(test.testId);
    if (parsed.className && parsed.caseName) {
      return parsed.className + " · " + parsed.caseName;
    }
    return parsed.caseName || "(unnamed)";
  }

  function treeCaseName(test) {
    return parseNodeId(test.testId).caseName || "(unnamed)";
  }

  function caseChineseTitle(test) {
    if (!test.caseTitle) return "";
    var wrap = document.createElement("div");
    wrap.innerHTML = test.caseTitle;
    var trigger = wrap.querySelector(".pilot-title-trigger");
    var text = trigger
      ? trigger.textContent
      : wrap.textContent || "";
    return String(text || "").trim();
  }

  function plainTitle(test) {
    if (test.caseId || test.caseTitle) {
      var wrap = document.createElement("div");
      wrap.innerHTML = test.caseTitle || "";
      var trigger = wrap.querySelector(".pilot-title-trigger");
      var text = trigger
        ? trigger.textContent
        : wrap.textContent || test.caseTitle || "";
      text = String(text || "").trim();
      if (test.caseId && text) return test.caseId + " · " + text;
      if (test.caseId) return test.caseId;
      if (text) return text;
    }
    return treeCaseLabel(test);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        resolve();
      } catch (err) {
        reject(err);
      } finally {
        document.body.removeChild(ta);
      }
    });
  }

  function extractDetailHtml(test) {
    var wrap = document.createElement("div");
    wrap.innerHTML = test.caseTitle || "";
    var detail = wrap.querySelector(".pilot-case-detail");
    if (detail) return detail.outerHTML;
    var parts = [];
    if (test.caseId || test.priority || plainTitle(test)) {
      parts.push('<div class="pilot-case-detail">');
      parts.push('<div class="pilot-case-title">');
      if (test.caseId) parts.push("<strong>" + escapeHtml(test.caseId) + "</strong> ");
      if (test.priority) parts.push("<span>[" + escapeHtml(test.priority) + "]</span> ");
      parts.push(escapeHtml(plainTitle(test)));
      parts.push("</div></div>");
    }
    return parts.join("") || "<p>暂无步骤详情</p>";
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function decodeHtmlEntities(s) {
    // Stock HTML reports store logs already entity-escaped (&quot; / &gt; / &#x27;).
    // Decode once before we escape for our own innerHTML insertion.
    var el = document.createElement("textarea");
    el.innerHTML = String(s || "");
    return el.value;
  }

  function screenshotHref(raw) {
    var href = String(raw || "").trim().replace(/\\/g, "/");
    var marker = "artifacts/";
    var idx = href.toLowerCase().indexOf(marker);
    if (idx >= 0) return href.slice(idx);
    return href;
  }

  function linkifyScreenshot(line) {
    var match = line.match(/screenshot:\s*(\S+)/i);
    if (!match) return null;
    var href = screenshotHref(match[1]);
    var label = escapeHtml(line.slice(0, match.index)) + "screenshot: ";
    return (
      label +
      '<a class="pilot-shot-link" href="' +
      escapeHtml(href) +
      '" target="_blank" rel="noopener">查看截图</a>'
    );
  }

  function formatLog(log) {
    var raw = decodeHtmlEntities(log || "No log output captured.");
    return String(raw)
      .split("\n")
      .map(function (line) {
        var linked = linkifyScreenshot(line);
        if (linked) {
          if (/^E/.test(line)) return '<span class="error">' + linked + "</span>";
          return linked;
        }
        var esc = escapeHtml(line);
        if (/^E/.test(line)) {
          return '<span class="error">' + esc + "</span>";
        }
        return esc;
      })
      .join("\n");
  }

  function fileUrlToLocalPath(fileUrl) {
    // file:///D:/a/trace.zip → D:/a/trace.zip
    if (!/^file:/i.test(fileUrl)) return "";
    var path = String(fileUrl).replace(/^file:\/+/i, "");
    try {
      path = decodeURIComponent(path);
    } catch (err) {
      return "";
    }
    if (/^\/[A-Za-z]:[\\/]/.test(path)) path = path.slice(1);
    return path;
  }

  function bindTraceViewerLinks(root) {
    var anchors = (root || document).querySelectorAll("a[href]");
    Array.prototype.forEach.call(anchors, function (anchor) {
      var attr = anchor.getAttribute("href") || "";
      var bare = attr.split("#")[0].split("?")[0];
      if (!/trace\.zip$/i.test(bare)) return;
      if (/^pilot-trace:/i.test(attr)) return;
      var local = fileUrlToLocalPath(anchor.href);
      if (!local) return;
      anchor.href = "pilot-trace://show?path=" + encodeURIComponent(local);
      anchor.removeAttribute("target");
      anchor.title = "打开 Trace Viewer；首次点击时浏览器会询问是否允许";
      if (!anchor.textContent || /trace\.zip/i.test(anchor.textContent)) {
        anchor.textContent = "打开 Trace";
      }
    });
  }

  function extrasHtml(extras) {
    if (!extras || !extras.length) return "";
    var chunks = ['<div class="pilot-extras">'];
    extras.forEach(function (extra) {
      var name = extra.name || extra.format_type || "extra";
      var content = extra.content || "";
      chunks.push("<div><strong>" + escapeHtml(name) + "</strong></div>");
      if (extra.format_type === "html") {
        chunks.push("<div>" + content + "</div>");
      } else {
        chunks.push("<pre>" + escapeHtml(typeof content === "string" ? content : JSON.stringify(content, null, 2)) + "</pre>");
      }
    });
    chunks.push("</div>");
    return chunks.join("");
  }

  function buildEnvBar(environment) {
    var env = environment || {};
    var keys = Object.keys(env);
    if (!keys.length) return null;

    var root = document.createElement("section");
    root.className = "pilot-env";

    // 框架已知字段优先；其余键按名字排序（产品可通过 AuthProvider 自定义键）
    var preferred = ["base_url"];
    var labels = {
      base_url: "Base URL",
    };
    var ordered = preferred
      .filter(function (k) {
        return Object.prototype.hasOwnProperty.call(env, k);
      })
      .concat(
        keys.filter(function (k) {
          return preferred.indexOf(k) < 0;
        }).sort()
      );

    ordered.forEach(function (key) {
      var value = env[key];
      var text =
        value == null
          ? ""
          : typeof value === "object"
            ? JSON.stringify(value)
            : String(value);
      var item = document.createElement("div");
      item.className = "pilot-env__item";
      var label = labels[key] || key;
      var valueHtml;
      if (key === "base_url" && /^https?:\/\//i.test(text)) {
        valueHtml =
          '<a href="' +
          escapeHtml(text) +
          '" target="_blank" rel="noopener noreferrer">' +
          escapeHtml(text) +
          "</a>";
      } else {
        valueHtml = escapeHtml(text);
      }
      item.innerHTML =
        '<div class="pilot-env__label">' +
        escapeHtml(label) +
        '</div><div class="pilot-env__value">' +
        valueHtml +
        "</div>";
      root.appendChild(item);
    });
    return root;
  }

  function buildOverview(counts) {
    var root = document.createElement("section");
    root.className = "pilot-overview";
    STAT_META.forEach(function (meta) {
      var n = counts[meta.key] || 0;
      var card = document.createElement("div");
      card.className = "pilot-stat pilot-stat--" + meta.key;
      card.innerHTML =
        '<div class="pilot-stat__icon" aria-hidden="true">' +
        meta.icon +
        "</div>" +
        '<div class="pilot-stat__body">' +
        '<div class="pilot-stat__value">' +
        n +
        "</div>" +
        '<div class="pilot-stat__label">' +
        meta.label +
        "</div></div>";
      root.appendChild(card);
    });
    return root;
  }

  function groupTests(tests) {
    // 仅按结果分组，不再区分 API / E2E / Other
    var byResult = {};
    var order = RESULT_ORDER.slice();
    RESULT_ORDER.forEach(function (r) {
      byResult[r] = [];
    });
    tests.forEach(function (t) {
      var r = t._result;
      if (!byResult[r]) {
        byResult[r] = [];
        order.push(r);
      }
      byResult[r].push(t);
    });
    byResult._order = order;
    return byResult;
  }

  function makeToggle(label, count, levelClass) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pilot-tree-toggle" + (levelClass ? " " + levelClass : "");
    btn.innerHTML =
      '<span class="pilot-tree-toggle__chevron">▼</span>' +
      "<span>" +
      escapeHtml(label) +
      '</span><span class="pilot-tree-badge">' +
      count +
      "</span>";
    return btn;
  }

  function appendCaseRow(parent, test, aside, onSelect) {
    var row = document.createElement("div");
    row.className = "pilot-tree-case";
    row.dataset.uid = test._uid;

    var label = treeCaseLabel(test);
    var cnTitle = caseChineseTitle(test);
    var main = document.createElement("button");
    main.type = "button";
    main.className = "pilot-tree-case__main";
    if (cnTitle) {
      main.setAttribute("aria-label", label + "，" + cnTitle);
      row.classList.add("has-tip");
    }
    main.innerHTML =
      '<span class="pilot-tree-case__status ' +
      escapeHtml(test._result) +
      '"></span>' +
      '<span class="pilot-tree-case__meta">' +
      '<div class="pilot-tree-case__title">' +
      escapeHtml(label) +
      "</div></span>";

    var durationText = test.duration ? String(test.duration).trim() : "";
    var durationEl = null;
    if (durationText) {
      durationEl = document.createElement("span");
      durationEl.className = "pilot-tree-case__duration";
      durationEl.textContent = durationText;
      durationEl.title = "执行耗时";
    }

    var copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "pilot-tree-case__copy";
    copyBtn.title = "复制用例名";
    copyBtn.setAttribute("aria-label", "复制用例名");
    copyBtn.innerHTML =
      '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">' +
      '<rect x="5" y="5" width="8" height="8" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5"/>' +
      '<path d="M3 10.5V3.5A1.5 1.5 0 0 1 4.5 2H10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>' +
      "</svg>";

    main.addEventListener("click", function () {
      aside.querySelectorAll(".pilot-tree-case.is-selected").forEach(function (el) {
        el.classList.remove("is-selected");
      });
      row.classList.add("is-selected");
      var groupEl = row.closest(".pilot-tree-group");
      if (groupEl) groupEl.classList.remove("is-collapsed");
      onSelect(test);
    });
    copyBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      var name = treeCaseName(test);
      copyText(name).then(
        function () {
          copyBtn.classList.add("is-copied");
          copyBtn.title = "已复制";
          setTimeout(function () {
            copyBtn.classList.remove("is-copied");
            copyBtn.title = "复制用例名";
          }, 1200);
        },
        function () {
          copyBtn.title = "复制失败";
        }
      );
    });

    row.appendChild(main);
    if (durationEl) row.appendChild(durationEl);
    row.appendChild(copyBtn);
    if (cnTitle) {
      var tip = document.createElement("div");
      tip.className = "pilot-tree-case__tip";
      tip.setAttribute("role", "tooltip");
      tip.textContent = cnTitle;
      row.appendChild(tip);
    }
    parent.appendChild(row);
  }

  function buildTree(tests, onSelect) {
    var aside = document.createElement("aside");
    aside.className = "pilot-case-tree";
    var grouped = groupTests(tests);

    (grouped._order || RESULT_ORDER).forEach(function (result) {
      if (result === "_order") return;
      var list = grouped[result];
      if (!list || !list.length) return;

      var group = document.createElement("div");
      group.className = "pilot-tree-group";
      // Expand failed/error by default; collapse passed.
      if (result === "passed" || result === "skipped") {
        group.classList.add("is-collapsed");
      }

      var toggle = makeToggle(RESULT_LABEL[result] || result, list.length);
      toggle.addEventListener("click", function () {
        group.classList.toggle("is-collapsed");
      });
      group.appendChild(toggle);

      var children = document.createElement("div");
      children.className = "pilot-tree-children";
      list.forEach(function (test) {
        appendCaseRow(children, test, aside, onSelect);
      });

      group.appendChild(children);
      aside.appendChild(group);
    });

    return aside;
  }

  function buildDetailPane() {
    var pane = document.createElement("div");
    pane.className = "pilot-detail-pane";
    pane.innerHTML =
      '<div class="pilot-detail-empty">请选择左侧用例查看步骤与日志</div>' +
      '<div class="pilot-detail-steps" hidden>' +
      '<button type="button" class="pilot-panel-head pilot-panel-head--toggle" data-action="toggle-steps" aria-expanded="true">' +
      '<span class="pilot-panel-head__title">用例步骤详情</span>' +
      '<span class="pilot-panel-head__hint" data-role="steps-hint">折叠</span>' +
      "</button>" +
      '<div class="pilot-panel-body" data-role="steps"></div>' +
      "</div>" +
      '<div class="pilot-detail-log" hidden>' +
      '<div class="pilot-panel-head"><span class="pilot-panel-head__title">用例执行日志</span></div>' +
      '<div class="pilot-panel-body" data-role="log"></div>' +
      "</div>";

    var stepsWrap = pane.querySelector(".pilot-detail-steps");
    var toggleBtn = pane.querySelector('[data-action="toggle-steps"]');
    var stepsHint = pane.querySelector('[data-role="steps-hint"]');
    toggleBtn.addEventListener("click", function () {
      var collapsed = stepsWrap.classList.toggle("is-collapsed");
      stepsHint.textContent = collapsed ? "展开" : "折叠";
      toggleBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    });

    pane.showTest = function (test) {
      pane.querySelector(".pilot-detail-empty").hidden = true;
      stepsWrap.hidden = false;
      pane.querySelector(".pilot-detail-log").hidden = false;
      // 切换用例时展开步骤区，避免长步骤被折叠挡住
      stepsWrap.classList.remove("is-collapsed");
      stepsHint.textContent = "折叠";
      toggleBtn.setAttribute("aria-expanded", "true");
      pane.querySelector('[data-role="steps"]').innerHTML = extractDetailHtml(test);
      pane.querySelector('[data-role="log"]').innerHTML =
        formatLog(test.log) + extrasHtml(test.extras);
      // 旧报告里的 trace.zip 相对链接改成协议地址，点击即拉起 show-trace
      bindTraceViewerLinks(pane);
    };

    return pane;
  }

  function mount(blob) {
    var host = document.getElementById("pilot-report-ui");
    if (!host) return;
    host.innerHTML = "";

    var tests = flattenTests(blob);
    var counts = countByResult(tests);
    var envBar = buildEnvBar(blob.environment);
    if (envBar) host.appendChild(envBar);
    host.appendChild(buildOverview(counts));

    var layout = document.createElement("section");
    layout.className = "pilot-detail-layout";
    var detail = buildDetailPane();
    var tree = buildTree(tests, function (test) {
      detail.showTest(test);
    });
    layout.appendChild(tree);
    layout.appendChild(detail);
    host.appendChild(layout);

    document.body.classList.add("pilot-enhanced");

    // Auto-select first failed/error case when present.
    var preferred =
      tests.find(function (t) {
        return t._result === "failed" || t._result === "error";
      }) || tests[0];
    if (preferred) {
      var row = Array.prototype.find.call(
        tree.querySelectorAll(".pilot-tree-case"),
        function (el) {
          return el.dataset.uid === preferred._uid;
        }
      );
      var mainBtn = row && row.querySelector(".pilot-tree-case__main");
      if (mainBtn) mainBtn.click();
    }
  }

  function boot() {
    var host = document.getElementById("pilot-report-ui");
    var container = document.getElementById("data-container");
    if (!container) {
      if (host) {
        host.innerHTML =
          '<p class="pilot-detail-empty">未找到报告数据（data-container）</p>';
      }
      return;
    }
    var blob = decodeBlob(container.getAttribute("data-jsonblob"));
    if (!blob) {
      if (host) {
        host.innerHTML =
          '<p class="pilot-detail-empty">报告数据解析失败，请打开控制台查看错误</p>';
      }
      return;
    }
    try {
      mount(blob);
    } catch (err) {
      console.error("pilot report: mount failed", err);
      if (host) {
        host.innerHTML =
          '<p class="pilot-detail-empty">报告 UI 渲染失败：' +
          String(err && err.message ? err.message : err) +
          "</p>";
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    // Defer one tick so the stock report renderer finishes first.
    setTimeout(boot, 0);
  }
})();
