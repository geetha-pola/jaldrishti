# Local Development Setup (Windows)

## 1. PostgreSQL & PostGIS Installation
1. Download the EnterpriseDB installer for PostgreSQL 16 for Windows: https://www.enterprisedb.com/downloads/postgres-postgresql-downloads
2. Run the installer and remember the `postgres` user password. Keep default port 5432.
3. At the end of the installation, launch the **Stack Builder** utility.
4. In Stack Builder, under "Spatial Extensions", select and install **PostGIS**.

## 2. Database Creation
Open `pgAdmin 4` or the `psql` command line tool and run:
```sql
CREATE DATABASE jaldrishti;
\c jaldrishti
CREATE EXTENSION postgis;
SELECT PostGIS_Full_Version();
```

## 3. Configuration
Copy `backend/.env.example` to `backend/.env` and update the `DATABASE_URL` with your password:
```
DATABASE_URL=postgresql+psycopg://postgres:<YOUR_PASSWORD>@localhost:5432/jaldrishti
```

## 4. Migrations & Seed Data
Navigate to the `backend` directory and run:
```bash
python -m alembic upgrade head
```

## 5. Verification
Run the verification script to ensure PostgreSQL and PostGIS are correctly integrated:
```bash
python verify_postgis.py
```

## 6. Starting FastAPI
```bash
uvicorn app.main:app --reload
```
