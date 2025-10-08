
# Halloween Costume Voting — Email/Phone Auth

This version lets **any participant from your spreadsheet** vote once by validating their email (and phone last-4 if present). People can vote even if they don't upload a costume.

## Quick start
```bash
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ADMIN_KEY=letmein   # change in prod
python app.py
# http://localhost:5000
```

## Importing your participant list
1. Prepare a CSV with columns: `email,phone,name` (header required).
   - Emails are matched case-insensitively.
   - Phone can be blank; if set, voters must enter **last 4 digits** to proceed.
2. Visit: `http://localhost:5000/admin/import?key=YOURKEY`
3. Upload the CSV. Rows are upserted by email.

## Flow
- **Upload**: Anyone can submit a costume (optional).
- **Vote**: On Home, voter enters their email (+ last4 if required).
  - If email exists in the imported list and hasn't voted, they see the gallery to cast **one** vote.
- **Rankings**: Top 10 by votes.

## Resetting
Delete `site.db` and the `static/uploads/` directory.
