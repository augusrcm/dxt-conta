window.DXT_BASE_PATH = document.body.dataset.basePath || "";

window.dxtUrl = function (url) {
    if (!url) return url;
    if (/^(http|https):\/\//.test(url)) return url;
    return window.DXT_BASE_PATH + url;
};window.DXTBase = window.DXTBase || {};

window.DXTBase.formatDateShortEs = function (value) {
  if (!value) return "—";

  const texto = String(value).trim();

  const dias = {
    sun: "Dom",
    mon: "Lun",
    tue: "Mar",
    wed: "Mie",
    thu: "Jue",
    fri: "Vie",
    sat: "Sab",
  };

  const meses = {
    jan: "Ene",
    feb: "Feb",
    mar: "Mar",
    apr: "Abr",
    may: "May",
    jun: "Jun",
    jul: "Jul",
    aug: "Ago",
    sep: "Sep",
    oct: "Oct",
    nov: "Nov",
    dec: "Dic",
  };

  let match = texto.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) {
    const anio = Number(match[1]);
    const mes = Number(match[2]);
    const dia = Number(match[3]);

    const fecha = new Date(anio, mes - 1, dia);
    const diasArr = ["Dom", "Lun", "Mar", "Mie", "Jue", "Vie", "Sab"];
    const mesesArr = [
      "Ene",
      "Feb",
      "Mar",
      "Abr",
      "May",
      "Jun",
      "Jul",
      "Ago",
      "Sep",
      "Oct",
      "Nov",
      "Dic",
    ];

    return `${diasArr[fecha.getDay()]}, ${String(dia).padStart(2, "0")} ${mesesArr[mes - 1]}`;
  }

  match = texto.match(/^([A-Za-z]{3}),\s*(\d{1,2})\s*([A-Za-z]{3})/);
  if (match) {
    const diaSemana = dias[match[1].toLowerCase()] || match[1];
    const dia = String(match[2]).padStart(2, "0");
    const mes = meses[match[3].toLowerCase()] || match[3];

    return `${diaSemana}, ${dia} ${mes}`;
  }

  return texto;
};
window.DXTBase.todayLocalISO = function () {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
};

window.DXTBase.getDataTableLanguageEs = function (overrides) {
  const base = {
    decimal: ",",
    thousands: ".",
    processing: "Procesando...",
    search: "Buscar:",
    lengthMenu: "Mostrar _MENU_ registros",
    info: "Mostrando _START_ a _END_ de _TOTAL_ registros",
    infoEmpty: "Mostrando 0 a 0 de 0 registros",
    infoFiltered: "(filtrados de _MAX_ registros)",
    infoPostFix: "",
    loadingRecords: "Cargando...",
    zeroRecords: "No se encontraron resultados",
    emptyTable: "No hay datos disponibles",
    paginate: {
      first: "Primero",
      previous: "Anterior",
      next: "Siguiente",
      last: "Último",
    },
    aria: {
      sortAscending: ": activar para ordenar de manera ascendente",
      sortDescending: ": activar para ordenar de manera descendente",
    },
    select: {
      rows: {
        _: "%d filas seleccionadas",
        0: "Haz clic en una fila para seleccionarla",
        1: "1 fila seleccionada",
      },
    },
  };

  if (!overrides || typeof overrides !== "object") return base;

  const result = JSON.parse(JSON.stringify(base));
  Object.keys(overrides).forEach((key) => {
    if (
      overrides[key] &&
      typeof overrides[key] === "object" &&
      !Array.isArray(overrides[key]) &&
      result[key] &&
      typeof result[key] === "object"
    ) {
      result[key] = Object.assign({}, result[key], overrides[key]);
    } else {
      result[key] = overrides[key];
    }
  });
  return result;
};

window.DXTBase.applyDataTableSpanishDefaults = function () {
  if (
    !window.jQuery ||
    !window.jQuery.fn ||
    !window.jQuery.fn.dataTable ||
    window.jQuery.fn.dataTable.__dxtSpanishApplied
  ) {
    return;
  }

  window.jQuery.extend(true, window.jQuery.fn.dataTable.defaults, {
    language: window.DXTBase.getDataTableLanguageEs(),
  });

  window.jQuery.fn.dataTable.__dxtSpanishApplied = true;
};

window.DXTBase.applyDataTableSpanishDefaults();

$(document).ajaxError(function (event, xhr) {
  if (xhr && xhr.status === 401) {
    let msg = "Tu sesión expiró por inactividad.";

    try {
      const resp = xhr.responseJSON || JSON.parse(xhr.responseText);
      if (resp && resp.msg) {
        msg = resp.msg;
      }
    } catch (e) {}

    Swal.fire({
      icon: "warning",
      title: "Sesión expirada",
      text: msg,
      confirmButtonText: "Ir al login",
      allowOutsideClick: false,
      allowEscapeKey: false,
    }).then(function () {
      window.location.href = dxtUrl("/login");
    });
  }
});

window.DXTBase.initFlatpickrDate = function (selector, options) {
  if (!window.flatpickr) return null;

  const elements =
    typeof selector === "string"
      ? document.querySelectorAll(selector)
      : selector instanceof Element
        ? [selector]
        : selector;

  if (!elements || !elements.length) return null;

  const baseOptions = {
    dateFormat: "Y-m-d",
    altInput: true,
    altFormat: "d/m/Y",
    allowInput: true,
    locale: "es"
  };

  return flatpickr(elements, Object.assign({}, baseOptions, options || {}));
};
window.DXTBase = window.DXTBase || {};



window.DXTBase = window.DXTBase || {};

window.DXTBase.initSelect2Es = function (selector, options) {
  if (!window.jQuery || !window.jQuery.fn || !window.jQuery.fn.select2) return [];

  const jq = window.jQuery;
  const elements = typeof selector === "string"
    ? jq(selector)
    : selector instanceof Element
      ? jq(selector)
      : jq(selector || []);

  if (!elements.length) return [];

  const cfg = Object.assign({
    width: "100%",
    language: "es",
    allowClear: true,
    placeholder: "Seleccione",
    minimumResultsForSearch: 0
  }, options || {});

  elements.each(function () {
    const item = jq(this);
    if (item.data("select2")) item.select2("destroy");
    item.select2(cfg);
  });

  return elements.toArray();
};

window.DXTBase.numeroEnteroLiteralEs = function (value, apocoparUno) {
  const unidades = {
    0: "cero", 1: "uno", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco",
    6: "seis", 7: "siete", 8: "ocho", 9: "nueve", 10: "diez",
    11: "once", 12: "doce", 13: "trece", 14: "catorce", 15: "quince",
    16: "dieciseis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve",
    20: "veinte", 21: "veintiuno", 22: "veintidos", 23: "veintitres",
    24: "veinticuatro", 25: "veinticinco", 26: "veintiseis", 27: "veintisiete",
    28: "veintiocho", 29: "veintinueve"
  };
  const decenas = {
    30: "treinta", 40: "cuarenta", 50: "cincuenta", 60: "sesenta",
    70: "setenta", 80: "ochenta", 90: "noventa"
  };
  const centenas = {
    100: "cien", 200: "doscientos", 300: "trescientos", 400: "cuatrocientos",
    500: "quinientos", 600: "seiscientos", 700: "setecientos", 800: "ochocientos",
    900: "novecientos"
  };

  function apocopar(texto) {
    if (texto === "uno") return "un";
    if (texto.endsWith("veintiuno")) return texto.slice(0, -9) + "veintiun";
    if (texto.endsWith(" y uno")) return texto.slice(0, -6) + " y un";
    if (texto.endsWith(" uno")) return texto.slice(0, -4) + " un";
    return texto;
  }

  function literal(numero, apoco) {
    numero = Number(numero || 0);
    numero = Math.trunc(numero);

    let texto;
    if (numero < 0) {
      texto = "menos " + literal(Math.abs(numero), false);
    } else if (numero < 30) {
      texto = unidades[numero];
    } else if (numero < 100) {
      const decena = Math.floor(numero / 10) * 10;
      const unidad = numero % 10;
      texto = decenas[decena] + (unidad ? " y " + literal(unidad, false) : "");
    } else if (numero < 1000) {
      if (centenas[numero]) {
        texto = centenas[numero];
      } else {
        const centena = Math.floor(numero / 100) * 100;
        const resto = numero % 100;
        texto = (centena === 100 ? "ciento" : centenas[centena]) + " " + literal(resto, false);
      }
    } else if (numero < 1000000) {
      const miles = Math.floor(numero / 1000);
      const resto = numero % 1000;
      texto = miles === 1 ? "mil" : literal(miles, true) + " mil";
      if (resto) texto += " " + literal(resto, false);
    } else if (numero < 1000000000000) {
      const millones = Math.floor(numero / 1000000);
      const resto = numero % 1000000;
      texto = millones === 1 ? "un millon" : literal(millones, true) + " millones";
      if (resto) texto += " " + literal(resto, false);
    } else {
      texto = String(numero);
    }

    return apoco ? apocopar(texto) : texto;
  }

  return literal(value, !!apocoparUno);
};

window.DXTBase.montoLiteralBolivianos = function (value, options) {
  const cfg = options && typeof options === "object" ? options : {};
  let textoValor = String(value == null ? "0" : value).trim();

  if (textoValor.indexOf(",") >= 0 && textoValor.indexOf(".") < 0) {
    textoValor = textoValor.replace(",", ".");
  } else {
    textoValor = textoValor.replace(/,/g, "");
  }

  const importe = Number(textoValor);
  const seguro = Number.isFinite(importe) ? importe : 0;
  const totalCentavos = Math.round(Math.abs(seguro) * 100);
  const enteros = Math.floor(totalCentavos / 100);
  const centavos = totalCentavos % 100;
  const signo = seguro < 0 ? "menos " : "";
  const literal = window.DXTBase.numeroEnteroLiteralEs(enteros, true);
  const prefijo = cfg.prefijo === false ? "" : "Son: ";
  const resultado = `${prefijo}${signo}${literal} ${String(centavos).padStart(2, "0")}/100 bolivianos`;

  if (cfg.uppercase) return resultado.toUpperCase();
  return resultado.charAt(0).toUpperCase() + resultado.slice(1);
};

window.DXTBase = window.DXTBase || {};

window.DXTBase.getCsrfToken = function () {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? String(meta.getAttribute('content') || '') : '';
};

window.DXTBase.withCsrfHeaders = function (headers) {
  const result = new Headers(headers || {});
  const token = window.DXTBase.getCsrfToken();
  if (token && !result.has('X-CSRFToken')) result.set('X-CSRFToken', token);
  if (!result.has('X-Requested-With')) result.set('X-Requested-With', 'XMLHttpRequest');
  return result;
};

(function () {
  if (window.fetch && !window.fetch.__dxtCsrfWrapped) {
    const nativeFetch = window.fetch.bind(window);
    const mutating = { POST: true, PUT: true, PATCH: true, DELETE: true };

    const wrappedFetch = function (input, init) {
      const cfg = Object.assign({}, init || {});
      const method = String(cfg.method || 'GET').toUpperCase();
      if (mutating[method]) {
        cfg.headers = window.DXTBase.withCsrfHeaders(cfg.headers);
      }
      return nativeFetch(input, cfg);
    };

    wrappedFetch.__dxtCsrfWrapped = true;
    window.fetch = wrappedFetch;
  }
})();
