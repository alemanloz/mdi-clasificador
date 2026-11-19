"""
Monitor MDI v4 — Configuración.
Reconstruido desde la base funcional, capa por capa.
"""

# ═══════════════════════════════════════════════════════════
# GOOGLE NEWS RSS
# ═══════════════════════════════════════════════════════════
RSS_BASE = "https://news.google.com/rss/search?q={query}&hl=es-419&gl=EC&ceid=EC:es-419"

# Sintaxis Google News RSS:
#   - Sin operadores → AND implícito (TODAS las palabras deben aparecer)
#   - OR            → cualquiera de los términos
#   - "comillas"    → frase exacta
#   - (paréntesis)  → agrupar alternativas con OR
#   - site:dominio  → restringe resultados a un dominio específico
#
# ⚠️ IMPORTANTE: gl=EC y ceid=EC:es-419 son SESGO geográfico, NO filtro estricto.
#    Sin "Ecuador" explícito, las queries genéricas (homicidio, robo, narcotráfico)
#    devuelven noticias de México, Colombia, Perú y otros países hispanohablantes.
#    "Ecuador" es OBLIGATORIO en toda query temática.
BUSQUEDAS_RSS = [
    # ═══ POR ENTE GUBERNAMENTAL ═══
    # Incluyen "Ecuador" para evitar confusión con instituciones homónimas
    # de otros países (ej. "Policía Nacional" existe en Colombia, Perú, etc.)
    '"ministerio del interior" Ecuador (seguridad OR cifras OR operativo)',
    '"Policía Nacional" Ecuador (operativo OR detenidos OR cifras)',
    '"Daniel Noboa" (seguridad OR decreto OR emergencia)',
    '"John Reimberg"',
    '"fiscalía general" Ecuador (detenidos OR investigación OR procesados)',
    '"fuerzas armadas" Ecuador (operativo OR decomiso OR patrullaje)',
    '"ministerio de defensa" Ecuador (seguridad OR operativo)',
    'SNAI Ecuador (cárceles OR amotinamiento OR penitenciaría)',
    '"ECU 911" (emergencia OR alerta OR rescate)',

    # ═══ POR TEMÁTICA DE SEGURIDAD ═══
    # "Ecuador" al inicio + paréntesis para OR → fuerza geo-filtro real.
    # Google interpreta:  Ecuador (A OR B) = Ecuador AND (A OR B)
    'Ecuador (homicidio OR asesinato OR sicariato OR "muertes violentas")',
    'Ecuador (femicidio OR feminicidio OR "violencia de género")',
    'Ecuador ("toque de queda" OR "restricción de movilidad")',
    'Ecuador ("estado de excepción" OR "conflicto armado interno")',
    'Ecuador (narcotráfico OR "decomiso de droga" OR "cocaína incautada")',
    'Ecuador ("armas decomisadas" OR explosivos OR granada)',
    'Ecuador (robo OR asalto OR atraco OR extorsión)',
    'Ecuador (secuestro OR "privación de libertad")',
    'Ecuador ("operativo policial" OR allanamiento OR megaoperativo)',
    'Ecuador (detenidos OR aprehendidos OR capturados)',
    'Ecuador "personas desaparecidas"',
    'Ecuador ("trata de personas" OR "explotación sexual")',
    'Ecuador ("tráfico ilícito de migrantes" OR coyotero)',
    'Ecuador ("crimen organizado" OR "banda delictiva" OR "lavado de activos")',

    # ═══ CIFRAS Y ESTADÍSTICAS ═══
    'Ecuador ("cifras de seguridad" OR "estadísticas de delitos")',
    'Ecuador ("informe de seguridad" OR "reporte de seguridad")',

    # ═══ FUENTES ECUATORIANAS DIRECTAS ═══
    # site: restringe a dominio específico → garantiza artículos de medios ecuatorianos
    # que el scraping de portales podría no capturar (si cambian su HTML).
    'site:primicias.ec seguridad',
    'site:eluniverso.com seguridad',
    'site:elcomercio.com seguridad Ecuador',
    'site:teleamazonas.com seguridad',

    # ═══ REDES SOCIALES (noticias que citan publicaciones oficiales en X) ═══
    '"@PoliciaEcuador"',
    '"@MinInteriorEc"',
    '"@Presidencia_Ec" (seguridad OR decreto)',
    '"@DanielNoboaOk" seguridad',
]

# ═══════════════════════════════════════════════════════════
# FEEDS RSS INSTITUCIONALES + MEDIOS (directos)
# ═══════════════════════════════════════════════════════════
# Los feeds RSS son MÁS CONFIABLES que el scraping de portales porque
# son datos estructurados (XML) que no dependen de selectores CSS.
# Si un feed no existe o falla, simplemente no devuelve artículos (sin error).
FEEDS_INSTITUCIONALES = [
    # ── Instituciones gubernamentales ──
    {
        "nombre": "Min. Interior",
        "url": "https://www.ministeriodelinterior.gob.ec/feed/",
        "grupo": "Ministerio del Interior",
    },
    {
        "nombre": "Policía Nacional",
        "url": "https://www.policia.gob.ec/feed/",
        "grupo": "Policía Nacional",
    },
    {
        "nombre": "Presidencia",
        "url": "https://www.presidencia.gob.ec/feed/",
        "grupo": "Presidencia",
    },
    # ── Medios ecuatorianos — secciones de seguridad ──
    # Complementan el scraping de PORTALES_NOTICIAS como respaldo.
    # Solo se incluyen feeds RSS CONFIRMADOS como funcionales.
    {
        "nombre": "Primicias Seguridad",
        "url": "https://www.primicias.ec/noticias/seguridad/feed/",
        "grupo": "Medios",
    },
    {
        "nombre": "El Comercio Seguridad",
        # ✅ URL corregida — la anterior (/actualidad/seguridad/feed/) no existía.
        # El Comercio usa /categoria/actualidad/seguridad/ como sección real.
        "url": "https://www.elcomercio.com/categoria/actualidad/seguridad/feed/",
        "grupo": "Medios",
    },
    # ❌ REMOVIDOS (sin feed RSS funcional):
    # - Teleamazonas: /etiqueta/seguridad/feed/ bloqueado por robots.txt; /feed/ retorna 4xx
    # - Expreso: no tiene sección "seguridad"; usa Arc Publishing sin RSS público
    # - Ecuavisa: robots.txt bloquea scraping; no tiene sección de seguridad estándar
    # → Estos medios SÍ se capturan vía las queries site: en BUSQUEDAS_RSS
]

# ═══════════════════════════════════════════════════════════
# PORTALES DE NOTICIAS — secciones de seguridad
# ═══════════════════════════════════════════════════════════
PORTALES_NOTICIAS = [
    # ✅ VALIDADO — página funcional con artículos recientes de seguridad
    {
        "nombre": "Primicias",
        "url": "https://www.primicias.ec/noticias/seguridad/",
        "selector": "article a, .card a, .story a",
        "dominio": "primicias.ec",
    },
    # ✅ VALIDADO — página funcional con artículos recientes de seguridad
    {
        "nombre": "El Universo",
        "url": "https://www.eluniverso.com/noticias/seguridad/",
        "selector": "article a, .card a, .story-card a",
        "dominio": "eluniverso.com",
    },
    # ✅ CORREGIDO — la URL anterior (/actualidad/seguridad/) era una nota individual,
    # no la sección. La sección real está en /categoria/actualidad/seguridad/
    {
        "nombre": "El Comercio",
        "url": "https://www.elcomercio.com/categoria/actualidad/seguridad/",
        "selector": "article a, .card a",
        "dominio": "elcomercio.com",
    },
    # ✅ CORREGIDO — la URL anterior (/category/seguridad/) devolvía 404.
    # Teleamazonas usa /etiqueta/ en lugar de /category/ para sus tags.
    {
        "nombre": "Teleamazonas",
        "url": "https://www.teleamazonas.com/etiqueta/seguridad/",
        "selector": "article a, .post a, .entry a",
        "dominio": "teleamazonas.com",
    },
    # ✅ CORREGIDO — Expreso NO tiene sección "seguridad". La sección más cercana
    # con contenido de delitos, juicios y seguridad es /justicia/.
    {
        "nombre": "Expreso",
        "url": "https://www.expreso.ec/justicia/",
        "selector": "article a, .card a",
        "dominio": "expreso.ec",
    },
    # ❌ REMOVIDO: Ecuavisa
    # - No tiene sección /noticias/seguridad (la URL no existe)
    # - Usa estructura /metadatos/-/meta/<tag> con tags dispersos (criminalidad,
    #   terrorismo-ecuador, fuerzas-armadas, etc.) — no hay una sección unificada
    # - robots.txt bloquea scraping de las páginas de metadatos
    # → Ecuavisa SÍ se captura mediante las queries site: y temáticas en BUSQUEDAS_RSS
]

# ═══════════════════════════════════════════════════════════
# CUENTAS X/TWITTER — redes sociales oficiales
# ═══════════════════════════════════════════════════════════
CUENTAS_X = [
    {"handle": "Presidencia_Ec", "grupo": "Presidencia", "nombre": "Presidencia EC"},
    {"handle": "DanielNoboaOk", "grupo": "Presidencia", "nombre": "Daniel Noboa"},
    {"handle": "MinInteriorEc", "grupo": "Ministerio del Interior", "nombre": "Min. Interior"},
    {"handle": "JohnReimberg", "grupo": "Ministerio del Interior", "nombre": "John Reimberg"},
    {"handle": "PoliciaEcuador", "grupo": "Policía Nacional", "nombre": "Policía Nacional"},
    {"handle": "ComunicacionEc", "grupo": "Presidencia", "nombre": "Comunicación EC"},
    {"handle": "SNAI_Ec", "grupo": "SNAI", "nombre": "SNAI"},
    {"handle": "ECU911_", "grupo": "ECU 911", "nombre": "ECU 911"},
    {"handle": "LupaMediaEC", "grupo": "Medios", "nombre": "Lupa Media EC"},
]

# Puentes RSS para X/Twitter (costo cero, orden de prioridad)
# RSSHub: open-source, genera RSS desde redes sociales — rsshub.app es instancia pública gratuita
# Nitter: frontend alternativo de X con feeds RSS — instancias frágiles pero funcionales
RSSHUB_INSTANCES = [
    "https://rsshub.app",
]

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://xcancel.com",
    "https://nitter.poast.org",
]

# ═══════════════════════════════════════════════════════════
# ENTES MONITOREADOS
# ═══════════════════════════════════════════════════════════
ENTES = {
    "Presidencia": ["presidencia", "presidente", "noboa", "decreto ejecutivo", "gobierno nacional"],
    "Ministerio del Interior": ["ministerio del interior", "ministro del interior", "reimberg"],
    "Policía Nacional": ["policía nacional", "policía", "comandante general"],
    "Ministerio de Defensa Nacional": ["ministerio de defensa nacional", "fuerzas armadas", "ejército", "comando conjunto"],
    "SNAI": ["snai", "cárceles", "penitenciaría", "rehabilitación social"],
    "ECU 911": ["ecu 911", "ecu911"],
}

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

# Patrones regex por tema (fallback sin LLM)
PATRONES_TEMAS = {
    "homicidios_intencionales": [
        r"homicidio", r"asesinato", r"sicariato", r"muerte\s+violent",
        r"crimen", r"ultimado",
    ],
    "toques_de_queda": [
        r"toque\s+de\s+queda", r"restricci[oó]n\s+de\s+movilidad",
    ],
    "estados_de_excepcion": [
        r"estado\s+de\s+excepci[oó]n", r"decreto\s+de\s+emergencia",
        r"conflicto\s+armado\s+interno",
    ],
    "robos": [
        r"\brobo", r"asalto", r"atraco", r"extorsi[oó]n", r"hurto",
    ],
    "narcotrafico": [
        r"narcotr[aá]fico", r"droga", r"coca[ií]na", r"alcaloide",
        r"narcomenudeo",
    ],
    "armas_explosivos": [
        r"arma", r"municion", r"explosivo", r"granada", r"fusil",
        r"decomis.*arma",
    ],
    "femicidio": [
        r"femicidio", r"feminicidio", r"violencia\s+de\s+g[eé]nero",
    ],
    "operativos": [
        r"operativo", r"intervenci[oó]n\s+policial", r"allanamiento",
        r"megaoperativo",
    ],
    "demas_detenciones": [
        r"detenid[oa]", r"aprehendid[oa]", r"capturad[oa]", r"arrestad[oa]",
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
        r"crimen\s+organizado", r"banda\s+delictiva", r"lavado\s+de\s+activos",
    ],
}

PATRON_CIFRAS = r"(\d[\d\.,]*)\s*(por\s*ciento|%|personas?|casos?|muertos?|detenidos?|toneladas?|kilos?|armas?)"

# ═══════════════════════════════════════════════════════════
# PRIORIZACIÓN — Criterios de clasificación
# ═══════════════════════════════════════════════════════════
# ALTA:  cualquier temática de seguridad + mención de ente clave
#        (Presidente, Ministro del Interior, Comandante de Policía Nacional)
# MEDIA: cualquier temática de seguridad + valores numéricos comparativos
#        (cifras, porcentajes, temporalidad contrastable con datos MDI)
# BAJA:  todo lo demás (no cumple ALTA ni MEDIA)

ENTES_PRIORIZACION_ALTA = [
    "Presidencia",
    "Ministerio del Interior",
    "Policía Nacional",
]

# Palabras clave combinadas de los 3 entes de prioridad ALTA
PALABRAS_ENTES_ALTA = []
for _ente_alta in ENTES_PRIORIZACION_ALTA:
    PALABRAS_ENTES_ALTA.extend(ENTES[_ente_alta])

# Patrones regex para detectar valores comparativos (prioridad MEDIA).
# Si la noticia trata un tema de seguridad Y contiene cifras/temporalidad
# que se pueden contrastar con los datos abiertos del MDI → MEDIA.
PATRONES_VALORES_COMPARATIVOS = [
    # Cifras con unidades
    r'\d+\s*(%|por\s*ciento)',
    r'\d+\s*(casos?|muertos?|detenidos?|personas?|víctimas?|toneladas?|kilos?'
    r'|armas?|homicidios?|robos?|femicidios?|heridos?|procesados?)',
    # Cambios numéricos
    r'(aumentó?|disminuyó?|creció?|bajó?|subió?|redujo?|incrementó?)\s*(en\s+)?\d+',
    # Comparaciones explícitas
    r'(comparad[oa]|respecto\s+(a|al)|en\s+relación\s+(con|a)|frente\s+a|versus|vs\.?)',
    # Temporalidad comparativa
    r'(año|mes|semana|trimestre|semestre|periodo)\s+(anterior|pasad[oa]|previo)',
    # Fechas específicas (meses con año)
    r'(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+de\s+20\d{2}',
    # Rangos de años
    r'20\d{2}\s*[-–]\s*20\d{2}',
    # Indicadores estadísticos
    r'(tasa|índice|indicador|estadística)\s+de',
    # Proporciones
    r'\d+\s*de\s+cada\s+\d+',
]

# ═══════════════════════════════════════════════════════════
# COLUMNAS — Hoja "Captura" (22 columnas)
# ═══════════════════════════════════════════════════════════
COLUMNAS_CAPTURA = [
    "id", "fecha_publicacion", "hora_publicacion", "franja_horaria",
    "zona_horaria", "fuente", "grupo", "titulo", "url",
    "fecha_descubrimiento", "precision_fecha", "relevante",
    "numero_afirmaciones", "estado_extraccion", "metodo_descubrimiento",
    "tipo_texto", "longitud_texto", "texto_publicacion",
    "autor", "dominio", "error_extraccion", "intentos_extraccion",
]

# ═══════════════════════════════════════════════════════════
# COLUMNAS — Hoja "Clasificación" (59 columnas)
# ═══════════════════════════════════════════════════════════
_BASE_CLAS = [
    "id_publicacion", "fecha_publicacion", "fuente", "titulo", "url",
    "noticia_completa", "tematica_principal", "tematicas_detectadas", "prioridad",
]
_TEMA_COLS = []
for _t in TEMAS:
    _TEMA_COLS.extend([f"tema_{_t}", f"{_t}_valor", f"{_t}_tipo_valor"])

_META_COLS = ["confianza_clasificacion", "modelo_usado", "fecha_clasificacion",
              "metodo_clasificacion"]
_VALIDACION_COLS = ["aprobacion_humana", "tematica_validada_humana", "valor_real_bd",
                    "resultado_contraste", "nombre_revisor", "observacion_humana",
                    "fecha_validacion"]

COLUMNAS_CLASIFICACION = _BASE_CLAS + _TEMA_COLS + _META_COLS + _VALIDACION_COLS

# ═══════════════════════════════════════════════════════════
# PROMPT PARA GEMINI
# ═══════════════════════════════════════════════════════════
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

PROMPT_CLASIFICACION = """Eres un analista de seguridad de Ecuador del Ministerio del Interior (MDI). Analiza esta noticia y devuelve SOLO un JSON válido.

TÍTULO: {titulo}
FUENTE: {fuente}
FECHA: {fecha}
TEXTO:
{texto}

CRITERIOS DE PRIORIDAD (aplícalos estrictamente):
- ALTA: La noticia trata CUALQUIER temática de seguridad (ver lista abajo) Y además menciona
  a alguno de estos entes clave: Presidente/Presidencia/Noboa, Ministro o Ministerio del Interior,
  Policía Nacional/Comandante General. Es decir: tema + ente = ALTA.
- MEDIA: La noticia trata CUALQUIER temática de seguridad Y además contiene valores numéricos
  comparativos: cifras absolutas, porcentajes, tasas, o referencias temporales (año anterior,
  trimestre pasado, fechas específicas) que podrían contrastarse con datos oficiales del MDI.
  Es decir: tema + cifras/temporalidad comparativa = MEDIA.
- BAJA: Todo lo que NO cumple criterios de ALTA ni de MEDIA.
  Nota: si cumple ALTA y MEDIA simultáneamente, prioridad = ALTA.

Temáticas de seguridad (datos abiertos MDI/DEES): homicidios_intencionales, toques_de_queda,
estados_de_excepcion, robos, narcotrafico, armas_explosivos, femicidio, operativos,
demas_detenciones, personas_desaparecidas, trata_de_personas, trafico_ilicito_migrantes, otros_delitos.

Responde EXACTAMENTE con este formato JSON (sin texto adicional):
{{
  "tematica_principal": "<uno de las 13 temáticas listadas arriba>",
  "tematicas_detectadas": ["tema1", "tema2"],
  "prioridad": "<ALTA, MEDIA o BAJA>",
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
En "entes_mencionados" lista los nombres de los entes que aparecen en la noticia.
"""

# ═══════════════════════════════════════════════════════════
# HEADERS HTTP
# ═══════════════════════════════════════════════════════════
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# ═══════════════════════════════════════════════════════════
# LÍMITES TÉCNICOS
# ═══════════════════════════════════════════════════════════
MAX_REINTENTOS = 2
TIMEOUT_SEGUNDOS = 20
PAUSA_ENTRE_REQUESTS = 1.0
PAUSA_ENTRE_LLM = 4
MAX_TEXTO_CARACTERES = 50000
MAX_TEXTO_LLM = 8000
MAX_ARTICULOS_EXTRACCION = 80   # máximo de artículos a extraer texto completo
MAX_ARTICULOS_LLM = 50
MAX_REGISTROS_POR_ENVIO = 25
