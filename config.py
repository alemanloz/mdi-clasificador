"""
Clasificador MDI — Configuración.
Constantes de temáticas, entes, patrones y prompts para clasificación
de noticias de seguridad de Ecuador.
"""

# ═══════════════════════════════════════════════════════════
# TEMAS DE CLASIFICACIÓN — 13 temáticas DEES
# ═══════════════════════════════════════════════════════════
TEMAS = [
    "homicidios_intencionales",
    "toques_de_queda",
    "estados_de_excepcion",
    "robos",
    "narcotrafico",
    "armas_explosivos",
    "femicidio",
    "operativos",
    "demas_detenciones",
    "personas_desaparecidas",
    "trata_de_personas",
    "trafico_ilicito_migrantes",
    "otros_delitos",
]

# ═══════════════════════════════════════════════════════════
# ENTES GUBERNAMENTALES
# ═══════════════════════════════════════════════════════════
ENTES = {
    "Presidencia": ["presidencia", "presidente", "noboa",
                    "decreto ejecutivo", "gobierno nacional"],
    "Ministerio del Interior": ["ministerio del interior",
                                "ministro del interior", "reimberg"],
    "Policía Nacional": ["policía nacional", "policía",
                         "comandante general"],
    "Ministerio de Defensa Nacional": ["ministerio de defensa nacional",
                                       "fuerzas armadas", "ejército",
                                       "comando conjunto"],
    "SNAI": ["snai", "cárceles", "penitenciaría",
             "rehabilitación social"],
    "ECU 911": ["ecu 911", "ecu911"],
}

# ═══════════════════════════════════════════════════════════
# PATRONES REGEX POR TEMA (fallback sin LLM)
# ═══════════════════════════════════════════════════════════
PATRONES_TEMAS = {
    "homicidios_intencionales": [
        r"homicidio", r"asesinato", r"sicariato",
        r"muerte\s+violent", r"crimen", r"ultimado",
    ],
    "toques_de_queda": [
        r"toque\s+de\s+queda", r"restricci[oó]n\s+de\s+movilidad",
    ],
    "estados_de_excepcion": [
        r"estado\s+de\s+excepci[oó]n", r"decreto\s+de\s+emergencia",
        r"conflicto\s+armado\s+interno",
    ],
    "robos": [r"\brobo", r"asalto", r"atraco", r"extorsi[oó]n", r"hurto"],
    "narcotrafico": [
        r"narcotr[aá]fico", r"droga", r"coca[ií]na",
        r"alcaloide", r"narcomenudeo",
    ],
    "armas_explosivos": [
        r"arma", r"municion", r"explosivo", r"granada",
        r"fusil", r"decomis.*arma",
    ],
    "femicidio": [
        r"femicidio", r"feminicidio", r"violencia\s+de\s+g[eé]nero",
    ],
    "operativos": [
        r"operativo", r"intervenci[oó]n\s+policial",
        r"allanamiento", r"megaoperativo",
    ],
    "demas_detenciones": [
        r"detenid[oa]", r"aprehendid[oa]",
        r"capturad[oa]", r"arrestad[oa]",
    ],
    "personas_desaparecidas": [
        r"desaparecid[oa]", r"persona\s+desaparecida",
    ],
    "trata_de_personas": [
        r"trata\s+de\s+personas", r"explotaci[oó]n\s+sexual",
    ],
    "trafico_ilicito_migrantes": [
        r"tr[aá]fico\s+il[ií]cito\s+de\s+migrantes", r"coyoter",
    ],
    "otros_delitos": [
        r"crimen\s+organizado", r"banda\s+delictiva",
        r"lavado\s+de\s+activos",
    ],
}

PATRON_CIFRAS = (
    r"(\d[\d\.,]*)\s*(por\s*ciento|%|personas?|casos?|muertos?|"
    r"detenidos?|toneladas?|kilos?|armas?)"
)

# ═══════════════════════════════════════════════════════════
# PRE-FILTRO DE LECTURA — Columna de prioridad en hoja origen
# ═══════════════════════════════════════════════════════════
# Nombre de la columna en la hoja Captura que contiene la
# prioridad asignada por el monitor.  Si la columna cambia de
# nombre en Sheets, basta actualizar aquí (los valores ALTA,
# MEDIA, BAJA se mantienen).
COL_PRIORIDAD_ORIGEN = "prioridad"

# Prioridades que el clasificador debe procesar.
# Noticias cuya prioridad de origen NO esté en esta lista
# se descartan ANTES de la clasificación (ahorra llamadas LLM).
PRIORIDADES_PERMITIDAS = ["ALTA", "MEDIA"]

# ═══════════════════════════════════════════════════════════
# PRIORIZACIÓN (cálculo interno del clasificador)
# ═══════════════════════════════════════════════════════════
ENTES_PRIORIZACION_ALTA = [
    "Presidencia",
    "Ministerio del Interior",
    "Policía Nacional",
]

PALABRAS_ENTES_ALTA = []
for _e in ENTES_PRIORIZACION_ALTA:
    PALABRAS_ENTES_ALTA.extend(ENTES[_e])

PATRONES_VALORES_COMPARATIVOS = [
    r'\d+\s*(%|por\s*ciento)',
    r'\d+\s*(casos?|muertos?|detenidos?|personas?|víctimas?|toneladas?|kilos?'
    r'|armas?|homicidios?|robos?|femicidios?|heridos?|procesados?)',
    r'(aumentó?|disminuyó?|creció?|bajó?|subió?|redujo?|incrementó?)\s*(en\s+)?\d+',
    r'(comparad[oa]|respecto\s+(a|al)|en\s+relación\s+(con|a)|frente\s+a|versus|vs\.?)',
    r'(año|mes|semana|trimestre|semestre|periodo)\s+(anterior|pasad[oa]|previo)',
    r'(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|'
    r'noviembre|diciembre)\s+de\s+20\d{2}',
    r'20\d{2}\s*[-–]\s*20\d{2}',
    r'(tasa|índice|indicador|estadística)\s+de',
    r'\d+\s*de\s+cada\s+\d+',
]

# ═══════════════════════════════════════════════════════════
# COLUMNAS DE SALIDA — Hoja "Validación"
# ═══════════════════════════════════════════════════════════
COLS_DATOS = [
    "id_publicacion", "fecha_publicacion", "fuente", "titulo", "url",
    "prioridad", "texto_publicacion", "noticia_completa",
]

_COLS_TEMAS = []
for _t in TEMAS:
    _COLS_TEMAS.extend([f"tema_{_t}", f"{_t}_valor", f"{_t}_tipo_valor"])

COLS_CLASIFICACION = (
    ["tematica_principal", "tematicas_detectadas"]
    + _COLS_TEMAS
    + ["entes_mencionados", "tiene_cifras_comparativas",
       "confianza_clasificacion", "modelo_usado", "fecha_clasificacion"]
)

COLS_DUPLICADOS = ["duplicados_grupo"]

COLS_VALIDACION = [
    "nombre_revisor", "aprobacion_tematica", "tematica_corregida_humana",
    "valor_real_bd_mdi", "fuente_dato_bd", "fecha_consulta_bd",
    "resultado_contraste", "observacion_evaluador", "fecha_validacion",
]

COLS_ESTATUS = ["estatus_notificacion"]

TODAS_COLUMNAS = (
    COLS_DATOS + COLS_CLASIFICACION + COLS_DUPLICADOS
    + COLS_VALIDACION + COLS_ESTATUS
)

# ═══════════════════════════════════════════════════════════
# GEMINI
# ═══════════════════════════════════════════════════════════
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/{model}:generateContent?key={api_key}"
)

# ═══════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════

PROMPT_CLASIFICACION = """Eres un analista de seguridad de Ecuador del Ministerio del Interior (MDI).
Clasifica esta noticia y devuelve SOLO un JSON válido.

TÍTULO: {titulo}
FUENTE: {fuente}
FECHA: {fecha}
TEXTO:
{texto}

Temáticas de seguridad (datos abiertos MDI/DEES): homicidios_intencionales, toques_de_queda,
estados_de_excepcion, robos, narcotrafico, armas_explosivos, femicidio, operativos,
demas_detenciones, personas_desaparecidas, trata_de_personas, trafico_ilicito_migrantes, otros_delitos.

Responde EXACTAMENTE con este formato JSON (sin texto adicional):
{{
  "tematica_principal": "<uno de las 13 temáticas>",
  "tematicas_detectadas": ["tema1", "tema2"],
  "entes_mencionados": ["ente1", "ente2"],
  "tiene_cifras_comparativas": true/false,
  "homicidios_intencionales": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}},
  "toques_de_queda": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}},
  "estados_de_excepcion": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}},
  "robos": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}},
  "narcotrafico": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}},
  "armas_explosivos": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}},
  "femicidio": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}},
  "operativos": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}},
  "demas_detenciones": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}},
  "personas_desaparecidas": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}},
  "trata_de_personas": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}},
  "trafico_ilicito_migrantes": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}},
  "otros_delitos": {{"detectado": "SI/NO", "valor": null, "tipo_valor": null}}
}}

Si hay cifras, pon "valor": <número> y "tipo_valor": "absoluto" o "porcentaje" o "tasa".
En "entes_mencionados" lista SOLO nombres de instituciones que aparecen explícitamente."""


PROMPT_DUPLICADOS = """Eres un analista del Ministerio del Interior de Ecuador.
Analiza las siguientes noticias e identifica cuáles se refieren al MISMO evento o hecho
noticioso específico, incluso si son de fuentes distintas o con títulos diferentes.

NOTICIAS:
{lista_noticias}

REGLAS:
- Solo agrupa noticias que claramente se refieren al MISMO evento específico
  (ej. "operativo en barrio X el día Y" de distintas fuentes).
- NO agrupar noticias sobre el mismo TEMA general pero eventos distintos
  (ej. dos robos diferentes en Guayaquil son eventos separados).
- Para cada grupo, identifica cuál noticia es la MÁS COMPLETA
  (la que tiene más detalles, datos concretos y contexto).
- Si una noticia es única (sin duplicados), NO la incluyas en ningún grupo.

Responde SOLO con JSON válido:
{{
  "grupos": [
    {{
      "ids": ["id1", "id2"],
      "id_mas_completa": "id2",
      "evento": "descripción breve del evento común"
    }}
  ]
}}

Si NO hay noticias duplicadas, responde: {{"grupos": []}}"""


# ═══════════════════════════════════════════════════════════
# LÍMITES
# ═══════════════════════════════════════════════════════════
MAX_TEXTO_LLM = 8000
PAUSA_ENTRE_LLM = 4         # segundos entre llamadas a Gemini
MAX_REINTENTOS = 2
MAX_REGISTROS_POR_ENVIO = 25  # filas por POST al Web App

