import os
import requests
from flask import Flask, jsonify

app = Flask(__name__)

TOKEN_URL = ("https://auth.opensky-network.org/auth/realms/"
             "opensky-network/protocol/openid-connect/token")
STATES_URL = "https://opensky-network.org/api/states/all"

# Região do Rio de Janeiro (bounding box)
LAT, LON, D = -22.82, -43.32, 4.0  # ~240 NM


@app.route("/")
def teste():
    diag = {}

    # 0) Qual IP o Render está usando pra sair? (pra comparar com bloqueios)
    try:
        diag["ip_saida_render"] = requests.get(
            "https://api.ipify.org?format=json", timeout=10
        ).json()
    except Exception as e:
        diag["ip_saida_render"] = f"erro: {e}"

    cid = os.environ.get("OPENSKY_CLIENT_ID")
    csec = os.environ.get("OPENSKY_CLIENT_SECRET")
    diag["tem_client_id"] = bool(cid)
    diag["tem_client_secret"] = bool(csec)

    if not (cid and csec):
        diag["erro"] = "Faltam variáveis de ambiente no Render."
        return jsonify(diag), 400

    # 1) Pegar o token OAuth2
    try:
        tr = requests.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": csec,
        }, timeout=15)
        diag["token_status"] = tr.status_code
        if not tr.ok:
            diag["token_resposta"] = tr.text[:400]
            return jsonify(diag), 502
        token = tr.json().get("access_token")
        diag["token_recebido"] = bool(token)
    except Exception as e:
        diag["erro_token"] = str(e)
        return jsonify(diag), 502

    # 2) Chamar states/all autenticado
    try:
        params = {"lamin": LAT - D, "lamax": LAT + D,
                  "lomin": LON - D, "lomax": LON + D}
        sr = requests.get(
            STATES_URL,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        diag["states_status"] = sr.status_code
        # cabeçalhos úteis de cota/limite, se vierem
        diag["rate_headers"] = {
            k: v for k, v in sr.headers.items()
            if "rate" in k.lower() or "remaining" in k.lower()
            or "retry" in k.lower()
        }
        if sr.ok:
            estados = sr.json().get("states") or []
            diag["aeronaves_encontradas"] = len(estados)
            diag["amostra"] = [
                {"hex": s[0], "callsign": (s[1] or "").strip()}
                for s in estados[:5]
            ]
            diag["RESULTADO"] = "✅ FUNCIONOU no Render"
        else:
            diag["states_resposta"] = sr.text[:400]
            diag["RESULTADO"] = "❌ Token OK, mas states/all falhou"
    except Exception as e:
        diag["erro_states"] = str(e)

    return jsonify(diag)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
