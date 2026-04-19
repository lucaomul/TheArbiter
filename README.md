# ⚔️ The Arbiter

I built this because I was tired of getting "okay-ish" answers from just one AI. Sometimes you need a second opinion, or in this case, a three-way technical debate to actually get something solid.

**The Arbiter** is a multi-agent setup where **GPT-4o**, **Gemini 2.5**, and **Llama 3.3 (via Groq)** act as a board of experts. They won't stop until they reach a consensus on whatever challenge you throw at them.

### 🧠 The Board of Experts
Instead of one prompt, you’re hiring a specialized team:
* **The Architect (GPT-4o):** Does the heavy lifting and builds the initial solution.
* **The Tech Critic (Gemini 2.5):** Tries to break the solution by finding technical flaws.
* **The Logic Critic (Llama 3.3 @ Groq):** Makes sure the reasoning is airtight and efficient.

If the critics find a hole in the plan, the Architect has to go back to the drawing board. They keep at it until everyone agrees it's a "win".

### ⚡ Cool stuff I added:
* **Cost Tracker:** A real-time cent-counter so you know exactly what you're spending on APIs.
* **Smart Memory:** The agents remember previous critiques, so they actually improve instead of going in circles.
* **Neon Dark Mode:** Built with Streamlit, because nobody likes a boring white UI.
* **One-Click PDF:** Grab the final, agreed-upon solution as a clean document.

### 🛠️ How to run it
1. **Clone it:**
   ```bash
   git clone [https://github.com/lucaomul/TheArbiter.git](https://github.com/lucaomul/TheArbiter.git)
   cd TheArbiter

2. **Setup:**
Install what's needed: pip install -r requirements.txt

3. **Secrets:**
Pop your API keys into a .env file (don't worry, it's ignored by Git).

4. **Launch:**
streamlit run app.py