"""Planner module moved into core package."""
import os
from pathlib import Path
from typing import Dict, List, Optional
from .analyzer import CodebaseAnalyzer
from ..ai import AIModernizer


class ModernizationPlanner:
    def __init__(self, service_path: str, use_ai: bool = True) -> None:
        self.service_path = Path(service_path)
        self.use_ai = use_ai
        self.analyzer = CodebaseAnalyzer(service_path, use_ai)
        self.ai_modernizer = AIModernizer() if use_ai else None

    def plan(self) -> Dict:
        """Generate a modernization plan for the service."""
        findings = self.analyzer.analyze()
        steps = []
        if self.use_ai:
            if not self.ai_modernizer or not self.ai_modernizer.is_available():
                raise RuntimeError("AI backend unavailable - service down")
            try:
                findings = self.ai_modernizer.enhance_analysis(findings)
            except Exception:
                findings['ai_enhanced'] = False

            ai_steps = self.ai_modernizer.generate_ai_modernization_steps(findings)
            actionable_ai_steps = []
            for s in (ai_steps or []):
                patch = s.get('patch') if isinstance(s, dict) else None
                if patch and isinstance(patch, dict):
                    has_real_target = any(k and not str(k).startswith('AI-suggested-file') for k in patch.keys())
                    if has_real_target:
                        actionable_ai_steps.append(s)
                else:
                    actionable_ai_steps.append(s)

            if actionable_ai_steps:
                steps = actionable_ai_steps
                ai_fallback = False
            else:
                steps = self._generate_steps(findings)
                ai_fallback = True
        else:
            steps = self._generate_steps(findings)
            ai_fallback = False

        plan = {
            "service": str(self.service_path),
            "current_state": findings,
            "steps": steps,
            "estimated_loc": self._estimate_loc_changes(),
            "risk_level": self._assess_risk(),
            "ai_fallback": bool(ai_fallback)
        }

        return plan

    def _generate_steps(self, findings: Dict) -> List[Dict]:
        steps = []
        if "python" in findings["languages"]:
            steps.extend(self._python_steps(findings))
        if "javascript" in findings["languages"] or "typescript" in findings["languages"]:
            steps.extend(self._javascript_steps(findings))
        if "java" in findings["languages"]:
            steps.extend(self._java_steps(findings))
        if "golang" in findings["languages"]:
            steps.extend(self._golang_steps(findings))
        if self.use_ai and self.ai_modernizer:
            ai_steps = self.ai_modernizer.generate_ai_modernization_steps(findings)
            steps.extend(ai_steps)
        return steps

    def _python_steps(self, findings: Dict) -> List[Dict]:
        steps = []
        py2_issues = [i for i in findings["outdated_issues"] if i["type"] == "python2_print"]
        if py2_issues:
            steps.append({
                "id": "python_print_function",
                "title": "Update Python 2 print statements",
                "description": "Replace 'print' statements with 'print()' function calls",
                "files_affected": [i["file"] for i in py2_issues],
                "estimated_loc": len(py2_issues) * 5,
                "risk": "low"
            })

        if "python" in findings["frameworks"]:
            steps.append({
                "id": "update_dependencies",
                "title": "Update Python dependencies",
                "description": "Update outdated Python packages to latest compatible versions",
                "files_affected": ["requirements.txt", "pyproject.toml"],
                "estimated_loc": 10,
                "risk": "medium"
            })

        steps.append({
            "id": "add_type_hints",
            "title": "Add type hints to functions",
            "description": "Add type annotations to improve code maintainability",
            "files_affected": findings["languages"].get("python", [])[:5],
            "estimated_loc": 50,
            "risk": "low"
        })

        return steps

    def _javascript_steps(self, findings: Dict) -> List[Dict]:
        steps = []
        steps.append({
            "id": "es6_syntax",
            "title": "Modernize to ES6+ syntax",
            "description": "Convert var to const/let, arrow functions, template literals",
            "files_affected": findings["languages"].get("javascript", [])[:5],
            "estimated_loc": 100,
            "risk": "low"
        })
        if "javascript" in findings["frameworks"]:
            steps.append({
                "id": "update_js_deps",
                "title": "Update JavaScript dependencies",
                "description": "Update npm packages to latest versions",
                "files_affected": ["package.json"],
                "estimated_loc": 5,
                "risk": "medium"
            })
        return steps

    def _java_steps(self, findings: Dict) -> List[Dict]:
        steps = []
        steps.append({
            "id": "java_modernize",
            "title": "Modernize Java code",
            "description": "Use var for local variables, switch expressions, text blocks",
            "files_affected": findings["languages"].get("java", [])[:5],
            "estimated_loc": 150,
            "risk": "medium"
        })
        return steps

    def _golang_steps(self, findings: Dict) -> List[Dict]:
        steps = []
        steps.append({
            "id": "go_modules",
            "title": "Update Go dependencies",
            "description": "Update go.mod dependencies to latest versions",
            "files_affected": ["go.mod", "go.sum"],
            "estimated_loc": 10,
            "risk": "medium"
        })
        return steps

    def _estimate_loc_changes(self) -> int:
        total_files = sum(len(files) for files in self.analyzer._detect_languages().values())
        return min(total_files * 20, 500)

    def _assess_risk(self) -> str:
        issue_count = len(self.analyzer._detect_outdated_issues())
        if issue_count > 10:
            return "high"
        elif issue_count > 5:
            return "medium"
        else:
            return "low"
