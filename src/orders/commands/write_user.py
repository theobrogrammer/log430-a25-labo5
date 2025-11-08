"""
Users (write-only model)
SPDX - License - Identifier: LGPL - 3.0 - or -later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""
import json
import datetime
from orders.commands.user_event_producer import UserEventProducer
from orders.models.user import User
from db import get_sqlalchemy_session

def add_user(name: str, email: str, user_type_id: int = 1):
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
    
    if user_type_id not in [1, 2, 3]:
        raise ValueError("Invalid user_type_id. Must be 1 (Client), 2 (Employee), or 3 (Manager).")
    
    session = get_sqlalchemy_session()

    try: 
        # ÉTAPE 1: Transaction principale - Création utilisateur en base
        new_user = User(name=name, email=email, user_type_id=user_type_id)
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
            'user_type_id': new_user.user_type_id,
            'datetime': str(datetime.datetime.now())
        })
        # Pas d'attente de réponse - Fire and Forget!
        
        return new_user.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def delete_user(user_id: int):
    """
    Delete user in MySQL
    
    TODO: Implémenter événement UserDeleted pour maintenir la cohérence
    du pattern Event-Driven. Le consumer (coolriel) pourrait:
    - Archiver les emails de bienvenue
    - Nettoyer les données utilisateur
    - Notifier d'autres services de la suppression
    """
    session = get_sqlalchemy_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            # Récupérer les données utilisateur avant suppression pour l'événement
            user_name = user.name
            user_email = user.email
            user_type_id = user.user_type_id
            
            session.delete(user)
            session.commit()
            
            # Événement ASYNCHRONE UserDeleted vers Kafka
            user_event_producer = UserEventProducer()
            user_event_producer.get_instance().send('user-events', value={
                'event': 'UserDeleted',
                'id': user_id,
                'name': user_name,
                'email': user_email,
                'user_type_id': user_type_id,
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

