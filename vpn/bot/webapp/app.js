/* AeroProject VPN — Mini App */
(function () {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  let STATE = null;
  let pollTimer = null;
  let currentPay = null;

  // ---------- helpers ----------
  const $ = (id) => document.getElementById(id);
  const haptic = (type) => { try { tg && tg.HapticFeedback.impactOccurred(type || "light"); } catch (e) {} };
  const notify = (type) => { try { tg && tg.HapticFeedback.notificationOccurred(type); } catch (e) {} };

  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(t._t);
    t._t = setTimeout(() => t.classList.remove("show"), 2200);
  }

  async function api(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Init-Data": (tg && tg.initData) || "" },
      body: JSON.stringify(body || {}),
    });
    try { return await res.json(); } catch (e) { return { ok: false, error: "network" }; }
  }

  function copy(text) {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => toast("Скопировано")).catch(() => fallbackCopy(text));
    } else { fallbackCopy(text); }
    notify("success");
  }
  function fallbackCopy(text) {
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); toast("Скопировано"); } catch (e) {}
    document.body.removeChild(ta);
  }

  // ---------- screens ----------
  function showLoader(v) { $("loader").classList.toggle("hidden", !v); }
  function showApp() {
    $("gate").classList.add("hidden");
    $("app").classList.remove("hidden");
    $("tabbar").classList.remove("hidden");
  }
  function showGate(opts) {
    showLoader(false);
    $("app").classList.add("hidden");
    $("tabbar").classList.add("hidden");
    const g = $("gate");
    g.classList.remove("hidden");
    $("gate-text").textContent = opts.text;
    const btn = $("gate-btn");
    if (opts.button) {
      btn.textContent = opts.button.label;
      btn.classList.remove("hidden");
      btn.onclick = opts.button.onClick;
    } else { btn.classList.add("hidden"); }
  }

  // ---------- render ----------
  function statusMeta(s) {
    return {
      none:    { label: "Нет подписки", cls: "none" },
      trial:   { label: "Пробный период", cls: "trial" },
      active:  { label: "Активна", cls: "active" },
      expired: { label: "Истекла", cls: "expired" },
    }[s] || { label: s, cls: "none" };
  }

  function renderHero() {
    const sub = STATE.subscription;
    const meta = statusMeta(sub.status);
    const pill = $("status-pill");
    pill.textContent = meta.label;
    pill.className = "pill " + meta.cls;

    // ring
    const C = 2 * Math.PI * 52;
    const pct = sub.has_key ? (sub.progress || 0) : 0;
    $("ring-fg").style.strokeDashoffset = String(C - (C * pct) / 100);
    $("ring-value").textContent = sub.forever ? "∞" : (sub.has_key ? (sub.days_left + "д") : "—");

    $("status-expires").textContent =
      sub.has_key ? (sub.forever ? "Бессрочная подписка" : "до " + (sub.expires_human || "")) :
      "Активируй пробный период или выбери тариф";

    const btn = $("hero-action");
    if (sub.status === "active" || sub.status === "trial") {
      btn.textContent = "Подключить";
      btn.className = "btn btn-primary";
      btn.onclick = () => { haptic(); setTab("key"); };
    } else if (sub.status === "expired") {
      btn.textContent = "Продлить подписку";
      btn.className = "btn btn-primary";
      btn.onclick = () => { haptic(); scrollToTariffs(); };
    } else if (STATE.trial_available) {
      btn.textContent = "🎁 Попробовать " + STATE.trial_days + " дн. бесплатно";
      btn.className = "btn btn-primary";
      btn.onclick = doTrial;
    } else {
      btn.textContent = "Выбрать тариф";
      btn.className = "btn btn-primary";
      btn.onclick = () => { haptic(); scrollToTariffs(); };
    }
  }

  function scrollToTariffs() {
    $("tariffs").scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function renderTariffs() {
    const box = $("tariffs");
    box.innerHTML = "";
    STATE.tariffs.forEach((t) => {
      const el = document.createElement("div");
      el.className = "tariff" + (t.plan === "6_months" ? " best" : "");
      el.innerHTML =
        (t.badge ? '<span class="badge">' + t.badge + "</span>" : "") +
        '<div><div class="tariff-name">' + t.title + "</div>" +
        '<div class="tariff-sub">≈ ' + t.per_month + "₽ / мес</div></div>" +
        '<div class="tariff-price">' + t.price + "₽<small>" + t.days + " дней</small></div>";
      el.onclick = () => openPaySheet(t);
      box.appendChild(el);
    });
  }

  function renderKey() {
    const sub = STATE.subscription;
    const has = sub.has_key && sub.sub_url;
    $("key-empty").classList.toggle("hidden", !!has);
    $("key-box").classList.toggle("hidden", !has);
    if (has) {
      $("sub-link").textContent = sub.sub_url;
      $("copy-link").onclick = () => { haptic(); copy(sub.sub_url); };
      $("connect-link").onclick = () => {
        haptic();
        const url = sub.sub_url.replace("/sub/", "/app/");
        if (tg) tg.openLink(url); else window.open(url, "_blank");
      };
    }
  }

  function renderRef() {
    const r = STATE.referral;
    $("ref-count").textContent = r.count;
    $("ref-hours").textContent = r.bonus_hours;
    $("ref-link").textContent = r.link;
    $("ref-copy").onclick = () => { haptic(); copy(r.link); };
    $("ref-share").onclick = () => {
      haptic();
      const text = "🛡 Быстрый VPN без логов — первый день бесплатно!";
      const url = "https://t.me/share/url?url=" + encodeURIComponent(r.link) + "&text=" + encodeURIComponent(text);
      if (tg) tg.openTelegramLink(url); else window.open(url, "_blank");
    };
  }

  function renderAdmin() {
    document.querySelectorAll(".admin-only").forEach((e) => e.classList.toggle("hidden", !STATE.is_admin));
  }

  // ---------- devices ----------
  function renderDevices() {
    const d = STATE.devices || {};
    const limit = d.limit || 0;
    const used = typeof d.used === "number" ? d.used : 0;
    $("dev-count").textContent = (d.has_key ? used : 0) + " / " + limit;

    let status;
    if (!d.has_key) status = "Лимит активируется с подпиской";
    else if (d.online) status = "🟢 Сейчас онлайн · " + used + " из " + limit;
    else status = "Подключено устройств: " + used + " из " + limit;
    $("dev-status").textContent = status;

    const pct = limit ? Math.max(6, Math.min(100, Math.round((used / limit) * 100))) : 0;
    $("dev-bar-fill").style.width = pct + "%";
    $("dev-bar-fill").classList.toggle("full", limit && used >= limit);

    const price = d.pack_price || 0;
    const size = d.pack_size || 10;
    $("dev-buy").textContent = "➕ Докупить +" + size + " устройств · " + price + "₽";
    $("dev-buy").onclick = () => openPaySheet({
      plan: "devices_10",
      title: "+" + size + " устройств",
      price: price,
      _devices: true,
    });
    $("dev-refresh").onclick = () => { haptic(); loadDevices(true); };
  }

  async function loadDevices(spin) {
    if (spin) $("dev-status").textContent = "Обновляем…";
    const res = await api("api/devices");
    if (res && res.ok && res.devices) {
      STATE.devices = Object.assign({}, STATE.devices, res.devices);
      renderDevices();
    }
  }

  function renderAll() {
    if (STATE.user && STATE.user.photo_url) {
      $("avatar").style.backgroundImage = "url(" + STATE.user.photo_url + ")";
    }
    renderHero();
    renderDevices();
    renderTariffs();
    renderKey();
    renderRef();
    renderAdmin();
  }

  // ---------- actions ----------
  async function doTrial() {
    haptic("medium");
    const btn = $("hero-action");
    btn.textContent = "Создаём ключ…";
    btn.disabled = true;
    const res = await api("api/trial");
    btn.disabled = false;
    if (!res.ok) { notify("error"); toast(res.error || "Ошибка"); renderHero(); return; }
    notify("success");
    STATE.subscription = res.subscription;
    STATE.trial_available = false;
    renderAll();
    toast("Готово! Подписка активна 🎉");
    setTab("key");
  }

  function openPaySheet(t) {
    haptic();
    currentPay = t;
    const p = STATE.payment;
    const methods = [];
    if (p.crypto_enabled) methods.push({ m: "crypto", ico: "crypto", icon: "🪙", label: "Криптовалюта (CryptoBot)" });
    methods.push({ m: "card_ru", ico: "ru", icon: "💳", label: "Карта РФ" });
    methods.push({ m: "card_ua", ico: "ua", icon: "💳", label: "Карта Украины" });

    $("sheet-content").innerHTML =
      "<h3>" + t.title + "</h3><p class='pay-sum'>К оплате " + t.price + "₽</p>" +
      '<div class="pay-methods">' +
      methods.map((x) =>
        '<div class="pay-m" data-m="' + x.m + '"><div class="ico ' + x.ico + '">' + x.icon + "</div>" + x.label + "</div>"
      ).join("") + "</div>";

    $("sheet-content").querySelectorAll(".pay-m").forEach((el) => {
      el.onclick = () => startPayment(t, el.getAttribute("data-m"));
    });
    openSheet();
  }

  async function startPayment(t, method) {
    haptic("medium");
    $("sheet-content").innerHTML = "<h3>Создаём счёт…</h3><p class='pay-sum'>Секунду</p>";
    const res = await api("api/buy", { plan: t.plan, method });
    if (!res.ok) { notify("error"); toast(res.error || "Ошибка"); closeSheet(); return; }

    if (res.method === "crypto") {
      $("sheet-content").innerHTML =
        "<h3>Оплата криптой</h3><p class='pay-sum'>" + t.title + " — " + t.price + "₽</p>" +
        '<button id="pay-open" class="btn btn-primary">Перейти к оплате</button>' +
        '<button id="pay-check" class="btn btn-soft" style="margin-top:10px">Я оплатил — проверить</button>' +
        '<p class="muted" style="text-align:center;margin-top:12px;font-size:13px">Ключ выдастся автоматически после оплаты</p>';
      $("pay-open").onclick = () => { haptic(); tg ? tg.openTelegramLink(res.pay_url) : window.open(res.pay_url, "_blank"); };
      $("pay-check").onclick = () => checkPayment(res.order_id, true);
      startPolling(res.order_id);
    } else {
      const card = res.card;
      $("sheet-content").innerHTML =
        "<h3>Оплата картой</h3><p class='pay-sum'>" + t.title + " — " + t.price + "₽</p>" +
        (card
          ? '<div class="card-label">Реквизиты</div><div class="codebox" id="card-num">' + card + "</div>" +
            '<button id="card-copy" class="btn btn-soft" style="margin-top:10px">Скопировать номер</button>'
          : "<p class='muted'>Напиши администратору за реквизитами:</p>") +
        '<p class="muted" style="margin-top:14px;font-size:13px">Заказ #' + res.order_id +
        ". После оплаты напиши " + res.admin + " — ключ выдадут вручную.</p>" +
        '<button id="card-admin" class="btn btn-primary" style="margin-top:6px">Написать администратору</button>';
      const cc = $("card-copy"); if (cc) cc.onclick = () => copy(card);
      $("card-admin").onclick = () => {
        const u = (res.admin || "").replace("@", "");
        if (tg) tg.openTelegramLink("https://t.me/" + u); else window.open("https://t.me/" + u, "_blank");
      };
      startPolling(res.order_id);
    }
  }

  function startPolling(orderId) {
    stopPolling();
    let ticks = 0;
    pollTimer = setInterval(() => {
      ticks++;
      if (ticks > 45) return stopPolling();
      checkPayment(orderId, false);
    }, 4000);
  }
  function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

  async function checkPayment(orderId, manual) {
    const res = await api("api/payment-status", { order_id: orderId });
    if (res.ok && res.status === "paid") {
      stopPolling();
      notify("success");
      const isDevices = currentPay && currentPay._devices;
      if (res.subscription) STATE.subscription = res.subscription;
      closeSheet();
      if (isDevices) {
        // Лимит устройств изменился — подтягиваем свежее состояние.
        const fresh = await api("api/state");
        if (fresh && fresh.ok) STATE = fresh;
        renderAll();
        loadDevices(true);
        toast("Готово! Устройства добавлены ✅");
      } else {
        renderAll();
        toast("Оплачено! Подписка активна ✅");
        setTab("key");
      }
    } else if (manual) {
      toast("Оплата ещё не пришла");
    }
  }

  // ---------- sheet ----------
  function openSheet() { $("sheet").classList.remove("hidden"); }
  function closeSheet() { stopPolling(); $("sheet").classList.add("hidden"); }

  // ---------- admin ----------
  async function loadAdmin() {
    if (!STATE.is_admin) return;
    const [s, o, u] = await Promise.all([
      api("api/admin/stats"), api("api/admin/orders"), api("api/admin/users"),
    ]);
    if (s.ok) {
      const st = s.stats;
      $("admin-stats").innerHTML = [
        ["Пользователей", st.total_users], ["Подписок", st.active_subs],
        ["Ключей", st.active_keys], ["Заказов", st.pending_orders],
      ].map(([c, n]) => '<div class="stat"><div class="stat-num">' + n + '</div><div class="stat-cap">' + c + "</div></div>").join("");
    }
    if (o.ok) renderOrders(o.orders);
    if (u.ok) {
      $("admin-users").innerHTML = u.users.map((x) =>
        '<div class="urow"><span>' + (x.username ? "@" + x.username : x.first_name || x.id) +
        '</span><span class="muted">' + x.id + (x.blocked ? " 🚫" : "") + "</span></div>"
      ).join("") || "<div class='muted'>Пусто</div>";
    }
    $("bc-send").onclick = sendBroadcast;
  }

  function renderOrders(orders) {
    const box = $("admin-orders");
    if (!orders.length) { box.innerHTML = "<div class='muted'>Нет заказов</div>"; return; }
    box.innerHTML = "";
    orders.forEach((o) => {
      const el = document.createElement("div");
      el.className = "order";
      el.innerHTML =
        '<div class="order-top"><span>@' + (o.username || o.user_id) + " · " + o.plan +
        '</span><b>' + o.price + "₽</b></div>" +
        '<div class="row"><button class="btn btn-ok btn-sm">Подтвердить</button>' +
        '<button class="btn btn-bad btn-sm">Отклонить</button></div>';
      const [okBtn, noBtn] = el.querySelectorAll("button");
      okBtn.onclick = () => orderAction(o.id, "confirm");
      noBtn.onclick = () => orderAction(o.id, "reject");
      box.appendChild(el);
    });
  }

  async function orderAction(id, action) {
    haptic("medium");
    const res = await api("api/admin/order-action", { order_id: id, action });
    if (res.ok) { notify("success"); toast(action === "confirm" ? "Подтверждено" : "Отклонено"); loadAdmin(); }
    else { notify("error"); toast(res.error || "Ошибка"); }
  }

  async function sendBroadcast() {
    const text = $("bc-text").value.trim();
    if (!text) return toast("Введите текст");
    haptic("medium");
    $("bc-send").disabled = true;
    const res = await api("api/admin/broadcast", { text });
    $("bc-send").disabled = false;
    if (res.ok) { notify("success"); toast("Отправлено " + res.sent + " из " + res.total); $("bc-text").value = ""; }
    else { toast(res.error || "Ошибка"); }
  }

  // ---------- tabs ----------
  function setTab(name) {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    $("tab-" + name).classList.add("active");
    document.querySelectorAll(".tabbtn").forEach((b) => b.classList.toggle("active", b.getAttribute("data-tab") === name));
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (tg) { name === "home" ? tg.BackButton.hide() : tg.BackButton.show(); }
    if (name === "admin") loadAdmin();
  }

  // ---------- init ----------
  async function init() {
    if (tg) {
      tg.ready(); tg.expand();
      try { tg.setHeaderColor("#141a22"); tg.setBackgroundColor("#141a22"); } catch (e) {}
      tg.BackButton.onClick(() => setTab("home"));
    }

    document.querySelectorAll(".tabbtn").forEach((b) => {
      b.onclick = () => { haptic(); setTab(b.getAttribute("data-tab")); };
    });
    $("sheet").querySelector(".sheet-backdrop").onclick = closeSheet;

    const data = await api("api/state");
    showLoader(false);

    if (!data.ok) {
      showGate({ text: "Открой приложение через нашего Telegram-бота, чтобы продолжить." });
      return;
    }
    STATE = data;

    if (data.blocked) {
      showGate({ text: "Ваш аккаунт заблокирован. Обратитесь в поддержку." });
      return;
    }
    if (data.needs_channel) {
      showGate({
        text: "Подпишитесь на наш канал, чтобы пользоваться приложением.",
        button: {
          label: "Открыть канал",
          onClick: () => {
            const u = data.channel.username;
            if (tg) tg.openTelegramLink("https://t.me/" + u); else window.open("https://t.me/" + u, "_blank");
            setTimeout(reloadState, 1500);
          },
        },
      });
      return;
    }

    renderAll();
    showApp();
    loadDevices();
  }

  async function reloadState() {
    const data = await api("api/state");
    if (data.ok && !data.needs_channel && !data.blocked) { STATE = data; renderAll(); showApp(); loadDevices(); }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
