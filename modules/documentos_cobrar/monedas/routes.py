from flask import render_template, request, jsonify
from utils.db import execute_query, execute_query_one
from utils.decorators import login_required

from modules.monedas import monedas_bp

MONEDAS_PERMITIDAS = {'BOB', 'USD', 'UFV'}

# ─────────────────────────────────────────────
# INDEX
# ─────────────────────────────────────────────
@monedas_bp.route('/')
@login_required
def index():
    return render_template('monedas_index.html')


# ─────────────────────────────────────────────
# DATA — feed para DataTables
# ─────────────────────────────────────────────
@monedas_bp.route('/data')
@login_required
def data():
    rows = execute_query(
        """
        SELECT codigo, nombre, simbolo, activo
        FROM contabilidad.moneda
        WHERE codigo IN ('BOB', 'USD', 'UFV')
        ORDER BY CASE codigo
            WHEN 'BOB' THEN 1
            WHEN 'USD' THEN 2
            WHEN 'UFV' THEN 3
            ELSE 99
        END
        """,
        fetchall=True
    )

    result = []
    for r in rows:
        result.append({
            'codigo': r['codigo'],
            'nombre': r['nombre'],
            'simbolo': r['simbolo'] or '',
            'activo': r['activo'],
        })

    return jsonify({'data': result})


# ─────────────────────────────────────────────
# CREAR — BLOQUEADO
# ─────────────────────────────────────────────
@monedas_bp.route('/crear', methods=['POST'])
@login_required
def crear():
    return jsonify({
        'ok': False,
        'msg': 'No está permitido crear nuevas monedas. El catálogo está restringido a BOB, USD y UFV.'
    }), 403


# ─────────────────────────────────────────────
# EDITAR — SOLO nombre y simbolo
# ─────────────────────────────────────────────
@monedas_bp.route('/editar/<string:codigo>', methods=['PUT'])
@login_required
def editar(codigo):
    codigo = (codigo or '').strip().upper()

    if codigo not in MONEDAS_PERMITIDAS:
        return jsonify({
            'ok': False,
            'msg': 'Solo se permite modificar las monedas BOB, USD y UFV.'
        }), 403

    existe = execute_query_one(
        "SELECT 1 FROM contabilidad.moneda WHERE codigo = %s",
        (codigo,)
    )
    if not existe:
        return jsonify({
            'ok': False,
            'msg': f'La moneda "{codigo}" no existe.'
        }), 404

    d = request.get_json() or {}
    campo = d.get('campo')
    valor = d.get('valor')

    campos_permitidos = {'nombre', 'simbolo'}
    if campo not in campos_permitidos:
        return jsonify({
            'ok': False,
            'msg': 'Solo está permitido modificar nombre y símbolo.'
        }), 400

    if campo == 'nombre':
        valor = (valor or '').strip()
        if not valor:
            return jsonify({
                'ok': False,
                'msg': 'El nombre no puede estar vacío.'
            }), 400

    elif campo == 'simbolo':
        valor = (valor or '').strip()
        if not valor:
            return jsonify({
                'ok': False,
                'msg': 'El símbolo no puede estar vacío.'
            }), 400

    execute_query(
        f"UPDATE contabilidad.moneda SET {campo} = %s WHERE codigo = %s",
        (valor, codigo)
    )

    return jsonify({
        'ok': True,
        'msg': 'Moneda actualizada correctamente.'
    })


# ─────────────────────────────────────────────
# ELIMINAR — BLOQUEADO
# ─────────────────────────────────────────────
@monedas_bp.route('/eliminar/<string:codigo>', methods=['DELETE'])
@login_required
def eliminar(codigo):
    return jsonify({
        'ok': False,
        'msg': 'No está permitido eliminar monedas del catálogo controlado.'
    }), 403