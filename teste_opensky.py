import os
import requests
from flask import Flask, jsonify

app = Flask(__name__)

TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"

@app.route("/")
def diagnostico():
    diag = {}

    # 1. IP de saída do Render
    try:
        ip = requests.get("https://api.ipify.org?format=json", timeout=10)
        diag["ip_saida_render"] = ip.json()
    except Exception as e:
        diag["ip_saida_render"] = f"ERRO: {e}"

    # 2. Credenciais presentes?
    client_id = os.environ.get("OPENSKY_CLIENT_ID")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET")
    diag["tem_client_id"] = bool(client_id)
    diag["tem_client_secret"] = bool(client_secret)

    # 3. TESTE DE CONECTIVIDADE PURA (sem autenticar)
    try:
        ping = requests.get("https://auth.opensky-network.org/", timeout=10)
        diag["auth_host_alcancavel"] = f"OK - status {ping.status_code}"
    except Exception as e:
        diag["auth_host_alcancavel"] = f"BLOQUEADO: {e}"

    # 4. Teste de host neutro (controle) - google
    try:
        g = requests.get("https://www.google.com", timeout=10)
        diag["google_alcancavel"] = f"OK - status {g.status_code}"
    except Exception as e:
        diag["google_alcancavel"] = f"BLOQUEADO: {e}"

    # 5. Tentativa real de token
    if client_id and client_secret:
        try:
            tr = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            diag["token_status"] = tr.status_code
            if tr.status_code == 200:
                diag["token_ok"] = "access_token" in tr.json()
            else:
                diag["token_resposta"] = tr.text[:300]
        except Exception as e:
            diag["erro_token"] = str(e)

    return jsonify(diag)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
