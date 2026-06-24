#include <WiFi.h>
#include <PubSubClient.h>

// --- PINOS DOS LEDS (Item 4.3 / Critérios do Relatório) ---
const int PIN_LED_VERDE = 18;     // Normotermia
const int PIN_LED_VERMELHO = 19;  // Alerta Crítico

// --- CONFIGURAÇÕES DE REDE E BROKER ---
const char* SSID = "Wokwi-GUEST"; // Padrão do simulador Wokwi
const char* PASSWORD = ""; 
const char* MQTT_BROKER = "broker.hivemq.com";
const int MQTT_PORTA = 1883;

// --- TÓPICOS MQTT ---
const char* TOPICO_PUBLISH_TEMP = "incubadora_jess1801/temperatura";
const char* TOPICO_PUBLISH_PWM  = "incubadora_jess1801/pwm_atuacao";
const char* TOPICO_SUBSCRIBE_SP = "incubadora_jess1801/setpoint";

// --- VARIÁVEIS DO MODELO TERMODINÂMICO ---
float temperaturaAtual = 25.0; 
float setpointAlvo = 36.8; // SP2 Padrão inicial     
float atuacaoPWM = 0.0;
float erroAnterior = 0.0;
const float TAmbiente = 25.0;  

unsigned long ultimoTempo = 0;
const long intervalo = 1000; // Amostragem de 1 segundo (1Hz)

WiFiClient espClient;
PubSubClient mqttClient(espClient);

// --- FUNÇÕES DE PERTINÊNCIA LINGUÍSTICA (FUZZIFICAÇÃO) ---
float pertinenciaTrapezio(float x, float a, float b, float c, float d) {

  if (x < a || x > d)
    return 0.0;

  if (x >= b && x <= c)
    return 1.0;

  if (x >= a && x < b) {

    if (b == a)
      return 1.0;

    return (x - a) / (b - a);
  }

  if (x > c && x <= d) {

    if (d == c)
      return 1.0;

    return (d - x) / (d - c);
  }

  return 0.0;
}

float pertinenciaTriangulo(float x, float a, float b, float c) {
  if (x <= a || x >= c) return 0.0;
  if (x == b) return 1.0;
  if (x > a && x < b) return (x - a) / (b - a);
  if (x > b && x < c) return (c - x) / (c - b);
  return 0.0;
}

void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.print("Conectando ao Wi-Fi virtual...");
  WiFi.begin(SSID, PASSWORD);
  
  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED && tentativas < 20) { 
    delay(200); 
    Serial.print(".");
    tentativas++;
  }
  if(WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[Wi-Fi] Conectado!");
  }
}

void conectarMQTT() {
  if (mqttClient.connected()) return;
  Serial.print("Tentando conexão MQTT...");
  String clientId = "ESP32_Incubadora_G_" + String(random(1000, 9999));
  
  if (mqttClient.connect(clientId.c_str())) {
    Serial.println("Conectado ao Broker!");
    mqttClient.subscribe(TOPICO_SUBSCRIBE_SP);
  } else {
    Serial.print("Falha. Erro = ");
    Serial.println(mqttClient.state());
  }
}

void callbackMQTT(char* topic, byte* payload, unsigned int length) {
  String mensagem = "";
  for (unsigned int i = 0; i < length; i++) { 
    mensagem += (char)payload[i]; 
  }
  
  if (String(topic) == TOPICO_SUBSCRIBE_SP) {
    float spRecebido = mensagem.toFloat();
    if (spRecebido >= 30.0 && spRecebido <= 40.0) { // Faixa real de operação segura
      setpointAlvo = spRecebido;
      Serial.print("-> Novo SetPoint recebido via Dashboard: ");
      Serial.println(setpointAlvo);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(10);
  
  pinMode(PIN_LED_VERDE, OUTPUT);
  pinMode(PIN_LED_VERMELHO, OUTPUT);
  
  digitalWrite(PIN_LED_VERDE, LOW);
  digitalWrite(PIN_LED_VERMELHO, LOW);

  mqttClient.setServer(MQTT_BROKER, MQTT_PORTA);
  mqttClient.setCallback(callbackMQTT);
  
  conectarWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) conectarWiFi();
  if (WiFi.status() == WL_CONNECTED && !mqttClient.connected()) conectarMQTT();
  
  mqttClient.loop();
  delay(5); // Amortecedor de CPU para o simulador Wokwi

  unsigned long tempoAtual = millis();
  if (tempoAtual - ultimoTempo >= intervalo) {
    ultimoTempo = tempoAtual;
    
    // 1. CÁLCULO DAS VARIÁVEIS DE ENTRADA EXIGIDAS (Item 4.4)
    float erro = setpointAlvo - temperaturaAtual;
    float deltaErro = erro - erroAnterior;
    erroAnterior = erro;
    
    // 2. FUZZIFICAÇÃO (Item 4.5)
    // Entrada 1: Erro (Faixa de -15 a 15)
    float e_negativo = pertinenciaTrapezio(erro, -15.0, -10.0, -1.5, 0.0);
    float e_zero     = pertinenciaTriangulo(erro, -1.5, 0.0, 1.5);
    float e_positivo = pertinenciaTrapezio(erro, 0.0, 1.5, 10.0, 15.0); 
    
    // Entrada 2: Variação do Erro (Faixa de -5 a 5)
    float v_diminuendo = pertinenciaTrapezio(deltaErro, -5.0, -3.0, -0.5, 0.0);
    float v_estavel    = pertinenciaTriangulo(deltaErro, -0.5, 0.0, 0.5);
    float v_crescendo  = pertinenciaTrapezio(deltaErro, 0.0, 0.5, 3.0, 5.0);
   
   
    // 3. INFERÊNCIA FUZZY (Mapeamento Base de Regras - Item 4.6)
    float r1 = min(e_positivo, v_crescendo);  // Erro positivo crescendo -> Atua forte
    float r2 = min(e_positivo, v_estavel);    // Erro positivo estável -> Atua médio
    float r3 = min(e_positivo, v_diminuendo); // Erro positivo diminuindo -> Atua fraco
    float r4 = min(e_zero, v_estavel);        // Erro próximo de zero e estável -> Atua fraco
    float r5 = min(e_zero, v_diminuendo);     // Erro em zero e diminuindo -> Desliga
    float r6 = e_negativo;                    // Temperatura acima do setpoint -> Desliga
    
    // Agregação das saídas linguísticas
    float out_desligado = max(r5, r6);
    float out_fraco     = max(r3, r4);
    float out_medio     = r2;
    float out_forte     = r1;
    
    // 4. DEFUZZIFICAÇÃO POR CENTROIDE DISCRETO (Item 4.7)
    float somaMomentos = 0.0;
    float somaAreas = 0.0;
    
    for (int x = 0; x <= 100; x += 5) { // Resolução de amostragem discreta de 5%
      float mu_desligado = pertinenciaTrapezio(x, 0, 0, 5, 15);
      float mu_fraco     = pertinenciaTriangulo(x, 10, 30, 50);
      float mu_medio     = pertinenciaTriangulo(x, 40, 60, 80);
      float mu_forte     = pertinenciaTrapezio(x, 70, 85, 95, 100);
      
      float mu_x = max(max(min(mu_desligado, out_desligado), min(mu_fraco, out_fraco)),
                       max(min(mu_medio, out_medio), min(mu_forte, out_forte)));
      
      somaMomentos += x * mu_x;
      somaAreas += mu_x;
    }
    
    // Saturação e salvamento da atuação calculada (Item 7)
    if (somaAreas > 0.0) {
      atuacaoPWM = somaMomentos / somaAreas;
    } else {
      atuacaoPWM = 0.0;
    }
    
    // 5. EQUAÇÃO DA PLANTA TERMODINÂMICA CALIBRADA (Item 4.8)
    if (atuacaoPWM < 0)
  atuacaoPWM = 0;

    if (atuacaoPWM > 100)
      atuacaoPWM = 100;

    float ganho_termico = (atuacaoPWM / 100.0) * 3.5;

    float perda_termica = (temperaturaAtual - TAmbiente) * 0.03;

temperaturaAtual =
temperaturaAtual +
(ganho_termico - perda_termica);

    temperaturaAtual += random(-5, 6) / 100.0;

    // Saturação física da planta para evitar valores impossíveis (Item 7)
    if (temperaturaAtual < 20.0) temperaturaAtual = 20.0;
    if (temperaturaAtual > 42.0) temperaturaAtual = 42.0;

    // --- ACIONAMENTO DOS SINALIZADORES FÍSICOS (LEDs) ---
    if (temperaturaAtual >= 36.0 && temperaturaAtual <= 37.5) { // Faixa de Normotermia
      digitalWrite(PIN_LED_VERDE, HIGH);   
      digitalWrite(PIN_LED_VERMELHO, LOW);
    } else { // Alerta de Hipotermia ou Hipertermia
      digitalWrite(PIN_LED_VERDE, LOW);
      digitalWrite(PIN_LED_VERMELHO, HIGH); 
    }
    Serial.print("SP=");
    Serial.print(setpointAlvo);

    Serial.print(" ERRO=");
    Serial.print(erro);

    Serial.print(" TEMP=");
    Serial.print(temperaturaAtual);

    Serial.print(" PWM=");
    Serial.println(atuacaoPWM);
    // 6. TRANSMISSÃO DOS DADOS VIA MQTT (Item 4.9)
    if (mqttClient.connected()) {
      String strTemp = String(temperaturaAtual, 2);
      String strPWM = String(atuacaoPWM, 1);
      
      mqttClient.publish(TOPICO_PUBLISH_TEMP, strTemp.c_str());
      mqttClient.publish(TOPICO_PUBLISH_PWM, strPWM.c_str());
    }
    
      }
}
