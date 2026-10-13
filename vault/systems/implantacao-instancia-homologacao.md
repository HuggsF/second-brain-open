---
type: system
status: active
date: 2026-10-09
---
# Implantação da Instância de Homologação (SRV-API)

**Data:** 2026-10-07  
**Servidor:** `SRV-API` (`191.233.18.195`)  
**Status:** Concluído e Operacional em Paralelo à Produção

---

## 1. Topologia de Coexistência (Produção vs Homologação)

Ambas as instâncias rodam na mesma máquina virtual de forma 100% isolada, com portas, processos e bancos de dados SQLite distintos:

| Recurso | Instância de Produção | Instância de Homologação |
| :--- | :--- | :--- |
| **Diretório** | `/home/ti-kiosk/hub` | `/home/ti-kiosk/hub-homolog` |
| **Porta Local** | `3000` | `3001` |
| **Gerenciador PM2** | `hub-logistico` (ID 0) | `hub-homolog` (ID 1) |
| **Banco de Dados** | `/home/ti-kiosk/hub/hub.db` (13 MB) | `/home/ti-kiosk/hub-homolog/hub-homolog.db` (32 KB) |
| **Ambiente (`.env`)** | `PORT=3000` (implícito) | `PORT=3001` / `DB_PATH=./hub-homolog.db` |
| **Consumo de Memória** | ~116 MB | ~75 MB |
| **Proteção de Fila** | Geração automática conforme painel | `gerar_automatico = 0` (todas as lojas em modo manual) |
| **Acesso Externo** | `https://hub.touticosmetics.com.br` | Túnel SSH (`localhost:3001`) ou subdomínio Nginx |

---

## 2. Passo a Passo Executado no Servidor

1. **Deploy dos Arquivos:** Pacote contendo a branch `fix/duplicidade-etiquetas-jt` enviado e descompactado em `/home/ti-kiosk/hub-homolog`.
2. **Isolamento de Ambiente:** Criado `.env` configurando `PORT=3001` e `DB_PATH=./hub-homolog.db`.
3. **Instalação Limpa:** `npm install` executado com sucesso.
4. **Validação de Testes:** Suíte automatizada (`npm test`) executada diretamente no servidor com 100% de aprovação (todos os 4 testes de duplicidade aprovados).
5. **Inicialização no PM2:**
   ```bash
   sudo pm2 start /home/ti-kiosk/hub-homolog/server.js --name hub-homolog --cwd /home/ti-kiosk/hub-homolog
   ```
6. **Segurança de Fila:** Tabela `lojas` ajustada para `gerar_automatico = 0`, garantindo que pedidos de homologação nunca emitam etiquetas sem intervenção deliberada de testes.

---

## 3. Configuração do Nginx (Pronto para `hub-hml.touticosmetics.com.br`)

O Nginx já foi configurado e ativado em `/etc/nginx/sites-available/hub-homolog` (com symlink em `sites-enabled`):
```nginx
server {
    server_name hub-hml.touticosmetics.com.br;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    listen 80;
}
```

*Assim que o apontamento DNS tipo A for criado para `191.233.18.195`, basta executar:*
```bash
sudo certbot --nginx -d hub-hml.touticosmetics.com.br
```

---

## 4. Como Acessar a Homologação

### Opção A: Imediata via Túnel SSH (Sem precisar aguardar DNS)
```bash
ssh -i C:\KIOSK\SRV-API_key.pem -L 3001:127.0.0.1:3001 ti-kiosk@191.233.18.195 -N
```
Acesse no navegador: `http://localhost:3001`  
Credenciais padrão: `admin` / `admin123`.

### Opção B: Via Domínio Público Oficial (Após criação do DNS)
`https://hub-hml.touticosmetics.com.br`

## Proteção local atualizada em 2026-10-08

Informações de implantação acima são históricas, sem nova inspeção remota. Nova branch adiciona HUB_ENV=hml, seed com todas as lojas desligadas e bloqueio de processamento/emissão direta. Configurar só DB_PATH não era garantia suficiente. Ainda sem deploy; [[protecoes-processamento-emissao-hub]]. Sandbox e operação manual controlada pendentes.
