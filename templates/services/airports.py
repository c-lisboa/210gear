import csv, os, io, requests

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BASE = "https://davidmegginson.github.io/ourairports-data"

_cache = {"airports": None, "runways": None, "freqs": None}

def _baixar_csv(nome):
    """Baixa o CSV do OurAirports e retorna lista de dicts."""
    caminho = os.path.join(DATA_DIR, nome)
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    r = requests.get(f"{BASE}/{nome}", timeout=30)
    r.encoding = "utf-8"
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(r.text)
    return list(csv.DictReader(io.StringIO(r.text)))

def _carregar():
    if _cache["airports"] is None:
        _cache["airports"] = _baixar_csv("airports.csv")
        _cache["runways"]  = _baixar_csv("runways.csv")
        _cache["freqs"]    = _baixar_csv("airport-frequencies.csv")

def buscar(termo):
    """Busca por ICAO, IATA ou nome."""
    _carregar()
    termo = termo.strip().upper()
    resultado = []
    for a in _cache["airports"]:
        if (termo == a["ident"].upper()
                or termo == a["iata_code"].upper()
                or termo in a["name"].upper()):
            resultado.append(a)
    return resultado[:30]

def detalhes(ident):
    """Retorna aeroporto + pistas + frequências pelo código ICAO/ident."""
    _carregar()
    ident = ident.strip().upper()
    aero = next((a for a in _cache["airports"] if a["ident"].upper() == ident), None)
    if not aero:
        return None
    pistas = [r for r in _cache["runways"] if r["airport_ident"].upper() == ident]
    freqs  = [f for f in _cache["freqs"] if f["airport_ident"].upper() == ident]
    return {"aero": aero, "pistas": pistas, "freqs": freqs}

def aeroportos_rj():
    """Todos os aeroportos do estado do Rio de Janeiro (iso_region BR-RJ)."""
    _carregar()
    return [a for a in _cache["airports"]
            if a["iso_region"] == "BR-RJ" and a["type"] != "closed_airport"]
