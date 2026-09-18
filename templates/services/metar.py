import requests

API = "https://aviationweather.gov/api/data"

def metar(icao):
    try:
        r = requests.get(f"{API}/metar",
                         params={"ids": icao, "format": "json"}, timeout=15)
        if not r.text.strip():          # resposta vazia
            return None
        dados = r.json()
        return dados[0] if dados else None
    except Exception:
        return None

def taf(icao):
    try:
        r = requests.get(f"{API}/taf",
                         params={"ids": icao, "format": "json"}, timeout=15)
        if not r.text.strip():
            return None
        dados = r.json()
        return dados[0] if dados else None
    except Exception:
        return None


# ---------- Tabelas de tradução ----------
NUVENS = {"FEW": "Poucas nuvens (1-2/8)", "SCT": "Nuvens esparsas (3-4/8)",
          "BKN": "Nublado (5-7/8)", "OVC": "Encoberto (8/8)",
          "CLR": "Céu limpo", "SKC": "Céu limpo", "NSC": "Sem nuvens significativas",
          "NCD": "Sem nuvens detectadas", "VV": "Céu obscurecido (visibilidade vertical)"}

TIPO_NUVEM = {"CB": "Cumulonimbus (tempestade)", "TCU": "Torre cumulus (crescimento vertical)"}

DESCRITOR = {"MI": "raso", "PR": "parcial", "BC": "bancos", "DR": "baixo (arrastando)",
             "BL": "soprando", "SH": "pancadas de", "TS": "trovoada com", "FZ": "congelante"}

FENOMENO = {
    "DZ": "chuvisco", "RA": "chuva", "SN": "neve", "SG": "grãos de neve",
    "IC": "cristais de gelo", "PL": "pelotas de gelo", "GR": "granizo",
    "GS": "granizo pequeno/neve granular", "UP": "precipitação desconhecida",
    "BR": "névoa úmida", "FG": "nevoeiro", "FU": "fumaça", "VA": "cinza vulcânica",
    "DU": "poeira generalizada", "SA": "areia", "HZ": "névoa seca (haze)",
    "PY": "borrifo", "PO": "redemoinhos de poeira/areia", "SQ": "rajada (squall)",
    "FC": "nuvem funil / tornado", "SS": "tempestade de areia", "DS": "tempestade de poeira",
}

# ícone + cor por fenômeno (chave = código base)
ESTILO_FENOMENO = {
    "TS": ("⛈️", "#c0392b"),   # trovoada - vermelho
    "RA": ("🌧️", "#2980b9"),   # chuva - azul
    "DZ": ("🌦️", "#5dade2"),   # chuvisco
    "SN": ("❄️", "#5dade2"),   # neve
    "GR": ("🧊", "#c0392b"),   # granizo - vermelho
    "GS": ("🧊", "#e67e22"),
    "FG": ("🌫️", "#7f8c8d"),   # nevoeiro - cinza
    "BR": ("🌫️", "#95a5a6"),   # névoa úmida
    "HZ": ("🌫️", "#95a5a6"),
    "FU": ("💨", "#7f8c8d"),
    "FC": ("🌪️", "#c0392b"),   # tornado - vermelho
    "SQ": ("💨", "#e67e22"),
    "SS": ("🏜️", "#e67e22"),
    "DS": ("🏜️", "#e67e22"),
}

def _traduzir_fenomeno(token):
    """Retorna dict {texto, icone, cor} ou None."""
    partes = []
    if token.startswith("+"):
        partes.append("forte"); token = token[1:]
    elif token.startswith("-"):
        partes.append("fraca"); token = token[1:]
    elif token.startswith("VC"):
        partes.append("nas proximidades"); token = token[2:]

    descritores, fenomenos, codigos = [], [], []
    i = 0
    while i < len(token):
        par = token[i:i+2]
        if par in DESCRITOR:
            descritores.append(DESCRITOR[par]); codigos.append(par)
        elif par in FENOMENO:
            fenomenos.append(FENOMENO[par]); codigos.append(par)
        else:
            return None
        i += 2

    if not fenomenos and not descritores:
        return None

    texto = " ".join(descritores + fenomenos)
    if partes:
        texto = f"{texto} ({', '.join(partes)})"

    # escolhe ícone/cor: prioriza trovoada, depois o primeiro código conhecido
    icone, cor = "🌡️", "#34495e"
    for cod in codigos:
        if cod in ESTILO_FENOMENO:
            icone, cor = ESTILO_FENOMENO[cod]
            if cod == "TS":       # trovoada tem prioridade máxima
                break
    return {"texto": f"Fenômeno: {texto}", "icone": icone, "cor": cor}


def _linha(texto, icone="ℹ️", cor="#34495e"):
    return {"texto": texto, "icone": icone, "cor": cor}


def decodificar(raw):
    if not raw:
        return []
    linhas = []
    partes = raw.replace("=", "").split()

    for p in partes:
        if not linhas and len(p) == 4 and p.isalpha():
            linhas.append(_linha(f"Estação: {p}", "📍", "#34495e"))
        elif p.endswith("Z") and len(p) == 7 and p[:6].isdigit():
            linhas.append(_linha(f"Observação: dia {p[:2]}, {p[2:4]}:{p[4:6]} UTC", "🕒", "#34495e"))
        elif p.endswith("KT") and len(p) >= 7:
            direcao, veloc = p[:3], p[3:5]
            dir_txt = "variável" if direcao == "VRB" else f"{direcao}°"
            extra = ""
            cor = "#16a085"
            if "G" in p:
                rajada = p[p.index("G")+1:p.index("KT")]
                extra = f", rajadas de {rajada} nós"
                cor = "#e67e22"   # rajada = laranja (atenção)
            linhas.append(_linha(f"Vento: {dir_txt} a {int(veloc)} nós{extra}", "💨", cor))
        elif len(p) == 7 and p[3] == "V" and p.replace("V", "").isdigit():
            linhas.append(_linha(f"Direção do vento variando entre {p[:3]}° e {p[4:]}°", "🧭", "#16a085"))
        elif "/" in p and (p[0].isdigit() or p[0] == "M") and len(p) <= 7:
            try:
                t, d = p.split("/")
                conv = lambda x: f"-{x[1:]}" if x.startswith("M") else x
                linhas.append(_linha(f"Temperatura: {conv(t)}°C | Ponto de orvalho: {conv(d)}°C", "🌡️", "#e67e22"))
            except ValueError:
                pass
        elif p.startswith("Q") and p[1:].isdigit():
            linhas.append(_linha(f"Pressão (QNH): {p[1:]} hPa", "📊", "#8e44ad"))
        elif p.startswith("A") and p[1:].isdigit() and len(p) == 5:
            linhas.append(_linha(f"Pressão: {p[1:3]}.{p[3:]} inHg", "📊", "#8e44ad"))
        elif p == "CAVOK":
            linhas.append(_linha("CAVOK: visibilidade ≥10 km, sem nuvens baixas nem tempo significativo", "☀️", "#27ae60"))
        elif p == "NOSIG":
            linhas.append(_linha("NOSIG: sem mudança significativa prevista", "✅", "#27ae60"))
        elif p[:3] in NUVENS and p[:2] != "VV":
            alt = p[3:6]
            base = f" a {int(alt)*100} pés" if alt.isdigit() else ""
            tipo, cor, icone = "", "#2980b9", "☁️"
            for cod, nome in TIPO_NUVEM.items():
                if p.endswith(cod):
                    tipo = f" — {nome}"
                    cor, icone = "#c0392b", "⛈️"   # CB/TCU = vermelho
            linhas.append(_linha(f"{NUVENS[p[:3]]}{base}{tipo}", icone, cor))
        elif p.startswith("VV"):
            alt = p[2:]
            base = f" a {int(alt)*100} pés" if alt.isdigit() else ""
            linhas.append(_linha(f"Céu obscurecido{base}", "🌫️", "#7f8c8d"))
        elif p.isdigit() and len(p) == 4:
            vis = "10 km ou mais" if p == "9999" else f"{int(p)} metros"
            cor = "#27ae60" if p == "9999" or int(p) >= 5000 else "#e67e22"
            linhas.append(_linha(f"Visibilidade: {vis}", "👁️", cor))
        elif p.endswith("SM"):
            linhas.append(_linha(f"Visibilidade: {p.replace('SM','')} milhas terrestres", "👁️", "#27ae60"))
        else:
            f = _traduzir_fenomeno(p)
            if f:
                linhas.append(f)

    return linhas

def resumo(raw):
    """Analisa o METAR e retorna um badge {texto, cor, icone} de severidade."""
    if not raw:
        return None
    txt = raw.upper()

    # --- ADVERSAS (vermelho): trovoada, granizo, tornado, tempestade de areia ---
    graves = ["TS", "GR", "FC", "SS", "DS", "+SN", "VA"]
    if any(g in txt for g in graves):
        return {"texto": "CONDIÇÕES ADVERSAS", "cor": "#c0392b", "icone": "⛈️"}

    # --- ATENÇÃO (laranja): chuva forte, nevoeiro, baixa visibilidade, rajadas ---
    partes = txt.split()
    baixa_vis = any(p.isdigit() and len(p) == 4 and int(p) < 5000 for p in partes)
    rajada = any("G" in p and p.endswith("KT") for p in partes)
    if "+RA" in txt or "FG" in txt or "SH" in txt or baixa_vis or rajada:
        return {"texto": "CONDIÇÕES DE ATENÇÃO", "cor": "#e67e22", "icone": "🌧️"}

    # --- MODERADAS (amarelo): chuva fraca, chuvisco, névoa úmida ---
    if any(x in txt for x in ["RA", "DZ", "BR", "HZ", "BKN", "OVC"]):
        return {"texto": "CONDIÇÕES MODERADAS", "cor": "#f39c12", "icone": "🌥️"}

    # --- BOAS (verde) ---
    return {"texto": "CONDIÇÕES BOAS", "cor": "#27ae60", "icone": "☀️"}

# ---------- Decodificador de TAF ----------
MUDANCA = {
    "FM":   ("A partir de", "🔄", "#2980b9"),
    "BECMG":("Tornando-se gradualmente", "📈", "#8e44ad"),
    "TEMPO":("Temporariamente", "⏳", "#e67e22"),
    "PROB30":("Probabilidade 30%", "🎲", "#f39c12"),
    "PROB40":("Probabilidade 40%", "🎲", "#e67e22"),
}

def _decodificar_grupo(token):
    """Decodifica um único token de TAF em {texto, icone, cor} ou None."""
    p = token
    # Vento
    if p.endswith("KT") and len(p) >= 7:
        direcao, veloc = p[:3], p[3:5]
        dir_txt = "variável" if direcao == "VRB" else f"{direcao}°"
        extra, cor = "", "#16a085"
        if "G" in p:
            rajada = p[p.index("G")+1:p.index("KT")]
            extra = f", rajadas de {rajada} nós"; cor = "#e67e22"
        return _linha(f"Vento: {dir_txt} a {int(veloc)} nós{extra}", "💨", cor)
    # Visibilidade
    if p.isdigit() and len(p) == 4:
        vis = "10 km ou mais" if p == "9999" else f"{int(p)} metros"
        cor = "#27ae60" if p == "9999" or int(p) >= 5000 else "#e67e22"
        return _linha(f"Visibilidade: {vis}", "👁️", cor)
    if p.endswith("SM"):
        return _linha(f"Visibilidade: {p.replace('SM','')} milhas", "👁️", "#27ae60")
    if p == "CAVOK":
        return _linha("CAVOK: visibilidade e teto excelentes", "☀️", "#27ae60")
    # Nuvens
    if p[:3] in NUVENS and p[:2] != "VV":
        alt = p[3:6]
        base = f" a {int(alt)*100} pés" if alt.isdigit() else ""
        tipo, cor, icone = "", "#2980b9", "☁️"
        for cod, nome in TIPO_NUVEM.items():
            if p.endswith(cod):
                tipo = f" — {nome}"; cor, icone = "#c0392b", "⛈️"
        return _linha(f"{NUVENS[p[:3]]}{base}{tipo}", icone, cor)
    # Fenômenos (chuva, trovoada etc.)
    return _traduzir_fenomeno(p)


def _periodo_horario(token):
    """Traduz janelas de validade e horários (ex: 1512/1618, FM151800)."""
    if "/" in token and len(token) == 9:  # 1512/1618
        i, f = token.split("/")
        return f"do dia {i[:2]} às {i[2:]}h até dia {f[:2]} às {f[2:]}h UTC"
    if len(token) == 6 and token.isdigit():  # 151800 (após FM)
        return f"dia {token[:2]} às {token[2:4]}:{token[4:]} UTC"
    return None


def decodificar_taf(raw):
    """Decodifica o TAF em blocos por período de previsão."""
    if not raw:
        return []
    tokens = raw.replace("=", "").split()
    blocos = []
    atual = {"titulo": "Previsão principal", "icone": "📋", "cor": "#34495e",
             "periodo": "", "itens": []}

    i = 0
    while i < len(tokens):
        t = tokens[i]
        chave = "PROB30" if t == "PROB30" else "PROB40" if t == "PROB40" else \
                t[:5] if t.startswith("BECMG") or t.startswith("TEMPO") else \
                t[:2] if t.startswith("FM") else None

        if chave in MUDANCA:
            blocos.append(atual)
            titulo, icone, cor = MUDANCA[chave]
            periodo = ""
            # FM tem o horário grudado (FM151800)
            if chave == "FM":
                periodo = _periodo_horario(t[2:]) or ""
            atual = {"titulo": titulo, "icone": icone, "cor": cor,
                     "periodo": periodo, "itens": []}
            i += 1
            continue

        # janela de validade ou horário
        per = _periodo_horario(t)
        if per and not atual["itens"]:
            atual["periodo"] = per
            i += 1
            continue

        item = _decodificar_grupo(t)
        if item:
            atual["itens"].append(item)
        i += 1

    blocos.append(atual)
    return [b for b in blocos if b["itens"] or b["periodo"]]


def resumo_taf(raw):
    """Resumo geral do TAF (pior condição prevista)."""
    return resumo(raw)  # reaproveita a mesma lógica de severidade
