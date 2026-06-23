import streamlit as st
import pandas as pd
import time
import matplotlib.pyplot as plt
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

#StreamLit
st.set_page_config(page_title="Monitoramento - Incubadora NeoNatal", layout="wide")
st.title("Painel de Monitoramento")
st.subheader("Monitoramento de Temperatura")
st.caption("Modelo para medição de temperatura de uma incubadora para recém-nascidos")


if "temperatura" not in st.session_state:
    st.session_state.temperatura = 25.0

if "atuacao" not in st.session_state:
    st.session_state.atuacao = 0.0

if "setpoint_atual" not in st.session_state:
    st.session_state.setpoint_atual = 36.8

if "historico" not in st.session_state:
    st.session_state.historico = pd.DataFrame(columns=["Tempo", "Temperatura", "Atuação", "SetPoint"])

if "contador" not in st.session_state:
    st.session_state.contador = 0

#Configuracao do Fuzzy
erro = ctrl.Antecedent(np.arange(-20, 20.1, 0.1), 'erro')
atuacao = ctrl.Consequent(np.arange(0, 101, 1), 'atuacao')

# Funções de Pertinência da Entrada (Erro expandido com transições suaves)
erro['negativo'] = fuzz.trapmf(erro.universe, [-20, -20, -1.5, 0])
erro['zero'] = fuzz.trimf(erro.universe, [-1.5, 0, 1.5])
erro['positivo'] = fuzz.trapmf(erro.universe, [0, 1.5, 20, 20])

# Funções de Pertinência da Saída (PWM de Atuação)
atuacao['desligado'] = fuzz.trimf(atuacao.universe, [0, 0, 10])
atuacao['fraco'] = fuzz.trimf(atuacao.universe, [5, 25, 50])
atuacao['medio'] = fuzz.trimf(atuacao.universe, [35, 55, 75])
atuacao['forte'] = fuzz.trapmf(atuacao.universe, [60, 85, 100, 100])

# Base de Regras
rule1 = ctrl.Rule(erro['negativo'], atuacao['desligado'])
rule2 = ctrl.Rule(erro['zero'], atuacao['medio']) # Reajustado para manter calor no setpoint
rule3 = ctrl.Rule(erro['positivo'], atuacao['forte'])

# Inicialização do Sistema
sistema = ctrl.ControlSystem([rule1, rule2, rule3])
simulador = ctrl.ControlSystemSimulation(sistema)

def calcular_atuacao(erro_valor):
    # Garante que o erro fique dentro do novo universo expandido
    erro_saturado = np.clip(erro_valor, -20.0, 20.0)
    simulador.input['erro'] = erro_saturado
    simulador.compute()
    return simulador.output['atuacao']

#SetPoints
st.sidebar.header("🎯 Painel Médico (SetPoints)")

sp_selecionado = st.sidebar.radio(
    "Escolha o cenário de operação para o ensaio:",
    ("SP1 (36.2°C)", "SP2 (36.8°C)", "SP3 (37.4°C)"),
    index=1
)

novo_sp = 36.2 if "SP1" in sp_selecionado else (36.8 if "SP2" in sp_selecionado else 37.4)


if novo_sp != st.session_state.setpoint_atual:
    st.session_state.setpoint_atual = novo_sp
    st.session_state.temperatura = 25.0
    st.session_state.contador = 0
    st.session_state.historico = pd.DataFrame(columns=["Tempo", "Temperatura", "Atuação", "SetPoint"])

#Definição da Temperatura ambiente
t_ambiente = 25.0


#Calibração dos valores
def planta_termica(temp_atual, potencia_pwm):
    
    ganho = potencia_pwm * 0.15
    perda = (temp_atual - t_ambiente) * 0.95
    return temp_atual + (ganho - perda) * 0.1

#Ciclo de controle
erro_atual = st.session_state.setpoint_atual - st.session_state.temperatura

st.session_state.atuacao = calcular_atuacao(erro_atual)

st.session_state.temperatura = planta_termica(
    st.session_state.temperatura,
    st.session_state.atuacao
)

st.session_state.contador += 1
novo_ponto = pd.DataFrame([{
    "Tempo": st.session_state.contador,
    "Temperatura": st.session_state.temperatura,
    "Atuação": st.session_state.atuacao,
    "SetPoint": st.session_state.setpoint_atual
}])

st.session_state.historico = pd.concat([st.session_state.historico, novo_ponto], ignore_index=True)

if len(st.session_state.historico) > 80:
    st.session_state.historico = st.session_state.historico.iloc[1:].reset_index(drop=True)

#DashBoard visual
col1, col2, col3 = st.columns(3)
col1.metric("Temperatura Real na Estufa", f"{st.session_state.temperatura:.2f} °C")
col2.metric("SetPoint Clínico Alvo", f"{st.session_state.setpoint_atual:.2f} °C")
col3.metric("Potência do Aquecedor (PWM)", f"{st.session_state.atuacao:.1f} %")

if 36.0 <= st.session_state.temperatura <= 37.5:
    st.success("🟢 STATUS DO SISTEMA: NORMOTERMIA")
elif 35.0 <= st.session_state.temperatura < 36.0 or 37.5 < st.session_state.temperatura <= 38.0:
    st.warning("🟡 STATUS DO SISTEMA: ATENÇÃO (FORA DA ZONA IDEAL)")
else:
    st.error("🔴 STATUS DO SISTEMA: CRÍTICO")

st.markdown("---")

#LEDs
st.subheader("💡 Estado dos Sinalizadores Físicos (LEDs Virtuais)")
c_verde, c_vermelho = st.columns(2)

if 36.0 <= st.session_state.temperatura <= 37.5:
    c_verde.markdown("<div style='background-color: #2ecc71; padding: 15px; border-radius: 8px; text-align: center; color: white; font-weight: bold;'>🟢 LED VERDE: ACESO (Segurança Hospitalar)</div>", unsafe_allow_html=True)
    c_vermelho.markdown("<div style='background-color: #34495e; padding: 15px; border-radius: 8px; text-align: center; color: #7f8c8d;'>⚫ LED VERMELHO: APAGADO</div>", unsafe_allow_html=True)
else:
    c_verde.markdown("<div style='background-color: #34495e; padding: 15px; border-radius: 8px; text-align: center; color: #7f8c8d;'>⚫ LED VERDE: APAGADO</div>", unsafe_allow_html=True)
    c_vermelho.markdown("<div style='background-color: #e74c3c; padding: 15px; border-radius: 8px; text-align: center; color: white; font-weight: bold;'>🔴 LED VERMELHO: ACESO (Alarme Crítico Ativo)</div>", unsafe_allow_html=True)

st.markdown("---")

#Graficos
tab1, tab2 = st.tabs(["📊 Curvas Temporais", "🧠 Mapeamento Nebuloso (Fuzzy)"])

with tab1:
    st.subheader("Análise Dinâmica do Sistema de Controle")
    st.line_chart(
        st.session_state.historico.set_index("Tempo")[["Temperatura", "SetPoint"]]
    )
    st.caption("Perfil de Esforço do Atuador de Potência (%)")
    st.area_chart(
        st.session_state.historico.set_index("Tempo")["Atuação"]
    )

with tab2:
    st.subheader("Distribuição Matemática das Regras (scikit-fuzzy)")
    
    fig, ax = plt.subplots(figsize=(10, 4))
    x = erro.universe
    
    ax.plot(x, fuzz.trapmf(x, [-20, -20, -1.5, 0]), label="Erro Negativo", color='#e74c3c', linewidth=2)
    ax.plot(x, fuzz.trimf(x, [-1.5, 0, 1.5]), label="Erro Zero", color='#2ecc71', linewidth=2)
    ax.plot(x, fuzz.trapmf(x, [0, 1.5, 20, 20]), label="Erro Positivo", color='#3498db', linewidth=2)
    
    ax.axvline(erro_atual, color="black", linestyle="--", linewidth=1.5)
    ax.text(erro_atual + 0.4, 0.5, f'Erro Atual\n({erro_atual:.2f}°C)', color='black', fontweight='bold')
    
    ax.set_xlim([-10, 15]) # Foca o gráfico na área útil do erro de inicialização
    ax.set_title("Interseção Dinâmica do Erro nas Funções de Pertinência")
    ax.set_xlabel("Erro de Temperatura (°C)")
    ax.set_ylabel("Grau de Pertinência (μ)")
    ax.legend(loc='upper right')
    ax.grid(True, linestyle=':')
    
    st.pyplot(fig)

# Refresh controlado de 200ms para uma convergência fluida e rápida
time.sleep(0.2)
st.rerun()
