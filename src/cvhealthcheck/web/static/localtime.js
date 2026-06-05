// Display-only timestamp localization (ADR 0007 follow-on — UTC-vs-local fix).
//
// Storage stays UTC (collected_at / generated_at / imported_at are ISO-8601 …Z,
// the source of truth). This file ONLY changes what the user SEES: it renders a
// UTC ISO timestamp in the BROWSER's own timezone with an explicit zone label,
// so no mental offset is needed and the time is never shown bare/ambiguous.
//
// Two entry points, both global:
//   window.fmtLocalTime(iso)  -> "YYYY-MM-DD HH:MM <ZONE>" in browser-local time.
//   data-localtime sweep      -> any element with a data-localtime="<utc iso>"
//                                attribute has its text rewritten in place on load
//                                (its raw UTC text is the no-JS / bad-value fallback).
(function () {
  function pad(n) { return String(n).padStart(2, "0"); }

  function zoneLabel(d) {
    // Prefer the browser locale's short zone name (e.g. "CEST", "EDT", "GMT+2").
    try {
      var parts = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" }).formatToParts(d);
      for (var i = 0; i < parts.length; i++) {
        if (parts[i].type === "timeZoneName" && parts[i].value) return parts[i].value;
      }
    } catch (e) { /* fall through to numeric offset */ }
    // Fallback: numeric offset, e.g. "UTC+02:00".
    var off = -d.getTimezoneOffset();             // minutes east of UTC
    var sign = off >= 0 ? "+" : "-";
    var abs = Math.abs(off);
    return "UTC" + sign + pad(Math.floor(abs / 60)) + ":" + pad(abs % 60);
  }

  function fmtLocalTime(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);   // unparseable -> show raw, never blank
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate())
         + " " + pad(d.getHours()) + ":" + pad(d.getMinutes())
         + " " + zoneLabel(d);
  }

  function convertAll(root) {
    var nodes = (root || document).querySelectorAll("[data-localtime]");
    for (var i = 0; i < nodes.length; i++) {
      var iso = nodes[i].getAttribute("data-localtime");
      if (!iso) continue;
      var out = fmtLocalTime(iso);
      if (out) nodes[i].textContent = out;
    }
  }

  window.fmtLocalTime = fmtLocalTime;
  window.convertLocalTimes = convertAll;   // call after injecting dynamic markup

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { convertAll(); });
  } else {
    convertAll();
  }
})();
