import paho.mqtt.client as mqtt
import pandas as pd
import time
import random
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl


BROKER = "broker.hivemq.com"
PORTA = 1883
TOPICO_TEMP = "incubadora_jess1801/temperatura"
TOPICO_PWM = "incubadora_jess1801/pwm_atuacao"
TOPICO_SETPOINT = "incubadora_jess1801/setpoint"


temperatura_atual = 25.0
setpoint_alvo = 36.8  # SP2 Padrão Inicial
atuacao_pwm = 0.0
erro_anterior = 0.0
t_ambiente = 25.0


erro = ctrl.Antecedent(np.arange(-15, 15.1, 0.1), 'erro')
# Entrada 2: Variação do Erro (-5°C a +5°C)
delta_erro = ctrl.Antecedent(np.arange(-5, 5.1, 0.1), 'delta_erro')
# Saída: Atuação PWM (0% a 100%)
atuacao = ctrl.Consequent(np.arange(0, 101, 1), 'atuacao')

erro['negativo'] = fuzz.trapmf(erro.universe, [-15, -15, -1.5, 0.0])
erro['zero'] = fuzz.trimf(erro.universe, [-1.5, 0.0, 1.5])
erro['positivo'] = fuzz.trapmf(erro.universe, [0.0, 1.5, 15, 15])

delta_erro['diminuendo'] = fuzz.trapmf(delta_erro.universe, [-5.0, -5.0, -0.5, 0.0])
delta_erro['estavel'] = fuzz.trimf(delta_erro.universe, [-0.5, 0.0, 0.5])
delta_erro['crescendo'] = fuzz.trapmf(delta_erro.universe, [0.0, 0.5, 5.0, 5.0])

atuacao['desligado'] = fuzz.trimf(atuacao.universe, [0, 0, 10])
atuacao['fraco'] = fuzz.trimf(atuacao.universe, [5, 25, 50])
atuacao['medio'] = fuzz.trimf(atuacao.universe, [35, 55, 75])
atuacao['forte'] = fuzz.trapmf(atuacao.universe, [60, 85, 100, 100])

rule1 = ctrl.Rule(erro['positivo'] & delta_erro['crescendo'], atuacao['forte'])
rule2 = ctrl.Rule(erro['positivo'] & delta_erro['estavel'], atuacao['medio'])
rule3 = ctrl.Rule(erro['positivo'] & delta_erro['diminuendo'], atuacao['fraco'])
rule4 = ctrl.Rule(erro['zero'] & delta_erro['estavel'], atuacao['fraco'])
rule5 = ctrl.Rule(erro['zero'] & delta_erro['diminuendo'], atuacao['desligado'])
rule6 = ctrl.Rule(erro['negativo'], atuacao['desligado'])

sistema_controle = ctrl.ControlSystem([rule1, rule2, rule3, rule4, rule5, rule6])
simulador_fuzzy = ctrl.ControlSystemSimulation(sistema_controle)

def planta_termica(temp_atual, potencia_pwm):
    ganho = potencia_pwm * 0.15
    perda = (temp_atual - t_ambiente) * 0.09
    return temp_atual + ((ganho - perda) * 0.06)


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("[MQTT] Conectado com sucesso ao Broker HiveMQ!")
        client.subscribe(TOPICO_SETPOINT)
        print(f"[MQTT] Inscrito no tópico de comandos: {TOPICO_SETPOINT}")
    else:
        print(f"[MQTT] Falha na conexão. Código de erro: {rc}")

def on_message(client, userdata, msg):
    global setpoint_alvo
    try:
        payload = msg.payload.decode()
        novo_sp = float(payload)
        if 30.0 <= novo_sp <= 42.0:
            setpoint_alvo = novo_sp
            print(f"\n[NODE-RED] Novo SetPoint recebido via Dashboard: {setpoint_alvo}°C")
    except ValueError:
        print("[ERRO] Payload de SetPoint inválido recebido.")

def executar_simulador():
    global temperatura_atual, atuacao_pwm, erro_anterior
    
    # Configuração e Conexão do Cliente MQTT
    client_id = f"Simulador_Python_Fuzzy_{random.randint(1000, 9999)}"
    cliente = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    cliente.on_connect = on_connect
    cliente.on_message = on_message
    
    print("[INFO] Inicializando Motor Termodinâmico...")
    cliente.connect(BROKER, PORTA, keepalive=60)
    cliente.loop_start()  # Ativa escuta asgíncrona para capturar o SetPoint do Node-RED
    
    print("\n--- SIMULADOR RODANDO ---")
    print("Abra o painel do Node-RED em http://localhost:1880/ui para monitorar.")
    
    try:
        while True:
            erro_atual = setpoint_alvo - temperatura_atual
            v_erro = erro_atual - erro_anterior
            erro_anterior = erro_atual
            
            simulador_fuzzy.input['erro'] = np.clip(erro_atual, -15.0, 15.0)
            simulador_fuzzy.input['delta_erro'] = np.clip(v_erro, -5.0, 5.0)
            
            try:
                simulador_fuzzy.compute()
                atuacao_pwm = simulador_fuzzy.output['atuacao']
            except Exception:
                # Fallback de segurança caso as regras encontrem indefinição nas bordas
                atuacao_pwm = 0.0
                
            # Saturação de proteção física
            atuacao_pwm = np.clip(atuacao_pwm, 0.0, 100.0)
            
            # 3. Evolução Física da Planta Térmica Amortecida
            temperatura_atual = planta_termica(temperatura_atual, atuacao_pwm)
            temperatura_atual = np.clip(temperatura_atual, 20.0, 42.0)
            
            # 4. Publicação das Variáveis de Estado para o Node-RED
            str_temp = f"{temperatura_atual:.2f}"
            str_pwm = f"{atuacao_pwm:.1f}"
            
            cliente.publish(TOPICO_TEMP, str_temp, qos=1)
            cliente.publish(TOPICO_PWM, str_pwm, qos=1)
            
            print(f"[Estado] SP Alvo: {setpoint_alvo}°C | Temp Atual: {str_temp}°C | PWM: {str_pwm}%", end="\r")
            
            time.sleep(1.0)
            
    except KeyboardInterrupt:
        print("\n[INFO] Encerrando simulador...")
        cliente.loop_stop()
        cliente.disconnect()
        print("[INFO] Conexões finalizadas com sucesso.")

if __name__ == "__main__":
    executar_simulador()
