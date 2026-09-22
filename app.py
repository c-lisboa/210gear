import os
import time
import math
import requests

from flask import Flask, render_template, request, jsonify
from services import airports, metar, opensky

app = Flask(__name__)

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
# 🌎 Centro padrão (Rio de Janeiro) e bandeiras
# ─────────────────────────────────────────────
CENTRO_PADRAO = {"lat": -22.8, "lon": -43.4, "raio": 80}  # raio em milhas náuticas

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
# 🚦 Cache de tráfego (protege contra excesso de requisições)
# ─────────────────────────────────────────────
CACHE_SEGUNDOS = 8
_cache_trafego = {}  # chave = "lat,lon,raio" → {"dados": [...], "hora": timestamp}

@app.route("/api/trafego")
def api_trafego():
    # Agora recebemos DIRETO: centro (lat, lon) e raio em milhas náuticas
    lat = request.args.get("lat", CENTRO_PADRAO["lat"], type=float)
    lon = request.args.get("lon", CENTRO_PADRAO["lon"], type=float)
    raio_nm = request.args.get("raio", CENTRO_PADRAO["raio"], type=float)

    # adsb.lol limita o raio a 250 nm
    raio_nm = max(1, min(raio_nm, 250))

    chave = f"{round(lat, 3)},{round(lon, 3)},{round(raio_nm)}"
    agora = time.time()

    # 1) Se tem cache recente, devolve sem bater na API
    cache = _cache_trafego.get(chave)
    if cache and (agora - cache["hora"] < CACHE_SEGUNDOS):
        return jsonify(cache["dados"])

    # 2) Busca na adsb.lol (grátis, sem chave, funciona na nuvem)
    try:
        url = f"https://api.adsb.lol/v2/point/{lat}/{lon}/{raio_nm}"
        r = requests.get(url, timeout=(5, 10))
        aeronaves = r.json().get("ac") or []
    except Exception as e:
        print("Erro adsb.lol:", e)
        if cache:
            return jsonify(cache["dados"])
        return jsonify([])

    # 3) Monta a lista de aviões
    avioes = []
    for a in aeronaves:
        lat_a = a.get("lat")
        lon_a = a.get("lon")
        if lat_a is None or lon_a is None:
            continue
        avioes.append({
            "icao": a.get("hex", ""),
            "callsign": (a.get("flight") or "").strip() or "N/D",
            "pais": a.get("flag") or "Desconhecido",
            "bandeira": "✈️",
            "lon": lon_a,
            "lat": lat_a,
            "alt": a.get("alt_baro") if isinstance(a.get("alt_baro"), (int, float)) else 0,
            "solo": a.get("alt_baro") == "ground",
            "veloc": a.get("gs") or 0,
            "rumo": a.get("track") or 0,
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
