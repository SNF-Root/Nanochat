.PHONY: server frontend workers snfRAG stop help

help:
	@echo "  server   - Start the backend server"
	@echo "  frontend - Start the frontend development server"
	@echo "  workers  - Start 2 background upload workers"
	@echo "  snfRAG - Start both backend and frontend in parallel"
	@echo "  stop     - Stop both servers"
	@echo "  help     - Show this help message"

server:
	cd .. && DB_HOST=db DB_PORT=5432 uvicorn app.server.main:app --host 0.0.0.0 --reload --port 8000

frontend:
	cd frontend && npm run dev -- --host 0.0.0.0

workers:
	cd .. && PYTHONPATH=/app:/app/preprocessing python -m app.setup_worker
	cd .. && PYTHONPATH=/app:/app/preprocessing python -m app.worker


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
