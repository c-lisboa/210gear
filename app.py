import os
import time
import math
import requests

from flask import Flask, render_template, request, jsonify
from services import airports, metar, opensky

app = Flask(__name__)

# ─────────────────────────────────────────────
# 🌐 Fontes de dados ADS-B (todas usam o mesmo formato v2)
# ─────────────────────────────────────────────
FONTES_ADSB = [
    "https://api.adsb.lol",   # aberta, principal
    "https://api.adsb.fi",    # adsb.fi — URL correta (era opendata.*, estava errada)
]

# Cabeçalho: alguns serviços (adsb.one/Cloudflare) exigem User-Agent
CABECALHOS_ADSB = {
    "User-Agent": "Mozilla/5.0 (compatible; SiteAviacaoRJ/1.0)",
    "Accept": "application/json",
}

def buscar_adsb(caminho):
    """
    Tenta cada fonte ADS-B até obter aeronaves.
    caminho ex: '/v2/point/-22.82/-43.32/10' ou '/v2/callsign/GLO1234'
    """
    ultima_lista = []
    for base in FONTES_ADSB:
        try:
            r = requests.get(base + caminho,
                             headers=CABECALHOS_ADSB,
                             timeout=(5, 10))
            if not r.ok:
                print(f"{base} respondeu {r.status_code}")
                continue
            ac = r.json().get("ac") or []
            if ac:
                return ac
            ultima_lista = ac
        except Exception as e:
            print(f"Erro em {base}{caminho}:", e)
    return ultima_lista

# ─────────────────────────────────────────────
# 🗺️ Rotas de páginas
# ─────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("home.html", rj=airports.aeroportos_rj())

@app.route("/busca")
def busca():
    termo = request.args.get("q", "")
    resultados = airports.buscar(termo) if termo else []
    return render_template("busca.html", termo=termo, resultados=resultados)

@app.route("/aeroporto/<ident>")
def aeroporto(ident):
    dados = airports.detalhes(ident)
    if not dados:
        return "Aeroporto não encontrado", 404
    icao = dados["aero"]["ident"]
    m = metar.metar(icao)
    t = metar.taf(icao)
    raw_m = m["rawOb"] if m else ""
    raw_t = t["rawTAF"] if t else ""
    return render_template("aeroporto.html", d=dados,
                           metar=m, taf=t,
                           decodificado=metar.decodificar(raw_m),
                           resumo=metar.resumo(raw_m),
                           taf_blocos=metar.decodificar_taf(raw_t),
                           taf_resumo=metar.resumo_taf(raw_t))

@app.route("/mapa")
def mapa():
    return render_template("mapa.html")

@app.route("/voo")
def voo():
    return render_template("voo.html")

# ─────────────────────────────────────────────
# ✈️ API de aviões (rota antiga, mantida)
# ─────────────────────────────────────────────
@app.route("/api/avioes")
def api_avioes():
    return jsonify(opensky.avioes_rj())

# ─────────────────────────────────────────────
# 🌎 Centro padrão (Rio de Janeiro)
# ─────────────────────────────────────────────
CENTRO_PADRAO = {"lat": -22.8, "lon": -43.4, "raio": 80}  # raio em milhas náuticas

# ─────────────────────────────────────────────
# 🏳️ Prefixos de matrícula → país
# ─────────────────────────────────────────────
PREFIXO_PAIS = {
    "PP": ("Brasil", "BR"), "PR": ("Brasil", "BR"), "PS": ("Brasil", "BR"),
    "PT": ("Brasil", "BR"), "PU": ("Brasil", "BR"),
    "LV": ("Argentina", "AR"), "LQ": ("Argentina", "AR"),
    "CC": ("Chile", "CL"), "CX": ("Uruguai", "UY"),
    "ZP": ("Paraguai", "PY"), "CP": ("Bolívia", "BO"),
    "N": ("Estados Unidos", "US"), "C": ("Canadá", "CA"),
    "G": ("Reino Unido", "GB"), "D": ("Alemanha", "DE"),
    "F": ("França", "FR"), "EC": ("Espanha", "ES"), "CS": ("Portugal", "PT"),
    "HK": ("Colômbia", "CO"), "OB": ("Peru", "PE"), "HP": ("Panamá", "PA"),
    "XA": ("México", "MX"), "XB": ("México", "MX"), "XC": ("México", "MX"),
    "PH": ("Holanda", "NL"), "I": ("Itália", "IT"),
}

def bandeira_de_iso(iso):
    if not iso or len(iso) != 2:
        return "🏳️"
    return chr(ord(iso[0].upper()) + 127397) + chr(ord(iso[1].upper()) + 127397)

def pais_por_registro(reg):
    """Descobre o país pelo prefixo da matrícula (PR-ABC → Brasil)."""
    if not reg:
        return ("Desconhecido", "🏳️")
    r = reg.upper().replace("-", "")
    for tam in (2, 1):  # tenta prefixo de 2 letras, depois de 1
        pref = r[:tam]
        if pref in PREFIXO_PAIS:
            nome, iso = PREFIXO_PAIS[pref]
            return (nome, bandeira_de_iso(iso))
    return ("Desconhecido", "🏳️")

# ─────────────────────────────────────────────
# 🔧 Converte 1 aeronave crua da API → formato do site
# ─────────────────────────────────────────────
def montar_aviao(a):
    lat_a = a.get("lat")
    lon_a = a.get("lon")

    registro = a.get("r", "") or ""
    pais, bandeira = pais_por_registro(registro)

    alt_baro = a.get("alt_baro")
    no_solo = alt_baro == "ground"
    alt = alt_baro if isinstance(alt_baro, (int, float)) else 0

    squawk = a.get("squawk", "") or ""
    emergencia = squawk in ("7500", "7600", "7700")

    return {
        "icao": a.get("hex", ""),
        "callsign": (a.get("flight") or "").strip() or "N/D",
        "pais": pais,
        "bandeira": bandeira,
        "lon": lon_a,
        "lat": lat_a,
        "alt": alt,                          # altitude barométrica (ft)
        "solo": no_solo,
        "veloc": a.get("gs") or 0,           # velocidade solo (nós)
        "rumo": a.get("track") or 0,         # proa
        "registro": registro,                # matrícula (PR-ABC)
        "tipo": a.get("t", "") or "",         # código ICAO do tipo (A320)
        "modelo": a.get("desc", "") or "",    # descrição do modelo
        "subindo": a.get("baro_rate") or 0,   # ft/min (+sobe / -desce)
        "squawk": squawk,
        "emergencia": emergencia,
        "categoria": a.get("category", "") or "",
    }

# ─────────────────────────────────────────────
# 🚦 Cache de tráfego (protege contra excesso de requisições)
# ─────────────────────────────────────────────
CACHE_SEGUNDOS = 8
_cache_trafego = {}  # chave = "lat,lon,raio" → {"dados": [...], "hora": timestamp}

@app.route("/api/trafego")
def api_trafego():
    # centro (lat, lon) e raio em milhas náuticas
    lat = request.args.get("lat", CENTRO_PADRAO["lat"], type=float)
    lon = request.args.get("lon", CENTRO_PADRAO["lon"], type=float)
    raio_nm = request.args.get("raio", CENTRO_PADRAO["raio"], type=float)
    raio_nm = max(1, min(raio_nm, 250))  # limite de 250 nm

    chave = f"{round(lat, 3)},{round(lon, 3)},{round(raio_nm)}"
    agora = time.time()

    # 1) Cache recente → devolve sem bater na API
    cache = _cache_trafego.get(chave)
    if cache and (agora - cache["hora"] < CACHE_SEGUNDOS):
        return jsonify(cache["dados"])

    # 2) Busca nas fontes ADS-B (cascata: adsb.one → adsb.lol)
    aeronaves = buscar_adsb(f"/v2/point/{lat}/{lon}/{raio_nm}")
    if not aeronaves and cache:
        # nenhuma fonte trouxe dados agora → mantém o último resultado bom
        return jsonify(cache["dados"])

    # 3) Monta a lista de aviões
    avioes = []
    for a in aeronaves:
        if a.get("lat") is None or a.get("lon") is None:
            continue
        avioes.append(montar_aviao(a))

    # 4) Salva no cache e devolve
    _cache_trafego[chave] = {"dados": avioes, "hora": agora}
    return jsonify(avioes)

# ─────────────────────────────────────────────
# 🔎 Busca de voo por callsign (cascata de fontes)
# ─────────────────────────────────────────────
@app.route("/api/voo/<callsign>")
def api_voo(callsign):
    cs = callsign.strip().upper().replace(" ", "")
    if not cs:
        return jsonify({"erro": "Informe um número de voo."})

    aeronaves = buscar_adsb(f"/v2/callsign/{cs}")
    if not aeronaves:
        return jsonify({"erro": "Voo não encontrado no ar agora."})

    # pega a primeira aeronave que tenha posição
    a = next((x for x in aeronaves if x.get("lat") is not None), aeronaves[0])
    return jsonify(montar_aviao(a))

# ─────────────────────────────────────────────
# 🔍 Detalhes da aeronave (Hexdb.io — grátis, sem chave)
# ─────────────────────────────────────────────
_cache_aviao = {}  # chave = icao → dados

@app.route("/api/aviao/<icao>")
def info_aviao(icao):
    icao = icao.strip().lower()
    if not icao:
        return jsonify({})

    if icao in _cache_aviao:
        return jsonify(_cache_aviao[icao])

    resultado = {}
    try:
        r = requests.get(f"https://hexdb.io/api/v1/aircraft/{icao}", timeout=8)
        if r.ok and r.text.strip():
            d = r.json()
            resultado = {
                "registro": d.get("Registration", ""),
                "modelo": d.get("Type", "") or d.get("ICAOTypeCode", ""),
                "fabricante": d.get("Manufacturer", ""),
                "dono": d.get("RegisteredOwners", ""),
            }
    except Exception as e:
        print("Erro Hexdb:", e)

    _cache_aviao[icao] = resultado
    return jsonify(resultado)


# ─────────────────────────────────────────────
# 🩺 Diagnóstico das fontes ADS-B (acesse /diagnostico no navegador)
# ─────────────────────────────────────────────
@app.route("/diagnostico")
def diagnostico():
    caminho = "/v2/point/-22.8/-43.4/80"
    linhas = ["<h2>Diagnóstico das fontes ADS-B</h2>",
              f"<p>Testando: <code>{caminho}</code></p><ul>"]
    for base in FONTES_ADSB:
        try:
            r = requests.get(base + caminho,
                             headers=CABECALHOS_ADSB,
                             timeout=(5, 10))
            status = r.status_code
            try:
                qtd = len(r.json().get("ac") or [])
                info = f"✅ <b>{status}</b> — <b>{qtd}</b> aeronaves"
            except Exception:
                # não veio JSON (provável bloqueio HTML do Cloudflare)
                trecho = r.text[:120].replace("<", "&lt;")
                info = f"⚠️ <b>{status}</b> — resposta não-JSON: <code>{trecho}...</code>"
        except Exception as e:
            info = f"❌ ERRO: {e}"
        linhas.append(f"<li><b>{base}</b><br>{info}</li><br>")
    linhas.append("</ul>")
    return "".join(linhas)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=7860)
