/* ============================================================
   DXT-CONTA - Main JavaScript (Solo Layout)
   Funcionalidad del topbar, sidebar y componentes globales
   ============================================================ */

(function () {
  "use strict";

  // ── Inicialización ────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    initSidebar();
    initUserMenu();
    initThemeToggle();
    initFlashMessages();
    initGestionSelector();
  });

  // ── Toggle Sidebar ────────────────────────────────────────
  function initSidebar() {
    const toggleBtn = document.getElementById("toggleSidebar");
    const sidebar = document.getElementById("sidebar");
    const body = document.body;

    if (!toggleBtn) return;

    // Cargar estado del sidebar desde localStorage
    const sidebarCollapsed =
      localStorage.getItem("sidebarCollapsed") === "true";
    if (sidebarCollapsed) {
      body.classList.add("sidebar-collapsed");
    }

    // Toggle al hacer clic
    toggleBtn.addEventListener("click", function () {
      body.classList.toggle("sidebar-collapsed");

      // Guardar estado en localStorage
      const isCollapsed = body.classList.contains("sidebar-collapsed");
      localStorage.setItem("sidebarCollapsed", isCollapsed);
    });

    // Cerrar sidebar en móvil al hacer clic fuera
    if (window.innerWidth <= 768) {
      document.addEventListener("click", function (e) {
        if (!sidebar.contains(e.target) && !toggleBtn.contains(e.target)) {
          body.classList.remove("sidebar-open");
        }
      });

      // Abrir sidebar en móvil
      toggleBtn.addEventListener("click", function () {
        body.classList.toggle("sidebar-open");
      });
    }
  }

  // ── Menú de Usuario ───────────────────────────────────────
  function initUserMenu() {
    const userBtn = document.getElementById("userMenuBtn");
    const userDropdown = document.getElementById("userDropdown");

    if (!userBtn || !userDropdown) return;

    // Toggle dropdown
    userBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      userDropdown.classList.toggle("show");
    });

    // Cerrar al hacer clic fuera
    document.addEventListener("click", function (e) {
      if (!userBtn.contains(e.target) && !userDropdown.contains(e.target)) {
        userDropdown.classList.remove("show");
      }
    });

    // Cerrar al presionar ESC
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        userDropdown.classList.remove("show");
      }
    });
  }

  // ── Toggle Tema (Light/Dark) ──────────────────────────────
  function initThemeToggle() {
    // Cargar tema desde localStorage
    const savedTheme = localStorage.getItem("theme") || "light";
    document.documentElement.setAttribute("data-theme", savedTheme);

    // Crear botón de tema si no existe
    const topbarRight = document.querySelector(".topbar-right");
    if (!topbarRight) return;

    const themeBtn = document.createElement("button");
    themeBtn.className = "btn-toggle-theme";
    themeBtn.innerHTML =
      savedTheme === "dark"
        ? '<i class="fas fa-sun"></i>'
        : '<i class="fas fa-moon"></i>';
    themeBtn.setAttribute("aria-label", "Toggle Theme");
    themeBtn.style.cssText = `
            width: 40px;
            height: 40px;
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--text-secondary);
            transition: all 0.15s ease;
        `;

    // Hover effect
    themeBtn.addEventListener("mouseenter", function () {
      this.style.backgroundColor = "var(--bg-hover)";
      this.style.color = "var(--primary-color)";
    });

    themeBtn.addEventListener("mouseleave", function () {
      this.style.backgroundColor = "transparent";
      this.style.color = "var(--text-secondary)";
    });

    // Toggle tema
    themeBtn.addEventListener("click", function () {
      const currentTheme = document.documentElement.getAttribute("data-theme");
      const newTheme = currentTheme === "light" ? "dark" : "light";

      document.documentElement.setAttribute("data-theme", newTheme);
      localStorage.setItem("theme", newTheme);

      this.innerHTML =
        newTheme === "dark"
          ? '<i class="fas fa-sun"></i>'
          : '<i class="fas fa-moon"></i>';
    });

    // Insertar antes del selector de gestión
    const gestionSelector = topbarRight.querySelector(".gestion-selector");
    if (gestionSelector) {
      topbarRight.insertBefore(themeBtn, gestionSelector);
    } else {
      topbarRight.insertBefore(themeBtn, topbarRight.firstChild);
    }
  }

  // ── Flash Messages Auto-Dismiss ───────────────────────────
  function initFlashMessages() {
    const alerts = document.querySelectorAll(".alert");

    alerts.forEach(function (alert) {
      // Auto-dismiss después de 5 segundos
      setTimeout(function () {
        const bsAlert = new bootstrap.Alert(alert);
        bsAlert.close();
      }, 5000);
    });
  }

  // ── Selector de Gestión ───────────────────────────────────
  function initGestionSelector() {
    const gestionSelect = document.getElementById("gestionSelect");

    if (!gestionSelect) return;

    // Cargar gestión desde localStorage
    const savedGestion = localStorage.getItem("gestion_actual");
    if (savedGestion) {
      gestionSelect.value = savedGestion;
    }

    // Guardar cambios
    gestionSelect.addEventListener("change", function () {
      const gestion = this.value;
      localStorage.setItem("gestion_actual", gestion);

      // Mostrar notificación
      showNotification("Gestión cambiada a " + gestion, "info");

      // Recargar página si es necesario
      // location.reload();
    });
  }

  // ── Notificaciones Toast ──────────────────────────────────
  window.showNotification = function (message, type = "info") {
    // Crear contenedor si no existe
    let toastContainer = document.getElementById("toastContainer");
    if (!toastContainer) {
      toastContainer = document.createElement("div");
      toastContainer.id = "toastContainer";
      toastContainer.style.cssText = `
                position: fixed;
                top: 80px;
                right: 20px;
                z-index: 9999;
                display: flex;
                flex-direction: column;
                gap: 10px;
            `;
      document.body.appendChild(toastContainer);
    }

    // Crear toast
    const toast = document.createElement("div");
    toast.className = `alert alert-${type} alert-dismissible fade show`;
    toast.style.cssText = `
            min-width: 300px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            animation: slideInRight 0.3s ease;
        `;

    const icons = {
      success: "fa-check-circle",
      danger: "fa-times-circle",
      warning: "fa-exclamation-triangle",
      info: "fa-info-circle",
    };

    toast.innerHTML = `
            <i class="fas ${icons[type]}"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

    toastContainer.appendChild(toast);

    // Auto-dismiss después de 4 segundos
    setTimeout(function () {
      const bsAlert = new bootstrap.Alert(toast);
      bsAlert.close();
    }, 4000);
  };

  // Agregar animación
  const style = document.createElement("style");
  style.textContent = `
        @keyframes slideInRight {
            from {
                opacity: 0;
                transform: translateX(100px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }
    `;
  document.head.appendChild(style);

  // ── Confirmación de Eliminación ──────────────────────────
  window.confirmDelete = function (
    message = "¿Está seguro de eliminar este registro?",
  ) {
    return confirm(message);
  };

  // ── Formateo de Números ───────────────────────────────────
  window.formatNumber = function (number, decimals = 2) {
    return parseFloat(number)
      .toFixed(decimals)
      .replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  };

  // ── Formateo de Moneda ────────────────────────────────────
  window.formatCurrency = function (amount, currency = "Bs") {
    const formatted = formatNumber(amount, 2);
    return `${currency} ${formatted}`;
  };

  // ── Formateo de Fecha ─────────────────────────────────────
  window.formatDate = function (dateString, format = "dd/mm/yyyy") {
    const date = new Date(dateString);
    const day = String(date.getDate()).padStart(2, "0");
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const year = date.getFullYear();

    switch (format) {
      case "dd/mm/yyyy":
        return `${day}/${month}/${year}`;
      case "yyyy-mm-dd":
        return `${year}-${month}-${day}`;
      case "dd-mm-yyyy":
        return `${day}-${month}-${year}`;
      default:
        return `${day}/${month}/${year}`;
    }
  };

  // ── Debounce Helper ───────────────────────────────────────
  window.debounce = function (func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  };

  // ── Loading Overlay ───────────────────────────────────────
  window.showLoading = function (message = "Cargando...") {
    let overlay = document.getElementById("loadingOverlay");

    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "loadingOverlay";
      overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
            `;

      overlay.innerHTML = `
                <div style="
                    background: white;
                    padding: 2rem;
                    border-radius: 8px;
                    text-align: center;
                    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
                ">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <p style="margin-top: 1rem; margin-bottom: 0; color: #64748b;">${message}</p>
                </div>
            `;

      document.body.appendChild(overlay);
    }

    overlay.style.display = "flex";
  };

  window.hideLoading = function () {
    const overlay = document.getElementById("loadingOverlay");
    if (overlay) {
      overlay.style.display = "none";
    }
  };

  // ── Copiar al Portapapeles ────────────────────────────────
  window.copyToClipboard = function (text) {
    if (navigator.clipboard) {
      navigator.clipboard
        .writeText(text)
        .then(function () {
          showNotification("Copiado al portapapeles", "success");
        })
        .catch(function () {
          showNotification("Error al copiar", "danger");
        });
    } else {
      // Fallback para navegadores antiguos
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();

      try {
        document.execCommand("copy");
        showNotification("Copiado al portapapeles", "success");
      } catch (err) {
        showNotification("Error al copiar", "danger");
      }

      document.body.removeChild(textarea);
    }
  };

  // ── Validación de Formularios ─────────────────────────────
  window.validateForm = function (formId) {
    const form = document.getElementById(formId);
    if (!form) return false;

    // Usar validación nativa de HTML5
    if (!form.checkValidity()) {
      form.classList.add("was-validated");

      // Enfocar el primer campo inválido
      const firstInvalid = form.querySelector(":invalid");
      if (firstInvalid) {
        firstInvalid.focus();
      }

      return false;
    }

    return true;
  };

  // ── Prevenir Doble Submit ─────────────────────────────────
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      const submitBtn = form.querySelector('button[type="submit"]');

      if (submitBtn && !submitBtn.disabled) {
        submitBtn.disabled = true;
        submitBtn.innerHTML =
          '<span class="spinner-border spinner-border-sm me-2"></span>Procesando...';

        // Re-habilitar después de 3 segundos (por si hay error)
        setTimeout(function () {
          submitBtn.disabled = false;
          submitBtn.innerHTML =
            submitBtn.getAttribute("data-original-text") || "Guardar";
        }, 3000);
      }
    });
  });

  // ── Responsive: Ajustar sidebar en resize ─────────────────
  let resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (window.innerWidth > 768) {
        document.body.classList.remove("sidebar-open");
      }
    }, 250);
  });

  // ── Log de Inicialización ─────────────────────────────────
  console.log(
    "%c DXT-CONTA ",
    "background: #2563eb; color: white; font-weight: bold; padding: 4px 8px; border-radius: 4px;",
  );
  console.log("Sistema de Contabilidad v1.0.0");
  console.log("Layout inicializado correctamente ✓");
})();
