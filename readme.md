# Healthcare Interoperability Instance

## Requisitos
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) instalado

## Dependências principais
| Pacote | Versão | Descrição |
|--------|--------|-----------|
| `healthcare-sdk` | 0.2.1 | Base framework (REST, MLLP, usecases) |
| `google-generativeai` | ≥0.8.6 | Gemini AI para normalização |
| `sqlalchemy` | ≥2.0 | ORM / acesso ao banco de dados |
| `python-dotenv` | ≥1.2.2 | Carregamento do `.env` |

## Como rodar

```bash
# 1. Instalar dependências
uv sync

# 2. cria a .env
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_HOST=
POSTGRES_PORT=
POSTGRES_DB=
GEMINI_API_KEY=
AI_PROVIDER=

# 3. Rodar a aplicação
uv run python app.py
```

REST API disponível em `http://localhost:8000` | MLLP em `localhost:2575`

> Sem Postgres configurado, usa SQLite (`healthcare.db`) automaticamente.

## Rotas REST

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/messages` | Lista todas as mensagens recebidas |
| `POST` | `/messages` | Processa e ingere uma nova mensagem (HL7v2 ou FHIR) |
| `GET` | `/messages/{id}` | Consulta uma mensagem pelo ID |
| `POST` | `/messages/{id}/commit` | Comita/confirma uma mensagem pendente |
| `GET` | `/logs` | Lista os logs da aplicação |
