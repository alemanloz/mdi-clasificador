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
    COLS_PRIORIDAD_1,
    COLS_VALIDACION,
    COLS_VERIFICACION_HUMANA,
    ENTES,
    ENTES_PRIORIZACION_ALTA,
    GEMINI_API_URL,
    GEMINI_MODEL,
    GROQ_API_URL,
    GROQ_MODEL,
    MAX_REGISTROS_POR_ENVIO,
    MAX_REINTENTOS,
    MAX_REINTENTOS_GROQ,
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

    # prioridad_1: tema+ente=ALTA, tema+cifras_comparativas=MEDIA, resto=BAJA
    prioridad_1 = _calcular_prioridad_1(
        tematica_principal, entes_detectados, tiene_cifras
    )

    return {
        "tematica_principal": tematica_principal,
        "tematicas_detectadas": temas_detectados,
        "entes_mencionados": entes_detectados,
        "tiene_cifras_comparativas": tiene_cifras,
        "detalles_temas": detalles_temas,
        "prioridad": prioridad,
        "prioridad_1": prioridad_1,
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


# ═══════════════════════════════════════════════════════════
# CLASIFICACIÓN CON GROQ (fallback de Gemini)
# ═══════════════════════════════════════════════════════════

def llamar_groq(prompt: str, api_key: str) -> str | None:
    """Llama a la API de Groq (formato OpenAI) y devuelve el texto."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres un analista de seguridad de Ecuador del "
                    "Ministerio del Interior (MDI). Responde SOLO con "
                    "JSON válido, sin texto adicional."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
    }

    for intento in range(MAX_REINTENTOS_GROQ + 1):
        try:
            resp = requests.post(
                GROQ_API_URL, json=payload, headers=headers, timeout=60,
            )
            if resp.status_code == 429:
                espera = 2 ** (intento + 2)
                print(f"   ⏳ Groq rate limit, esperando {espera}s …")
                time.sleep(espera)
                continue
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return None
        except requests.RequestException as e:
            if intento < MAX_REINTENTOS_GROQ:
                print(f"   ⚠️  Error Groq (intento {intento + 1}): {e}")
                time.sleep(2 ** (intento + 1))
            else:
                print(f"   ❌ Error Groq agotado: {e}")
                return None
    return None


def clasificar_noticia(noticia: dict, api_key: str,
                       groq_api_key: str = "") -> dict:
    """Clasifica una noticia: Gemini → Groq → regex."""
    texto = noticia.get("noticia_completa", "")
    if len(texto) > MAX_TEXTO_LLM:
        texto = texto[:MAX_TEXTO_LLM] + " [TRUNCADO]"

    prompt = PROMPT_CLASIFICACION.format(
        titulo=noticia.get("titulo", "Sin título"),
        fuente=noticia.get("fuente", "Desconocida"),
        fecha=noticia.get("fecha_publicacion", "Sin fecha"),
        texto=texto or noticia.get("titulo", ""),
    )

    # ── Intento 1: Gemini ──
    modelo_usado = GEMINI_MODEL
    respuesta = llamar_gemini(prompt, api_key)
    datos = parsear_json_gemini(respuesta)

    # ── Intento 2: Groq (si Gemini falló) ──
    if not datos or "tematica_principal" not in datos:
        if groq_api_key:
            print(f"   ⚠️  Gemini no respondió, intentando Groq …")
            modelo_usado = GROQ_MODEL
            respuesta = llamar_groq(prompt, groq_api_key)
            datos = parsear_json_gemini(respuesta)
        else:
            datos = None

    # ── Intento 3: regex (si ambos LLM fallaron) ──
    if not datos or "tematica_principal" not in datos:
        print(f"   ⚠️  LLMs no devolvieron JSON válido, usando regex")
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

    # prioridad_1: preferir la del LLM; fallback a cálculo local
    prioridad_1_llm = str(datos.get("prioridad_1", "")).upper()
    if prioridad_1_llm in ("ALTA", "MEDIA", "BAJA"):
        prioridad_1 = prioridad_1_llm
    else:
        prioridad_1 = _calcular_prioridad_1(tema_p, entes, cifras)

    return {
        "tematica_principal": tema_p,
        "tematicas_detectadas": temas_det,
        "entes_mencionados": entes,
        "tiene_cifras_comparativas": cifras,
        "detalles_temas": detalles,
        "prioridad": prioridad,
        "prioridad_1": prioridad_1,
        "confianza_clasificacion": "llm",
        "modelo_usado": modelo_usado,
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


def _calcular_prioridad_1(
    tema: str,
    entes: list[str],
    cifras_comparativas: bool,
) -> str:
    """Calcula prioridad_1 (independiente de la prioridad copiada de Captura).

    - ALTA: la noticia tiene al menos una temática de seguridad Y menciona
            algún ente gubernamental de seguridad.
    - MEDIA: la noticia tiene al menos una temática de seguridad Y contiene
             valores comparativos (cifras contrastables con datos MDI).
    - BAJA: todo lo demás.
    """
    es_tema_real = tema in TEMAS and tema != "otros_delitos"

    if es_tema_real and entes:
        return "ALTA"

    if es_tema_real and cifras_comparativas:
        return "MEDIA"

    return "BAJA"


# ═══════════════════════════════════════════════════════════
# DETECCIÓN DE DUPLICADOS
# ═══════════════════════════════════════════════════════════

def detectar_duplicados(
    noticias: list[dict], api_key: str,
    groq_api_key: str = "",
) -> dict[str, dict]:
    """Detecta noticias duplicadas usando Gemini → Groq (batch).

    Returns:
        dict[id_publicacion -> {
            "grupo": "GRUPO-1: evento...",
            "es_principal": True/False,
            "id_principal": "id de la noticia más completa",
        }]
    """
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

    # Fallback a Groq si Gemini no devolvió datos válidos
    if (not datos or "grupos" not in datos) and groq_api_key:
        print(f"   ⚠️  Gemini no respondió para duplicados, intentando Groq …")
        respuesta = llamar_groq(prompt, groq_api_key)
        datos = parsear_json_gemini(respuesta)

    resultado = {}

    if datos and "grupos" in datos:
        grupos = datos["grupos"]
        for gi, grupo in enumerate(grupos, 1):
            ids = grupo.get("ids", [])
            mejor = str(grupo.get("id_mas_completa", ""))
            evento = grupo.get("evento", "")
            etiqueta = f"GRUPO-{gi}"
            if evento:
                etiqueta += f": {evento[:60]}"
            for uid in ids:
                uid_str = str(uid)
                es_principal = uid_str == mejor
                resultado[uid_str] = {
                    "grupo": etiqueta,
                    "es_principal": es_principal,
                    "id_principal": mejor,
                }
        print(f"   ✅ {len(grupos)} grupo(s) de duplicados encontrados")
    else:
        print("   ✅ Sin duplicados detectados")

    return resultado


# ═══════════════════════════════════════════════════════════
# ARMADO DE FILAS DE SALIDA
# ═══════════════════════════════════════════════════════════

def armar_fila(noticia: dict, clasif: dict, dup_info: dict | None) -> dict:
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

    # === Sección VERIFICACIÓN HUMANA DE CATEGORÍAS (vacía, la llena el evaluador) ===
    fila["verificacion_humana_categorias"] = ""

    # === Sección PRIORIDAD_1 ===
    # prioridad_1: determinada por el LLM (tema+ente=ALTA, tema+cifras=MEDIA, resto=BAJA)
    # Distinta de "prioridad" (col F) que se copia de Captura.
    fila["prioridad_1"] = clasif.get("prioridad_1", "BAJA")

    # === Sección DUPLICADOS ===
    if dup_info:
        fila["duplicados_grupo"] = dup_info.get("grupo", "")
        fila["es_noticia_principal"] = "SI" if dup_info.get("es_principal") else "NO"
        fila["duplicado_de_id"] = (
            "" if dup_info.get("es_principal")
            else dup_info.get("id_principal", "")
        )
    else:
        fila["duplicados_grupo"] = ""
        fila["es_noticia_principal"] = ""
        fila["duplicado_de_id"] = ""

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
    groq_api_key = os.environ.get("GROQ_API_KEY", "")
    if not args.solo_regex and not api_key:
        print("❌ Falta variable GEMINI_API_KEY (o usa --solo-regex)")
        sys.exit(1)
    if groq_api_key:
        print("   ✅ Groq configurado como fallback de Gemini")
    else:
        print("   ℹ️  GROQ_API_KEY no configurada — fallback será solo regex")

    # ── Lectura ──
    print("=" * 60)
    print("MDI CLASIFICADOR DE NOTICIAS (cloud)")
    print(f"Fecha: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    modo_txt = "regex" if args.solo_regex else (
        "Gemini → Groq → regex" if groq_api_key else "Gemini → regex"
    )
    print(f"Modo: {modo_txt}")
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
            clasif = clasificar_noticia(noticia, api_key, groq_api_key)
            time.sleep(PAUSA_ENTRE_LLM)

        clasificaciones.append(clasif)
        prior_origen = noticia.get("prioridad_origen", "?")
        print(
            f"           → {clasif['tematica_principal']} "
            f"| p_origen: {prior_origen} | p1: {clasif.get('prioridad_1', '?')} "
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
        duplicados_map = detectar_duplicados(noticias, api_key, groq_api_key)

    # ── Armar filas ──
    print(f"\n📝 Armando {len(noticias)} filas para Sheets …")
    filas = []
    for noticia, clasif in zip(noticias, clasificaciones):
        dup_info = duplicados_map.get(noticia["id_publicacion"])
        fila = armar_fila(noticia, clasif, dup_info)
        filas.append(fila)

    # ── Escribir a Sheets ──
    print(f"\n📤 Escribiendo a hoja '{args.hoja_destino}' …")
    ok = escribir_a_sheets(webapp_url, filas, args.hoja_destino)

    # ── Resumen ──
    conteo_origen = {}
    conteo_p1 = {}
    for fila_r, c in zip(filas, clasificaciones):
        po = fila_r.get("prioridad", "?")
        conteo_origen[po] = conteo_origen.get(po, 0) + 1
        p1 = c.get("prioridad_1", "BAJA")
        conteo_p1[p1] = conteo_p1.get(p1, 0) + 1

    print("\n" + "=" * 60)
    print("RESUMEN")
    print(f"  Total clasificadas: {len(filas)}")
    print("  Prioridad (origen Captura):")
    for p in ["ALTA", "MEDIA", "BAJA"]:
        if p in conteo_origen:
            print(f"    {p}: {conteo_origen[p]}")
    print("  Prioridad_1 (calculada por LLM):")
    for p in ["ALTA", "MEDIA", "BAJA"]:
        if p in conteo_p1:
            print(f"    {p}: {conteo_p1[p]}")
    if duplicados_map:
        grupos = set()
        for v in duplicados_map.values():
            grupos.add(v["grupo"].split(":")[0].strip())
        print(f"  Grupos duplicados: {len(grupos)}")
    print(f"  Escritura a Sheets: {'✅ OK' if ok else '❌ FALLÓ'}")
    print("=" * 60)

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
