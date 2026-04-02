# Nanochat

A RAG-based system for searching and retrieving information from PROM forms and email threads.

## Repository Structure

```
PROM/
├── app/                          # Application layer
│   ├── frontend/                 # React frontend application
│   ├── server/                   # FastAPI backend server
│   │   └── main.py              # API endpoints for email/PROM search
│   └── Makefile                 # Commands to run server and frontend
│
├── preprocessing/                # Data preprocessing pipeline
│   ├── database/                # Database setup and connections
│   │   ├── pg.py               # PostgreSQL/pgvector connection and table initialization
│   │   └── __init__.py
│   ├── models/                  # Data models
│   │   └── insert.py           # Email and PromForm dataclasses with DB insert methods
│   ├── email_pipeline.py       # End-to-end pipeline for processing email threads
│   ├── prom_pipeline.py        # End-to-end pipeline for processing PROM forms
│   ├── order_emails.py         # Parse and organize emails into conversation threads
│   ├── filter_emails.py        # Extract and clean main message content from emails
│   ├── promTothread.py         # Extract structured data from PROM .docx files
│   └── embed_emails.py         # Generate embeddings for email content
│
├── files/                       # Data files (emails, PROM forms)
├── compose.yml                  # Docker Compose configuration
├── Dockerfile                   # Container image definition
├── container_requirements.txt   # Python dependencies
└── start.sh                     # Legacy helper script for manual container operations
```

## File Organization

### Email Processing
All files with "email" in the name handle email-related operations:
- `email_pipeline.py` - Orchestrates the complete email processing workflow
- `order_emails.py` - Parses mbox files and creates threaded conversations
- `filter_emails.py` - Cleans and extracts relevant content from email bodies
- `embed_emails.py` - Generates vector embeddings for semantic search

### PROM Processing
All files with "prom" in the name handle PROM form operations:
- `prom_pipeline.py` - Orchestrates the complete PROM form processing workflow
- `promTothread.py` - Extracts structured fields from PROM .docx documents

## Preprocessing Files

| File | Description |
|------|-------------|
| `email_pipeline.py` | End-to-end pipeline that processes email threads, filters content, generates embeddings, and inserts into database |
| `prom_pipeline.py` | End-to-end pipeline that extracts PROM form data from .docx files, generates embeddings, and inserts into database |
| `order_emails.py` | Parses mbox format emails and organizes them into threaded conversations by message ID |
| `filter_emails.py` | Extracts main message content and removes headers, signatures, and quoted text |
| `promTothread.py` | Converts PROM .docx files to structured data by extracting fields like chemicals, processes, and staff considerations |
| `embed_emails.py` | Generates OpenAI embeddings for email threads to enable semantic similarity search |
| `database/pg.py` | Provides database connection utilities and functions to initialize email_embeddings and prom_embeddings tables |
| `models/insert.py` | Defines Email and PromForm dataclasses with methods to insert records into PostgreSQL |

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Environment variables (export in your shell):
  ```bash
  export POSTGRES_USER=user
  export POSTGRES_PASSWORD=user_pw
  export POSTGRES_DB=appdb
  export STANFORD_API_KEY=your_api_key_here
  ```

### Running with Docker Compose

#### 1. Build and Start Containers

```bash
# Build the images
docker compose build

# Start containers in background
docker compose up -d

# Check container status
docker compose ps

# View logs
docker compose logs -f
```

#### 2. Access Running Containers

**Get a shell in the server container:**
```bash
docker compose exec server bash
```

**Get a shell in the database container:**
```bash
docker compose exec db bash
```

**Connect to PostgreSQL directly:**
```bash
docker compose exec db psql -U user -d appdb
```

#### 3. Run the Application

**Inside the server container (after `docker compose exec server bash`):**

```bash
# Navigate to app directory
cd app

# Start both backend and frontend
make snfRAG

# Or start individually:
make server    # Backend only (port 8000)
make frontend  # Frontend only (port 3000)

# Stop all servers
make stop
```

**Run preprocessing pipelines (from project root inside container):**
```bash
# Process email threads
python preprocessing/email_pipeline.py

# Process PROM forms
python preprocessing/prom_pipeline.py
```

### Accessing the Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **Database**: localhost:5433 (exposed from container port 5432)

### Stopping Containers

```bash
# Stop containers (keeps data)
docker compose down

# Stop and remove volumes (deletes database data)
docker compose down -v
```

## Development

### Code Changes
The project root is mounted at `/app` in the server container, so code changes on your local machine are immediately reflected inside the container without rebuilding.

### Database Initialization
The database starts empty. Run the preprocessing pipelines to populate it with email and PROM data.

### Running One-Off Commands
```bash
# Run a script without entering the container
docker compose run server python your_script.py

# Run database initialization
docker compose run server python preprocessing/database/pg.py
```

## Architecture

- **Database**: PostgreSQL with pgvector extension for vector similarity search
- **Backend**: FastAPI server with endpoints for semantic search over emails and PROM forms
- **Frontend**: React application with Vite for fast development
- **Embeddings**: OpenAI text-embedding-ada-002 model for semantic search
- **Document Processing**: Docling library for extracting structured data from .docx files
