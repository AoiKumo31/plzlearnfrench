# How to Deploy the Telegram Coach to Render (Free Web Service)

Since Render Blueprints cost money, we will deploy this completely for free as a **Web Service**. 

*Note: Render Web Services require a web server to bind to a port, otherwise the deploy fails. I have updated `bot.py` to run a tiny silent web server alongside the Telegram bot.*

### Step 1: Push this code to GitHub
1. Create a free account on [GitHub](https://github.com/) if you don't have one.
2. In the top right corner of GitHub, click the `+` icon and select **New repository**.
3. Name it `french-coach-bot` and click **Create repository** (keep it Private).
4. Copy the repository URL (it will look like `https://github.com/vantran/french-coach-bot.git`).

Open a new terminal window on your Mac, go to this project folder, and run these commands to push your code:
```bash
cd /Users/vantran/Desktop/plzlearnfrench
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/vantran/french-coach-bot.git
git push -u origin main
```

### Step 2: Set up a Render Web Service
1. Create a free account on [Render.com](https://render.com/).
2. In the Render Dashboard, click **New +** and select **Web Service**.
3. Connect your GitHub account and select your `french-coach-bot` repository.
4. Fill out the settings as follows:
   - **Name:** `french-coach-bot`
   - **Region:** Pick any
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Instance Type:** `Free`

### Step 4: Add API Keys (Environment Variables)
Scroll down to the **Advanced** section (or the Environment tab) and add:
- Key: `TELEGRAM_BOT_TOKEN` | Value: `8189009046:AAHFQ3ZizybpDNWtMzY3YjrCkGsAuVwZUwE`
- Key: `CEREBRAS_API_KEY` | Value: `csk-e62cjkxyetwrydxen5t8hft6hhywpyte64dwd38kewxw8nnx`
- **Key: `PYTHON_VERSION` | Value: `3.10.11` <- CRITICAL FIX**

> **🚨 Why Python Version?** Render uses Python 3.14 by default, which fails to build `pydantic`. Setting it to `3.10.11` fixes the build error!

> **Note on Free Hosting:** Render's free tier does not support Persistent Disks. This means your SQLite database will reset if the server restarts. To keep it 100% free, we just accept that your streak might reset occasionally. (If you want to save data forever, let me know and I can switch it to Firebase or Supabase later!)

### Step 5: Deploy!
Click **Create Web Service**. Wait about 2–3 minutes for it to build. Once it says "Live", your bot will run 24/7!
