# Auth Testing

Admin: bxibichvzpd@indogmail.com / Agency@Studio2026

Step 1: DB
  mongosh; use test_database
  db.users.find({role:"admin"})  -> hash starts with $2b$

Step 2: API
  curl -c c.txt -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d '{"email":"bxibichvzpd@indogmail.com","password":"Agency@Studio2026"}'
  curl -b c.txt http://localhost:8001/api/auth/me
