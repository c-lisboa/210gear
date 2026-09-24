import os
import time
import requests

from flask import Flask, render_template, request, jsonify
from services import airports, metar, opensky, agregador

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


@app.route("/voo")
def voo():
    return render_template("voo.html")


# ─────────────────────────────────────────────
# ✈️ Rota antiga mantida
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
    if not reg:
        return ("Desconhecido", "🏳️")
    r = reg.upper().replace("-", "")
    for tam in (2, 1):
        pref = r[:tam]
        if pref in PREFIXO_PAIS:
            nome, iso = PREFIXO_PAIS[pref]
            return (nome, bandeira_de_iso(iso))
    return ("Desconhecido", "🏳️")


# ─────────────────────────────────────────────
# 🔧 Converte 1 aeronave crua (formato v2) → formato do site
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
        "alt": alt,
        "solo": no_solo,
        "veloc": a.get("gs") or 0,
        "rumo": a.get("track") or 0,
        "registro": registro,
        "tipo": a.get("t", "") or "",
        "modelo": a.get("desc", "") or "",
        "subindo": a.get("baro_rate") or 0,
        "squawk": squawk,
        "emergencia": emergencia,
        "categoria": a.get("category", "") or "",
        "fonte": a.get("_fonte", ""),
    }


# ─────────────────────────────────────────────
# 🚦 Cache de tráfego
# ─────────────────────────────────────────────
CACHE_SEGUNDOS = 8
_cache_trafego = {}


@app.route("/api/trafego")
def api_trafego():
    lat = request.args.get("lat", CENTRO_PADRAO["lat"], type=float)
    lon = request.args.get("lon", CENTRO_PADRAO["lon"], type=float)
    raio_nm = request.args.get("raio", CENTRO_PADRAO["raio"], type=float)
    raio_nm = max(1, min(raio_nm, 250))

    chave = f"{round(lat, 3)},{round(lon, 3)},{round(raio_nm)}"
    agora = time.time()

    cache = _cache_trafego.get(chave)
    if cache and (agora - cache["hora"] < CACHE_SEGUNDOS):
        return jsonify(cache["dados"])

    aeronaves = agregador.buscar_trafego(lat, lon, raio_nm)
    if not aeronaves and cache:
        return jsonify(cache["dados"])

    avioes = [montar_aviao(a) for a in aeronaves
              if a.get("lat") is not None and a.get("lon") is not None]

    _cache_trafego[chave] = {"dados": avioes, "hora": agora}
    return jsonify(avioes)


# ─────────────────────────────────────────────
# 🔎 Busca de voo por callsign
# ─────────────────────────────────────────────
@app.route("/api/voo/<callsign>")
def api_voo(callsign):
    cs = callsign.strip().upper().replace(" ", "")
    if not cs:
        return jsonify({"erro": "Informe um número de voo."})

    aeronaves = agregador.buscar_por_callsign(cs)
    if not aeronaves:
        return jsonify({"erro": "Voo não encontrado no ar agora."})

    a = next((x for x in aeronaves if x.get("lat") is not None), aeronaves[0])
    return jsonify(montar_aviao(a))


# ─────────────────────────────────────────────
# 🔍 Detalhes da aeronave (Hexdb.io — grátis, sem chave)
# ─────────────────────────────────────────────
_cache_aviao = {}


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
# 📸 Foto da aeronave (Planespotters.net — grátis, sem chave)
# ─────────────────────────────────────────────
_cache_foto = {}


@app.route("/api/foto/<icao>")
def info_foto(icao):
    icao = icao.strip().lower()
    if not icao:
        return jsonify({})

    # só usa cache se tiver foto de verdade
    if _cache_foto.get(icao, {}).get("thumb"):
        return jsonify(_cache_foto[icao])

    reg = request.args.get("reg", "").strip().upper()
    resultado = {}
    headers = {"User-Agent": "SiteAviacaoRJ/1.0 (contato@exemplo.com)"}

    def _extrair(js):
        fotos = (js or {}).get("photos") or []
        if not fotos:
            return {}
        f = fotos[0]
        return {
            "thumb": (f.get("thumbnail_large") or f.get("thumbnail") or {}).get("src", ""),
            "link": f.get("link", ""),
            "autor": f.get("photographer", ""),
        }

    try:
        # 1) por hex
        url = f"https://api.planespotters.net/pub/photos/hex/{icao}"
        r = requests.get(url, headers=headers, timeout=10)
        print(f"[FOTO] hex {icao} -> {r.status_code}")
        if r.ok:
            resultado = _extrair(r.json())

        # 2) fallback por registro (matrícula), se veio e não achou por hex
        if not resultado.get("thumb") and reg:
            url = f"https://api.planespotters.net/pub/photos/reg/{reg}"
            r = requests.get(url, headers=headers, timeout=10)
            print(f"[FOTO] reg {reg} -> {r.status_code}")
            if r.ok:
                resultado = _extrair(r.json())
    except Exception as e:
        print("[FOTO] erro:", e)

    if resultado.get("thumb"):
        _cache_foto[icao] = resultado
    return jsonify(resultado)



# ─────────────────────────────────────────────
# 🩺 Diagnóstico das fontes
# ─────────────────────────────────────────────
@app.route("/diagnostico")
def diagnostico():
    lat, lon, raio = -22.8, -43.4, 80
    linhas = ["<h2>Diagnóstico das fontes de tráfego</h2><ul>"]

    # OpenSky
    try:
        d_lat = raio / 60.0
        os_ac = opensky.buscar_estados(lat - d_lat, lon - d_lat,
                                       lat + d_lat, lon + d_lat)
        tok = "✅ token" if opensky._obter_token() else "⚠️ anônimo"
        linhas.append(f"<li><b>OpenSky</b> ({tok}) — <b>{len(os_ac)}</b> aeronaves</li>")
    except Exception as e:
        linhas.append(f"<li><b>OpenSky</b> — ❌ {e}</li>")

    # ADS-B
    for base in agregador.FONTES_ADSB:
        try:
            r = requests.get(f"{base}/v2/point/{lat}/{lon}/{raio}",
                             headers=agregador.CABECALHOS, timeout=(5, 10))
            qtd = len(r.json().get("ac") or [])
            linhas.append(f"<li><b>{base}</b> — <b>{r.status_code}</b> / {qtd} aeronaves</li>")
        except Exception as e:
            linhas.append(f"<li><b>{base}</b> — ❌ {e}</li>")

    # Agregado
    try:
        total = len(agregador.buscar_trafego(lat, lon, raio))
        linhas.append(f"<li><b>🎯 AGREGADO (sem duplicados)</b> — <b>{total}</b> aeronaves</li>")
    except Exception as e:
        linhas.append(f"<li>Agregado — ❌ {e}</li>")

    linhas.append("</ul>")
    return "".join(linhas)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=7860)
