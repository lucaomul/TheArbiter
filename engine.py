import json
from agents import AIAgent
from prompts import AUDITOR_PROMPT, PROPOSER_PROMPT, CRITIC_PROMPT

def start_arbiter():
    print("\n" + "=".center(60, "="))
    print("⚔️  THE ARBITER: CONSENSUS ENGINE (v2.5 ENGLISH)".center(60))
    print("=".center(60, "="))

    # CONFIGURATION: Using your available 2026 models
    auditor = AIAgent("Auditor", "gemini", "gemini-2.5-flash", AUDITOR_PROMPT)
    proposer = AIAgent("Proposer", "openai", "gpt-4o", PROPOSER_PROMPT)
    critic = AIAgent("Critic", "gemini", "gemini-2.5-pro", CRITIC_PROMPT)

    user_input = input("\n[USER]> Enter the problem or task: ")

    # PHASE 1: Audit
    print("\n[DEBUG] Running Audit phase...")
    audit_raw = auditor.ask(user_input)
    audit_res = AIAgent.clean_json(audit_raw)

    if not audit_res.get("clear", True):
        print("\n⚠️  CLARIFICATION REQUIRED:")
        for q in audit_res.get("questions", []):
            print(f"  - {q}")
        clarify = input("\n[USER]> Provide more details: ")
        user_input += f" | Additional Context: {clarify}"

    # PHASE 2: Negotiation Loop
    final_solution = ""
    
    for round_num in range(1, 3):
        print(f"\n" + f" 🔄 ROUND {round_num} ".center(40, "-"))
        
        # 1. Proposal
        print("💡 Proposer (OpenAI) is thinking...")
        prop_raw = proposer.ask(user_input)
        prop_res = AIAgent.clean_json(prop_raw)
        proposal = prop_res.get('proposal', 'Error: Could not generate proposal.')

        # 2. Critique
        print("🛡️  Critic (Gemini) is auditing...")
        crit_raw = critic.ask(f"Task: {user_input}\nProposal: {proposal}")
        crit_res = AIAgent.clean_json(crit_raw)
        
        if "error" in crit_res:
            print(f"❌ Gemini Error: {crit_res['error']}")
            final_solution = proposal
            break

        if crit_res.get("consensus", False):
            print("✅ CONSENSUS REACHED!")
            final_solution = proposal
            break
        else:
            print(f"❌ Critique received. Updating proposal...")
            feedback = crit_res.get('critique', 'No specific feedback provided.')
            user_input += f" | Address this feedback: {feedback}"
            final_solution = proposal

    print("\n" + "🏆 FINAL SOLUTION:".center(60, "="))
    print(final_solution)
    print("=".center(60, "=") + "\n")

if __name__ == "__main__":
    start_arbiter()