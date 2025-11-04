"""
Jaeger Tracing Configuration
SPDX - License - Identifier: LGPL - 3.0 - or -later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

def configure_tracing(app, service_name="store-manager"):
    """Configure Jaeger tracing for the Flask application"""
    
    # Create a resource with service information
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0"
    })

    # Set up the tracer provider
    trace.set_tracer_provider(TracerProvider(resource=resource))
    
    # Configure OTLP exporter to send traces to Jaeger
    otlp_exporter = OTLPSpanExporter(
        endpoint="http://jaeger:4317",
        insecure=True
    )
    
    # Add span processor
    span_processor = BatchSpanProcessor(otlp_exporter)
    trace.get_tracer_provider().add_span_processor(span_processor)

    # Instrument Flask app automatically
    FlaskInstrumentor().instrument_app(app)
    
    # Instrument requests library for outgoing HTTP calls
    RequestsInstrumentor().instrument()
    
    return trace.get_tracer(__name__)