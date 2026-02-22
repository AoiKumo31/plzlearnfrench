# How to Deploy the Telegram Coach to Render (24/7)

To make your bot run 24/7, we will host it on **Render** (it's free/cheap and very easy). 

Render requires the code to live on GitHub, so here is the step-by-step process:

### Step 1: Push this code to GitHub
1. Create a free account on [GitHub](https://github.com/) if you don't have one.
2. In the top right corner of GitHub, click the `+` icon and select **New repository**.
3. Name it `french-coach-bot` and click **Create repository** (keep it Private).
4. Do not initialize it with a README. Copy the repository URL (it will look like `https://github.com/vantran/french-coach-bot.git`).

Open a new terminal window on your Mac, go to this project folder, and run these commands to push your code:
```bash
cd /Users/vantran/Desktop/plzlearnfrench
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <paste-your-github-url-here>
git push -u origin main
```

### Step 2: Set up Render
1. Create an account on [Render.com](https://render.com/).
2. In the Render Dashboard, click **New +** and select **Blueprint**.
   *(Why Blueprint? Because I already wrote a `render.yaml` file in your folder that automatically configures everything!)*
3. Connect your GitHub account and select your `french-coach-bot` repository.
4. Render will read the `render.yaml` file and set up a **Background Worker** with a persistent disk for your SQLite database.

### Step 3: Add your API Keys (Environment Variables)
Once the service is created in Render, it will fail to start on the first try because it doesn't have your keys.
1. On your Render dashboard, click your `french-coach-bot` service.
2. Go to the **Environment** tab.
3. Add two environment variables:
   - Key: `TELEGRAM_BOT_TOKEN` | Value: `8189009046:AAHFQ3ZizybpDNWtMzY...`
   - Key: `CEREBRAS_API_KEY` | Value: `csk-e62cjkx...`
4. Click **Save Changes**.
5. Render will automatically redeploy the bot. 

Once the deploy is green and says "Live", your bot is running 24/7! You can close your laptop.
