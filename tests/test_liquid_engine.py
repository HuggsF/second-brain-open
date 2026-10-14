"""Test suite for core.liquid template engine."""
import pytest
from core.liquid import render_liquid, extract_liquid_variables


def test_simple_variable_interpolation():
    template = "Olá, {{ name }}! Seu pedido é #{{ order_id }}."
    ctx = {"name": "Hugo", "order_id": "27092088358"}
    assert render_liquid(template, ctx) == "Olá, Hugo! Seu pedido é #27092088358."


def test_nested_variable_interpolation():
    template = "Cliente: {{ customer.name }} (UF: {{ address.state }})"
    ctx = {
        "customer": {"name": "Cosmetic Log"},
        "address": {"state": "ES"}
    }
    assert render_liquid(template, ctx) == "Cliente: Cosmetic Log (UF: ES)"


def test_liquid_default_filter():
    template = "Ambiente: {{ env | default: 'hml' }}, Host: {{ host | default: '127.0.0.1' }}"
    assert render_liquid(template, {}) == "Ambiente: hml, Host: 127.0.0.1"
    assert render_liquid(template, {"env": "production"}) == "Ambiente: production, Host: 127.0.0.1"


def test_liquid_case_and_strip_filters():
    template = "Código: {{ code | upcase }} | Nome: {{ name | strip | downcase }}"
    ctx = {"code": "jt_recife", "name": "  TOUTI COSMETICS  "}
    assert render_liquid(template, ctx) == "Código: JT_RECIFE | Nome: touti cosmetics"


def test_liquid_replace_filter():
    template = "URL: {{ path | replace: 'old', 'new' }}"
    ctx = {"path": "/api/v1/old-endpoint"}
    assert render_liquid(template, ctx) == "URL: /api/v1/new-endpoint"


def test_liquid_if_condition_truthy():
    template = "{% if is_debug %}MODO DEBUG ATIVO{% else %}MODO PRODUCAO{% endif %}"
    assert render_liquid(template, {"is_debug": True}) == "MODO DEBUG ATIVO"
    assert render_liquid(template, {"is_debug": False}) == "MODO PRODUCAO"
    assert render_liquid(template, {}) == "MODO PRODUCAO"


def test_liquid_if_condition_equality():
    template = "{% if environment == 'production' %}HOST: 191.233.18.195{% else %}HOST: 127.0.0.1{% endif %}"
    assert render_liquid(template, {"environment": "production"}) == "HOST: 191.233.18.195"
    assert render_liquid(template, {"environment": "hml"}) == "HOST: 127.0.0.1"


def test_liquid_unless_condition():
    template = "{% unless is_production %}AVISO: AMBIENTE NAO PRODUTIVO{% endunless %}"
    assert render_liquid(template, {"is_production": False}) == "AVISO: AMBIENTE NAO PRODUTIVO"
    assert render_liquid(template, {"is_production": True}) == ""


def test_extract_liquid_variables():
    template = """
    Consulta SQLite:
    SELECT * FROM orders_queue WHERE erp_id = '{{ erp_id }}';
    {% if environment == 'production' %}
    Host: {{ prod_host | default: 'srv-api' }}
    {% endif %}
    """
    vars_found = extract_liquid_variables(template)
    assert "erp_id" in vars_found
    assert "environment" in vars_found
    assert "prod_host" in vars_found
