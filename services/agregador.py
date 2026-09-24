"""
Agregador de tráfego: OpenSky (principal) + ADS-B (lol/fi) complementar.
Junta por ICAO24 (hex) sem redundância, preferindo o campo mais preenchido.
"""
import math
import requests
from services import opensky

FONTES_ADSB = [
    "https://api.adsb.lol",
    "https://api.adsb.fi",
]
CABECALHOS = {
    "User-Agent": "Mozilla/5.0 (compatible; SiteAviacaoRJ/1.0)",
    "Accept": "application/json",
}


def _buscar_adsb(caminho):
    """Tenta cada fonte ADS-B até obter aeronaves (formato v2)."""
    for base in FONTES_ADSB:
        try:
            r = requests.get(base + caminho, headers=CABECALHOS, timeout=(5, 10))
            if not r.ok:
                continue
            ac = r.json().get("ac") or []
            if ac:
                return ac
        except Exception as e:
            print(f"Erro {base}{caminho}:", e)
    return []


def _mesclar(base, extra):
    """Preenche em 'base' os campos vazios com os de 'extra' (ambos formato v2)."""
    for chave, valor in extra.items():
        atual = base.get(chave)
        vazio = atual in (None, "", 0)
        if vazio and valor not in (None, "", 0):
            base[chave] = valor
    return base


def buscar_trafego(lat, lon, raio_nm):
    """
    Retorna lista de aeronaves cruas (formato ADS-B v2) já mescladas.
    1) OpenSky = principal   2) ADS-B = complemento/fallback
    """
    # bounding box aproximado a partir do centro + raio (1 NM ≈ 1/60 de grau lat)
    d_lat = raio_nm / 60.0
    d_lon = raio_nm / (60.0 * max(0.1, math.cos(math.radians(lat))))

    por_hex = {}

    # 1) OpenSky (principal)
    for a in opensky.buscar_estados(lat - d_lat, lon - d_lon,
                                    lat + d_lat, lon + d_lon):
        h = a.get("hex")
        if h:
            por_hex[h] = a

    # 2) ADS-B (complemento: enriquece existentes + adiciona os que faltam)
    adsb = _buscar_adsb(f"/v2/point/{lat}/{lon}/{round(raio_nm)}")
    for a in adsb:
        h = (a.get("hex") or "").strip().lower()
        if not h:
            continue
        a["hex"] = h
        a.setdefault("_fonte", "adsb")
        if h in por_hex:
            _mesclar(por_hex[h], a)          # OpenSky manda, ADS-B completa
        else:
            por_hex[h] = a                   # avião que só o ADS-B viu

    return list(por_hex.values())


def buscar_por_callsign(callsign):
    """Busca um voo por callsign (usa ADS-B, que tem esse endpoint direto)."""
    ac = _buscar_adsb(f"/v2/callsign/{callsign}")
    return ac
