"""AIModernizer extracted to its own module; uses OllamaClient from ollama_client.py"""
from typing import Dict, List
from pathlib import Path
from .ollama_client import OllamaClient


class AIModernizer:
    def __init__(self):
        self.ollama = OllamaClient()

    def is_available(self) -> bool:
        try:
            return self.ollama.is_available()
        except Exception:
            return False

    def enhance_analysis(self, findings: Dict) -> Dict:
        if not self.ollama.is_available():
            findings['ai_enhanced'] = False
            return findings

        findings['ai_enhanced'] = True
        findings['ai_insights'] = []

        for lang, files in findings.get('languages', {}).items():
            for file_path in files[:2]:
                full_path = Path(findings.get('service_path', '.')) / file_path
                if full_path.exists():
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            code = f.read()[:2000]

                        ai_analysis = self.ollama.analyze_code(
                            code, lang,
                            f"File: {file_path}, Framework: {findings.get('frameworks', {}).get(lang, 'Unknown')}"
                        )

                        if ai_analysis.get('issues'):
                            findings['ai_insights'].extend(ai_analysis['issues'])

                        if ai_analysis.get('suggestions'):
                            findings['ai_insights'].extend(ai_analysis['suggestions'])

                    except Exception:
                        pass

        return findings

    def generate_ai_modernization_steps(self, findings: Dict) -> List[Dict]:
        steps = []

        if not findings.get('ai_enhanced', False):
            return steps

        ai_insights = findings.get('ai_insights', [])

        for insight in ai_insights:
            if insight.get('type') == 'suggestion' or insight.get('type') == 'issue':
                title = insight.get('description', 'Modernization suggestion')
                code_example = insight.get('code_example', '') or insight.get('example', '')

                files = insight.get('files', []) or ([insight.get('file')] if insight.get('file') else [])
                if not files:
                    files = ["AI-suggested-file.py"]

                patch = {}
                if code_example:
                    for f in files:
                        patch[f] = code_example

                if insight.get('estimated_loc'):
                    est = int(insight.get('estimated_loc'))
                elif code_example:
                    est = len(code_example.splitlines())
                else:
                    est = 50

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
        try:
            return self.ollama.generate_modernization_diff(original, target_path, language, modernization_type)
        except Exception:
            return ''
