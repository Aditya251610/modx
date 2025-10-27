"""Analyzer module moved into core package."""
import os
import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from ..ai import AIModernizer


class CodebaseAnalyzer:
    def __init__(self, root_path: str = ".", use_ai: bool = True) -> None:
        self.root_path = Path(root_path)
        self.use_ai = use_ai
        self.ai_modernizer = AIModernizer() if use_ai else None

    def analyze(self) -> Dict:
        findings = {
            "languages": self._detect_languages(),
            "frameworks": self._detect_frameworks(),
            "outdated_issues": self._detect_outdated_issues(),
            "summary": {},
            "service_path": str(self.root_path)
        }

        findings["summary"] = {
            "total_files": self._count_files(),
            "languages_detected": list(findings["languages"].keys()),
            "frameworks_detected": list(findings["frameworks"].keys()),
            "issues_found": len(findings["outdated_issues"])
        }

        if self.use_ai and self.ai_modernizer:
            findings = self.ai_modernizer.enhance_analysis(findings)
            findings["summary"]["ai_enhanced"] = findings.get("ai_enhanced", False)

        return findings

    def _detect_languages(self) -> Dict[str, List[str]]:
        languages = {}
        extensions = {
            "python": [".py", ".pyw"],
            "javascript": [".js", ".jsx"],
            "typescript": [".ts", ".tsx"],
            "java": [".java"],
            "golang": [".go"]
        }

        for lang, exts in extensions.items():
            files = []
            for ext in exts:
                files.extend(list(self.root_path.rglob(f"*{ext}")))
            if files:
                languages[lang] = [str(f.relative_to(self.root_path)) for f in files[:5]]

        return languages

    def _detect_frameworks(self) -> Dict[str, str]:
        frameworks = {}

        if (self.root_path / "requirements.txt").exists():
            frameworks["python"] = "Generic Python"
        if (self.root_path / "pyproject.toml").exists():
            frameworks["python"] = "Modern Python"
        if (self.root_path / "setup.py").exists():
            frameworks["python"] = "Setuptools Python"

        if (self.root_path / "package.json").exists():
            try:
                with open(self.root_path / "package.json") as f:
                    pkg = json.load(f)
                    deps = pkg.get("dependencies", {})
                    dev_deps = pkg.get("devDependencies", {})

                    if "react" in deps or "react" in dev_deps:
                        frameworks["javascript"] = "React"
                    elif "next" in deps:
                        frameworks["javascript"] = "Next.js"
                    elif "nest" in deps:
                        frameworks["javascript"] = "NestJS"
                    else:
                        frameworks["javascript"] = "Node.js"
            except:
                frameworks["javascript"] = "Node.js"

        if (self.root_path / "pom.xml").exists():
            frameworks["java"] = "Maven"
        if (self.root_path / "build.gradle").exists():
            frameworks["java"] = "Gradle"

        if (self.root_path / "go.mod").exists():
            frameworks["golang"] = "Go Modules"

        return frameworks

    def _detect_outdated_issues(self) -> List[Dict]:
        issues = []

        py_files = list(self.root_path.rglob("*.py"))
        for py_file in py_files[:10]:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "print " in content and "from __future__ import print_function" not in content:
                        issues.append({
                            "file": str(py_file.relative_to(self.root_path)),
                            "type": "python2_print",
                            "message": "Uses Python 2 style print statement"
                        })
            except:
                pass

        pkg_path = self.root_path / "package.json"
        if pkg_path.exists():
            try:
                with open(pkg_path) as f:
                    pkg = json.load(f)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    for dep, version in deps.items():
                        if version.startswith("^0.") or version.startswith("~0."):
                            issues.append({
                                "file": "package.json",
                                "type": "outdated_dependency",
                                "message": f"Outdated dependency: {dep}@{version}"
                            })
            except:
                pass

        return issues

    def _count_files(self) -> int:
        extensions = ['.py', '.js', '.ts', '.java', '.go', '.jsx', '.tsx']
        count = 0
        for ext in extensions:
            count += len(list(self.root_path.rglob(f"*{ext}")))
        return count
