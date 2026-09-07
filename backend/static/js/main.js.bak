// Оценка загруженности на странице корпуса (Этап 2).
// Кнопки отправляют POST /corpus/<id>/report-load и обновляют блок
// расшифровки без перезагрузки страницы.
// В админ-режиме — редактирование расположения столовой (POST canteen-location).
// На главной — плашка входа администратора (справа сверху).

(function () {
  // document.currentScript c defer-скриптами работает не во всех браузерах
  // (в некоторых — null). Доходим до нужного скрипта через querySelector.
  var script = document.currentScript;
  if (!script || (!script.getAttribute("data-page") && !script.getAttribute("data-corpus"))) {
    script = document.querySelector('script[data-page]')
          || document.querySelector('script[data-corpus]')
          || document.currentScript;
  }
  var corpusId = script ? script.getAttribute("data-corpus") : null;
  var page = script ? script.getAttribute("data-page") : null;
  var isAdmin = script ? script.getAttribute("data-is-admin") === "1" : false;
  var csrfToken = script ? script.getAttribute("data-csrf") || "" : "";

  function csrfHeaders(extraHeaders) {
    var headers = extraHeaders || {};
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
    return headers;
  }

  // ===== Плашка входа администратора на главной =====
  if (page === "index") {
    var openBtn = document.getElementById("admin-login-btn");
    var modal = document.getElementById("admin-modal");
    var passwordInput = document.getElementById("admin-modal-password");
    var submitBtn = document.getElementById("admin-modal-submit");
    var closeBtn = document.getElementById("admin-modal-close");
    var errorMsg = document.getElementById("admin-modal-error");

    if (openBtn && modal) {
      function openModal() {
        modal.classList.add("open");
        modal.setAttribute("aria-hidden", "false");
        errorMsg.classList.remove("show");
        passwordInput.value = "";
        passwordInput.focus();
      }
      function closeModal() {
        modal.classList.remove("open");
        modal.setAttribute("aria-hidden", "true");
      }

      openBtn.addEventListener("click", openModal);
      closeBtn.addEventListener("click", closeModal);
      // Esc закрывает плашку
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          closeModal();
        }
      });

      function doLogin() {
        var password = passwordInput.value;
        submitBtn.disabled = true;
        fetch("/login", {
          method: "POST",
          headers: csrfHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ password: password }),
        })
          .then(function (resp) {
            return resp.json().then(function (data) {
              return { ok: resp.ok, data: data };
            });
          })
          .then(function (result) {
            if (result.ok) {
              window.location = "/";
            } else {
              errorMsg.classList.add("show");
              passwordInput.value = "";
              passwordInput.focus();
            }
          })
          .catch(function () {
            errorMsg.textContent = "Не получилось войти. Попробуйте ещё раз.";
            errorMsg.classList.add("show");
          })
          .finally(function () {
            submitBtn.disabled = false;
          });
      }

      submitBtn.addEventListener("click", doLogin);
      passwordInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          doLogin();
        }
      });
    }
    return;
  }

  if (!corpusId) {
    return;
  }

  var buttons = document.querySelectorAll(".report-btn");
  var loadCard = document.getElementById("load-card");
  var feedback = document.getElementById("report-feedback");
  var footerDiv = document.querySelector("footer");

  function applyLoad(newLoad) {
    loadCard.classList.remove("load-low", "load-medium", "load-high");
    loadCard.classList.add("load-" + newLoad);
  }

  function showFeedback(text, autoHide) {
    feedback.textContent = text;
    feedback.classList.add("show");
    if (footerDiv) footerDiv.classList.add("fb-shown");
    if (autoHide) {
      clearTimeout(feedback._timer);
      feedback._timer = setTimeout(function () {
        feedback.classList.remove("show");
        if (footerDiv) footerDiv.classList.remove("fb-shown");
      }, 2500);
    }
  }

  Array.prototype.forEach.call(buttons, function (btn) {
    btn.addEventListener("click", function () {
      var load = btn.getAttribute("data-load");

      // на время запроса блокируем кнопки, чтобы не слать повторно
      Array.prototype.forEach.call(buttons, function (b) { b.disabled = true; });

      fetch("/corpus/" + corpusId + "/report-load", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ load: load }),
      })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          if (data.error) {
            throw new Error(data.error);
          }
          applyLoad(data.load);
          showFeedback("Спасибо, обновили!", true);
        })
        .catch(function () {
          showFeedback("Не получилось обновить. Попробуйте ещё раз.", false);
        })
        .finally(function () {
          Array.prototype.forEach.call(buttons, function (b) { b.disabled = false; });
        });
    });
  });

  // Редактирование расположения (только в админ-режиме)
  var locEditBtn = document.getElementById("loc-edit-btn");
  var locPanel = document.getElementById("loc-edit-panel");
  var locInput = document.getElementById("loc-edit-input");
  var locSaveBtn = document.getElementById("loc-save-btn");
  var locText = document.getElementById("canteen-location");
  var locFeedback = document.getElementById("loc-feedback");

  if (locEditBtn && locPanel && locInput && locSaveBtn) {
    locEditBtn.addEventListener("click", function () {
      locPanel.hidden = false;
      locInput.focus();
      locEditBtn.hidden = true;
      locFeedback.textContent = "";
      locFeedback.classList.remove("error");
    });

    locSaveBtn.addEventListener("click", function () {
      var location = locInput.value.trim();
      if (!location) {
        locFeedback.textContent = "Не может быть пустым";
        locFeedback.classList.add("error");
        return;
      }

      locSaveBtn.disabled = true;
      fetch("/corpus/" + corpusId + "/canteen-location", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ canteen_location: location }),
      })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          if (data.error) {
            throw new Error(data.error);
          }
          // расположение сохранилось в общих данных — видно на всех страницах
          locText.textContent = "Столовая, " + data.canteen_location;
          locPanel.hidden = true;
          locEditBtn.hidden = false;
          locFeedback.textContent = "";
          locFeedback.classList.remove("error");
        })
        .catch(function () {
          locFeedback.textContent = "Не получилось сохранить.";
          locFeedback.classList.add("error");
        })
        .finally(function () {
          locSaveBtn.disabled = false;
        });
    });
  }

  // ===== Модальное окно меню (Этап 3) =====
  var menuOpenBtn = document.getElementById("menu-open-btn");
  var menuModal = document.getElementById("menu-modal");
  var menuModalBody = document.getElementById("menu-modal-body");
  var menuCloseBtn = document.getElementById("menu-modal-close");
  var menuGuestNote = document.getElementById("menu-guest-note");
  var menuAdminActions = document.getElementById("menu-admin-actions");
  var menuAddItemBtn = document.getElementById("menu-add-item-btn");
  var menuAddCatBtn = document.getElementById("menu-add-cat-btn");
  var menuForm = document.getElementById("menu-form");
  var menuFormTitle = document.getElementById("menu-form-title");
  var menuFormName = document.getElementById("menu-form-name");
  var menuFormPrice = document.getElementById("menu-form-price");
  var menuFormDesc = document.getElementById("menu-form-desc");
  var menuFormPriceWrap = document.getElementById("menu-form-price-wrap");
  var menuFormDescWrap = document.getElementById("menu-form-desc-wrap");
  var menuFormCatWrap = document.getElementById("menu-form-cat-wrap");
  var menuFormCat = document.getElementById("menu-form-cat");
  var menuFormError = document.getElementById("menu-form-error");
  var menuFormSave = document.getElementById("menu-form-save");
  var menuFormCancel = document.getElementById("menu-form-cancel");

  var menuData = [];          // сырые данные меню (категории с items) для админа
  var menuFormMode = null;    // null | {type:'cat', id} | {type:'item', catId, id}
  var adminMenuCache = null;  // меню для админа (с hidden-категориями)

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function fetchMenu() {
    if (!menuModal || !menuModalBody) return;
    menuModalBody.innerHTML = '<p class="menu-empty">Загружаем меню…</p>';
    fetch("/corpus/" + corpusId + "/menu")
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (data && data.error) { throw new Error(data.error); }
        var cats = data || [];
        adminMenuCache = cats;
        renderMenu(cats);
      })
      .catch(function () {
        menuModalBody.innerHTML = '<p class="menu-empty">Не получилось загрузить меню.</p>';
      });
  }

  function renderMenu(cats) {
    if (!menuModalBody) return;
    if (!cats.length) {
      menuModalBody.innerHTML = '<p class="menu-empty">Меню пока пустое.</p>';
    } else {
      var html = "";
      cats.forEach(function (cat) {
        html += '<div class="menu-category' + (cat.visible ? '' : ' unavailable') + '">';
        html += '<div class="menu-category-head">';
        html += '<span class="menu-cat-name">' + esc(cat.name) + '</span>';
        if (!cat.visible) {
          html += '<span class="menu-cat-hidden-tag">нет в наличии</span>';
        }
        if (isAdmin) {
          html += '<button type="button" class="menu-btn ghost" data-act="edit-cat" data-id="' + esc(cat.id) + '">Изменить</button>';
          html += '<button type="button" class="menu-btn ghost" data-act="toggle-cat" data-id="' + esc(cat.id) + '">' + (cat.visible ? 'Нет в наличии' : 'В наличии') + '</button>';
          html += '<button type="button" class="menu-btn danger" data-act="del-cat" data-id="' + esc(cat.id) + '">Удалить</button>';
        }
        html += '</div>';
        if (cat.items && cat.items.length) {
          cat.items.forEach(function (item) {
            html += '<div class="menu-item' + (item.visible ? '' : ' unavailable') + '">';
            html += '<div class="menu-item-top">';
            html += '<span class="menu-item-name">' + esc(item.name);
            if (!item.visible) { html += '<span class="menu-item-hidden-tag">нет в наличии</span>'; }
            html += '</span>';
            html += '<span class="menu-item-price">' + esc(item.price) + ' ₽</span>';
            html += '</div>';
            if (item.description) {
              html += '<div class="menu-item-desc">' + esc(item.description) + '</div>';
            }
            if (isAdmin) {
              html += '<div class="menu-item-admin">';
              html += '<button type="button" class="menu-btn ghost" data-act="edit-item" data-cat="' + esc(cat.id) + '" data-id="' + esc(item.id) + '">Изменить</button>';
              html += '<button type="button" class="menu-btn ghost" data-act="toggle-item" data-cat="' + esc(cat.id) + '" data-id="' + esc(item.id) + '">' + (item.visible ? 'Нет в наличии' : 'В наличии') + '</button>';
              html += '<button type="button" class="menu-btn danger" data-act="del-item" data-cat="' + esc(cat.id) + '" data-id="' + esc(item.id) + '">Удалить</button>';
              html += '</div>';
            }
            html += '</div>';
          });
        } else {
          html += '<p class="menu-empty">В категории пока нет блюд.</p>';
        }
        html += '</div>';
      });
      menuModalBody.innerHTML = html;
    }
    if (isAdmin) {
      menuAdminActions.hidden = false;
      menuGuestNote.hidden = true;
    } else {
      menuAdminActions.hidden = true;
      menuGuestNote.hidden = false;
    }
  }

  function openMenuModal() {
    if (!menuModal) return;
    menuModal.classList.add("open");
    menuModal.setAttribute("aria-hidden", "false");
    fetchMenu();
  }

  function closeMenuModal() {
    if (!menuModal) return;
    menuModal.classList.remove("open");
    menuModal.setAttribute("aria-hidden", "true");
    hideMenuForm();
  }

  if (menuOpenBtn) {
    menuOpenBtn.addEventListener("click", openMenuModal);
  }
  if (menuCloseBtn) {
    menuCloseBtn.addEventListener("click", closeMenuModal);
  }
  if (menuModal) {
    menuModal.addEventListener("click", function (e) {
      if (e.target === menuModal) closeMenuModal();
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && menuModal && menuModal.classList.contains("open")) {
      closeMenuModal();
    }
  });

  function hideMenuForm() {
    if (!menuForm) return;
    menuForm.classList.remove("open");
    menuFormMode = null;
  }

  function openMenuForm(mode) {
    if (!menuForm) return;
    menuFormMode = mode;
    menuFormError.textContent = "";
    menuFormName.value = "";
    menuFormPrice.value = "";
    menuFormDesc.value = "";
    if (mode.type === "item") {
      menuFormTitle.textContent = mode.id ? "Изменить блюдо" : "Новое блюдо";
      menuFormCatWrap.hidden = false;
      menuFormPriceWrap.hidden = false;
      menuFormDescWrap.hidden = false;
      fillCategorySelect(mode.catId);
    } else {
      menuFormTitle.textContent = mode.id ? "Переименовать категорию" : "Новая категория";
      menuFormCatWrap.hidden = true;
      menuFormPriceWrap.hidden = true;
      menuFormDescWrap.hidden = true;
    }
    menuForm.classList.add("open");
    menuFormName.focus();
  }

  function fillCategorySelect(selectedId) {
    if (!menuFormCat) return;
    menuFormCat.innerHTML = "";
    (adminMenuCache || []).forEach(function (cat) {
      var opt = document.createElement("option");
      opt.value = cat.id;
      opt.textContent = cat.name;
      if (cat.id === selectedId) opt.selected = true;
      menuFormCat.appendChild(opt);
    });
  }

  function menuFormSaveHandler() {
    if (!menuFormMode) return;
    var mode = menuFormMode;
    var name = menuFormName.value.trim();
    if (!name) {
      menuFormError.textContent = "Название не может быть пустым.";
      return;
    }
    menuFormSave.disabled = true;
    var payload;
    if (mode.type === "item") {
      payload = { name: name, description: menuFormDesc.value.trim() };
      var priceText = menuFormPrice.value.trim();
      var price = parseInt(priceText, 10);
      if (priceText === "" || isNaN(price) || price < 0 || String(price) !== priceText) {
        menuFormError.textContent = "Укажите целую неотрицательную цену в рублях.";
        menuFormSave.disabled = false;
        return;
      }
      payload.price = price;
      var catId = menuFormCat.value;
      var url, method;
      if (mode.id) {
        url = "/corpus/" + corpusId + "/menu/items/" + mode.id;
        method = "PUT";
      } else {
        url = "/corpus/" + corpusId + "/menu/items";
        payload.category_id = catId;
        method = "POST";
      }
      fetch(url, {
        method: method,
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          if (data.error) { throw new Error(data.error); }
          hideMenuForm();
          fetchMenu();
        })
        .catch(function (err) {
          menuFormError.textContent = err.message || "Не получилось сохранить.";
        })
        .finally(function () { menuFormSave.disabled = false; });
    } else {
      payload = { name: name };
      var url2, method2;
      if (mode.id) {
        url2 = "/corpus/" + corpusId + "/menu/categories/" + mode.id;
        method2 = "PUT";
      } else {
        url2 = "/corpus/" + corpusId + "/menu/categories";
        method2 = "POST";
      }
      fetch(url2, {
        method: method2,
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          if (data.error) { throw new Error(data.error); }
          hideMenuForm();
          fetchMenu();
        })
        .catch(function (err) {
          menuFormError.textContent = err.message || "Не получилось сохранить.";
        })
        .finally(function () { menuFormSave.disabled = false; });
    }
  }

  menuFormSave.addEventListener("click", menuFormSaveHandler);
  menuFormCancel.addEventListener("click", hideMenuForm);

  // Делегирование кликов на кнопки в списке меню
  if (menuModalBody) {
    menuModalBody.addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-act]");
      if (!btn) return;
      var act = btn.getAttribute("data-act");
      var id = btn.getAttribute("data-id");
      var catId = btn.getAttribute("data-cat");
      if (act === "edit-cat") {
        openMenuForm({ type: "cat", id: id });
        menuFormName.value = findCatById(id).name;
      } else if (act === "del-cat") {
        if (!confirm("Удалить категорию и все её блюда?")) return;
        apiDelete("/corpus/" + corpusId + "/menu/categories/" + id);
      } else if (act === "toggle-cat") {
        var cat = findCatById(id);
        apiPatch("/corpus/" + corpusId + "/menu/categories/" + id, { visible: !cat.visible });
      } else if (act === "edit-item") {
        var it = findItemById(catId, id);
        openMenuForm({ type: "item", catId: catId, id: id });
        menuFormName.value = it.name;
        menuFormPrice.value = it.price;
        menuFormDesc.value = it.description;
      } else if (act === "del-item") {
        if (!confirm("Удалить блюдо?")) return;
        apiDelete("/corpus/" + corpusId + "/menu/items/" + id);
      } else if (act === "toggle-item") {
        var item = findItemById(catId, id);
        apiPatch("/corpus/" + corpusId + "/menu/items/" + id, { visible: !item.visible });
      }
    });
  }

  function findCatById(id) {
    for (var i = 0; i < (adminMenuCache || []).length; i++) {
      if (adminMenuCache[i].id === id) return adminMenuCache[i];
    }
    return null;
  }

  function findItemById(catId, itemId) {
    var cat = findCatById(catId);
    if (!cat) return null;
    for (var i = 0; i < cat.items.length; i++) {
      if (cat.items[i].id === itemId) return cat.items[i];
    }
    return null;
  }

  function apiDelete(url) {
    fetch(url, { method: "DELETE", headers: csrfHeaders() })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (data.error) { throw new Error(data.error); }
        fetchMenu();
      })
      .catch(function () { window.alert("Не получилось удалить."); });
  }

  function apiPatch(url, payload) {
    fetch(url, {
      method: "PATCH",
      headers: csrfHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (data.error) { throw new Error(data.error); }
        fetchMenu();
      })
      .catch(function () { window.alert("Не получилось изменить."); });
  }

  if (menuAddItemBtn) {
    menuAddItemBtn.addEventListener("click", function () {
      openMenuForm({ type: "item", catId: null });
    });
  }
  if (menuAddCatBtn) {
    menuAddCatBtn.addEventListener("click", function () {
      openMenuForm({ type: "cat", id: null });
    });
  }
})();
