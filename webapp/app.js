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

  // Встроенная SVG-иконка (без эмодзи).
  const icon = (name) => '<svg class="ic"><use href="#ic-' + name + '"></use></svg>';
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

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
    try { return await res.json(); } catch (e) { return { ok: false, error: "Нет связи с сервером" }; }
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

  // ---------- render: главный экран ----------
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

    const C = 2 * Math.PI * 52;
    const pct = sub.has_key ? (sub.progress || 0) : 0;
    $("ring-fg").style.strokeDashoffset = String(C - (C * pct) / 100);
    $("ring-value").textContent = sub.forever ? "∞" : (sub.has_key ? (sub.days_left + "д") : "—");

    $("status-expires").textContent =
      sub.has_key ? (sub.forever ? "Бессрочная подписка" : "действует до " + (sub.expires_human || "")) :
      "Активируйте пробный период или выберите тариф";

    const btn = $("hero-action");
    if (sub.status === "active" || sub.status === "trial") {
      btn.innerHTML = icon("connect") + " Подключить";
      btn.className = "btn btn-primary";
      btn.onclick = () => { haptic(); setTab("key"); };
    } else if (sub.status === "expired") {
      btn.innerHTML = "Продлить подписку";
      btn.className = "btn btn-primary";
      btn.onclick = () => { haptic(); scrollToTariffs(); };
    } else if (STATE.trial_available) {
      btn.innerHTML = icon("gift") + " Попробовать бесплатно · " + STATE.trial_days + " дн.";
      btn.className = "btn btn-primary";
      btn.onclick = doTrial;
    } else {
      btn.innerHTML = "Выбрать тариф";
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
        (t.badge ? '<span class="badge">' + esc(t.badge) + "</span>" : "") +
        '<div><div class="tariff-name">' + esc(t.title) + "</div>" +
        '<div class="tariff-sub">примерно ' + t.per_month + " ₽ в месяц</div></div>" +
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
      const text = "Пользуюсь быстрым VPN без логов — первый день бесплатно. Заходи:";
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

    const st = $("dev-status");
    if (!d.has_key) {
      st.innerHTML = "Лимит активируется вместе с подпиской";
    } else if (d.online) {
      st.innerHTML = '<span class="dot online"></span> Сейчас онлайн · ' + used + " из " + limit;
    } else {
      st.innerHTML = '<span class="dot"></span> Сейчас не подключено';
    }

    const pct = limit ? Math.max(6, Math.min(100, Math.round((used / limit) * 100))) : 0;
    $("dev-bar-fill").style.width = pct + "%";
    $("dev-bar-fill").classList.toggle("full", limit && used >= limit);

    const price = d.pack_price || 0;
    const size = d.pack_size || 10;
    $("dev-buy").innerHTML = icon("plus") + " Добавить +" + size + " устройств · " + price + "₽";
    $("dev-buy").onclick = () => openPaySheet({
      plan: "devices_10",
      title: "+" + size + " устройств",
      price: price,
      _devices: true,
    });
    $("dev-refresh").onclick = () => { haptic(); loadDevices(true); };
  }

  async function loadDevices(spin) {
    if (spin) $("dev-status").innerHTML = "Обновляем…";
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
    toast("Готово, подписка активна");
    setTab("key");
  }

  function openPaySheet(t) {
    haptic();
    currentPay = t;
    const p = STATE.payment;
    const methods = [];
    if (p.crypto_enabled) methods.push({ m: "crypto", ic: "coin", label: "Криптовалюта (CryptoBot)" });
    methods.push({ m: "card_ru", ic: "card", label: "Карта РФ" });
    methods.push({ m: "card_ua", ic: "card", label: "Карта Украины" });

    $("sheet-content").innerHTML =
      "<h3>" + esc(t.title) + "</h3><p class='pay-sum'>К оплате " + t.price + " ₽</p>" +
      '<div class="pay-methods">' +
      methods.map((x) =>
        '<div class="pay-m" data-m="' + x.m + '"><span class="ico">' + icon(x.ic) + "</span>" + x.label +
        '<span class="pay-arrow">' + icon("chevron") + "</span></div>"
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
        "<h3>Оплата криптовалютой</h3><p class='pay-sum'>" + esc(t.title) + " — " + t.price + " ₽</p>" +
        '<button id="pay-open" class="btn btn-primary">Перейти к оплате</button>' +
        '<button id="pay-check" class="btn btn-soft" style="margin-top:10px">Я оплатил — проверить</button>' +
        '<p class="muted center small" style="margin-top:12px">Ключ выдастся автоматически после оплаты</p>';
      $("pay-open").onclick = () => { haptic(); tg ? tg.openTelegramLink(res.pay_url) : window.open(res.pay_url, "_blank"); };
      $("pay-check").onclick = () => checkPayment(res.order_id, true);
      startPolling(res.order_id);
    } else {
      const card = res.card;
      $("sheet-content").innerHTML =
        "<h3>Оплата картой</h3><p class='pay-sum'>" + esc(t.title) + " — " + t.price + " ₽</p>" +
        (card
          ? '<div class="card-label">Реквизиты для перевода</div><div class="codebox" id="card-num">' + esc(card) + "</div>" +
            '<button id="card-copy" class="btn btn-soft" style="margin-top:10px">' + icon("copy") + " Скопировать номер</button>"
          : "<p class='muted'>Напишите администратору за реквизитами.</p>") +
        '<p class="muted small" style="margin-top:14px">Заказ #' + res.order_id +
        ". После перевода напишите " + esc(res.admin) + " — подтвердим вручную.</p>" +
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
        const fresh = await api("api/state");
        if (fresh && fresh.ok) STATE = fresh;
        renderAll();
        loadDevices(true);
        toast("Готово, устройства добавлены");
      } else {
        renderAll();
        toast("Оплата прошла, подписка активна");
        setTab("key");
      }
    } else if (manual) {
      toast("Оплата ещё не поступила");
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
      const cards = [
        ["users", "Пользователей", st.total_users],
        ["check", "Подписок", st.active_subs],
        ["key", "Ключей", st.active_keys],
        ["doc", "Заказов", st.pending_orders],
      ];
      $("admin-stats").innerHTML = cards.map(([ic, c, n]) =>
        '<div class="stat"><div class="stat-top">' + icon(ic) +
        '<span class="stat-num">' + n + "</span></div>" +
        '<div class="stat-cap">' + c + "</div></div>").join("");
    }
    if (o.ok) renderOrders(o.orders);
    if (u.ok) {
      $("admin-users").innerHTML = u.users.map((x) => {
        const name = x.username ? "@" + esc(x.username) : esc(x.first_name || x.id);
        const blockTag = x.blocked ? '<span class="utag">заблокирован</span>' : "";
        return '<div class="urow" data-id="' + x.id + '"><span>' + name + blockTag +
          '</span><span class="muted">' + x.id + " " + icon("chevron") + "</span></div>";
      }).join("") || "<div class='muted'>Пусто</div>";
      $("admin-users").querySelectorAll(".urow").forEach((row) => {
        row.onclick = () => {
          const id = row.getAttribute("data-id");
          $("u-search").value = id;
          findUser(id);
          $("u-card").scrollIntoView({ behavior: "smooth", block: "center" });
        };
      });
    }
    $("bc-send").onclick = sendBroadcast;
    $("u-find").onclick = () => findUser($("u-search").value.trim());
    $("u-search").onkeydown = (e) => { if (e.key === "Enter") findUser($("u-search").value.trim()); };
  }

  function renderOrders(orders) {
    const box = $("admin-orders");
    if (!orders.length) { box.innerHTML = "<div class='muted'>Нет новых заказов</div>"; return; }
    box.innerHTML = "";
    orders.forEach((o) => {
      const el = document.createElement("div");
      el.className = "order";
      el.innerHTML =
        '<div class="order-top"><span>@' + esc(o.username || o.user_id) + " · " + esc(o.plan) +
        '</span><b>' + o.price + "₽</b></div>" +
        '<div class="row"><button class="btn btn-ok btn-sm">' + icon("check") + ' Подтвердить</button>' +
        '<button class="btn btn-bad btn-sm">' + icon("x") + ' Отклонить</button></div>';
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

  // --- управление пользователем ---
  async function findUser(q) {
    if (!q) return toast("Введите ID или @username");
    const res = await api("api/admin/user", { query: q });
    if (!res.ok) { notify("error"); $("u-card").classList.add("hidden"); return toast(res.error || "Не найдено"); }
    renderUserCard(res.user);
  }

  function subLine(sub) {
    if (!sub || !sub.has_key) return "нет подписки";
    if (sub.forever) return "бессрочно";
    if (sub.status === "expired") return "истекла";
    return sub.days_left + " дн. · до " + (sub.expires_human || "");
  }

  function renderUserCard(u) {
    const box = $("u-card");
    box.classList.remove("hidden");
    const name = u.username ? "@" + esc(u.username) : esc(u.first_name || ("ID " + u.id));
    box.innerHTML =
      '<div class="uc-head"><div class="uc-name">' + name + "</div>" +
      '<span class="pill ' + (u.blocked ? "expired" : "active") + '">' +
      (u.blocked ? "Заблокирован" : "Активен") + "</span></div>" +
      '<div class="uc-grid">' +
      ucItem("ID", u.id) +
      ucItem("Подписка", subLine(u.subscription)) +
      ucItem("Лимит устройств", u.device_limit) +
      ucItem("Приглашено", u.referrals) +
      ucItem("Баланс", (u.balance || 0) + " ₽") +
      ucItem("Регистрация", u.joined || "—") +
      "</div>" +
      '<div class="card-label" style="margin-top:14px">Выдать подписку</div>' +
      '<div class="uc-grant">' +
      [7, 30, 90, 365].map((d) => '<button class="btn btn-soft btn-sm" data-d="' + d + '">+' + d + " дн.</button>").join("") +
      "</div>" +
      '<button id="uc-block" class="btn btn-sm ' + (u.blocked ? "btn-ok" : "btn-bad") + '" style="margin-top:10px">' +
      icon(u.blocked ? "unlock" : "lock") + (u.blocked ? " Разблокировать" : " Заблокировать") + "</button>";

    box.querySelectorAll(".uc-grant button").forEach((b) => {
      b.onclick = () => userAction(u.id, "grant", parseInt(b.getAttribute("data-d"), 10));
    });
    $("uc-block").onclick = () => userAction(u.id, u.blocked ? "unblock" : "block");
  }

  function ucItem(label, value) {
    return '<div class="uc-item"><span class="muted">' + label + "</span><b>" + esc(value) + "</b></div>";
  }

  async function userAction(id, action, days) {
    haptic("medium");
    const res = await api("api/admin/user-action", { user_id: id, action, days });
    if (res.ok) {
      notify("success");
      toast(action === "grant" ? "Начислено " + days + " дн."
        : action === "block" ? "Пользователь заблокирован"
        : action === "unblock" ? "Пользователь разблокирован" : "Готово");
      renderUserCard(res.user);
    } else { notify("error"); toast(res.error || "Ошибка"); }
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
      showGate({ text: "Откройте приложение через нашего Telegram-бота, чтобы продолжить." });
      return;
    }
    STATE = data;

    if (data.blocked) {
      showGate({ text: "Ваш доступ приостановлен. Напишите в поддержку." });
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
