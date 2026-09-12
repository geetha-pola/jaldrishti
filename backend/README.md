# JALDRISHTI Backend

This is the FastAPI backend for JALDRISHTI.

## Requirements
- Python 3.10+
- PostgreSQL + PostGIS (see the `database` folder)

## How to Start the Backend Locally

1. Setup the database by following the instructions in `database/README.md`.

2. Navigate to the backend directory:
   ```bash
   cd backend
   ```

3. Create a virtual environment and activate it:
   ```bash
   # On Windows
   python -m venv venv
   .\venv\Scripts\activate

   # On Linux/macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Copy the `.env.example` file to `.env` and configure your variables:
   ```bash
   cp .env.example .env
   ```

6. Run the FastAPI server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

7. Check the API health:
   Visit `http://localhost:8000/health` in your browser.