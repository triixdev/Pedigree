"use strict";

(function () {
  var $ = function (id) { return document.getElementById(id); };
  var lastModel = null;
  var lastDepth = 4;
  var memoryId = null;

  // ----- a random id that stays in this browser, no sign in needed
  function userId() {
    var id = null;
    try { id = localStorage.getItem("pedigree_user"); } catch (e) { id = null; }
    if (!id || !/^[A-Za-z0-9_-]{1,40}$/.test(id)) {
      id = memoryId;
    }
    if (!id) {
      var bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);
      id = Array.prototype.map.call(bytes, function (b) {
        return ("0" + b.toString(16)).slice(-2);
      }).join("");
      try { localStorage.setItem("pedigree_user", id); } catch (e) { /* kept in memory only */ }
    }
    memoryId = id;
    return id;
  }

  // ----- small helpers. Text from the network only ever goes in as text.
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function asText(v) {
    if (v === null || v === undefined) return "";
    if (Array.isArray(v)) return v.map(asText).join(" -> ");
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  }

  function pick(obj, keys) {
    for (var i = 0; i < keys.length; i++) {
      var v = obj[keys[i]];
      if (v !== undefined && v !== null && v !== "") return v;
    }
    return "";
  }

  function setStatus(node, text, isError) {
    node.textContent = text || "";
    node.className = isError ? "error" : "";
  }

  function api(path, options) {
    return fetch(path, options).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (!res.ok) {
          var detail = data && data.detail;
          throw new Error(typeof detail === "string" ? detail : "Please check what you entered and try again.");
        }
        return data;
      });
    });
  }

  function post(path, body) {
    return api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }

  // ----- showing flags
  var SEVERITY = { review: "To review", warning: "Warning", warn: "Warning", info: "Note" };
  var SKIP = { kind: 1, code: 1, type: 1, flag: 1, name: 1, severity: 1, path: 1 };

  function humanize(key) {
    var s = key.replace(/_/g, " ");
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  function labelFor(key) {
    if (key === "summary") return "Why";
    if (key === "why") return "Details";
    if (/reason|message|explain|because/i.test(key)) return "Why";
    if (/source|url|link|evidence/i.test(key)) return "Sources";
    return humanize(key);
  }

  function rank(label) {
    return label === "Why" ? 0 : (label === "Sources" ? 1 : (label === "Details" ? 2 : 3));
  }

  // a small record like {"node": "org/model"} becomes "Node: org/model"
  function recordText(obj) {
    return Object.keys(obj).map(function (k) {
      var v = obj[k];
      return humanize(k) + ": " + (Array.isArray(v) ? v.join(", ") : asText(v));
    }).join("; ");
  }

  // a path can be a list of nodes like {"id": "org/model", "type": "model"}
  function pathText(p) {
    if (!Array.isArray(p)) return asText(p);
    return p.map(function (x) {
      if (x && typeof x === "object") return x.id || x.name || x.model || JSON.stringify(x);
      return String(x);
    }).join(" -> ");
  }

  // text goes in as text, and only Hugging Face addresses become links
  function linkify(text) {
    var wrap = el("dd");
    String(text).split(/(https:\/\/huggingface\.co\/[^\s,;)"']+)/).forEach(function (part) {
      if (!part) return;
      if (/^https:\/\/huggingface\.co\//.test(part)) {
        var a = el("a", null, part.replace("https://huggingface.co/", ""));
        a.href = part;
        a.rel = "noopener noreferrer";
        a.target = "_blank";
        wrap.appendChild(a);
        wrap.appendChild(document.createTextNode(" "));
      } else {
        wrap.appendChild(document.createTextNode(part));
      }
    });
    return wrap;
  }

  function flagCard(f) {
    var sev = String(pick(f, ["severity"])).toLowerCase();
    var card = el("article", "flag" + (sev === "review" ? " review" : ""));
    card.appendChild(el("p", "tag", SEVERITY[sev] || sev || "Flag"));
    card.appendChild(el("h3", null, asText(pick(f, ["kind", "code", "type", "flag", "name"])) || "flag"));

    var dl = el("dl");
    if (f.path) {
      dl.appendChild(el("dt", null, "Path"));
      dl.appendChild(el("dd", null, pathText(f.path)));
    }

    var rows = [];
    Object.keys(f).forEach(function (key) {
      if (SKIP[key]) return;
      var v = f[key];
      if (v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) return;
      var label = labelFor(key);
      var text;
      if (Array.isArray(v)) text = v.map(asText).join(label === "Sources" ? " " : ", ");
      else if (typeof v === "object") text = recordText(v);
      else text = asText(v);
      text = text.replace(/`/g, "");
      rows.push({ label: label, text: text });
    });
    rows.sort(function (a, b) { return rank(a.label) - rank(b.label); });
    rows.forEach(function (r) {
      dl.appendChild(el("dt", null, r.label));
      dl.appendChild(linkify(r.text));
    });

    card.appendChild(dl);
    return card;
  }

  function showResult(data) {
    var flags = data.flags || [];
    var counts = { review: 0, warning: 0, info: 0 };
    flags.forEach(function (f) {
      var s = String(f.severity || "").toLowerCase();
      if (s === "review") counts.review++;
      else if (s === "warning" || s === "warn") counts.warning++;
      else counts.info++;
    });
    $("summary").textContent = data.model + ", following " + data.depth + " levels: " +
      counts.review + " to review, " + counts.warning + " warnings, " + counts.info + " notes";

    var box = $("flags");
    box.textContent = "";
    if (flags.length === 0) {
      box.appendChild(el("p", null, "No flags for this model at this depth. That does not mean nothing is wrong: only the rules that have been written are checked."));
    }
    flags.forEach(function (f) { box.appendChild(flagCard(f)); });

    $("raw").textContent = JSON.stringify(data.lineage, null, 2);
    $("results").hidden = false;
    $("notes").hidden = false;
  }

  // ----- check form
  $("check-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var model = $("model").value.trim();
    var depth = $("depth").value;
    var refresh = $("refresh").checked;
    var button = $("check-button");

    setStatus($("status"), "Reading the Hub and walking the graph. This can take a few seconds.", false);
    $("results").hidden = true;
    $("notes").hidden = true;
    $("skeleton").hidden = false;
    button.disabled = true;

    var url = "/api/check?model=" + encodeURIComponent(model) +
      "&depth=" + encodeURIComponent(depth) + "&refresh=" + (refresh ? "true" : "false");

    api(url).then(function (data) {
      lastModel = data.model;
      lastDepth = data.depth;
      setStatus($("status"), "", false);
      showResult(data);
    }).catch(function (err) {
      setStatus($("status"), err.message, true);
    }).then(function () {
      $("skeleton").hidden = true;
      button.disabled = false;
    });
  });

  // ----- saving a decision
  $("decide-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (!lastModel) return;
    post("/api/decide", {
      user: userId(),
      model: lastModel,
      verdict: $("verdict").value,
      note: $("note").value,
      depth: lastDepth
    }).then(function () {
      $("note").value = "";
      setStatus($("saved-status"), "Decision saved.", false);
      loadSaved();
    }).catch(function (err) {
      setStatus($("saved-status"), err.message, true);
    });
  });

  // ----- saved decisions
  var VERDICT = { approved: "Approved", rejected: "Rejected", needs_review: "Needs review" };

  function loadSaved() {
    return post("/api/decisions", { user: userId() }).then(function (rows) {
      var box = $("saved");
      box.textContent = "";
      if (!rows.length) {
        box.appendChild(el("p", null, "Nothing saved yet."));
        return;
      }
      rows.forEach(function (d) {
        var item = el("div", "saved-item");
        item.appendChild(el("p", "id", d.model));
        var when = new Date(Number(d.at) / 1e6);
        var stamp = isNaN(when.getTime()) ? "" : " on " + when.toLocaleDateString();
        item.appendChild(el("p", null, (VERDICT[d.verdict] || d.verdict) + stamp));
        if (d.note) item.appendChild(el("p", null, d.note));
        box.appendChild(item);
      });
    });
  }

  $("load-button").addEventListener("click", function () {
    setStatus($("saved-status"), "", false);
    loadSaved().catch(function (err) { setStatus($("saved-status"), err.message, true); });
  });

  $("recheck-button").addEventListener("click", function () {
    var button = $("recheck-button");
    button.disabled = true;
    setStatus($("saved-status"), "Re-checking your saved models against the Hub. This can take a while.", false);
    post("/api/recheck", { user: userId(), refresh: true }).then(function (rows) {
      var box = $("saved");
      box.textContent = "";
      setStatus($("saved-status"), "", false);
      if (!rows.length) {
        box.appendChild(el("p", null, "Nothing saved yet."));
        return;
      }
      rows.forEach(function (r) {
        var item = el("div", "saved-item");
        item.appendChild(el("p", "id", r.model));
        item.appendChild(el("p", null, "Your decision: " + (VERDICT[r.your_verdict] || r.your_verdict)));
        if (r.changed) {
          item.appendChild(el("p", null, "The lineage has changed since you decided. Flags to review now: " + asText(r.review_flags_now)));
          (r.changes || []).forEach(function (c) { item.appendChild(el("p", null, asText(c))); });
        } else {
          item.appendChild(el("p", null, "No change since you decided."));
        }
        box.appendChild(item);
      });
    }).catch(function (err) {
      setStatus($("saved-status"), err.message, true);
    }).then(function () { button.disabled = false; });
  });

  $("forget-button").addEventListener("click", function () {
    if (!window.confirm("Delete every decision saved under this browser's id? This cannot be undone.")) return;
    post("/api/forget", { user: userId() }).then(function () {
      $("saved").textContent = "";
      setStatus($("saved-status"), "Your saved decisions were deleted.", false);
    }).catch(function (err) {
      setStatus($("saved-status"), err.message, true);
    });
  });
})();