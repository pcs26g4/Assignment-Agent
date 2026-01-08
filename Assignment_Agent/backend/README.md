# FastAPI Backend

## Setup Instructions

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up PostgreSQL database:**
   - Create a database named `login_db`
   - Update the `DATABASE_URL` in `.env` file if needed
   - Default: `postgresql://postgres:postgres@localhost:5432/login_db`

3. **Create `.env` file:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and update the `DATABASE_URL` and `SECRET_KEY` as needed.

4. **Run the application:**
   ```bash
   uvicorn main:app --reload
   ```

5. **Initialize database with test user (optional):**
   ```bash
   python init_db.py
   ```
   This creates a test user:
   - Email: `admin@example.com`
   - Password: `admin123`

## API Endpoints

- `POST /login` - Login endpoint
- `GET /me` - Get current user info (requires authentication)
- `GET /` - API root

## Database Schema

The `users` table has the following structure:
- `id` (Integer, Primary Key)
- `email` (String, Unique)
- `hashed_password` (String)

