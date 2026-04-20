.PHONY: server server-saml-debug frontend workers snfRAG stop help

help:
	@echo "  server            - Start the backend server"
	@echo "  server-saml-debug - Like server, with SAML_DEBUG + uvicorn --log-level debug"
	@echo "  frontend          - Start the frontend development server"
	@echo "  workers           - Start 2 background upload workers"
	@echo "  snfRAG            - Start both backend and frontend in parallel"
	@echo "  stop              - Stop both servers"
	@echo "  help              - Show this help message"

server:
	cd .. && DB_HOST=db DB_PORT=5432 uvicorn app.server.main:app --host 0.0.0.0 --reload --port 8000

# Verbose SAML (python3-saml) + uvicorn debug. ACS logs use phase= to separate:
#   saml_validation = crypto / IdP status / malformed assertion
#   credential        = SAML ok but no email in attributes (IdP release / mapping)
#   allowlist         = email known but not in allow-list
#   transport         = e.g. GET callback without SAMLResponse
server-saml-debug:
	cd .. && SAML_DEBUG=true DB_HOST=db DB_PORT=5432 uvicorn app.server.main:app --host 0.0.0.0 --reload --port 8000 --log-level debug

frontend:
	cd frontend && npm run dev -- --host 0.0.0.0

workers:
	cd .. && PYTHONPATH=/app:/app/preprocessing python -m app.setup_worker
	@for i in 1 2 3 4; do \
		cd .. && PYTHONPATH=/app:/app/preprocessing python -m app.worker & \
	done; \
	wait


snfRAG:
	@echo "Starting SNF RAG development environment..."
	@echo "Backend will be available at: http://localhost:8000"
	@echo "Frontend will be available at: http://localhost:3000"
	@echo "Press Ctrl+C to stop both servers"
	@echo ""
	@trap 'make stop' INT; \
	$(MAKE) server & \
	$(MAKE) frontend & \
	wait

stop:
	@echo "Stopping all development servers..."
	@pkill -f "uvicorn" || true
	@pkill -f "vite" || true
	@echo "Stopped all development servers"
