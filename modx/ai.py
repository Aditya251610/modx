"""
AI module for ModX - Ollama integration
Provides AI-powered code analysis and modernization suggestions.
"""

import os
import requests
import json
from typing import Dict, List, Optional
from pathlib import Path

class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        # Allow configuration via environment variable, default to a lighter model
        # Use a smaller model by default to increase compatibility with low-RAM hosts
        self.model = model or os.environ.get('OLLAMA_MODEL') or "codegemma:2b"

    def is_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                # Accept exact matches or model name prefixes (e.g. 'codellama:latest')
                for m in models:
                    name = m.get('name') or m.get('model') or ''
                    if not name:
                        continue
                    req = self.model
                    # Accept exact matches, prefix matches, or the reverse (requested
                    # model is a prefix of available model name or vice-versa).
                    if name == req or name.startswith(req) or req.startswith(name):
                        return True
                return False
            return False
        except Exception:
            return False

    def analyze_code(self, code: str, language: str, context: str = "") -> Dict:
        """Analyze code using Ollama AI."""
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
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                raw = result.get('response', '')
                # Try to parse model output as JSON; if it fails, fall back to a
                # conservative wrapper so the rest of the pipeline can still use
                # the AI output as a suggestion.
                try:
                    ai_response = json.loads(raw or '{}')
                except Exception:
                    # Wrap the raw text as a single suggestion entry so downstream
                    # logic can treat it safely and deterministically.
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
        """Generate modernized code using Ollama AI."""
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

        except:
            return code

    def generate_modernization_diff(self, original: str, target_path: str, language: str, modernization_type: str, minimal: bool = False) -> str:
        """Ask the AI to produce a unified diff (git-style) for updating a file.

        This enforces that the AI returns a diff that starts with '---' and '+++' and
        is directly consumable by `git apply`.
        """
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
                # Normalize leading whitespace
                raw = raw.strip('\n')
                # If model followed instruction to say NO_DIFF_AVAILABLE
                if raw.strip() == 'NO_DIFF_AVAILABLE':
                    return ''
                return raw
            else:
                return ""
        except Exception:
            return ""

class AIModernizer:
    def __init__(self):
        self.ollama = OllamaClient()

    def is_available(self) -> bool:
        """Return whether the configured AI backend is available."""
        try:
            return self.ollama.is_available()
        except Exception:
            return False

    def enhance_analysis(self, findings: Dict) -> Dict:
        """Enhance analysis results with AI insights."""
        if not self.ollama.is_available():
            findings['ai_enhanced'] = False
            return findings

        findings['ai_enhanced'] = True
        findings['ai_insights'] = []

        # Analyze sample files with AI
        for lang, files in findings.get('languages', {}).items():
            for file_path in files[:2]:  # Analyze first 2 files per language
                full_path = Path(findings.get('service_path', '.')) / file_path
                if full_path.exists():
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            code = f.read()[:2000]  # First 2000 chars

                        ai_analysis = self.ollama.analyze_code(
                            code, lang,
                            f"File: {file_path}, Framework: {findings.get('frameworks', {}).get(lang, 'Unknown')}"
                        )

                        if ai_analysis.get('issues'):
                            findings['ai_insights'].extend(ai_analysis['issues'])

                        if ai_analysis.get('suggestions'):
                            findings['ai_insights'].extend(ai_analysis['suggestions'])

                    except:
                        pass

        return findings

    def generate_ai_modernization_steps(self, findings: Dict) -> List[Dict]:
        """Generate AI-powered modernization steps."""
        steps = []

        if not findings.get('ai_enhanced', False):
            return steps

        ai_insights = findings.get('ai_insights', [])

        for insight in ai_insights:
            # Only treat AI outputs as SUGGESTIONS — never auto-apply.
            # Create deterministic, testable step objects. If the AI provided a code example
            # we include it as a 'patch' for a specific file so migrator can apply it deterministically
            # when the user approves.
            if insight.get('type') == 'suggestion' or insight.get('type') == 'issue':
                title = insight.get('description', 'Modernization suggestion')
                code_example = insight.get('code_example', '') or insight.get('example', '')

                # Determine affected files if AI indicated a file, otherwise use a placeholder
                files = insight.get('files', []) or ([insight.get('file')] if insight.get('file') else [])
                if not files:
                    files = ["AI-suggested-file.py"]

                # Create a patch mapping file -> content if code_example present
                patch = {}
                if code_example:
                    for f in files:
                        patch[f] = code_example

                # Estimate LOC conservatively: if AI provided a LOC estimate, use it; else base on code_example lines
                if insight.get('estimated_loc'):
                    est = int(insight.get('estimated_loc'))
                elif code_example:
                    est = len(code_example.splitlines())
                else:
                    est = 50

                # If estimated LOC > 500, split into chunks of <=500 LOC to satisfy policy
                if est > 500:
                    chunks = (est + 499) // 500
                    per_chunk = max(1, est // chunks)
                    for idx in range(chunks):
                        steps.append({
                            "id": f"ai_{idx}_{title[:40].lower().replace(' ', '_')}",
                            "title": f"AI: {title} (part {idx+1}/{chunks})",
                            "description": title + " (split from large AI suggestion)",
                            "files_affected": files,
                            "estimated_loc": per_chunk,
                            "risk": "medium",
                            "ai_generated": True,
                            "patch": patch
                        })
                else:
                    steps.append({
                        "id": f"ai_{title[:40].lower().replace(' ', '_')}",
                        "title": f"AI: {title}",
                        "description": title,
                        "files_affected": files,
                        "estimated_loc": est,
                        "risk": "medium",
                        "ai_generated": True,
                        "patch": patch
                    })

        return steps

    def generate_modernization_diff(self, original: str, target_path: str, language: str, modernization_type: str) -> str:
        """Convenience wrapper: ask the underlying Ollama client for a unified diff."""
        try:
            return self.ollama.generate_modernization_diff(original, target_path, language, modernization_type)
        except Exception:
            return ''