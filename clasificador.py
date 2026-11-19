#!/usr/bin/env python3
"""
mdi-clasificador — Clasificador de noticias MDI (cloud).
Lee noticias desde Google Sheets (vía Apps Script Web App),
las clasifica con Gemini y detecta duplicados, luego escribe
los resultados de vuelta a Sheets.

Uso (GitHub Actions o local):
  python clasificador.py                        # clasifica todo
  python clasificador.py --solo-regex            # sin LLM
  python clasificador.py --incluir-baja          # incluye prioridad BAJA
  python clasificador.py --limite 20             # máx 20 noticias
  python clasificador.py --hoja "Captura_Nov"    # hoja origen personalizada
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

from config import (
    COL_PRIORIDAD_ORIGEN,
    COLS_CLASIFICACION,
    COLS_DATOS,
    COLS_DUPLICADOS,
    COLS_ESTATUS,
    COLS_VALIDACION,
    ENTES,
    ENTES_PRIORIZACION_ALTA,
    GEMINI_API_URL,
    GEMINI_MODEL,
    MAX_REGISTROS_POR_ENVIO,
    MAX_REINTENTOS,
    MAX_TEXTO_LLM,
    PALABRAS_ENTES_ALTA,
    PATRON_CIFRAS,
    PATRONES_TEMAS,
    PATRONES_VALORES_COMPARATIVOS,
    PAUSA_ENTRE_LLM,
    PRIORIDADES_PERMITIDAS,
    PROMPT_CLASIFICACION,
    PROMPT_DUPLICADOS,
    TEMAS,
    TODAS_COLUMNAS,
)


# ═══════════════════════════════════════════════════════════
# LECTURA DESDE GOOGLE SHEETS (vía Apps Script Web App GET)
# ═══════════════════════════════════════════════════════════

def leer_desde_sheets(webapp_url: str, hoja: str | None = None) -> list[dict]:
    """Lee noticias desde el Web App de Apps Script (GET → JSON)."""
    params = {}
    if hoja:
        params["hoja"] = hoja

    print(f"📡 Leyendo noticias desde Sheets …")
    try:
        resp = requests.get(webapp_url, params=params, timeout=60,
                            allow_redirects=True)
        resp.raise_for_status()
        datos = resp.json()
    except requests.RequestException as e:
        print(f"❌ Error al leer desde Sheets: {e}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ Respuesta no es JSON válido: {resp.text[:300]}")
        sys.exit(1)

    if isinstance(datos, dict) and "error" in datos:
        print(f"❌ Error del Web App: {datos['error']}")
        sys.exit(1)

    if isinstance(datos, dict) and "data" in datos:
        registros = datos["data"]
    elif isinstance(datos, list):
        registros = datos
    else:
        print(f"❌ Formato inesperado: {str(datos)[:300]}")
        sys.exit(1)

    print(f"   ✅ {len(registros)} noticias leídas")
    return registros


# ═══════════════════════════════════════════════════════════
# PREPARACIÓN DE NOTICIAS
# ═══════════════════════════════════════════════════════════

# Mapeo flexible de columnas de entrada
_MAPEO_COLUMNAS = {
    "id_publicacion": ["id_publicacion", "id", "ID"],
    "titulo": ["titulo", "título", "Titulo", "Título", "title"],
    "fuente": ["fuente", "Fuente", "source", "medio"],
    "fecha_publicacion": ["fecha_publicacion", "fecha", "Fecha",
                          "fecha_publicación", "date"],
    "url": ["url", "URL", "enlace", "link"],
    "noticia_completa": ["noticia_completa", "texto", "contenido",
                         "content", "body", "extracto"],
    "prioridad_origen": ["prioridad", "Prioridad", "priority", "nivel",
                         "prioridad_origen"],
    "texto_publicacion": ["texto_publicacion", "texto_publicación",
                          "Texto_publicacion", "texto publicacion"],
}


def _buscar_campo(registro: dict, campo: str) -> str:
    """Busca un campo en el registro usando mapeo flexible."""
    for variante in _MAPEO_COLUMNAS.get(campo, [campo]):
        if variante in registro:
            return str(registro[variante] or "").strip()
    return ""


def preparar_noticias(registros: list[dict]) -> list[dict]:
    """Normaliza registros crudos de Sheets a formato interno."""
    noticias = []
    for i, reg in enumerate(registros, 1):
        noticia = {
            "id_publicacion": _buscar_campo(reg, "id_publicacion") or str(i),
            "titulo": _buscar_campo(reg, "titulo"),
            "fuente": _buscar_campo(reg, "fuente"),
            "fecha_publicacion": _buscar_campo(reg, "fecha_publicacion"),
            "url": _buscar_campo(reg, "url"),
            "noticia_completa": _buscar_campo(reg, "noticia_completa"),
            # Campos copiados directamente de la hoja Captura
            "prioridad_origen": _buscar_campo(reg, "prioridad_origen"),
            "texto_publicacion": _buscar_campo(reg, "texto_publicacion"),
        }
        # Necesitamos al menos título o texto
        if noticia["titulo"] or noticia["noticia_completa"]:
            noticias.append(noticia)
        else:
            print(f"   ⚠️  Registro {i} sin título ni texto, omitido")
    return noticias


# ═══════════════════════════════════════════════════════════
# PRE-FILTRO POR PRIORIDAD DE ORIGEN
# ═══════════════════════════════════════════════════════════


def filtrar_por_prioridad_origen(
    registros: list[dict],
    col_prioridad: str,
    prioridades_permitidas: list[str],
) -> list[dict]:
    """Descarta registros cuya prioridad de origen NO está permitida.

    Se ejecuta ANTES de preparar_noticias() y de cualquier llamada LLM,
    ahorrando llamadas a Gemini en noticias que ya fueron clasificadas
    como BAJA por el monitor.

    Args:
        registros: lista cruda de dicts tal como viene de Sheets.
        col_prioridad: nombre de la columna de prioridad en la hoja
                       (configurable vía COL_PRIORIDAD_ORIGEN o --col-prioridad).
        prioridades_permitidas: valores aceptados (p. ej. ["ALTA", "MEDIA"]).

    Returns:
        lista filtrada de registros.
    """
    permitidas_upper = {p.upper() for p in prioridades_permitidas}

    # Buscar la columna con variantes flexibles
    variantes = _MAPEO_COLUMNAS.get("prioridad_origen", [col_prioridad])
    # Asegurar que el nombre exacto configurado esté en la búsqueda
    if col_prioridad not in variantes:
        variantes = [col_prioridad] + list(variantes)

    aceptados = []
    sin_columna = 0
    for reg in registros:
        valor = ""
        for v in variantes:
            if v in reg:
                valor = str(reg[v] or "").strip().upper()
                break

        if not valor:
            # Si no existe la columna de prioridad, incluir por defecto
            sin_columna += 1
            aceptados.append(reg)
        elif valor in permitidas_upper:
            aceptados.append(reg)

    descartados = len(registros) - len(aceptados)
    if descartados:
        print(f"\n   🔽 Pre-filtro: {descartados} noticias descartadas "
              f"(prioridad de origen no en {prioridades_permitidas})")
    if sin_columna:
        print(f"   ⚠️  {sin_columna} registros sin columna '{col_prioridad}' "
              f"— incluidos por defecto")
    return aceptados


# ═══════════════════════════════════════════════════════════
# CLASIFICACIÓN REGEX (fallback)
# ═══════════════════════════════════════════════════════════

def clasificar_regex(noticia: dict) -> dict:
    """Clasifica una noticia usando patrones regex (sin LLM)."""
    texto = f"{noticia.get('titulo', '')} {noticia.get('noticia_completa', '')}"
    texto_lower = texto.lower()

    # Detectar temas
    temas_detectados = []
    detalles_temas = {}
    for tema, patrones in PATRONES_TEMAS.items():
        detectado = any(re.search(p, texto_lower) for p in patrones)
        valor = None
        tipo_valor = None
        if detectado:
            temas_detectados.append(tema)
            # Buscar cifras asociadas
            match_cifra = re.search(PATRON_CIFRAS, texto_lower)
            if match_cifra:
                try:
                    valor = float(match_cifra.group(1).replace(",", "").replace(".", ""))
                except ValueError:
                    pass
                unidad = match_cifra.group(2)
                if "por ciento" in unidad or "%" in unidad:
                    tipo_valor = "porcentaje"
                else:
                    tipo_valor = "absoluto"
        detalles_temas[tema] = {
            "detectado": "SI" if detectado else "NO",
            "valor": valor,
            "tipo_valor": tipo_valor,
        }

    tematica_principal = temas_detectados[0] if temas_detectados else "otros_delitos"

    # Detectar entes
    entes_detectados = []
    for ente, palabras in ENTES.items():
        if any(p in texto_lower for p in palabras):
            entes_detectados.append(ente)

    # Cifras comparativas
    tiene_cifras = any(
        re.search(p, texto_lower) for p in PATRONES_VALORES_COMPARATIVOS
    )

    # Prioridad
    prioridad = _calcular_prioridad(
        tematica_principal, entes_detectados, tiene_cifras, texto_lower
    )

    return {
        "tematica_principal": tematica_principal,
        "tematicas_detectadas": temas_detectados,
        "entes_mencionados": entes_detectados,
        "tiene_cifras_comparativas": tiene_cifras,
        "detalles_temas": detalles_temas,
        "prioridad": prioridad,
        "confianza_clasificacion": "regex",
        "modelo_usado": "regex",
    }


# ═══════════════════════════════════════════════════════════
# CLASIFICACIÓN CON GEMINI
# ═══════════════════════════════════════════════════════════

def llamar_gemini(prompt: str, api_key: str) -> str | None:
    """Llama a la API de Gemini y devuelve el texto de respuesta."""
    url = GEMINI_API_URL.format(model=GEMINI_MODEL, api_key=api_key)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048,
        },
    }

    for intento in range(MAX_REINTENTOS + 1):
        try:
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 429:
                espera = 2 ** (intento + 2)
                print(f"   ⏳ Rate limit, esperando {espera}s …")
                time.sleep(espera)
                continue
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return None
        except requests.RequestException as e:
            if intento < MAX_REINTENTOS:
                print(f"   ⚠️  Error Gemini (intento {intento + 1}): {e}")
                time.sleep(2 ** (intento + 1))
            else:
                print(f"   ❌ Error Gemini agotado: {e}")
                return None
    return None


def parsear_json_gemini(texto: str) -> dict | None:
    """Extrae JSON de la respuesta de Gemini (a veces viene con markdown)."""
    if not texto:
        return None
    # Intentar directo
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    # Buscar bloque ```json ... ```
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", texto, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Buscar primer { ... }
    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def clasificar_noticia(noticia: dict, api_key: str) -> dict:
    """Clasifica una noticia con Gemini, fallback a regex."""
    texto = noticia.get("noticia_completa", "")
    if len(texto) > MAX_TEXTO_LLM:
        texto = texto[:MAX_TEXTO_LLM] + " [TRUNCADO]"

    prompt = PROMPT_CLASIFICACION.format(
        titulo=noticia.get("titulo", "Sin título"),
        fuente=noticia.get("fuente", "Desconocida"),
        fecha=noticia.get("fecha_publicacion", "Sin fecha"),
        texto=texto or noticia.get("titulo", ""),
    )

    respuesta = llamar_gemini(prompt, api_key)
    datos = parsear_json_gemini(respuesta)

    if not datos or "tematica_principal" not in datos:
        print(f"   ⚠️  Gemini no devolvió JSON válido, usando regex")
        return clasificar_regex(noticia)

    # Normalizar tema principal
    tema_p = datos.get("tematica_principal", "otros_delitos")
    if tema_p not in TEMAS:
        tema_p = "otros_delitos"

    # Extraer detalles por tema
    detalles = {}
    for t in TEMAS:
        info = datos.get(t, {})
        if isinstance(info, dict):
            detalles[t] = {
                "detectado": str(info.get("detectado", "NO")).upper(),
                "valor": info.get("valor"),
                "tipo_valor": info.get("tipo_valor"),
            }
        else:
            detalles[t] = {"detectado": "NO", "valor": None, "tipo_valor": None}

    temas_det = datos.get("tematicas_detectadas", [tema_p])
    if not isinstance(temas_det, list):
        temas_det = [tema_p]
    temas_det = [t for t in temas_det if t in TEMAS] or [tema_p]

    entes = datos.get("entes_mencionados", [])
    if not isinstance(entes, list):
        entes = []

    cifras = bool(datos.get("tiene_cifras_comparativas", False))

    texto_completo = (
        f"{noticia.get('titulo', '')} {noticia.get('noticia_completa', '')}"
    ).lower()

    prioridad = _calcular_prioridad(tema_p, entes, cifras, texto_completo)

    return {
        "tematica_principal": tema_p,
        "tematicas_detectadas": temas_det,
        "entes_mencionados": entes,
        "tiene_cifras_comparativas": cifras,
        "detalles_temas": detalles,
        "prioridad": prioridad,
        "confianza_clasificacion": "llm",
        "modelo_usado": GEMINI_MODEL,
    }


# ═══════════════════════════════════════════════════════════
# PRIORIZACIÓN
# ═══════════════════════════════════════════════════════════

def _calcular_prioridad(
    tema: str,
    entes: list[str],
    cifras: bool,
    texto_lower: str,
) -> str:
    """Calcula prioridad: ALTA / MEDIA / BAJA."""
    # ALTA: tema reconocido + ente clave
    es_tema_real = tema in TEMAS and tema != "otros_delitos"
    tiene_ente_alta = (
        any(e in ENTES_PRIORIZACION_ALTA for e in entes)
        or any(p in texto_lower for p in PALABRAS_ENTES_ALTA)
    )
    if es_tema_real and tiene_ente_alta:
        return "ALTA"

    # MEDIA: tema reconocido + cifras comparativas
    if es_tema_real and cifras:
        return "MEDIA"

    # MEDIA: tema reconocido (sin ente clave ni cifras)
    if es_tema_real:
        return "MEDIA"

    return "BAJA"


# ═══════════════════════════════════════════════════════════
# DETECCIÓN DE DUPLICADOS
# ═══════════════════════════════════════════════════════════

def detectar_duplicados(noticias: list[dict], api_key: str) -> dict[str, str]:
    """Detecta noticias duplicadas usando Gemini (batch)."""
    if len(noticias) < 2:
        return {}

    # Preparar lista compacta para el prompt
    items = []
    for n in noticias:
        items.append(
            f"- ID: {n['id_publicacion']} | "
            f"Título: {n.get('titulo', 'Sin título')[:120]} | "
            f"Fuente: {n.get('fuente', '?')} | "
            f"Extracto: {n.get('noticia_completa', '')[:200]}"
        )

    lista_txt = "\n".join(items)
    prompt = PROMPT_DUPLICADOS.format(lista_noticias=lista_txt)

    print(f"🔍 Detectando duplicados entre {len(noticias)} noticias …")
    respuesta = llamar_gemini(prompt, api_key)
    datos = parsear_json_gemini(respuesta)

    resultado = {}  # id -> "GRUPO-N (más completa)" o "GRUPO-N"

    if datos and "grupos" in datos:
        grupos = datos["grupos"]
        for gi, grupo in enumerate(grupos, 1):
            ids = grupo.get("ids", [])
            mejor = grupo.get("id_mas_completa", "")
            evento = grupo.get("evento", "")
            etiqueta_base = f"GRUPO-{gi}"
            if evento:
                etiqueta_base += f": {evento[:60]}"
            for uid in ids:
                uid_str = str(uid)
                if uid_str == str(mejor):
                    resultado[uid_str] = f"{etiqueta_base} (más completa)"
                else:
                    resultado[uid_str] = etiqueta_base
        print(f"   ✅ {len(grupos)} grupo(s) de duplicados encontrados")
    else:
        print("   ✅ Sin duplicados detectados")

    return resultado


# ═══════════════════════════════════════════════════════════
# ARMADO DE FILAS DE SALIDA
# ═══════════════════════════════════════════════════════════

def armar_fila(noticia: dict, clasif: dict, dup_label: str) -> dict:
    """Arma una fila con todas las columnas para escribir en Sheets."""
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    fila = {}

    # === Sección DATOS ===
    fila["id_publicacion"] = noticia.get("id_publicacion", "")
    fila["fecha_publicacion"] = noticia.get("fecha_publicacion", "")
    fila["fuente"] = noticia.get("fuente", "")
    fila["titulo"] = noticia.get("titulo", "")
    fila["url"] = noticia.get("url", "")
    # Prioridad: se copia directamente de la hoja Captura (no se recalcula)
    fila["prioridad"] = noticia.get("prioridad_origen", "") or clasif.get("prioridad", "MEDIA")
    # texto_publicacion: copiado de Captura para revisión inmediata del evaluador
    fila["texto_publicacion"] = noticia.get("texto_publicacion", "")[:5000]
    fila["noticia_completa"] = noticia.get("noticia_completa", "")[:2000]

    # === Sección CLASIFICACIÓN LLM ===
    fila["tematica_principal"] = clasif.get("tematica_principal", "")
    fila["tematicas_detectadas"] = ", ".join(
        clasif.get("tematicas_detectadas", [])
    )
    # Columnas por tema
    detalles = clasif.get("detalles_temas", {})
    for tema in TEMAS:
        info = detalles.get(tema, {})
        fila[f"tema_{tema}"] = info.get("detectado", "NO")
        fila[f"{tema}_valor"] = info.get("valor") if info.get("valor") else ""
        fila[f"{tema}_tipo_valor"] = info.get("tipo_valor") or ""

    fila["entes_mencionados"] = ", ".join(clasif.get("entes_mencionados", []))
    fila["tiene_cifras_comparativas"] = (
        "SI" if clasif.get("tiene_cifras_comparativas") else "NO"
    )
    fila["confianza_clasificacion"] = clasif.get("confianza_clasificacion", "")
    fila["modelo_usado"] = clasif.get("modelo_usado", "")
    fila["fecha_clasificacion"] = ahora

    # === Sección DUPLICADOS ===
    fila["duplicados_grupo"] = dup_label

    # === Sección VALIDACIÓN HUMANA (vacía) ===
    for col in COLS_VALIDACION:
        fila[col] = ""

    # === Sección ESTATUS (vacía) ===
    for col in COLS_ESTATUS:
        fila[col] = ""

    return fila


# ═══════════════════════════════════════════════════════════
# ESCRITURA A GOOGLE SHEETS (vía Apps Script Web App POST)
# ═══════════════════════════════════════════════════════════

def escribir_a_sheets(
    webapp_url: str,
    filas: list[dict],
    hoja_destino: str = "Validacion",
) -> bool:
    """Escribe filas clasificadas a Sheets vía POST al Web App."""
    total = len(filas)
    if total == 0:
        print("   ⚠️  Sin filas para escribir")
        return True

    # Enviar en lotes
    enviadas = 0
    for i in range(0, total, MAX_REGISTROS_POR_ENVIO):
        lote = filas[i : i + MAX_REGISTROS_POR_ENVIO]
        payload = {
            "accion": "escribir_clasificacion",
            "hoja": hoja_destino,
            "columnas": TODAS_COLUMNAS,
            "datos": lote,
        }

        try:
            resp = requests.post(
                webapp_url,
                json=payload,
                timeout=90,
                allow_redirects=True,
            )
            # Apps Script Web App siempre redirige (302),
            # requests sigue la redirección automáticamente
            if resp.status_code < 400:
                enviadas += len(lote)
                print(
                    f"   📤 Lote {i // MAX_REGISTROS_POR_ENVIO + 1}: "
                    f"{len(lote)} filas enviadas ({enviadas}/{total})"
                )
            else:
                print(f"   ❌ Error HTTP {resp.status_code}: {resp.text[:300]}")
                return False
        except requests.RequestException as e:
            print(f"   ❌ Error al escribir lote: {e}")
            return False

        # Pausa entre lotes para no sobrecargar Apps Script
        if i + MAX_REGISTROS_POR_ENVIO < total:
            time.sleep(2)

    print(f"   ✅ {enviadas} filas escritas en hoja '{hoja_destino}'")
    return True


# ═══════════════════════════════════════════════════════════
# FLUJO PRINCIPAL
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Clasificador de noticias MDI (cloud)"
    )
    parser.add_argument(
        "--solo-regex",
        action="store_true",
        help="Clasificar solo con regex, sin usar Gemini",
    )
    parser.add_argument(
        "--incluir-baja",
        action="store_true",
        help="Incluir noticias de prioridad BAJA en la salida",
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=0,
        help="Número máximo de noticias a procesar (0 = todas)",
    )
    parser.add_argument(
        "--hoja",
        type=str,
        default=None,
        help="Nombre de la hoja origen en Google Sheets",
    )
    parser.add_argument(
        "--hoja-destino",
        type=str,
        default="Validacion",
        help="Nombre de la hoja destino (default: Validacion)",
    )
    parser.add_argument(
        "--sin-duplicados",
        action="store_true",
        help="Omitir detección de duplicados",
    )
    parser.add_argument(
        "--col-prioridad",
        type=str,
        default=None,
        help="Nombre de la columna de prioridad en hoja origen "
             f"(default: {COL_PRIORIDAD_ORIGEN})",
    )
    args = parser.parse_args()

    # ── Variables de entorno ──
    webapp_url = os.environ.get("WEBAPP_URL")
    if not webapp_url:
        print("❌ Falta variable WEBAPP_URL (URL del Web App de Apps Script)")
        sys.exit(1)

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not args.solo_regex and not api_key:
        print("❌ Falta variable GEMINI_API_KEY (o usa --solo-regex)")
        sys.exit(1)

    # ── Lectura ──
    print("=" * 60)
    print("MDI CLASIFICADOR DE NOTICIAS (cloud)")
    print(f"Fecha: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Modo: {'regex' if args.solo_regex else 'Gemini + regex fallback'}")
    print("=" * 60)

    registros = leer_desde_sheets(webapp_url, args.hoja)
    if not registros:
        print("⚠️  No se encontraron noticias para clasificar")
        sys.exit(0)

    # ── Pre-filtro por prioridad de origen ──
    col_prior = args.col_prioridad or COL_PRIORIDAD_ORIGEN
    if not args.incluir_baja:
        total_antes = len(registros)
        registros = filtrar_por_prioridad_origen(
            registros, col_prior, PRIORIDADES_PERMITIDAS
        )
        if not registros:
            print("⚠️  No quedan noticias tras el pre-filtro de prioridad")
            sys.exit(0)
        print(f"📊 {len(registros)}/{total_antes} registros pasan el pre-filtro "
              f"(col: '{col_prior}', permitidas: {PRIORIDADES_PERMITIDAS})")
    else:
        print("   ℹ️  Pre-filtro desactivado (--incluir-baja)")

    noticias = preparar_noticias(registros)
    print(f"📋 {len(noticias)} noticias válidas")

    if args.limite > 0:
        noticias = noticias[: args.limite]
        print(f"   (limitado a {args.limite})")

    # ── Clasificación ──
    print("\n🏷️  Clasificando noticias …")
    clasificaciones = []
    for i, noticia in enumerate(noticias, 1):
        titulo_corto = (noticia.get("titulo") or "?")[:70]
        print(f"   [{i}/{len(noticias)}] {titulo_corto}")

        if args.solo_regex:
            clasif = clasificar_regex(noticia)
        else:
            clasif = clasificar_noticia(noticia, api_key)
            time.sleep(PAUSA_ENTRE_LLM)

        clasificaciones.append(clasif)
        prior_origen = noticia.get("prioridad_origen", "?")
        print(
            f"           → {clasif['tematica_principal']} "
            f"| prioridad origen: {prior_origen} "
            f"| {clasif['confianza_clasificacion']}"
        )

    # Nota: el filtro de prioridad BAJA se realiza ANTES de la
    # clasificación (pre-filtro por prioridad de origen de Captura).
    # La prioridad en la salida se copia directamente de Captura,
    # no se recalcula.

    if not noticias:
        print("\n⚠️  No quedan noticias tras filtrar por prioridad")
        sys.exit(0)

    # ── Duplicados ──
    duplicados_map = {}
    if not args.sin_duplicados and not args.solo_regex and len(noticias) >= 2:
        duplicados_map = detectar_duplicados(noticias, api_key)

    # ── Armar filas ──
    print(f"\n📝 Armando {len(noticias)} filas para Sheets …")
    filas = []
    for noticia, clasif in zip(noticias, clasificaciones):
        dup_label = duplicados_map.get(noticia["id_publicacion"], "")
        fila = armar_fila(noticia, clasif, dup_label)
        filas.append(fila)

    # ── Escribir a Sheets ──
    print(f"\n📤 Escribiendo a hoja '{args.hoja_destino}' …")
    ok = escribir_a_sheets(webapp_url, filas, args.hoja_destino)

    # ── Resumen ──
    conteo = {}
    for c in clasificaciones:
        p = c["prioridad"]
        conteo[p] = conteo.get(p, 0) + 1

    print("\n" + "=" * 60)
    print("RESUMEN")
    print(f"  Total clasificadas: {len(filas)}")
    for p in ["ALTA", "MEDIA", "BAJA"]:
        if p in conteo:
            print(f"  {p}: {conteo[p]}")
    if duplicados_map:
        grupos = set()
        for v in duplicados_map.values():
            grupos.add(v.split(":")[0].split("(")[0].strip())
        print(f"  Grupos duplicados: {len(grupos)}")
    print(f"  Escritura a Sheets: {'✅ OK' if ok else '❌ FALLÓ'}")
    print("=" * 60)

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
