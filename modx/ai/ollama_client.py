"""Ollama client wrapper extracted from modx.ai
Contains OllamaClient only.
"""
import os
import requests
import json
from typing import Dict, Optional


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.model = model or os.environ.get('OLLAMA_MODEL') or "codegemma:2b"

    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                for m in models:
                    name = m.get('name') or m.get('model') or ''
                    if not name:
                        continue
                    req = self.model
                    if name == req or name.startswith(req) or req.startswith(name):
                        return True
                return False
            return False
        except Exception:
            return False

    def analyze_code(self, code: str, language: str, context: str = "") -> Dict:
        if not self.is_available():
            return {"issues": [], "suggestions": [], "ai_available": False}

        prompt = f"""
        Analyze this {language} code for modernization opportunities and potential issues.
        Focus on:
        - Outdated patterns or syntax
        - Security vulnerabilities
        - Performance improvements
        - Best practices violations
        - Code quality issues

        Context: {context}

        Code:
        {code}

        Provide response in JSON format with:
        - issues: array of {{"type": "issue_type", "description": "description", "severity": "low|medium|high"}}
        - suggestions: array of {{"type": "modernization_type", "description": "description", "code_example": "example"}}
        """

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False
                },
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json()
                raw = result.get('response', '')
                try:
                    ai_response = json.loads(raw or '{}')
                except Exception:
                    ai_response = {
                        'issues': [],
                        'suggestions': [
                            {
                                'type': 'suggestion',
                                'description': 'AI raw suggestion',
                                'code_example': raw.strip(),
                            }
                        ]
                    }

                ai_response['ai_available'] = True
                return ai_response
            else:
                return {"issues": [], "suggestions": [], "ai_available": False}

        except Exception as e:
            return {"issues": [], "suggestions": [], "ai_available": False, "error": str(e)}

    def generate_modernization(self, code: str, language: str, modernization_type: str) -> str:
        if not self.is_available():
            return code

        prompt = f"""
        Modernize this {language} code by applying {modernization_type}.
        Provide only the modernized code, no explanations.

        Original code:
        {code}
        """

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                return result.get('response', code).strip()
            else:
                return code

        except Exception:
            return code

    def generate_modernization_diff(self, original: str, target_path: str, language: str, modernization_type: str, minimal: bool = False) -> str:
        if not self.is_available():
            return ""

        if minimal:
            prompt = f"""
            Produce the SMALLEST possible unified diff (git-style) that updates the file at path '{target_path}'.
            Return only the unified diff content. Absolutely no explanation or extra text.
            The diff MUST start with a line beginning with '---' and the following file
            header line beginning with '+++' (for example, '--- a/{target_path}' and '+++ b/{target_path}').
            If no safe minimal diff can be produced, reply exactly with 'NO_DIFF_AVAILABLE'.

            Modernization goal: {modernization_type}

            Original file path: {target_path}

            Original file contents:
            {original}
            """
        else:
            prompt = f"""
            Produce a unified diff (git-style) that updates the file at path '{target_path}'.
            The diff MUST be the only content in the response and MUST start with a line
            beginning with '---' and the following file header line beginning with '+++'
            (for example, '--- a/{target_path}' and '+++ b/{target_path}').

            The diff should apply cleanly to the file contents provided below. Provide
            no explanation, no JSON wrapper, and no extra text. If you cannot produce a
            valid patch, respond with the exact text: "NO_DIFF_AVAILABLE".

            Modernization goal: {modernization_type}

            Original file path: {target_path}

            Original file contents:
            {original}
            """

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                raw = result.get('response', '')
                if not raw:
                    return ""
                raw = raw.strip('\n')
                if raw.strip() == 'NO_DIFF_AVAILABLE':
                    return ''
                return raw
            else:
                return ""
        except Exception:
            return ""
