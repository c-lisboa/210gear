import requests

def avioes_rj():
    area = {"lamin": -23.4, "lomin": -44.9, "lamax": -20.7, "lomax": -40.9}
    try:
        r = requests.get("https://opensky-network.org/api/states/all",
                         params=area, timeout=15)
        estados = r.json().get("states") or []
    except Exception:
        estados = []
    return [{"callsign": (e[1] or "").strip(), "pais": e[2],
             "lat": e[6], "lon": e[5], "alt": e[7], "vel": e[9]}
            for e in estados if e[5] and e[6]]
