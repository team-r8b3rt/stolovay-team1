// Плавный переход между страницами сайта.
// При клике на внутреннюю ссылку страница мягко гаснет, затем происходит переход.

(function () {
  var EXIT_MS = 130;

  function startExit(href) {
    if (document.body.classList.contains("page-exit")) {
      return;
    }
    document.body.classList.add("page-exit");
    setTimeout(function () {
      window.location.href = href;
    }, EXIT_MS);
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest ? event.target.closest("a[href]") : null;
    if (!link) {
      return;
    }
    var href = link.getAttribute("href");
    if (!href || href.charAt(0) === "#") {
      return;
    }
    if (link.target && link.target !== "_self") {
      return;
    }
    if (link.hasAttribute("download")) {
      return;
    }
    if (href.indexOf("http") === 0) {
      return;
    }
    event.preventDefault();
    startExit(link.href);
  });

  window.pageTransition = { go: startExit };
})();