import os
import json
import re
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class AIAgent:
    def __init__(self, name, provider, model_name, system_instruction):
        self.name = name
        self.provider = provider
        self.model_name = model_name
        self.system_instruction = system_instruction
        
        if provider == "openai":
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        elif provider == "groq":
            self.client = OpenAI(
                api_key=os.getenv("GROQ_API_KEY"),
                base_url="https://api.groq.com/openai/v1"
            )
        elif provider == "gemini":
            self.api_key = os.getenv("GEMINI_API_KEY")

    def ask(self, prompt, history=""):
        # Adăugăm istoria conversației pentru ca AI-ul să aibă context (Memory)
        full_context = f"PREVIOUS_CONVERSATION_LOGS:\n{history}\n\nCURRENT_TASK:\n{prompt}" if history else prompt
        
        try:
            if self.provider in ["openai", "groq"]:
                params = {
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": self.system_instruction},
                        {"role": "user", "content": full_context}
                    ]
                }
                if self.provider == "openai":
                    params["response_format"] = {"type": "json_object"}
                
                response = self.client.chat.completions.create(**params)
                return response.choices[0].message.content
            
            elif self.provider == "gemini":
                model_path = self.model_name if self.model_name.startswith("models/") else f"models/{self.model_name}"
                url = f"https://generativelanguage.googleapis.com/v1beta/{model_path}:generateContent?key={self.api_key}"
                
                payload = {
                    "contents": [{
                        "parts": [{"text": f"INSTRUCTION: {self.system_instruction}\n\n{full_context}\n\nReturn ONLY JSON."}]
                    }]
                }
                
                response = requests.post(url, json=payload, timeout=30)
                res_json = response.json()
                if response.status_code != 200:
                    return json.dumps({"error": res_json.get('error', {}).get('message', 'API Error'), "consensus": False})
                return res_json['candidates'][0]['content']['parts'][0]['text']
                
        except Exception as e:
            return json.dumps({"error": str(e), "consensus": False})

    @staticmethod
    def clean_json(raw_data):
        try:
            raw_str = str(raw_data)
            match = re.search(r'\{.*\}', raw_str, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return json.loads(raw_str)
        except:
            return {"error": "JSON Parse Error", "raw": raw_data}