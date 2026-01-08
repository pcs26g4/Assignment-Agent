# Login Application

A full-stack login application with React frontend and FastAPI backend using PostgreSQL database.

## Project Structure

```
.
├── frontend/          # React application with Tailwind CSS
├── backend/           # FastAPI backend
└── README.md          # This file
```

## Prerequisites

- Node.js (v16 or higher)
- Python (v3.8 or higher)
- PostgreSQL (v12 or higher)

## Quick Start

### 1. Database Setup

Create a PostgreSQL database:
```sql
CREATE DATABASE login_db;
```

### 2. Backend Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your database credentials
uvicorn main:app --reload
```

Initialize database with test user:
```bash
python init_db.py
```

Test credentials:
- Email: `admin@example.com`
- Password: `admin123`

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

## Usage

1. Start the PostgreSQL database
2. Start the backend server (runs on http://localhost:8000)
3. Start the frontend server (runs on http://localhost:3000)
4. Navigate to http://localhost:3000
5. Login with the test credentials

## Features

- ✅ Login page with email/password authentication
- ✅ JWT token-based authentication
- ✅ Protected routes
- ✅ Responsive navbar after login
- ✅ PostgreSQL database integration
- ✅ Modern UI with Tailwind CSS

## Environment Variables

### Backend (.env)
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - Secret key for JWT tokens

## API Endpoints

- `POST /login` - User login
- `GET /me` - Get current user (requires authentication)

