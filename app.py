import time
import threading
import pandas as pd
import os
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from datetime import datetime
from iqoptionapi.stable_api import IQ_Option

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÕES ---
PARES_BASE = ["EURUSD", "GBPUSD", "EURJPY", "AUDCAD", "USDCAD", "USDJPY", "EURGBP", "AUDJPY"]
PARES_PARA_CATALOGAR = PARES_BASE + [p + "-OTC" for p in PARES_BASE]
TIMEFRANE_SEGUNDOS = 60
QUANTIDADE_VELAS = 240

db_resultados = {"ultima_atualizacao": "Iniciando...", "dados": []}
api_iq = None
catalogador_rodando = False

def conectar_api(email, senha):
    api = IQ_Option(email, senha)
    status, _ = api.connect()
    if status:
        api.change_balance("PRACTICE")
        return api
    return None

def buscar_velas(api, par, timeframe, quantidade):
    try:
        velas_raw = api.get_candles(par, timeframe, quantidade, time.time())
        if not velas_raw or len(velas_raw) < 50: return None
        df = pd.DataFrame(velas_raw)
        df.rename(columns={'open':'open', 'close':'close', 'from':'timestamp'}, inplace=True)
        df['cor'] = 'DOJI'
        df.loc[df['close'] > df['open'], 'cor'] = 'VERDE'
        df.loc[df['close'] < df['open'], 'cor'] = 'VERMELHA'
        df.set_index('timestamp', inplace=True)
        return df
    except: return None

# --- AUXILIARES ---
def get_minority(cores):
    v, r = cores.count('VERDE'), cores.count('VERMELHA')
    return 'CALL' if v < r else 'PUT' if r < v else 'NONE'

def get_majority(cores):
    v, r = cores.count('VERDE'), cores.count('VERMELHA')
    return 'CALL' if v > r else 'PUT' if r > v else 'NONE'

# --- PROCESSAMENTO DAS ESTRATÉGIAS ---
def processar_estrategias(df, par):
    resultados_par = []
    
    def mhi1():
        df_m = df.copy(); df_m['sinal'] = 'NONE'; padrao = []
        for i in range(len(df_m)):
            dt = datetime.fromtimestamp(df_m.index[i]); 
            if dt.minute % 5 == 4:
                padrao = [df_m['cor'].iloc[i-2], df_m['cor'].iloc[i-1], df_m['cor'].iloc[i]]
                df_m.iloc[i, df_m.columns.get_loc('sinal')] = get_minority(padrao)
        return df_m, "MHI 1", padrao

    def mhi2():
        df_m = df.copy(); df_m['sinal'] = 'NONE'; padrao = []
        for i in range(len(df_m)):
            dt = datetime.fromtimestamp(df_m.index[i]);
            if dt.minute % 5 == 0:
                padrao = [df_m['cor'].iloc[i-3], df_m['cor'].iloc[i-2], df_m['cor'].iloc[i-1]]
                df_m.iloc[i, df_m.columns.get_loc('sinal')] = get_minority(padrao)
        return df_m, "MHI 2", padrao

    def mhi3():
        df_m = df.copy(); df_m['sinal'] = 'NONE'; padrao = []
        for i in range(len(df_m)):
            dt = datetime.fromtimestamp(df_m.index[i]);
            if dt.minute % 5 == 1:
                padrao = [df_m['cor'].iloc[i-4], df_m['cor'].iloc[i-3], df_m['cor'].iloc[i-2]]
                df_m.iloc[i, df_m.columns.get_loc('sinal')] = get_minority(padrao)
        return df_m, "MHI 3", padrao

    def r7():
        df_m = df.copy(); df_m['sinal'] = 'NONE'; padrao = []
        for i in range(7, len(df_m)):
            dt = datetime.fromtimestamp(df_m.index[i]);
            if dt.minute % 5 == 0:
                padrao = [df_m['cor'].iloc[i-7], df_m['cor'].iloc[i-6]]
                if padrao[0] == padrao[1] and padrao[0] != 'DOJI':
                    df_m.iloc[i, df_m.columns.get_loc('sinal')] = 'CALL' if padrao[0] == 'VERDE' else 'PUT'
        return df_m, "R7", padrao

    def torres():
        df_m = df.copy(); df_m['sinal'] = 'NONE'; padrao = []
        for i in range(3, len(df_m)):
            padrao = list(df_m['cor'].iloc[i-3:i+1])
            sinal = 'NONE'
            if padrao[0] == 'VERMELHA' and all(x == 'VERDE' for x in padrao[1:]): sinal = 'PUT'
            elif padrao[0] == 'VERDE' and all(x == 'VERMELHA' for x in padrao[1:]): sinal = 'CALL'
            df_m.iloc[i, df_m.columns.get_loc('sinal')] = sinal
        return df_m, "Torres Gemeas", padrao

    def p3x1():
        df_m = df.copy(); df_m['sinal'] = 'NONE'; padrao = []
        for i in range(len(df_m)):
            dt = datetime.fromtimestamp(df_m.index[i]);
            if dt.minute % 5 == 3:
                padrao = [df_m['cor'].iloc[i-3], df_m['cor'].iloc[i-2], df_m['cor'].iloc[i-1]]
                df_m.iloc[i, df_m.columns.get_loc('sinal')] = get_minority(padrao)
        return df_m, "Padrao 3x1", padrao

    def p23():
        df_m = df.copy(); df_m['sinal'] = 'NONE'; padrao = []
        for i in range(len(df_m)):
            dt = datetime.fromtimestamp(df_m.index[i]);
            if dt.minute % 5 == 0:
                padrao = [df_m['cor'].iloc[i]]
                df_m.iloc[i, df_m.columns.get_loc('sinal')] = 'CALL' if padrao[0] == 'VERDE' else 'PUT'
        return df_m, "Padrao 23", padrao

    def mosqueteiros():
        df_m = df.copy(); df_m['sinal'] = 'NONE'; padrao = []
        for i in range(len(df_m)):
            dt = datetime.fromtimestamp(df_m.index[i]);
            if dt.minute % 5 == 2:
                padrao = [df_m['cor'].iloc[i-2], df_m['cor'].iloc[i-1], df_m['cor'].iloc[i]]
                df_m.iloc[i, df_m.columns.get_loc('sinal')] = get_majority(padrao)
        return df_m, "Tres Mosqueteiros", padrao

    def melhor3():
        df_m = df.copy(); df_m['sinal'] = 'NONE'; padrao = []
        for i in range(5, len(df_m)):
            dt = datetime.fromtimestamp(df_m.index[i]);
            if dt.minute % 5 == 0:
                padrao = [df_m['cor'].iloc[i-4], df_m['cor'].iloc[i-3], df_m['cor'].iloc[i-2]]
                df_m.iloc[i, df_m.columns.get_loc('sinal')] = get_majority(padrao)
        return df_m, "Melhor de 3", padrao

    def sevenflip():
        df_m = df.copy(); df_m['sinal'] = 'NONE'; padrao = []
        for i in range(6, len(df_m)):
            padrao = list(df_m['cor'].iloc[i-6:i+1])
            if padrao.count('VERDE') == 7: df_m.iloc[i, df_m.columns.get_loc('sinal')] = 'PUT'
            elif padrao.count('VERMELHA') == 7: df_m.iloc[i, df_m.columns.get_loc('sinal')] = 'CALL'
        return df_m, "Seven Flip", padrao

    funcoes = [mhi1, mhi2, mhi3, r7, torres, p3x1, p23, mosqueteiros, melhor3, sevenflip] 

    for func in funcoes:
        df_sinais, nome, padrao = func()
        v0, v1, v2, loss, total = 0, 0, 0, 0, 0
        for i in range(len(df_sinais)-4):
            s = df_sinais['sinal'].iloc[i]
            if s == 'NONE': continue
            total += 1
            alvo = 'VERDE' if s == 'CALL' else 'VERMELHA'
            if df_sinais['cor'].iloc[i+1] == alvo: v0 += 1
            elif df_sinais['cor'].iloc[i+2] == alvo: v1 += 1
            elif df_sinais['cor'].iloc[i+3] == alvo: v2 += 1
            else: loss += 1
        
        if total > 0:
            direcao = df_sinais[df_sinais['sinal'] != 'NONE']['sinal'].iloc[-1] if not df_sinais[df_sinais['sinal'] != 'NONE'].empty else "NONE"
            resultados_par.append({
                "par": par, "estrategia": nome,
                "assertividade": round(((v0+v1+v2)/total)*100, 2),
                "gales": {"v0": v0, "v1": v1, "v2": v2, "loss": loss},
                "padrao": padrao,
                "direcao": direcao
            })
    return resultados_par

def loop_catalogador():
    global db_resultados, api_iq, catalogador_rodando
    catalogador_rodando = True
    while True:
        if api_iq:
            todos_dados = []
            for par in PARES_PARA_CATALOGAR:
                df = buscar_velas(api_iq, par, TIMEFRANE_SEGUNDOS, QUANTIDADE_VELAS)
                if df is not None:
                    todos_dados.extend(processar_estrategias(df, par))
            db_resultados = {"ultima_atualizacao": datetime.now().strftime('%H:%M:%S'), "dados": todos_dados}
        time.sleep(120)

@app.route('/')
def home(): 
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    global api_iq, catalogador_rodando
    d = request.json
    api_iq = conectar_api(d.get('email'), d.get('password'))
    if api_iq:
        if not catalogador_rodando: 
            threading.Thread(target=loop_catalogador, daemon=True).start()
        return jsonify({"status": "success"})
    return jsonify({"status": "error"})

@app.route('/api/dados')
def get_dados(): 
    return jsonify(db_resultados)

if __name__ == "__main__":
    # Na AWS EC2, porta padrão é 5000, host 0.0.0.0 para acesso externo
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)