(function () {
  function showUnavailable() {
    if (window.Swal) {
      Swal.fire({
        icon: 'info',
        title: 'Ayuda no disponible',
        text: 'Esta pantalla todavía no tiene una ayuda vinculada.',
        confirmButtonText: 'Entendido'
      });
      return;
    }
    window.alert('Esta pantalla todavía no tiene una ayuda vinculada.');
  }

  function $(id) { return document.getElementById(id); }

  function stripPage(htmlText) {
    var parser = new DOMParser();
    var doc = parser.parseFromString(htmlText, 'text/html');
    var title = (doc.querySelector('.help-page-title') || doc.querySelector('title') || {}).textContent || 'Ayuda de esta pantalla';
    var shell = doc.querySelector('.help-page-shell') || doc.body;
    return { title: title.trim(), html: shell.innerHTML };
  }

  function setLoading(body) {
    body.innerHTML = '<div class="layout-help-modal__loading"><i class="fas fa-circle-notch fa-spin"></i><span>Cargando ayuda...</span></div>';
  }

  function openModal(modal) {
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeModal(modal) {
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  async function loadHelp(root, modal, titleEl, bodyEl) {
    var url = (root.dataset.helpUrl || '').trim();
    if (!url) {
      showUnavailable();
      return;
    }
    setLoading(bodyEl);
    openModal(modal);
    try {
      var response = await fetch(url, {
        headers: {
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin'
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      var htmlText = await response.text();
      var parsed = stripPage(htmlText);
      titleEl.textContent = parsed.title || 'Ayuda de esta pantalla';
      bodyEl.innerHTML = '<div class="layout-help-modal__content">' + parsed.html + '</div>';
      bodyEl.scrollTop = 0;
    } catch (error) {
      bodyEl.innerHTML = '<div class="layout-help-modal__empty"><i class="fas fa-triangle-exclamation"></i><span>No se pudo cargar la ayuda de esta pantalla.</span></div>';
    }
  }

  function bindHelpButton() {
    var root = $('layoutHelpRoot');
    var button = $('layoutHelpButton');
    var modal = $('layoutHelpModal');
    var titleEl = $('layoutHelpModalTitle');
    var bodyEl = $('layoutHelpModalBody');
    var closeBtn = $('layoutHelpModalClose');
    var closeFooterBtn = $('layoutHelpModalCloseFooter');
    if (!root || !button || !modal || !titleEl || !bodyEl) return;

    button.addEventListener('click', function (event) {
      event.preventDefault();
      loadHelp(root, modal, titleEl, bodyEl);
    });

    [closeBtn, closeFooterBtn].forEach(function (el) {
      if (!el) return;
      el.addEventListener('click', function () { closeModal(modal); });
    });

    modal.addEventListener('click', function (event) {
      var target = event.target;
      if (target && target.getAttribute('data-help-close') === '1') {
        closeModal(modal);
      }
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && modal.classList.contains('is-open')) {
        closeModal(modal);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindHelpButton);
  } else {
    bindHelpButton();
  }
})();
