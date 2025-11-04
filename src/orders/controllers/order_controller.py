"""
Order controller
SPDX - License - Identifier: LGPL - 3.0 - or -later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""

from logger import Logger
from flask import jsonify
from db import get_redis_conn
from orders.commands.write_order import add_order, delete_order, modify_order
from orders.queries.read_order import get_order_by_id, get_best_selling_products, get_highest_spending_users

# Import tracing if available
try:
    from opentelemetry import trace
    tracer = trace.get_tracer(__name__)
    TRACING_ENABLED = True
except ImportError:
    TRACING_ENABLED = False

logger = Logger.get_instance("order_controller")

def create_order(request):
    """Create order, use WriteOrder model"""
    if TRACING_ENABLED:
        with tracer.start_as_current_span("POST /orders") as span:
            try:
                payload = request.get_json() or {}
                user_id = payload.get('user_id')
                items = payload.get('items', [])
                
                # Ajouter des attributs au span
                span.set_attribute("user.id", user_id)
                span.set_attribute("order.items_count", len(items) if items else 0)
                span.set_attribute("http.method", "POST")
                span.set_attribute("http.route", "/orders")
                
                order_id = add_order(user_id, items)
                
                span.set_attribute("order.id", order_id)
                span.set_attribute("http.status_code", 201)
                
                return jsonify({'order_id': order_id}), 201
                
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                span.set_attribute("http.status_code", 500)
                return jsonify({'error': str(e)}), 500
    else:
        # Fallback sans tracing
        payload = request.get_json() or {}
        user_id = payload.get('user_id')
        items = payload.get('items', [])
        try:
            order_id = add_order(user_id, items)
            return jsonify({'order_id': order_id}), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
def update_order(request):
    """Update order, use WriteOrder model"""
    if TRACING_ENABLED:
        with tracer.start_as_current_span("PUT /orders") as span:
            try:
                payload = request.get_json() or {}
                order_id = payload.get('order_id')
                is_paid = payload.get('is_paid')
                
                span.set_attribute("order.id", order_id)
                span.set_attribute("order.is_paid", is_paid)
                span.set_attribute("http.method", "PUT")
                span.set_attribute("http.route", "/orders")
                
                logger.debug(f"Mettre à jour la commande {order_id}, status={is_paid}")

                # update MySQL
                status = modify_order(order_id, is_paid=is_paid)
                
                # update Redis
                r = get_redis_conn()
                order = r.hgetall(f"order:{order_id}")
                order['is_paid'] = str(is_paid)
                r.hset(f"order:{order_id}", mapping=order)

                # response
                logger.debug("Statut actuel", status)
                span.set_attribute("http.status_code", 200)
                return jsonify({'updated': status}), 200
                
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                span.set_attribute("http.status_code", 500)
                return jsonify({'error': str(e)}), 500
    else:
        # Fallback sans tracing
        payload = request.get_json() or {}
        order_id = payload.get('order_id')
        is_paid = payload.get('is_paid')
        logger.debug(f"Mettre à jour la commande {order_id}, status={is_paid}")

        try:
            # update MySQL
            status = modify_order(order_id, is_paid=is_paid)
            
            # update Redis
            r = get_redis_conn()
            order = r.hgetall(f"order:{order_id}")
            order['is_paid'] = str(is_paid)
            r.hset(f"order:{order_id}", mapping=order)

            # response
            logger.debug("Statut actuel", status)
            return jsonify({'updated': status}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

def remove_order(order_id):
    """Delete order, use WriteOrder model"""
    try:
        deleted = delete_order(order_id)
        if deleted:
            return jsonify({'deleted': True})
        return jsonify({'deleted': False}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_order(order_id):
    """Get order, use ReadOrder model"""
    if TRACING_ENABLED:
        with tracer.start_as_current_span("GET /orders/{id}") as span:
            try:
                span.set_attribute("order.id", order_id)
                span.set_attribute("http.method", "GET")
                span.set_attribute("http.route", "/orders/{id}")
                
                order = get_order_by_id(order_id)
                
                if order:
                    span.set_attribute("http.status_code", 200)
                    return jsonify(order), 200
                else:
                    span.set_attribute("http.status_code", 404)
                    return jsonify({'error': 'Order not found'}), 404
                    
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                span.set_attribute("http.status_code", 500)
                return jsonify({'error': str(e)}), 500
    else:
        # Fallback sans tracing
        try:
            order = get_order_by_id(order_id)
            if order:
                return jsonify(order), 200
            else:
                return jsonify({'error': 'Order not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
def get_report_highest_spending_users():
    """Get orders report: highest spending users"""
    return get_highest_spending_users()

def get_report_best_selling_products():
    """Get orders report: best selling products"""
    return get_best_selling_products()