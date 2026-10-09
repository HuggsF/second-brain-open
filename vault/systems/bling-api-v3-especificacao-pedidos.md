# Especificação Oficial Bling API v3: Estrutura Completa de Pedidos de Venda e Logística

**Data de Extração:** 2026-10-07  
**Fonte Primária:** [Portal do Desenvolvedor Bling](https://developer.bling.com.br/)  
**Especificação OpenAPI Oficial:** `https://developer.bling.com.br/build/assets/openapi-Dw6cY8yQ.json`  
**Referência da API:** [developer.bling.com.br/referencia#/Pedidos - Vendas](https://developer.bling.com.br/referencia#/Pedidos%20-%20Vendas/get_pedidos_vendas__idPedidoVenda_)  

---

## 1. Visão Geral da API v3 do Bling

A API v3 do Bling opera sob o padrão **OpenAPI 3.0 (OAS 3.0)** com autenticação mandatória via **OAuth 2.0** (`Bearer <access_token>`).
O endpoint principal para recuperação dos dados completos de um pedido de venda é:

```http
GET https://api.bling.com.br/Api/v3/pedidos/vendas/{idPedidoVenda}
```

A resposta é encapsulada na propriedade raiz `data`, combinando os esquemas:
`VendasDadosBaseDTO` + `VendasDadosDTO`.

---

## 2. Estrutura Completa do Objeto de Resposta (`data`)

Abaixo está o schema oficial extraído diretamente da especificação OpenAPI do Bling:

```json
{
  "id": 12345678,
  "numero": 123,
  "numeroLoja": "PED-SHOP-991",
  "data": "2026-10-07",
  "dataSaida": "2026-10-07",
  "dataPrevista": "2026-10-15",
  "totalProdutos": 150.00,
  "total": 170.00,
  "contato": {
    "id": 12345678,
    "nome": "Consumidor Final Exemplo",
    "tipoPessoa": "F",
    "numeroDocumento": "11122233344"
  },
  "situacao": {
    "id": 9,
    "valor": 1
  },
  "loja": {
    "id": 206085936
  },
  "numeroPedidoCompra": "OC-5541",
  "outrasDespesas": 0.00,
  "observacoes": "Entregar em horário comercial",
  "observacoesInternas": "",
  "desconto": {
    "valor": 0.00,
    "unidade": "REAL"
  },
  "categoria": {
    "id": 12345
  },
  "notaFiscal": {
    "id": 12345678
  },
  "tributacao": {
    "totalICMS": 0.00
  },
  "itens": [
    {
      "id": 12345678,
      "codigo": "PERFUME-TOUTI-VIP",
      "unidade": "UN",
      "quantidade": 1,
      "desconto": 0,
      "valor": 150.00,
      "aliquotaIPI": 0,
      "descricao": "Perfume Touti VIP 50ml",
      "descricaoDetalhada": "Fragrância Floral Amadeirada"
    }
  ],
  "parcelas": [
    {
      "id": 12345678,
      "dataVencimento": "2026-11-07",
      "valor": 170.00,
      "observacoes": "",
      "formaPagamento": { "id": 1 }
    }
  ],
  "transporte": {
    "fretePorConta": 0,
    "frete": 20.00,
    "quantidadeVolumes": 1,
    "pesoBruto": 0.85,
    "prazoEntrega": 5,
    "contato": {
      "id": 12345678,
      "nome": "J&T Express"
    },
    "etiqueta": {
      "nome": "Consumidor Final Exemplo",
      "endereco": "Av Jeronimo Monteiro",
      "numero": "100",
      "complemento": "Apto 301",
      "municipio": "Vitória",
      "uf": "ES",
      "cep": "29010000",
      "bairro": "Centro",
      "nomePais": "BRASIL"
    },
    "volumes": [
      {
        "id": 98765432,
        "servico": "JT_EXPRESS_PADRAO",
        "codigoRastreamento": "JT8880192837465BR"
      }
    ]
  },
  "vendedor": {
    "id": null
  },
  "intermediador": {
    "cnpj": null,
    "nomeUsuario": null
  },
  "taxas": {
    "taxaComissao": 0.00,
    "custoFrete": 20.00,
    "valorBase": 150.00
  }
}
```

---

## 3. Sub-Schemas Relevantes da Logística

### 3.1. `VendasTransporteVolumeDTO` (Esquema OpenAPI Oficial)
Na documentação do Bling, cada item do array `transporte.volumes[]` possui a seguinte especificação formal:

| Campo | Tipo | Descrição | Exemplo |
| :--- | :--- | :--- | :--- |
| `id` | `integer` | ID único do objeto de logística vinculado ao volume. | `12345678` |
| `servico` | `string` | Alias/identificador do serviço logístico utilizado. | `"ALIAS_123"` |
| `codigoRastreamento` | `string` | **Código oficial de rastreamento do volume.** | `"COD123BR"` / `"JT8880192837465BR"` |

> **Comprovação de Conformidade:**  
> O campo oficial definido no schema OpenAPI do Bling é **`codigoRastreamento`** (em `camelCase`).  
> O adapter [adapters/bling.js](file:///C:/KIOSK/hub-logistico/adapters/bling.js) agora lê diretamente:
> ```javascript
> const primeiroVolume = pedido.transporte?.volumes?.[0];
> const rastreioExistente = primeiroVolume?.codigoRastreamento
>     || primeiroVolume?.rastreamento?.codigo
>     || pedido.transporte?.etiqueta?.rastreamento
>     || null;
> ```

---

### 3.2. `VendasTransporteEtiquetaDTO` (Endereço Alternativo de Entrega)

| Campo | Tipo | Descrição |
| :--- | :--- | :--- |
| `nome` | `string` | Nome do destinatário |
| `endereco` | `string` | Logradouro de entrega |
| `numero` | `string` | Número do endereço |
| `complemento` | `string` | Complemento (sala, apto) |
| `bairro` | `string` | Bairro do destinatário |
| `municipio` | `string` | Cidade |
| `uf` | `string` | Sigla do Estado (2 dígitos) |
| `cep` | `string` | CEP com ou sem formatação |
| `nomePais` | `string` | País (`"BRASIL"` ou outro) |

> **Regra de Fallback do Bling:**  
> Quando o checkbox *"Endereço de entrega diferente da cobrança"* não está marcado no pedido, o Bling retorna `etiqueta` com campos vazios. O adapter resolve isso consultando `GET /contatos/{id}`, campo `data.endereco.geral` ou `data.endereco.cobranca`.

---

### 3.3. `LogisticasObjetosUpdateRequestDTO` (Atualização de Rastreio)
Para persistir o código de rastreio de um pedido faturado sem quebrar o bloqueio de edição de pedidos com NF-e emitida, utiliza-se:

```http
PUT https://api.bling.com.br/Api/v3/logisticas/objetos/{idObjeto}
```

Onde `{idObjeto}` é o `transporte.volumes[0].id` retornado no pedido.

```json
{
  "rastreamento": {
    "codigo": "JT8880192837465BR",
    "data": "2026-10-07 14:30:00",
    "ultimaAlteracao": "2026-10-07 14:30:00"
  },
  "dimensoes": { ... },
  "embalagem": { ... }
}
```

---

## 4. Conclusão e Evidência de Conformidade
A implementação do [hub-logistico](file:///C:/KIOSK/hub-logistico) implementa os mapeamentos abaixo no checkout local; isso não comprova conformidade integral com todos os schemas da API:
1. Extração fiel de `codigoRastreamento` de `transporte.volumes[0]`.
2. Fallback de endereço via `/contatos/{id}` para pedidos sem endereço de entrega customizado.
3. Gravação de rastreio via `/logisticas/objetos/{idObjeto}` respeitando os schemas de integridade de NF-e.

## Limites atuais

Extração e atualização operam no primeiro volume. Volumes ausentes/múltiplos dependem da DEM-13. Atendido não comprova pagamento ou NF-e emitida. Contrato WMS segue DEM-12.
