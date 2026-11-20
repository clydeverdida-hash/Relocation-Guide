(function () {
  "use strict";
  var cfg = window.SITE_CONFIG || {};
  var UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"];

  /* ---------- Placeholders from config ---------- */
  document.querySelectorAll("[data-config]").forEach(function (el) {
    var v = cfg[el.getAttribute("data-config")];
    if (v) el.textContent = v;
  });
  document.querySelectorAll("[data-config-href]").forEach(function (el) {
    var key = el.getAttribute("data-config-href");
    var v = cfg[key];
    if (!v || v.charAt(0) === "[") return;
    el.href = key === "email" ? "mailto:" + v : key === "phone" ? "tel:" + v.replace(/[^\d+]/g, "") : v;
  });
  if (cfg.logoSrc) {
    document.querySelectorAll(".logo-mark").forEach(function (el) {
      var img = new Image(); img.src = cfg.logoSrc; img.alt = cfg.brokerage || "Logo";
      el.replaceWith(img);
    });
  }
  if (cfg.headshotSrc) {
    document.querySelectorAll(".headshot").forEach(function (el) {
      el.innerHTML = ""; var img = new Image(); img.src = cfg.headshotSrc; img.alt = cfg.agentName || "";
      el.appendChild(img);
    });
  }
  var yr = document.getElementById("year"); if (yr) yr.textContent = new Date().getFullYear();

  /* ---------- Analytics (GA4, only if an ID is set) ---------- */
  window.track = function (name, params) {
    if (typeof window.gtag === "function") window.gtag("event", name, params || {});
  };
  if (cfg.ga4Id && /^G-[A-Z0-9]+$/.test(cfg.ga4Id)) {
    var s = document.createElement("script");
    s.async = true; s.src = "https://www.googletagmanager.com/gtag/js?id=" + cfg.ga4Id;
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", cfg.ga4Id);
  }

  /* ---------- UTM capture (kept for the session so it survives navigation) ---------- */
  var params = new URLSearchParams(location.search);
  var utm = {};
  try { utm = JSON.parse(sessionStorage.getItem("utm") || "{}"); } catch (e) { utm = {}; }
  var foundNew = false;
  UTM_KEYS.forEach(function (k) {
    var v = params.get(k);
    if (v) { if (!foundNew) { utm = {}; foundNew = true; } utm[k] = v.slice(0, 100); }
  });
  if (foundNew) { try { sessionStorage.setItem("utm", JSON.stringify(utm)); } catch (e) {} }
  if (!utm.utm_source && document.referrer && /youtube\.com|youtu\.be/i.test(document.referrer)) {
    utm.utm_source = "youtube"; utm.utm_medium = utm.utm_medium || "referral";
  }

  /* ---------- Lead form ---------- */
  var form = document.getElementById("lead-form");
  if (form) setupForm(form);

  document.querySelectorAll("[data-scroll-to-form]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      var f = document.getElementById("lead-form");
      f.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(function () { f.querySelector("input").focus({ preventScroll: true }); }, 400);
    });
  });

  function setupForm(form) {
    var nameEl = form.elements.fullName, emailEl = form.elements.email, phoneEl = form.elements.phone;
    var btn = form.querySelector("button[type=submit]");
    var status = form.querySelector(".form-status");
    var btnLabel = btn.textContent;
    var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

    // US numbers in any format (10 digits, optional leading 1), or international starting with +.
    function normalizePhone(raw) {
      var v = (raw || "").trim();
      var digits = v.replace(/\D/g, "");
      if (v.charAt(0) === "+") return digits.length >= 8 && digits.length <= 15 ? "+" + digits : "";
      if (digits.length === 11 && digits.charAt(0) === "1") digits = digits.slice(1);
      return digits.length === 10 && /^[2-9]/.test(digits) ? "+1" + digits : "";
    }
    function setError(input, msg) {
      var err = document.getElementById(input.id + "-error");
      input.setAttribute("aria-invalid", msg ? "true" : "false");
      if (err) err.textContent = msg || "";
    }
    function validate() {
      var ok = true;
      var name = nameEl.value.trim().replace(/\s+/g, " ");
      if (name.length < 2) { setError(nameEl, "Please enter your full name."); ok = false; }
      else if (name.length > 80) { setError(nameEl, "Please use a shorter name."); ok = false; }
      else setError(nameEl, "");
      var email = emailEl.value.trim();
      if (!EMAIL_RE.test(email) || email.length > 254) { setError(emailEl, "Please enter a valid email address."); ok = false; }
      else setError(emailEl, "");
      if (phoneEl) {
        if (!normalizePhone(phoneEl.value)) { setError(phoneEl, "Please enter a valid phone number."); ok = false; }
        else setError(phoneEl, "");
      }
      return ok;
    }
    nameEl.addEventListener("blur", function () { if (nameEl.value) validate(); });
    emailEl.addEventListener("blur", function () { if (emailEl.value) validate(); });
    if (phoneEl) phoneEl.addEventListener("blur", function () { if (phoneEl.value) validate(); });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      status.textContent = "";
      if (!validate()) {
        var firstBad = [nameEl, emailEl, phoneEl].filter(function (el) { return el && el.getAttribute("aria-invalid") === "true"; })[0];
        if (firstBad) firstBad.focus();
        return;
      }
      btn.disabled = true; btn.textContent = "Sending…";
      var payload = {
        fullName: nameEl.value.trim().replace(/\s+/g, " "),
        email: emailEl.value.trim(),
        phone: phoneEl ? normalizePhone(phoneEl.value) : "",
        marketingConsent: !!(form.elements.marketingConsent && form.elements.marketingConsent.checked),
        website: form.elements.website ? form.elements.website.value : "",
        utm: utm,
        page: location.pathname
      };
      fetch("/api/lead", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      })
        .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, data: d }; }); })
        .then(function (res) {
          // If the server asks for a field this copy of the form doesn't have, the page is
          // out of date (e.g. a tab left open across an update). Reload to get the current form.
          var fields = (res.data && res.data.fields) || {};
          var missing = Object.keys(fields).filter(function (k) { return !form.elements[k]; });
          var alreadyRefreshed = false;
          try { alreadyRefreshed = sessionStorage.getItem("formRefreshed") === "1"; } catch (e4) {}
          if (missing.length && !alreadyRefreshed) {
            try { sessionStorage.setItem("formRefreshed", "1"); } catch (e3) {}
            var q = new URLSearchParams(location.search); q.set("refresh", Date.now());
            location.replace(location.pathname + "?" + q.toString() + location.hash);
            return new Promise(function () {});
          }
          if (!res.ok || !res.data.ok) throw new Error(res.data.error || "Something went wrong.");
          window.track("generate_lead", {
            form: "relocation_guide",
            lead_source: utm.utm_source || "direct",
            campaign: utm.utm_campaign || "",
            video: utm.utm_content || ""
          });
          try { sessionStorage.setItem("leadFirstName", payload.fullName.split(" ")[0]); sessionStorage.removeItem("formRefreshed"); } catch (e2) {}
          // Small delay lets the analytics hit go out before navigating.
          setTimeout(function () { location.href = "thank-you.html"; }, 250);
        })
        .catch(function (err) {
          status.textContent = err.message + " Please try again.";
          btn.disabled = false; btn.textContent = btnLabel;
        });
    });
  }
})();
