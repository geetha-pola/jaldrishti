# JALDRISHTI Database

This folder contains the Docker Compose configuration for running a local PostgreSQL + PostGIS database for development.

## Requirements
- Docker
- Docker Compose

## How to Start the Database
1. Navigate to the `database` directory:
   ```bash
   cd database
   ```
2. Start the container in the background:
   ```bash
   docker-compose up -d
   ```
3. To stop the container:
   ```bash
   docker-compose down
   ```

## Database Details
- **Image:** `postgis/postgis:15-3.3`
- **Default Port:** `5432`
- **Default Database:** `jaldrishti`
- **Default User:** `postgres`
- **Default Password:** `postgres`

(If you want to use different credentials, create a `.env` file in this folder to override the variables in `docker-compose.yml`, or pass them directly when running `docker-compose`).