/* ============================================================
   DXT-CONTA - Session Management
   Control de sesión, timeout y renovación automática
   ============================================================ */

(function () {
  "use strict";

  // ── Configuración ─────────────────────────────────────────
  const CONFIG = {
    SESSION_TIMEOUT: 30 * 60 * 1000, // 30 minutos en milisegundos
    WARNING_TIME: 5 * 60 * 1000, // Advertir 5 minutos antes
    CHECK_INTERVAL: 60 * 1000, // Verificar cada 1 minuto
    RENEW_ENDPOINT: "/auth/renovar-sesion",
    LOGOUT_ENDPOINT: "/auth/logout",
  };

  let lastActivity = Date.now();
  let sessionTimer = null;
  let warningShown = false;

  // ── Inicialización ────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    initSessionMonitor();
    initActivityTracking();
    initWarningModal();
  });

  // ── Monitor de Sesión ─────────────────────────────────────
  function initSessionMonitor() {
    // Verificar sesión periódicamente
    sessionTimer = setInterval(checkSession, CONFIG.CHECK_INTERVAL);

    console.log("Monitor de sesión iniciado");
  }

  // ── Tracking de Actividad ─────────────────────────────────
  function initActivityTracking() {
    const events = ["mousedown", "keydown", "scroll", "touchstart", "click"];

    events.forEach(function (event) {
      document.addEventListener(event, updateActivity, true);
    });
  }

  function updateActivity() {
    lastActivity = Date.now();
    warningShown = false;

    // Ocultar modal de advertencia si está visible
    const warningModal = document.getElementById("sessionWarningModal");
    if (warningModal) {
      const modal = bootstrap.Modal.getInstance(warningModal);
      if (modal) {
        modal.hide();
      }
    }
  }

  // ── Verificar Estado de Sesión ────────────────────────────
  function checkSession() {
    const inactiveTime = Date.now() - lastActivity;
    const timeRemaining = CONFIG.SESSION_TIMEOUT - inactiveTime;

    // Sesión expirada
    if (timeRemaining <= 0) {
      handleSessionExpired();
      return;
    }

    // Mostrar advertencia
    if (timeRemaining <= CONFIG.WARNING_TIME && !warningShown) {
      showSessionWarning(Math.floor(timeRemaining / 1000));
      warningShown = true;
    }
  }

  // ── Modal de Advertencia ──────────────────────────────────
  function initWarningModal() {
    // Crear modal si no existe
    if (document.getElementById("sessionWarningModal")) return;

    const modalHTML = `
            <div class="modal fade" id="sessionWarningModal" data-bs-backdrop="static" data-bs-keyboard="false" tabindex="-1">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header bg-warning text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-exclamation-triangle me-2"></i>
                                Sesión por Expirar
                            </h5>
                        </div>
                        <div class="modal-body text-center">
                            <i class="fas fa-clock fa-3x text-warning mb-3"></i>
                            <p class="mb-3">Su sesión está por expirar por inactividad.</p>
                            <p class="mb-0">
                                Tiempo restante: <strong id="sessionTimeRemaining">5:00</strong>
                            </p>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" onclick="sessionManager.logout()">
                                <i class="fas fa-sign-out-alt me-2"></i>Cerrar Sesión
                            </button>
                            <button type="button" class="btn btn-primary" onclick="sessionManager.renewSession()">
                                <i class="fas fa-redo me-2"></i>Continuar Sesión
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

    document.body.insertAdjacentHTML("beforeend", modalHTML);
  }

  function showSessionWarning(secondsRemaining) {
    const modal = new bootstrap.Modal(
      document.getElementById("sessionWarningModal"),
    );
    modal.show();

    // Actualizar contador
    updateWarningTimer(secondsRemaining);
  }

  function updateWarningTimer(seconds) {
    const timerElement = document.getElementById("sessionTimeRemaining");
    if (!timerElement) return;

    const interval = setInterval(function () {
      seconds--;

      const minutes = Math.floor(seconds / 60);
      const secs = seconds % 60;
      timerElement.textContent = `${minutes}:${String(secs).padStart(2, "0")}`;

      if (seconds <= 0) {
        clearInterval(interval);
        handleSessionExpired();
      }
    }, 1000);
  }

  // ── Renovar Sesión ────────────────────────────────────────
  function renewSession() {
    fetch(CONFIG.RENEW_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
    })
      .then(function (response) {
        if (response.ok) {
          updateActivity();

          // Cerrar modal
          const modal = bootstrap.Modal.getInstance(
            document.getElementById("sessionWarningModal"),
          );
          if (modal) {
            modal.hide();
          }

          if (window.showNotification) {
            window.showNotification("Sesión renovada correctamente", "success");
          }

          console.log("Sesión renovada");
        } else {
          throw new Error("Error al renovar sesión");
        }
      })
      .catch(function (error) {
        console.error("Error:", error);
        if (window.showNotification) {
          window.showNotification("Error al renovar la sesión", "danger");
        }
      });
  }

  // ── Sesión Expirada ───────────────────────────────────────
  function handleSessionExpired() {
    clearInterval(sessionTimer);

    // Mostrar mensaje
    alert("Su sesión ha expirado por inactividad. Será redirigido al login.");

    // Redirigir al login
    window.location.href = CONFIG.LOGOUT_ENDPOINT + "?expired=true";
  }

  // ── Logout Manual ─────────────────────────────────────────
  function logout() {
    if (confirm("¿Está seguro de cerrar sesión?")) {
      window.location.href = CONFIG.LOGOUT_ENDPOINT;
    }
  }

  // ── Verificar Sesión en el Servidor ───────────────────────
  function checkServerSession() {
    const BASE_PATH = document.body.dataset.basePath || "";
    fetch(`${BASE_PATH}/auth/verificar-sesion`, {
      method: "GET",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        if (!data.valid) {
          handleSessionExpired();
        }
      })
      .catch(function (error) {
        console.error("Error al verificar sesión:", error);
      });
  }

  // Verificar sesión en el servidor cada 5 minutos
  setInterval(checkServerSession, 5 * 60 * 1000);

  // ── API Pública ───────────────────────────────────────────
  window.sessionManager = {
    renewSession: renewSession,
    logout: logout,
    getLastActivity: function () {
      return new Date(lastActivity);
    },
    getTimeRemaining: function () {
      const inactiveTime = Date.now() - lastActivity;
      return Math.max(0, CONFIG.SESSION_TIMEOUT - inactiveTime);
    },
  };

  // ── Advertencia al Cerrar Pestaña ─────────────────────────
  window.addEventListener("beforeunload", function (e) {
    // Solo mostrar si hay cambios sin guardar
    const unsavedForms = document.querySelectorAll("form.dirty");

    if (unsavedForms.length > 0) {
      e.preventDefault();
      e.returnValue = "¿Está seguro de salir? Hay cambios sin guardar.";
      return e.returnValue;
    }
  });

  // ── Marcar Formularios como "Dirty" ───────────────────────
  document.querySelectorAll("form").forEach(function (form) {
    const inputs = form.querySelectorAll("input, select, textarea");

    inputs.forEach(function (input) {
      input.addEventListener("change", function () {
        form.classList.add("dirty");
      });
    });

    form.addEventListener("submit", function () {
      form.classList.remove("dirty");
    });
  });

  console.log("Session Manager inicializado ✓");
  console.log("Timeout de sesión:", CONFIG.SESSION_TIMEOUT / 60000, "minutos");
})();
