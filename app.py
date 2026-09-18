import os
import time
import requests

from flask import Flask, render_template, request, jsonify
from services import airports, metar, opensky

app = Flask(__name__)

# ─────────────────────────────────────────────
# 🔑 Credenciais OpenSky OAuth2 (via variável de ambiente)
# ─────────────────────────────────────────────
OPENSKY_CLIENT_ID     = os.environ.get("OPENSKY_CLIENT_ID")
OPENSKY_CLIENT_SECRET = os.environ.get("OPENSKY_CLIENT_SECRET")

TOKEN_URL = ("https://auth.opensky-network.org/auth/realms/"
             "opensky-network/protocol/openid-connect/token")

# Guarda o token em memória para não pedir um novo a cada requisição
_token = {"valor": None, "expira_em": 0}

def _get_token():
    """Pega (ou renova) o token OAuth2. Retorna None se não houver credenciais."""
    if not (OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET):
        return None  # sem credenciais → acesso anônimo

    # Se ainda temos um token válido, reaproveita
    if _token["valor"] and time.time() < _token["expira_em"]:
        return _token["valor"]

    try:
        r = requests.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": OPENSKY_CLIENT_ID,
            "client_secret": OPENSKY_CLIENT_SECRET,
        }, timeout=15)
        r.raise_for_status()
        d = r.json()
        _token["valor"] = d["access_token"]
        _token["expira_em"] = time.time() + d.get("expires_in", 1800) - 30
        return _token["valor"]
    except Exception as e:
        print("Erro ao pegar token OpenSky:", e)
        return None

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

# ─────────────────────────────────────────────
# ✈️ API de aviões (rota antiga, mantida)
# ─────────────────────────────────────────────
@app.route("/api/avioes")
def api_avioes():
    return jsonify(opensky.avioes_rj())

# ─────────────────────────────────────────────
# 🌎 Área padrão e bandeiras
# ─────────────────────────────────────────────
BBOX_RJ = {"lamin": -25.0, "lomin": -48.0, "lamax": -20.0, "lomax": -40.0}

PAISES_ISO = {
    "Brazil": "BR", "United States": "US", "Argentina": "AR",
    "Chile": "CL", "Paraguay": "PY", "Uruguay": "UY", "Bolivia": "BO",
    "Portugal": "PT", "Spain": "ES", "France": "FR", "Germany": "DE",
    "United Kingdom": "GB", "Italy": "IT", "Colombia": "CO", "Peru": "PE",
    "Panama": "PA", "Mexico": "MX", "Canada": "CA", "Netherlands": "NL",
}

def bandeira_emoji(pais):
    iso = PAISES_ISO.get(pais)
    if not iso:
        return "🏳️"
    return chr(ord(iso[0]) + 127397) + chr(ord(iso[1]) + 127397)

# ─────────────────────────────────────────────
# 🚦 Cache de tráfego (protege sua cota da OpenSky)
# ─────────────────────────────────────────────
CACHE_SEGUNDOS = 8
_cache_trafego = {}  # chave = string da bbox → {"dados": [...], "hora": timestamp}

@app.route("/api/trafego")
def api_trafego():
    bbox = {
        "lamin": request.args.get("lamin", -23.2, type=float),
        "lomin": request.args.get("lomin", -44.0, type=float),
        "lamax": request.args.get("lamax", -22.4, type=float),
        "lomax": request.args.get("lomax", -42.9, type=float),
    }

    chave = f"{bbox['lamin']},{bbox['lomin']},{bbox['lamax']},{bbox['lomax']}"
    agora = time.time()

    # 1) Se tem cache recente, devolve sem bater na API
    cache = _cache_trafego.get(chave)
    if cache and (agora - cache["hora"] < CACHE_SEGUNDOS):
        return jsonify(cache["dados"])

    # 2) Busca na OpenSky (com token OAuth2, se houver credenciais)
    try:
        token = _get_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = requests.get("https://opensky-network.org/api/states/all",
                         params=bbox, headers=headers, timeout=30)
        if r.status_code == 429:
            print("OpenSky: limite atingido (429)")
            if cache:
                return jsonify(cache["dados"])
            return jsonify([])
        estados = r.json().get("states") or []
    except Exception as e:
        print("Erro OpenSky:", e)
        if cache:
            return jsonify(cache["dados"])
        return jsonify([])

    # 3) Monta a lista de aviões
    avioes = []
    for s in estados:
        if s[5] is None or s[6] is None:
            continue
        pais = s[2] or "Desconhecido"
        avioes.append({
            "icao": s[0], "callsign": (s[1] or "").strip() or "N/D",
            "pais": pais, "bandeira": bandeira_emoji(pais),
            "lon": s[5], "lat": s[6], "alt": s[7] or 0,
            "solo": s[8], "veloc": s[9] or 0, "rumo": s[10] or 0,
        })

    # 4) Salva no cache e devolve
    _cache_trafego[chave] = {"dados": avioes, "hora": agora}
    return jsonify(avioes)

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

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=7860)
