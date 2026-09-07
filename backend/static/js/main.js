// Оценка загруженности на странице корпуса (Этап 2).
// Кнопки отправляют POST /corpus/<id>/report-load и обновляют блок
// расшифровки без перезагрузки страницы.
// В админ-режиме — редактирование расположения столовой (POST canteen-location).
// На главной — плашка входа администратора (справа сверху).

(function () {
  var script = document.currentScript;
  var corpusId = script ? script.getAttribute("data-corpus") : null;
  var page = script ? script.getAttribute("data-page") : null;

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
          headers: { "Content-Type": "application/json" },
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
        headers: { "Content-Type": "application/json" },
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
        headers: { "Content-Type": "application/json" },
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
})();
