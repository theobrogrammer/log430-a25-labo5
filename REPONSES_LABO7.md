# LOG430 - Labo 7 : Réponses aux Questions

## 💡 Question 1 : Différences de Communication entre Services

### **Contexte**
Comparaison entre :
- **Communication store_manager ↔ coolriel** (Labo 7)
- **Communication store_manager ↔ payments_api** (Labo 5)

---

##  **Communication store_manager ↔ coolriel (Labo 7) : Event-Driven (Asynchrone)**

### **Pattern utilisé : Publish/Subscribe avec Kafka**

**Code dans `src/orders/commands/write_user.py` :**
```python
def add_user(name: str, email: str):
    """
    Insert user with items in MySQL
    
    PATTERN EVENT-DRIVEN: 
    1. Sauvegarde FIRST (transaction MySQL)
    2. Événement AFTER (fire-and-forget vers Kafka)
    
    Avantages de cette approche:
    - Si Kafka est down, l'utilisateur est quand même créé
    - Pas de rollback complexe entre MySQL et Kafka
    - Performance: pas d'attente de consumer
    """
    if not name or not email:
        raise ValueError("Cannot create user. A user must have name and email.")
    
    session = get_sqlalchemy_session()

    try: 
        # ÉTAPE 1: Transaction principale - Création utilisateur en base
        new_user = User(name=name, email=email)
        session.add(new_user)
        session.flush()  # Force l'obtention de l'ID avant commit
        session.commit()

        # ÉTAPE 2: ÉVÉNEMENT ASYNCHRONE - Publication vers Kafka
        # Note: Même si cette étape échoue, l'utilisateur reste créé
        # Contrairement à un appel HTTP synchrone qui pourrait forcer un rollback
        user_event_producer = UserEventProducer()
        user_event_producer.get_instance().send('user-events', value={
            'event': 'UserCreated',  # Type d'événement pour le routing
            'id': new_user.id, 
            'name': new_user.name,
            'email': new_user.email,
            'datetime': str(datetime.datetime.now())
        })
        # Pas d'attente de réponse - Fire and Forget!
        
        return new_user.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
```

**Code dans `coolriel/src/handlers/user_created_handler.py` :**
```python
def handle(self, event_data: Dict[str, Any]) -> None:
    """Create an HTML email based on user creation data"""
    user_id = event_data.get('id')
    name = event_data.get('name')
    email = event_data.get('email')
    datetime = event_data.get('datetime')
    
    # Génère le fichier HTML de bienvenue
    filename = os.path.join(self.output_dir, f"welcome_{user_id}.html")
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    self.logger.debug(f"Courriel HTML généré à {name} (ID: {user_id}), {filename}")
```

---

##  **Communication store_manager ↔ payments_api (Labo 5) : Synchrone HTTP**

### **Pattern utilisé : Request/Response HTTP**

**Code dans `src/orders/commands/write_order.py` :**
```python
def add_order(user_id: int, items: list):
    """Insert order with items in MySQL, keep Redis in sync"""
    # ... code de validation et calcul du total ...
    
    try:
        new_order = Order(user_id=user_id, total_amount=total_amount, payment_link=None)
        session.add(new_order)
        session.flush()   
        order_id = new_order.id

        # COMMUNICATION SYNCHRONE avec payments_api (Pattern HTTP Request/Response)
        # Contrairement à la création d'utilisateur qui utilise Kafka (asynchrone),
        # ici on ATTEND la réponse du service de paiement avant de continuer
        new_order.payment_link = request_payment_link(new_order.id, total_amount, user_id)
        session.flush()
        
        # ... reste du code ...
        session.commit()
        return order_id

def request_payment_link(order_id, total_amount, user_id):
    payment_transaction = {
        "user_id": user_id,
        "order_id": order_id,
        "total_amount": total_amount
    }
    
    # TODO: Appel HTTP synchrone réel vers payments_api
    # response = requests.post(
    #     "http://api-gateway:8080/payments-api/process", 
    #     json=payment_transaction,
    #     timeout=30
    # )
    
    # Retourne le lien de paiement - communication SYNCHRONE terminée
    return f"http://api-gateway:8080/payments-api/payments/process/{payment_id}"
```

---

## **Tableau Comparatif**

| **Aspect** | **Event-Driven (coolriel)** | **HTTP Synchrone (payments_api)** |
|------------|------------------------------|-----------------------------------|
| **Modèle** | Publish/Subscribe | Request/Response |
| **Transport** | Messages Kafka | HTTP REST |
| **Couplage temporel** | ❌ Faible (découplé) | ✅ Fort (couplé) |
| **Blocking** | ❌ Non-bloquant | ✅ Bloquant |
| **Résilience** | ✅ Tolérant aux pannes | ❌ Échoue si service down |
| **Performance** | ✅ Haute (asynchrone) | ❌ Dépend du service externe |
| **Complexité** | ❌ Plus complexe | ✅ Plus simple |
| **Debugging** | ❌ Flux asynchrone difficile | ✅ Flux linéaire facile |
| **Scalabilité** | ✅ Multiple consumers | ❌ Point-to-point |
| **Persistance** | ✅ Événements persistés | ❌ Pas de persistance automatique |

---

## ✅ **Avantages et Inconvénients**

### **Event-Driven (Kafka) :**

**✅ Avantages :**
- **Découplage temporel** : coolriel peut être offline, les événements sont persistés
- **Performance** : store_manager n'attend pas la réponse
- **Scalabilité** : Plusieurs consumers peuvent traiter les événements
- **Résilience** : Pas de perte d'événements grâce à la persistance Kafka
- **Auditabilité** : Historique complet des événements

**❌ Inconvénients :**
- **Complexité** : Infrastructure Kafka à gérer
- **Debugging** : Flux asynchrone plus difficile à tracer
- **Pas de feedback** : Pas de réponse immédiate en cas d'erreur
- **Eventual consistency** : Les données peuvent être temporairement incohérentes

### **HTTP Synchrone :**

**✅ Avantages :**
- **Simplicité** : Modèle request/response familier
- **Feedback immédiat** : Réponse et gestion d'erreur directe
- **Debugging facile** : Flux linéaire et prévisible
- **Consistency** : Cohérence immédiate des données

**❌ Inconvénients :**
- **Couplage fort** : Si payments_api est down, l'ordre échoue complètement
- **Performance** : Délai d'attente des appels HTTP
- **Point de défaillance** : Cascade d'échecs possible
- **Moins scalable** : Communication point-to-point

---

## 💡 Question 2 : Modifications dans `src/orders/commands/write_user.py`

### **Méthodes modifiées :**

#### **1. 🔧 Méthode `add_user()` - Signature mise à jour**

**Avant :**
```python
def add_user(name: str, email: str):
```

**Après :**
```python
def add_user(name: str, email: str, user_type_id: int = 1):
```

**Modifications apportées :**
- ✅ **Nouveau paramètre** : `user_type_id` avec valeur par défaut `1` (Client)
- ✅ **Validation** : Vérification que `user_type_id` est dans [1, 2, 3]
- ✅ **Création utilisateur** : Passage du `user_type_id` au modèle `User`
- ✅ **Événement Kafka** : Ajout de `user_type_id` dans le message

**Code complet mis à jour :**
```python
def add_user(name: str, email: str, user_type_id: int = 1):
    """Insert user with items in MySQL"""
    if not name or not email:
        raise ValueError("Cannot create user. A user must have name and email.")
    
    # Nouvelle validation pour les types d'utilisateur
    if user_type_id not in [1, 2, 3]:
        raise ValueError("Invalid user_type_id. Must be 1 (Client), 2 (Employee), or 3 (Manager).")
    
    session = get_sqlalchemy_session()
    try: 
        # Ajout du user_type_id au modèle User
        new_user = User(name=name, email=email, user_type_id=user_type_id)
        session.add(new_user)
        session.flush()
        session.commit()

        # Événement Kafka mis à jour avec user_type_id
        user_event_producer = UserEventProducer()
        user_event_producer.get_instance().send('user-events', value={
            'event': 'UserCreated',
            'id': new_user.id, 
            'name': new_user.name,
            'email': new_user.email,
            'user_type_id': new_user.user_type_id,  # NOUVEAU CHAMP
            'datetime': str(datetime.datetime.now())
        })
        return new_user.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
```

#### **2. 🔧 Méthode `delete_user()` - Complètement implémentée**

**Avant (TODO non implémenté) :**
```python
def delete_user(user_id: int):
    """Delete user in MySQL"""
    # ... code de suppression ...
    # TODO: envoyer un evenement UserDeleted à Kafka
```

**Après (Implémentation complète) :**
```python
def delete_user(user_id: int):
    """Delete user in MySQL"""
    session = get_sqlalchemy_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            # Récupération des données AVANT suppression pour l'événement
            user_name = user.name
            user_email = user.email
            user_type_id = user.user_type_id  # NOUVEAU CHAMP
            
            session.delete(user)
            session.commit()
            
            # Événement ASYNCHRONE UserDeleted vers Kafka - IMPLÉMENTÉ
            user_event_producer = UserEventProducer()
            user_event_producer.get_instance().send('user-events', value={
                'event': 'UserDeleted',
                'id': user_id,
                'name': user_name,
                'email': user_email,
                'user_type_id': user_type_id,  # NOUVEAU CHAMP
                'datetime': str(datetime.datetime.now())
            })
            
            return 1  
        else:
            return 0
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
```

### **3. 📊 Résumé des modifications :**

| **Aspect** | **Avant** | **Après** |
|------------|-----------|-----------|
| **Paramètres add_user** | `name, email` | `name, email, user_type_id=1` |
| **Validation** | Nom et email seulement | + Validation user_type_id |
| **Modèle User** | `User(name, email)` | `User(name, email, user_type_id)` |
| **Événement UserCreated** | Sans user_type_id | Avec user_type_id |
| **Événement UserDeleted** | TODO non implémenté | ✅ Complètement implémenté |
| **Données événement** | id, name, email, datetime | + user_type_id |

### **4. 🎯 Impact sur les consumers Kafka :**

**Handler UserCreated :**
- Peut maintenant recevoir et traiter le champ `user_type_id`
- Peut personnaliser le comportement selon le type d'utilisateur

**Handler UserDeleted (nouveau) :**
```python
class UserDeletedHandler(EventHandler):
    def get_event_type(self) -> str:
        return "UserDeleted"
    
    def handle(self, event_data: Dict[str, Any]) -> None:
        user_id = event_data.get('id')
        name = event_data.get('name')
        email = event_data.get('email')
        user_type_id = event_data.get('user_type_id')  # NOUVEAU CHAMP
        datetime_str = event_data.get('datetime')
        
        # Génère un email d'au revoir personnalisé
        # selon le type d'utilisateur
```

### **5. 🔒 Types d'utilisateur supportés :**
- **1 - Client** : Utilisateurs normaux (défaut)
- **2 - Employee** : Employés du magasin
- **3 - Manager** : Directeurs du magasin

---

## 💡 Question 3 : Implémentation de la Vérification du Type d'Utilisateur

La vérification du type d'utilisateur est implémentée à **plusieurs niveaux** pour assurer la cohérence et la personnalisation à travers tout le système event-driven.

### **1. 🔒 Validation côté Store Manager (`write_user.py`)**

#### **Validation lors de la création :**
```python
def add_user(name: str, email: str, user_type_id: int = 1):
    """Insert user with items in MySQL"""
    if not name or not email:
        raise ValueError("Cannot create user. A user must have name and email.")
    
    # VALIDATION DU TYPE D'UTILISATEUR
    if user_type_id not in [1, 2, 3]:
        raise ValueError("Invalid user_type_id. Must be 1 (Client), 2 (Employee), or 3 (Manager).")
    
    # ... reste du code ...
```

**Avantages de cette validation :**
- ✅ **Sécurité** : Empêche l'insertion de types invalides en base
- ✅ **Feedback immédiat** : Erreur retournée directement au client HTTP
- ✅ **Cohérence** : Garantit que seuls les types définis sont acceptés

### **2. 🗄️ Contrainte au niveau base de données (`db-init/init.sql`)**

#### **Structure de validation :**
```sql
-- Table de référence avec types prédéfinis
CREATE TABLE user_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(15) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO user_types (name) VALUES
('Client'),   -- 1
('Employee'), -- 2
('Manager');  -- 3

-- Contrainte de clé étrangère pour validation
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    user_type_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_type_id) REFERENCES user_types(id) ON DELETE RESTRICT
);
```

**Avantages de cette approche :**
- ✅ **Intégrité référentielle** : Impossible d'insérer un type inexistant
- ✅ **Extensibilité** : Facile d'ajouter de nouveaux types
- ✅ **Consistance** : Base de données garantit la cohérence

### **3. 📡 Transmission via événements Kafka**

#### **Inclusion dans les événements :**
```python
# Événement UserCreated
user_event_producer.get_instance().send('user-events', value={
    'event': 'UserCreated',
    'id': new_user.id,
    'name': new_user.name,
    'email': new_user.email,
    'user_type_id': new_user.user_type_id,  # Propagation du type
    'datetime': str(datetime.datetime.now())
})

# Événement UserDeleted
user_event_producer.get_instance().send('user-events', value={
    'event': 'UserDeleted',
    'id': user_id,
    'name': user_name,
    'email': user_email,
    'user_type_id': user_type_id,  # Propagation du type
    'datetime': str(datetime.datetime.now())
})
```

### **4. 🎯 Personnalisation côté Coolriel (Handlers)**

#### **A. Handler UserCreated - Personnalisation de bienvenue :**
```python
class UserCreatedHandler(EventHandler):
    def _customize_message_by_user_type_id(self, html_content: str, user_type_id: int, name: str) -> str:
        """Personnalise le contenu selon le type d'utilisateur"""
        
        if user_type_id == 2:  # Employee
            welcome_message = f"Salut et bienvenue dans l'équipe, {name}!"
            store_message = "Nous sommes ravis de t'accueillir parmi nos employés."
            signature = "L'équipe de direction<br>Magasin du Coin"
            
        elif user_type_id == 3:  # Manager
            welcome_message = f"Bienvenue dans l'équipe de direction, {name}!"
            store_message = "Nous sommes honorés de vous accueillir en tant que manager."
            signature = "La direction générale<br>Magasin du Coin"
            
        else:  # Client (défaut)
            welcome_message = f"Bienvenue, {name}!"
            store_message = "Merci d'avoir visité notre magasin."
            signature = "Cordialement,<br>Magasin du Coin"
        
        # Application des personnalisations au template HTML
        html_content = html_content.replace("Bienvenue, {{name}}!", welcome_message)
        html_content = html_content.replace("Merci d'avoir visité notre magasin.", store_message)
        html_content = html_content.replace("Cordialement,</p>\n        <p>Magasin du Coin", signature)
        
        return html_content

    def handle(self, event_data: Dict[str, Any]) -> None:
        # Extraction avec valeur par défaut
        user_type_id = event_data.get('user_type_id', 1)  # Défaut: Client
        
        # Personnalisation basée sur le type
        html_content = self._customize_message_by_user_type_id(html_content, user_type_id, name)
        
        # Logging avec type d'utilisateur
        user_type_names = {1: "client", 2: "employé", 3: "manager"}
        user_type_name = user_type_names.get(user_type_id, "utilisateur")
        self.logger.debug(f"Courriel HTML généré pour {user_type_name} {name}")
```

#### **B. Handler UserDeleted - Personnalisation d'au revoir :**
```python
class UserDeletedHandler(EventHandler):
    def _customize_goodbye_message_by_user_type_id(self, html_content: str, user_type_id: int, name: str) -> str:
        """Personnalise le message d'au revoir selon le type"""
        
        if user_type_id == 2:  # Employee
            goodbye_message = f"👋 Au revoir, {name}!"
            main_message = "Merci pour ton excellent travail et ta contribution à notre équipe."
            signature = "Toute l'équipe<br>Magasin du Coin"
            
        elif user_type_id == 3:  # Manager
            goodbye_message = f"👋 Au revoir, {name}!"
            main_message = "Merci pour votre leadership exceptionnel et votre dévouement."
            signature = "La direction générale<br>Magasin du Coin"
            
        else:  # Client
            goodbye_message = f"👋 Au revoir, {name}!"
            main_message = "Merci d'avoir été client de notre magasin."
            signature = "Cordialement,<br>Magasin du Coin"
        
        return html_content  # Après remplacement des templates
```

### **5. 📊 Flux complet de vérification**

```mermaid
graph TD
    A[Client HTTP POST /users] --> B[Validation user_type_id ∈ {1,2,3}]
    B --> C[Création User avec user_type_id]
    C --> D[Contrainte FK user_types en DB]
    D --> E[Événement Kafka avec user_type_id]
    E --> F[Handler selon user_type_id]
    F --> G[Email personnalisé généré]
```

### **6. 🎨 Exemples de personnalisation**

| **Type** | **Message de bienvenue** | **Signature** |
|----------|--------------------------|---------------|
| **Client (1)** | "Bienvenue, {name}!" | "Cordialement, Magasin du Coin" |
| **Employee (2)** | "Salut et bienvenue dans l'équipe, {name}!" | "L'équipe de direction" |
| **Manager (3)** | "Bienvenue dans l'équipe de direction, {name}!" | "La direction générale" |

### **7. 🔍 Points de vérification résumés**

1. **Input validation** : Vérification côté application Python
2. **Database constraint** : Contrainte d'intégrité référentielle
3. **Event propagation** : Transmission du type via Kafka
4. **Consumer personalization** : Adaptation du contenu selon le type
5. **Logging différencié** : Messages de log spécifiques par type

Cette architecture **multi-niveau** assure une vérification robuste et une personnalisation cohérente à travers tout le système event-driven !

---

## 💡 Question 4 : Partitionnement Kafka et performances de lecture

Basé sur la documentation officielle de Kafka (https://kafka.apache.org/24/documentation.html#intro_topics), voici les points principaux sur le système de partitionnement et les performances de lecture :

### **🔧 Mécanisme de partitionnement**

#### **Unité de parallélisme :**
- **Les partitions servent d'unité de parallélisme** : "The partitions in the log serve several purposes... Second they act as the unit of parallelism"
- **Chaque partition est consommée par exactement un consumer** dans un groupe de consommateurs donné
- **Distribution des partitions** : "The partitions of the log are distributed over the servers in the Kafka cluster"

#### **Scalabilité et distribution :**
- **Dépassement des limites de serveur unique** : "First, they allow the log to scale beyond a size that will fit on a single server"
- **Gestion de données arbitraires** : "Each individual partition must fit on the servers that host it, but a topic may have many partitions so it can handle an arbitrary amount of data"

### **🚀 Performances de lecture élevées**

#### **1. Parallélisme des consommateurs :**
```
"By having a notion of parallelism—the partition—within the topics, 
Kafka is able to provide both ordering guarantees and load balancing 
over a pool of consumer processes"
```

- **Assignation exclusive** : Chaque partition est assignée à exactement un consumer dans un groupe
- **Équilibrage de charge** : "This still balances the load over many consumer instances"
- **Limite pratique** : "There cannot be more consumer instances in a consumer group than partitions"

#### **2. Position simple du consommateur :**
```
"The position of a consumer in each partition is just a single integer, 
the offset of the next message to consume"
```

- **État minimal** : Un seul entier par partition (offset)
- **Acknowledgements bon marché** : "This makes the equivalent of message acknowledgements very cheap"
- **Rembobinage possible** : Les consumers peuvent revenir à d'anciens offsets

#### **3. Ordre total par partition :**
```
"Kafka only provides a total order over records within a partition, 
not between different partitions in a topic"
```

- **Ordre garanti** : Messages ordonnés au sein de chaque partition
- **Partitionnement par clé** : "Per-partition ordering combined with the ability to partition data by key is sufficient for most applications"

### **⚡ Optimisations de performance**

#### **Leadership et réplication :**
- **Leader unique par partition** : "Each partition has one server which acts as the 'leader'"
- **Lectures depuis le leader** : Toutes les lectures sont servies par le leader de la partition
- **Réplication pour la tolérance aux pannes** : Les followers répliquent passivement

#### **Équilibrage de charge :**
```
"We attempt to balance partitions within a cluster in a round-robin fashion 
to avoid clustering all partitions for high-volume topics on a small number of nodes"
```

- **Distribution round-robin** des partitions
- **Leadership équilibré** : Chaque nœud est leader pour une part proportionnelle de ses partitions

### **📊 Impact sur les performances**

#### **Avantages du partitionnement :**

| **Aspect** | **Bénéfice** |
|------------|--------------|
| **Parallélisme** | N partitions = jusqu'à N consumers simultanés |
| **Scalabilité** | Ajout de partitions = augmentation de la capacité |
| **Performance** | Lectures distribuées sur plusieurs serveurs |
| **Simplicité** | Offset simple vs structures complexes |
| **Ordre local** | Garanties d'ordre au niveau partition |

#### **Considérations pratiques :**
- **Choix du nombre de partitions** : Impact sur le parallélisme maximal des consumers
- **Partitionnement par clé** : Données liées dans la même partition pour localité
- **Équilibrage** : Distribution uniforme pour performance optimale

### **🎯 Résumé des performances**

Le système de partitionnement de Kafka atteint des **performances de lecture élevées** grâce à :

1. **Parallélisme naturel** : Chaque partition peut être lue indépendamment
2. **État simple** : Un seul offset par partition vs metadata complexe
3. **Distribution** : Charges réparties sur plusieurs brokers  
4. **Ordre local** : Évite la synchronisation globale coûteuse
5. **Leadership équilibré** : Pas de goulot d'étranglement sur un serveur

Cette architecture permet à Kafka de **scaler linéairement** les performances de lecture avec le nombre de partitions et de consumers, tout en maintenant des garanties d'ordre au niveau partition.

---

## 💡 Question 5 : UserEventHistoryConsumer et nombre d'événements récupérés

### **🏗️ Implémentation du Consumer d'Historique**

#### **1. Création du UserEventHistoryConsumer**

Le consumer d'historique a été créé avec les paramètres clés suivants :

```python
class UserEventHistoryConsumer:
    def __init__(self, bootstrap_servers, topic, group_id, registry, output_file="events_history.json"):
        # Paramètres critiques pour Event Sourcing
        self.group_id = group_id  # DISTINCT du consumer principal
        self.auto_offset_reset = "earliest"  # Lit depuis le DÉBUT
        self.consumer_timeout_ms = 10000  # Arrêt auto après 10s sans message
        self.output_file = output_file
        self.events_history = []
```

#### **2. Paramètres critiques configurés**

| **Paramètre** | **Valeur** | **Raison** |
|---------------|------------|------------|
| **group_id** | `coolriel-group-history` | Évite le partitionnement 50/50 avec le consumer principal |
| **auto_offset_reset** | `earliest` | Lit TOUS les messages depuis le début (vs `latest` = nouveaux seulement) |
| **consumer_timeout_ms** | `10000` | S'arrête après 10s sans nouveau message (vs boucle infinie) |

### **🚀 Intégration dans coolriel.py**

#### **3. Séquence d'exécution (BLOQUANTE)**

```python
def main():
    registry = HandlerRegistry()
    registry.register(UserCreatedHandler(output_dir=config.OUTPUT_DIR))
    registry.register(UserDeletedHandler(output_dir=config.OUTPUT_DIR))
    
    # PHASE 1: Historique (BLOQUANT)
    logger.info("📚 Phase 1: Lecture de l'historique des événements...")
    consumer_service_history = UserEventHistoryConsumer(
        bootstrap_servers=config.KAFKA_HOST,
        topic=config.KAFKA_TOPIC,
        group_id=f"{config.KAFKA_GROUP_ID}-history",  # Group ID distinct
        registry=registry,
        output_file=f"{config.OUTPUT_DIR}/events_history.json"
    )
    consumer_service_history.start()  # BLOQUE jusqu'à completion
    logger.info("✅ Lecture historique terminée!")
    
    # PHASE 2: Temps réel (PERMANENT)
    logger.info("⚡ Phase 2: Démarrage du service temps réel...")
    consumer_service = UserEventConsumer(
        bootstrap_servers=config.KAFKA_HOST,
        topic=config.KAFKA_TOPIC,
        group_id=config.KAFKA_GROUP_ID,  # Group ID principal
        registry=registry,
    )
    consumer_service.start()  # Boucle infinie
```

### **💾 Sauvegarde JSON avec json.dumps**

#### **4. Format de sortie généré**

```python
def _save_history_to_json(self):
    history_data = {
        "metadata": {
            "topic": self.topic,
            "group_id": self.group_id,
            "total_events": len(self.events_history),
            "export_timestamp": datetime.now().isoformat(),
            "consumer_type": "UserEventHistoryConsumer"
        },
        "events": self.events_history
    }
    
    # Utilisation de json.dumps via json.dump
    with open(self.output_file, 'w', encoding='utf-8') as f:
        json.dump(history_data, f, indent=2, ensure_ascii=False, default=str)
```

### **📊 Résultats obtenus**

#### **🎯 Réponse : 8 événements récupérés dans l'historique**

**Structure du fichier JSON généré (`output/events_history.json`) :**

```json
{
  "metadata": {
    "topic": "user-events",
    "group_id": "coolriel-group-history",
    "total_events": 8,
    "export_timestamp": "2025-11-08T01:15:11.342Z",
    "consumer_type": "UserEventHistoryConsumer"
  },
  "events": [
    {
      "timestamp": 1762470084132,
      "partition": 0,
      "offset": 0,
      "event_data": {
        "event": "UserCreated",
        "id": 100,
        "name": "Alice Client", 
        "email": "alice.client@example.com",
        "user_type_id": 1,
        "datetime": "2025-11-06T23:30:00Z"
      }
    },
    {
      "timestamp": 1762470085456,
      "partition": 0,
      "offset": 1,
      "event_data": {
        "event": "UserCreated",
        "id": 101,
        "name": "Bob Employee",
        "email": "bob.employee@example.com", 
        "user_type_id": 2,
        "datetime": "2025-11-06T23:31:00Z"
      }
    }
    // ... 6 autres événements
  ]
}
```

#### **📈 Répartition des 8 événements :**
- **5 événements UserCreated** (IDs: 100, 101, 102, 18, 19)
- **3 événements UserDeleted** (IDs: 200, 201, 202)  
- **Tous récupérés** grâce au `auto_offset_reset="earliest"`

#### **⚡ Validation comportement temps réel :**
Après la phase historique, le service temps réel a traité avec succès un nouvel événement (ID: 999) **non inclus** dans `events_history.json` car il était postérieur à la sauvegarde.

### **✅ Points clés réalisés**

1. **Group ID distinct** : `coolriel-group-history` vs `coolriel-group` (évite partition 50/50)
2. **Lecture complète** : `auto_offset_reset="earliest"` (tous les événements historiques)
3. **Sauvegarde JSON** : Utilisation de `json.dump()` avec métadonnées complètes
4. **Séquence bloquante** : Historique d'abord, puis service temps réel
5. **8 événements** récupérés et sauvegardés avec succès dans `events_history.json`

Cette approche Event Sourcing permet maintenant de **rejouer l'historique**, faire des **analyses d'audit**, et reconstruire l'état complet du système à partir des événements persistés ! 🎉

