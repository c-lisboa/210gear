import os
import time
import requests

TOKEN_URL = ("https://auth.opensky-network.org/auth/realms/"
             "opensky-network/protocol/openid-connect/token")
STATES_URL = "https://opensky-network.org/api/states/all"

# ─── Token OAuth2 em cache (dura ~30 min; renovamos com folga) ───
_token = {"valor": None, "expira": 0}


def _obter_token():
    """Pega (e cacheia) o token OAuth2 do OpenSky. Retorna string ou None."""
    agora = time.time()
    if _token["valor"] and agora < _token["expira"]:
        return _token["valor"]

    cid = os.environ.get("OPENSKY_CLIENT_ID")
    csec = os.environ.get("OPENSKY_CLIENT_SECRET")
    if not (cid and csec):
        return None  # sem credenciais → usa modo anônimo

    try:
        r = requests.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": csec,
        }, timeout=15)
        if not r.ok:
            print("OpenSky token falhou:", r.status_code, r.text[:200])
            return None
        js = r.json()
        _token["valor"] = js.get("access_token")
        # expira_in costuma ser 1800s; renovamos 60s antes
        _token["expira"] = agora + int(js.get("expires_in", 1800)) - 60
        return _token["valor"]
    except Exception as e:
        print("Erro token OpenSky:", e)
        return None


def _padronizar(estados):
    """
    Converte a lista crua 'states' do OpenSky no MESMO formato do ADS-B (v2),
    para que o agregador possa juntar tudo sem redundância.
    Índices OpenSky: 0=icao24 1=callsign 2=pais_origem 5=lon 6=lat
                     7=alt_baro 8=on_ground 9=veloc 10=track 11=vert_rate
                     14=squawk 16=categoria
    """
    saida = []
    for e in estados:
        lat, lon = e[6], e[5]
        if lat is None or lon is None:
            continue
        no_solo = bool(e[8])
        saida.append({
            "hex": (e[0] or "").strip().lower(),
            "flight": (e[1] or "").strip(),
            "lat": lat,
            "lon": lon,
            "alt_baro": "ground" if no_solo else (
                round(e[7] * 3.28084) if e[7] is not None else None),  # m→ft
            "gs": round(e[9] * 1.94384) if e[9] is not None else None,  # m/s→nós
            "track": e[10] if e[10] is not None else 0,
            "baro_rate": round(e[11] * 196.85) if e[11] is not None else 0,  # m/s→ft/min
            "squawk": e[14] or "",
            "r": "",          # OpenSky não traz matrícula → ADS-B/Hexdb completam
            "t": "",          # nem tipo
            "desc": "",
            "category": str(e[16]) if len(e) > 16 and e[16] else "",
            "_fonte": "opensky",
        })
    return saida


def buscar_estados(lamin, lomin, lamax, lomax):
    """
    Busca no OpenSky dentro do bounding box.
    Usa token se houver; senão tenta anônimo. Retorna lista padronizada (formato ADS-B).
    """
    params = {"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax}
    headers = {}
    tok = _obter_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"

    try:
        r = requests.get(STATES_URL, params=params, headers=headers, timeout=20)
        if not r.ok:
            print("OpenSky states falhou:", r.status_code)
            return []
        estados = r.json().get("states") or []
        return _padronizar(estados)
    except Exception as e:
        print("Erro OpenSky states:", e)
        return []


# ─── Rota antiga mantida para não quebrar /api/avioes ───
def avioes_rj():
    dados = buscar_estados(-23.4, -44.9, -20.7, -40.9)
    return [{"callsign": a["flight"], "pais": "", "lat": a["lat"],
             "lon": a["lon"], "alt": a["alt_baro"], "vel": a["gs"]}
            for a in dados]
