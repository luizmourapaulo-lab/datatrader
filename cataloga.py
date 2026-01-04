import time
import pandas as pd
import getpass
from datetime import datetime
from collections import defaultdict
import colorama
from colorama import Fore, Style, Back

# Inicializa o Colorama 
colorama.init(autoreset=True)

# --- Define algumas cores para facilitar ---
C_HEADER = Style.BRIGHT + Fore.YELLOW
C_PAIR = Style.BRIGHT + Fore.MAGENTA
C_STRATEGY = Fore.CYAN
C_SUCCESS = Fore.GREEN
C_WARN = Fore.YELLOW 
C_ERROR = Fore.RED  
C_DIM = Style.DIM + Fore.WHITE
C_BOLD = Style.BRIGHT
C_RESET = Style.RESET_ALL

# --- Importação da API ---
from iqoptionapi.stable_api import IQ_Option


# --- 1. CONFIGURAÇÃO E CONEXÃO ---

def conectar_api(email, senha):
    """Conecta à API da IQ Option (usando stable_api)."""
    print(f"Tentando conectar como {C_BOLD}{email}{C_RESET}...")
    api = IQ_Option(email, senha)
    status, message = api.connect()

    if status:
        print(f"{C_SUCCESS}Conectado com sucesso!{C_RESET}")
        print("Mudando para conta PRACTICE (DEMO)...")
        try:
            api.change_balance("PRACTICE")
            print(f"{C_SUCCESS}Conta alterada para PRACTICE.{C_RESET}")
            return api
        except Exception as e:
            print(f"{C_ERROR}Erro ao tentar mudar para conta PRACTICE: {e}{C_RESET}")
            return None
    else:
        if message is None: message = "Erro desconhecido."
        print(f"{C_ERROR}Falha na conexão: {message}{C_RESET}")
        return None

# --- 2. BUSCA E PREPARAÇÃO DOS DADOS ---

def buscar_velas(api, par, timeframe_segundos, quantidade):
    """Busca velas e converte para DataFrame do Pandas."""
    print(f"Buscando {C_BOLD}{quantidade}{C_RESET} velas de M1 para {C_PAIR}{par}{C_RESET}...")
    velas_raw = api.get_candles(par, timeframe_segundos, quantidade, time.time())

    if not velas_raw:
        print(f"{C_ERROR}Não foi possível buscar dados para {par}. Verifique se o par está correto/aberto.{C_RESET}")
        return None
    if len(velas_raw) == 0:
        print(f"{C_ERROR}Recebido 0 velas para {par}. Pulando...{C_RESET}")
        return None

    df = pd.DataFrame(velas_raw)
    colunas_esperadas = {'open', 'max', 'min', 'close', 'volume', 'from'}
    if not colunas_esperadas.issubset(df.columns):
        print(f"{C_ERROR}Colunas inesperadas para {par}: {list(df.columns)}. Pulando...{C_RESET}")
        return None

    df.rename(columns={'open':'open', 'max':'high', 'min':'low', 'close':'close', 'volume':'volume', 'from':'timestamp'}, inplace=True)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    df.set_index('timestamp', inplace=True)
    df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
    df['cor'] = 'DOJI'; df.loc[df['close'] > df['open'], 'cor'] = 'VERDE'; df.loc[df['close'] < df['open'], 'cor'] = 'VERMELHA'
    print(f"Dados de {C_PAIR}{par}{C_RESET} carregados. Total: {C_BOLD}{len(df)}{C_RESET} velas.")
    return df

# --- 3. DEFINIÇÃO DAS ESTRATÉGIAS ---

def get_minority_signal(candle_1, candle_2, candle_3):
    """Analisa 3 velas e retorna o sinal da MINORIA."""
    cores = [candle_1, candle_2, candle_3]
    verdes = cores.count('VERDE')
    vermelhas = cores.count('VERMELHA')
    if verdes < vermelhas: return 'CALL'
    elif vermelhas < verdes: return 'PUT'
    else: return 'NONE'

def get_majority_signal(candle_1, candle_2, candle_3):
    """Analisa 3 velas e retorna o sinal da MAIORIA."""
    cores = [candle_1, candle_2, candle_3]
    verdes = cores.count('VERDE')
    vermelhas = cores.count('VERMELHA')
    if verdes > vermelhas: return 'CALL'
    elif vermelhas > verdes: return 'PUT'
    else: return 'NONE'

#------- ESTRATEGIAS------------

def estrategia_MHI_1(df):
    df['sinal'] = 'NONE'
    for i in range(4, len(df)):
        if df['datetime'].iloc[i].minute % 5 == 4: # Gatilho em 12:04
            sinal = get_minority_signal(
                df['cor'].iloc[i-2], # Vela 12:02
                df['cor'].iloc[i-1], # Vela 12:03
                df['cor'].iloc[i]    # Vela 12:04
            )
            # O catalogador verifica i+1 (12:05)
            if sinal != 'NONE':
                df.loc[df.index[i], 'sinal'] = sinal
    return df

def estrategia_MHI_2(df):
    df['sinal'] = 'NONE'
    for i in range(5, len(df)):
        if df['datetime'].iloc[i].minute % 5 == 0: # Gatilho em 12:05
            sinal = get_minority_signal(
                df['cor'].iloc[i-3], # Vela 12:02
                df['cor'].iloc[i-2], # Vela 12:03
                df['cor'].iloc[i-1]  # Vela 12:04
            )
            # O catalogador verifica i+1 (12:06)
            if sinal != 'NONE':
                df.loc[df.index[i], 'sinal'] = sinal
    return df

def estrategia_MHI_3(df):
    df['sinal'] = 'NONE'
    for i in range(6, len(df)):
        if df['datetime'].iloc[i].minute % 5 == 1: # Gatilho em 12:06
            sinal = get_minority_signal(
                df['cor'].iloc[i-4], # Vela 12:02
                df['cor'].iloc[i-3], # Vela 12:03
                df['cor'].iloc[i-2]  # Vela 12:04
            )
            # O catalogador verifica i+1 (12:07)
            if sinal != 'NONE':
                df.loc[df.index[i], 'sinal'] = sinal
    return df


def estrategia_R7(df):
    df['sinal'] = 'NONE'
    for i in range(7, len(df)): # Precisa de pelo menos 7 velas anteriores
        if df['datetime'].iloc[i].minute % 5 == 0: # Gatilho em 12:05
            # Referências são 11:58 (i-7) e 11:59 (i-6)
            cor_ref_1 = df['cor'].iloc[i-6] # Vela 11:59
            cor_ref_2 = df['cor'].iloc[i-7] # Vela 11:58
            sinal = 'NONE'
            if cor_ref_1 == 'VERDE' and cor_ref_2 == 'VERDE':
                sinal = 'CALL'
            elif cor_ref_1 == 'VERMELHA' and cor_ref_2 == 'VERMELHA':
                sinal = 'PUT'
            # O catalogador verifica i+1 (12:06)
            if sinal != 'NONE':
                df.loc[df.index[i], 'sinal'] = sinal
    return df

def estrategia_Torres_Gemeas(df):
    df['sinal'] = 'NONE'
    for i in range(3, len(df)):
        # Gatilho na vela 'i' (ex: 12:03)
        cor_sinal = df['cor'].iloc[i-3] # Vela 12:00
        cor_t1 = df['cor'].iloc[i-2]    # Vela 12:01
        cor_t2 = df['cor'].iloc[i-1]    # Vela 12:02
        cor_t3 = df['cor'].iloc[i]      # Vela 12:03
        sinal = 'NONE'
        if (cor_sinal == 'VERMELHA' and cor_t1 == 'VERDE' and cor_t2 == 'VERDE' and cor_t3 == 'VERDE'):
            sinal = 'PUT'
        elif (cor_sinal == 'VERDE' and cor_t1 == 'VERMELHA' and cor_t2 == 'VERMELHA' and cor_t3 == 'VERMELHA'):
            sinal = 'CALL'
        # O catalogador verifica i+1 (12:04)
        if sinal != 'NONE':
            df.loc[df.index[i], 'sinal'] = sinal
    return df

def estrategia_Padrao_3x1(df):
    df['sinal'] = 'NONE'
    for i in range(3, len(df)):
        if df['datetime'].iloc[i].minute % 5 == 3: # Gatilho em 12:03
            sinal = get_minority_signal(
                df['cor'].iloc[i-3], # Vela 12:00
                df['cor'].iloc[i-2], # Vela 12:01
                df['cor'].iloc[i-1]  # Vela 12:02
            )
            # O catalogador verifica i+1 (12:04)
            if sinal != 'NONE':
                df.loc[df.index[i], 'sinal'] = sinal
    return df

def estrategia_Padrao_23(df):
    df['sinal'] = 'NONE'
    for i in range(len(df)):
        if df['datetime'].iloc[i].minute % 5 == 0: # Gatilho em 12:00
            cor_ref = df['cor'].iloc[i] # Vela 12:00
            sinal = 'NONE'
            if cor_ref == 'VERDE':
                sinal = 'CALL'
            elif cor_ref == 'VERMELHA':
                sinal = 'PUT'
            # O catalogador verifica i+1 (12:01)
            if sinal != 'NONE':
                df.loc[df.index[i], 'sinal'] = sinal
    return df

def estrategia_Tres_Mosqueteiros(df):
    df['sinal'] = 'NONE'
    for i in range(2, len(df)):
        if df['datetime'].iloc[i].minute % 5 == 2: # Gatilho em 12:02
            sinal = get_majority_signal(
                df['cor'].iloc[i-2], # Vela 12:00
                df['cor'].iloc[i-1], # Vela 12:01
                df['cor'].iloc[i]    # Vela 12:02
            )
            # O catalogador verifica i+1 (12:03)
            if sinal != 'NONE':
                df.loc[df.index[i], 'sinal'] = sinal
    return df


def estrategia_Melhor_de_3(df):
    df['sinal'] = 'NONE'
    for i in range(5, len(df)): # Ajustado o range
        if df['datetime'].iloc[i].minute % 5 == 0: # Gatilho em 12:05 (vela 1 do Q2)
            sinal = get_majority_signal(
                df['cor'].iloc[i-4], # Vela 12:01 (vela 2 do Q1)
                df['cor'].iloc[i-3], # Vela 12:02 (vela 3 do Q1)
                df['cor'].iloc[i-2]  # Vela 12:03 (vela 4 do Q1)
            )
            # O catalogador verifica i+1 (12:06)
            if sinal != 'NONE':
                df.loc[df.index[i], 'sinal'] = sinal 
        return df
#-----------------FIM DAS ESTRATEGIAS------------------

def estrategia_Seven_Flip(df):
    df['sinal'] = 'NONE'
    for i in range(6, len(df)): # 'i' é a Vela 7 (ex: 12:06)
        # Lista de 12:00 (i-6) a 12:06 (i)
        cores_7 = [df['cor'].iloc[k] for k in range(i-6, i+1)]
        sinal = 'NONE'
        
        # Verifica se todas as 7 são verdes (ignorando Dojis)
        verdes_validas = [c for c in cores_7 if c == 'VERDE']
        if len(verdes_validas) == 7 and all(c != 'VERMELHA' for c in cores_7):
             sinal = 'PUT' # Flip
        
        # Verifica se todas as 7 são vermelhas (ignorando Dojis)
        vermelhas_validas = [c for c in cores_7 if c == 'VERMELHA']
        if len(vermelhas_validas) == 7 and all(c != 'VERDE' for c in cores_7):
             sinal = 'CALL' # Flip
        
        # O catalogador verifica i+1 (12:07)
        if sinal != 'NONE':
            df.loc[df.index[i], 'sinal'] = sinal
    return df

# --- 4. O CATALOGADOR (BACKTESTER) ---

def catalogar_estrategia(par, df_com_sinais, nome_estrategia, max_gale=2):
    """Executa o backtest, imprime detalhes e armazena o resultado final."""
    
    global resultados_finais

    nome_exibicao = nome_estrategia.replace('estrategia_', '').replace('_', ' ').title()
    print(f"\n{C_STRATEGY}📊 Catalogando: {nome_exibicao}{C_RESET}")
    v0, v1, v2, loss, total = 0, 0, 0, 0, 0
    
    # Garante que não vamos ler além dos limites do DataFrame
    limite_loop = len(df_com_sinais) - (max_gale + 1) 
    
    for i in range(limite_loop):
        sinal = df_com_sinais['sinal'].iloc[i]
        if sinal == 'NONE': continue
        
        total += 1
        
        if sinal == 'CALL':
            if df_com_sinais['cor'].iloc[i+1]=='VERDE': v0+=1
            elif df_com_sinais['cor'].iloc[i+2]=='VERDE': v1+=1
            elif df_com_sinais['cor'].iloc[i+3]=='VERDE': v2+=1
            else: loss+=1
        elif sinal == 'PUT':
            if df_com_sinais['cor'].iloc[i+1]=='VERMELHA': v0+=1
            elif df_com_sinais['cor'].iloc[i+2]=='VERMELHA': v1+=1
            elif df_com_sinais['cor'].iloc[i+3]=='VERMELHA': v2+=1
            else: loss+=1

    if total == 0:
        print(f"{C_DIM}  Nenhum sinal encontrado.{C_RESET}")
        resultados_finais.append({'par': par, 'estrategia': nome_exibicao, 'assertividade': 0.0, 'sinais': 0})
        return

    v_total = v0 + v1 + v2
    assertividade = (v_total / total) * 100 if total > 0 else 0

    print(f"{C_DIM}  -----------------------------{C_RESET}")
    print(f"  Total de Sinais: {total:>10}")
    print(f"  {C_SUCCESS}Vitórias Mão 1:{v0:>11}{C_RESET}")
    print(f"  {C_SUCCESS}Vitórias Gale 1:{v1:>10}{C_RESET}")
    print(f"  {C_SUCCESS}Vitórias Gale 2:{v2:>10}{C_RESET}")
    print(f"  {C_ERROR}Derrotas (Loss):{loss:>10}{C_RESET}")
    print(f"{C_DIM}  -----------------------------{C_RESET}")
    print(f"  {C_BOLD}{C_SUCCESS}Total Vitórias: {v_total:>11}{C_RESET}")
    print(f"  {C_BOLD}{C_SUCCESS}Assertividade: {assertividade:>10.2f}%{C_RESET}")
    print(f"{C_DIM}  ============================={C_RESET}")

    resultados_finais.append({'par': par, 'estrategia': nome_exibicao, 'assertividade': assertividade, 'sinais': total})

# --- 5. EXECUÇÃO PRINCIPAL ---

if __name__ == "__main__":
    print(f"{C_HEADER}--- Login do Catalogador IQ Option ---{C_RESET}")
    EMAIL = input(f"Digite seu email: {C_BOLD}"); print(C_RESET, end='')
    SENHA = getpass.getpass("Digite sua senha (não aparecerá): ")

    pares_originais = ["EURUSD", "GBPUSD", "EURJPY", "AUDCAD", "USDCAD", "AUDCHF", "USDJPY", "USDCHF", "EURGBP", "EURAUD", "EURCAD", "EURCHF", "AUDJPY", "AUDNZD", "NZDJPY"]
    pares_otc = [par + "-OTC" for par in pares_originais]
    PARES_PARA_CATALOGAR = pares_originais + pares_otc
    TIMEFRANE_SEGUNDOS = 60
    QUANTIDADE_VELAS = 240 # Cerca de 4 horas de M1

    TODAS_AS_ESTRATEGIAS = [
        estrategia_MHI_1, estrategia_MHI_2, estrategia_MHI_3,
        estrategia_R7, estrategia_Torres_Gemeas, estrategia_Padrao_3x1,
        estrategia_Padrao_23, estrategia_Tres_Mosqueteiros,
        estrategia_Melhor_de_3, estrategia_Seven_Flip
    ]

    
    while True:
        # Reseta a lista de resultados a cada novo ciclo
        resultados_finais = [] 
        
        print(f"\n{C_HEADER}=== NOVO CICLO DE CATALOGAÇÃO (Iniciando {datetime.now().strftime('%H:%M:%S')}) ==={C_RESET}")

        api = conectar_api(EMAIL, SENHA)

        if api:
            print(f"\n{C_HEADER}--- Iniciando Catalogação ---{C_RESET}")
            print(f"{C_DIM}Pares a serem analisados: {', '.join(PARES_PARA_CATALOGAR)}{C_RESET}")

            for par in PARES_PARA_CATALOGAR:
                print(f"\n{C_DIM}##################################################{C_RESET}")
                print(f"{C_HEADER}Iniciando catalogação para o par: {C_PAIR}{par}{C_RESET}")
                print(f"{C_DIM}##################################################{C_RESET}")
                df_velas = buscar_velas(api, par, TIMEFRANE_SEGUNDOS, QUANTIDADE_VELAS)
                
                if df_velas is None or df_velas.empty:
                    print(f"{C_WARN}Pulando {par} por falta de dados ou erro.{C_RESET}")
                    for func_estrategia in TODAS_AS_ESTRATEGIAS:
                         nome_exibicao = func_estrategia.__name__.replace('estrategia_', '').replace('_', ' ').title()
                         resultados_finais.append({'par': par, 'estrategia': nome_exibicao, 'assertividade': 'N/A', 'sinais': 0})
                    continue
                
                for func_estrategia in TODAS_AS_ESTRATEGIAS:
                    df_copia = df_velas.copy()
                    df_com_sinais = func_estrategia(df_copia)
                    catalogar_estrategia(par, df_com_sinais, func_estrategia.__name__, max_gale=2)

            print(f"\n{C_SUCCESS}🎉 Catalogação Detalhada Concluída! 🎉{C_RESET}")

            print(f"\n\n{C_HEADER}--- SUMÁRIO FINAL DE ASSERTIVIDADE (%) ---{C_RESET}")
            resultados_agrupados = defaultdict(list)
            for res in resultados_finais: resultados_agrupados[res['par']].append(res)
            
            for par, resultados_do_par in resultados_agrupados.items():
                print(f"\n{C_PAIR}📊 Par: {par}{C_RESET}")
                resultados_do_par.sort(key=lambda x: x['assertividade'] if isinstance(x['assertividade'], (int, float)) else -1, reverse=True)
                for res in resultados_do_par:
                    estrategia = res['estrategia']; assertividade = res['assertividade']; sinais = res['sinais']
                    cor_assertividade = C_DIM
                    if isinstance(assertividade, (int, float)) and sinais > 0:
                        if assertividade >= 90: cor_assertividade = C_SUCCESS + Style.BRIGHT
                        elif assertividade >= 80: cor_assertividade = C_SUCCESS
                        elif assertividade >= 70: cor_assertividade = C_WARN
                        else: cor_assertividade = C_ERROR
                    assertividade_str = f"{assertividade:.2f}%" if isinstance(assertividade, (int, float)) else f"{C_DIM}{assertividade}{C_RESET}"
                    print(f"  {C_STRATEGY}{estrategia:<25}{C_RESET} {cor_assertividade}{assertividade_str:>10}{C_RESET} {C_DIM}({sinais} sinais){C_RESET}")
            print(f"\n{C_DIM}-----------------------------------------{C_RESET}")
        
        else:
            print(f"\n{C_ERROR}Não foi possível conectar. Tentando novamente em 5 minutos...{C_RESET}")

        
        print(f"\n{C_BOLD}Ciclo concluído. Aguardando 5 minutos para reiniciar... (Pressione Ctrl+C para parar){C_RESET}")
        try:
            time.sleep(300) 
        except KeyboardInterrupt:
            print(f"\n{C_WARN}Loop interrompido pelo usuário. Fechando...{C_RESET}")
            break