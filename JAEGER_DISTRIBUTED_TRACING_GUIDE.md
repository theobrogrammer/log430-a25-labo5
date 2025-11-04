# 🔍 Guide Jaeger Distributed Tracing - Labo 5

## 🎯 **Pourquoi utiliser Jaeger ?**

### **Le problème des microservices**

Imaginez cette situation :
```
Client fait une requête → KrakenD → Store Manager → Payment Service
                                 ↓
                              Timeout ! ❌
```

**Sans Jaeger** : "Quelque chose ne marche pas, mais où ?"
- Le client voit une erreur 500
- Chaque service a ses propres logs
- Impossible de suivre UNE requête à travers TOUS les services
- Debugging = chercher une aiguille dans une meule de foin 🔍

**Avec Jaeger** : Vue complète du parcours de CHAQUE requête !

### **Les défis qu'on résout avec Jaeger**

1. **"Où est le problème ?"** 🤔
   - Service A fonctionne (2ms)
   - Service B fonctionne (5ms) 
   - Service C est lent (500ms) ← **Le coupable !**

2. **"Combien de temps ça prend ?"** ⏱️
   - Requête totale : 507ms
   - Breakdown détaillé par service
   - Identification des goulots d'étranglement

3. **"Quelle requête a échoué ?"** 🔍
   - Trace ID unique pour chaque requête
   - Suivi d'une transaction spécifique
   - Context propagation entre services

---

## 🔧 **Ce qu'on a implémenté dans le code**

### **1. Configuration Jaeger (Infrastructure)**

#### **`docker-compose.yml` - Le collecteur**
```yaml
jaeger:
  image: jaegertracing/all-in-one:latest
  ports:
    - "16686:16686"  # Interface web
    - "4317:4317"    # Réception des traces (OTLP)
```
**Pourquoi ?** Jaeger doit recevoir et stocker toutes les traces des services.

#### **`requirements.txt` - Les dépendances**
```python
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-grpc
opentelemetry-instrumentation-flask
opentelemetry-instrumentation-requests
```
**Pourquoi ?** Ces librairies permettent à Python de créer et envoyer des traces.

#### **`src/tracing_config.py` - Configuration centrale**
```python
resource = Resource.create({
   "service.name": "store-manager",  # Identifier le service
   "service.version": "1.0.0"
})

otlp_exporter = OTLPSpanExporter(
   endpoint="http://jaeger:4317",  # Où envoyer les traces
   insecure=True
)
```
**Pourquoi ?** Chaque service doit dire à Jaeger "qui il est" et "où envoyer les traces".

### **2. Instrumentation automatique (Flask + Requests)**

```python
FlaskInstrumentor().instrument_app(app)  # Trace automatique des endpoints
RequestsInstrumentor().instrument()      # Trace automatique des appels HTTP
```

**Ce que ça fait automatiquement :**
- ✅ Chaque endpoint Flask = 1 span
- ✅ Chaque appel `requests.post()` = 1 span
- ✅ Headers de tracing propagés entre services

### **3. Spans manuels (Business Logic)**

#### **Dans `order_controller.py` (Couche API)**
```python
with tracer.start_as_current_span("POST /orders") as span:
    span.set_attribute("user.id", user_id)
    span.set_attribute("order.items_count", len(items))
    span.set_attribute("http.status_code", 201)
    
    order_id = add_order(user_id, items)  # Appel à la logique métier
```

**Pourquoi ces spans ?**
- 📊 **Mesurer la latence** de chaque endpoint
- 🏷️ **Ajouter du contexte métier** (user_id, order_id)
- ❌ **Tracer les erreurs** avec attributs détaillés

#### **Dans `write_order.py` (Logique métier)**
```python
with tracer.start_as_current_span("add_order") as span:
    span.set_attribute("order.total_amount", total_amount)
    
    # Appel au service de paiement
    with tracer.start_as_current_span("payment-service-call") as nested_span:
        response = requests.post('http://api-gateway:8080/payments-api/payments', ...)
        nested_span.set_attribute("http.status_code", response.status_code)
```

**Pourquoi cette hiérarchie ?**
```
POST /orders (120ms)
├─ add_order (115ms)
│  ├─ database_operations (10ms)
│  └─ payment-service-call (100ms)  ← Le plus lent !
└─ json_serialization (5ms)
```

### **4. Configuration KrakenD (API Gateway)**

#### **OpenTelemetry dans `krakend.json`**
```json
"extra_config": {
  "telemetry/opentelemetry": {
    "service_name": "krakend-gateway",
    "exporters": {
      "otlp": [
        {
          "name": "jaeger",
          "host": "jaeger",
          "port": 4317
        }
      ]
    }
  }
}
```

#### **Propagation des headers**
```json
{
  "endpoint": "/store-api/orders",
  "input_headers": ["*"]  # ← CRUCIAL pour la propagation !
}
```

**Pourquoi `input_headers: ["*"]` ?**
Sans ça, KrakenD bloque les headers de tracing → traces cassées ! 🚫

---

## 🔄 **Comment ça marche en pratique**

### **1. Le client fait une requête**
```bash
curl -X POST http://localhost:8080/store-api/orders -d '{"user_id":1,...}'
```

### **2. Propagation du contexte de tracing**
```
1. Client → KrakenD
   Headers: [génère trace-id: abc123, span-id: def456]

2. KrakenD → Store Manager  
   Headers: [trace-id: abc123, parent-span: def456, span-id: ghi789]

3. Store Manager → Payment Service
   Headers: [trace-id: abc123, parent-span: ghi789, span-id: jkl012]
```

**Le même `trace-id` relie toutes les operations !** 🔗

### **3. Résultat dans Jaeger**
```
Trace ID: abc123 (UNIQUE pour cette requête)
├─ krakend-gateway: POST /store-api/orders [150ms]
├─ store-manager: POST /orders [145ms]
│  ├─ add_order [140ms]
│  │  └─ payment-service-call [120ms]
│  └─ Redis operations [5ms]
└─ payment-service: POST /payments [115ms]
   ├─ create_payment [110ms]
   └─ database_insert [20ms]
```

---

## 💡 **Pourquoi c'est révolutionnaire**

### **Avant Jaeger (Debugging traditionnel)**
```bash
# Chercher dans chaque service séparément
docker logs store_manager | grep "user_id:1"
docker logs payments_api | grep "user_id:1" 
docker logs api-gateway | grep "POST"

# Essayer de reconstituer manuellement la timeline 😰
```

### **Avec Jaeger (Distributed tracing)**
```
1. Aller sur http://localhost:16686
2. Chercher par "user_id:1" ou "error:true"
3. Voir INSTANTANÉMENT le parcours complet ✨
4. Cliquer sur un span → détails précis
```

### **Exemples concrets d'utilisation**

#### **Scenario 1: Performance**
```
"Pourquoi mes commandes sont lentes ?"

Jaeger montre:
├─ Store Manager: 50ms    ✅ Rapide
├─ Payment Service: 2000ms ❌ PROBLÈME ICI !
└─ Database query: 1950ms  ← Requête SQL lente
```

#### **Scenario 2: Erreurs**
```
"Commande 123 a échoué, pourquoi ?"

Jaeger montre:
├─ Store Manager: Success
├─ Payment Service: ERROR ❌
│  └─ error.message: "Insufficient funds"
│  └─ user.balance: 10.50
│  └─ order.amount: 150.00
```

#### **Scenario 3: Rate limiting**
```
"Certaines requêtes sont rejetées"

Jaeger montre:
├─ KrakenD: HTTP 503 ❌
│  └─ error.message: "rate limit exceeded"
│  └─ client.ip: 192.168.1.100
├─ Store Manager: [SPAN MANQUANT]  ← Requête bloquée
```

---

## 🎯 **Valeur métier**

### **Pour les développeurs**
- ⚡ **Debugging 10x plus rapide**
- 🔍 **Root cause analysis précise**
- 📊 **Metrics de performance en temps réel**

### **Pour l'équipe**
- 🚨 **Alertes proactives** sur la latence
- 📈 **Optimisation data-driven**
- 🔒 **SLA monitoring** automatique

### **Pour le business**
- 💰 **Moins de downtime** = plus de revenus
- 😊 **Meilleure expérience utilisateur**
- 🚀 **Déploiements plus confiants**

---

## 🔮 **En production**

### **Échantillonnage intelligent**
```python
# Ne pas tracer 100% des requêtes (performance)
sampler = TraceIdRatioBasedSampler(rate=0.1)  # 10% des traces
```

### **Corrélation avec logs/métriques**
```python
# Dans les logs, inclure le trace_id
logger.info(f"Order created", extra={
    "trace_id": current_span().get_span_context().trace_id,
    "user_id": user_id
})
```

### **Alerting automatique**
```
Si latence > 1000ms ET error_rate > 5%
→ Alerte Slack: "Payment service dégradé !"
```

---

## ✅ Configuration terminée

Jaeger a été intégré avec succès dans l'architecture microservices :

### **Services configurés**
- ✅ **Jaeger UI** : http://localhost:16686
- ✅ **Store Manager** : Spans dans endpoints et logique métier
- ✅ **KrakenD Gateway** : Configuration OpenTelemetry
- ✅ **Payment Service** : (déjà configuré)
- ✅ **Saga Orchestrator** : (déjà configuré)

---

## 🎯 **Spans implémentés dans Store Manager**

### **1. Couche Controller (order_controller.py)**
```python
# Endpoints HTTP avec attributs métier
- POST /orders     → span "POST /orders"
- PUT /orders      → span "PUT /orders" 
- GET /orders/{id} → span "GET /orders/{id}"

# Attributs tracés :
- user.id, order.id, order.items_count
- http.method, http.route, http.status_code
- error (true/false), error.message
```

### **2. Couche Métier (write_order.py)**
```python
# Logique métier et appels externes
- add_order()              → span "add_order"
- request_payment_link()   → span "payment-service-call"

# Attributs tracés :
- order.total_amount, payment.amount
- order.product_ids, order.success
- Service externe : appel au Payment Service
```

---

## 🚀 **Comment tester le tracing**

### **1. Créer une commande**
```bash
curl -X POST http://localhost:8080/store-api/orders \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"items":[{"product_id":1,"quantity":2}]}'
```

### **2. Vérifier dans Jaeger UI**
1. Ouvrir : http://localhost:16686
2. Service : `store-manager`
3. Cliquer sur "Find Traces"
4. Vous devriez voir une trace avec les spans imbriqués :

```
POST /orders (Controller)
├─ add_order (Business Logic)
│  └─ payment-service-call (External Service)
└─ Response
```

### **3. Analyser les détails**
Cliquez sur une trace pour voir :
- **Durée totale** de la requête
- **Durée de chaque span** (endpoint, DB, service externe)
- **Attributs** : user_id, order_id, total_amount, etc.
- **Erreurs** s'il y en a (span en rouge)

---

## 📊 **Exemple de trace complète**

```
Trace ID: abc123...
Total Duration: 245ms

├─ POST /orders                    [240ms] 
│  ├─ user.id: 1
│  ├─ order.items_count: 1
│  ├─ http.method: POST
│  └─ http.status_code: 201
│
├─ add_order                       [235ms]
│  ├─ order.id: 9
│  ├─ order.total_amount: 50.0
│  ├─ order.product_ids: [1]
│  └─ order.success: true
│
└─ payment-service-call            [120ms]
   ├─ order.id: 9
   ├─ payment.amount: 50.0
   ├─ user.id: 1
   └─ http.status_code: 201
```

---

## 🔗 **Architecture de tracing complète**

```
Client Request
    ↓
KrakenD Gateway (avec OpenTelemetry)
    ↓
Store Manager
├─ order_controller.py (HTTP Spans)
└─ write_order.py (Business Logic Spans)
    ↓
Payment Service (via KrakenD)
├─ payment_controller.py (HTTP Spans)
└─ payment_logic.py (Business Logic Spans)
    ↓
Saga Orchestrator
├─ orchestrator_controller.py (HTTP Spans)
└─ saga_logic.py (Business Logic Spans)
    ↓
Jaeger Collector (port 4317)
    ↓
Jaeger UI (port 16686)
```

---

## ✨ **Résumé**

**Jaeger = "Google Analytics" pour vos microservices**

- **Visibilité** : Voir le parcours de chaque requête
- **Performance** : Mesurer précisément les temps de réponse  
- **Debugging** : Identifier instantanément les problèmes
- **Optimisation** : Prendre des décisions basées sur des données réelles

**Dans votre labo :** Vous pouvez maintenant comprendre exactement ce qui se passe quand une commande est créée, du clic client jusqu'à l'enregistrement en base ! 🎉

---

## 🎯 **Utilisation en production**

### **Avantages du distributed tracing :**
- **Debugging** : Identifier rapidement où une requête échoue
- **Performance** : Mesurer la latence de chaque service
- **Monitoring** : Alertes sur les temps de réponse élevés
- **Optimisation** : Identifier les services les plus lents

### **Best practices :**
- Ajouter des **attributs métier** pertinents (user_id, order_id)
- Tracer les **appels externes** (DB, API, microservices)
- **Échantillonner** les traces en production (1-10%)
- **Corréler** avec les logs et métriques

---

## ✅ **Status : Implémentation réussie !**

🎉 Jaeger est maintenant opérationnel dans votre architecture microservices labo5 !

**Testez dès maintenant :** http://localhost:16686