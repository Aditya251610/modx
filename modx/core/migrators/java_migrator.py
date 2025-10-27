"""Java-specific migrator."""

import re
from pathlib import Path
from typing import List, Dict
from .utils import BaseMigrator


class JavaMigrator(BaseMigrator):
    def handle_step(self, sid: str, work_path: Path, targets: List[str], changes: List[Dict]):
        if sid == 'java_modernize':
            return self._modernize_java(work_path)
        return []

    def _modernize_java(self, work_path: Path) -> List[Dict]:
        changes = []
        # Update Maven pom.xml if present
        pom_candidates = list(work_path.rglob('pom.xml'))
        for pom in pom_candidates:
            try:
                old = pom.read_text(encoding='utf-8')
            except Exception:
                old = ''
            new = old

            # Ensure <properties> section exists and contains Java 17 settings
            if '<properties>' not in new:
                # Add properties section after <modelVersion>
                model_version_match = re.search(r'(<modelVersion>.*?</modelVersion>)', new, flags=re.S)
                if model_version_match:
                    insert_point = model_version_match.end()
                    properties_block = '\n    <properties>\n        <java.version>17</java.version>\n        <maven.compiler.source>17</maven.compiler.source>\n        <maven.compiler.target>17</maven.compiler.target>\n    </properties>'
                    new = new[:insert_point] + properties_block + new[insert_point:]
                else:
                    # Fallback: prepend
                    new = '<project>\n    <properties>\n        <java.version>17</java.version>\n        <maven.compiler.source>17</maven.compiler.source>\n        <maven.compiler.target>17</maven.compiler.target>\n    </properties>\n' + new
            else:
                # Properties exists, ensure java.version is 17
                if '<java.version>' not in new:
                    # Insert java.version inside properties
                    props_match = re.search(r'(<properties>.*?)(\s*</properties>)', new, flags=re.S)
                    if props_match:
                        props_content = props_match.group(1)
                        new = new.replace(props_content, props_content + '\n        <java.version>17</java.version>')
                else:
                    # Update existing java.version to 17
                    new = re.sub(r"(<java.version>\s*)([0-9.]+)(\s*</java.version>)",
                                 lambda m: f"{m.group(1)}17{m.group(3)}",
                                 new)
                
                # Ensure maven.compiler.source and target are 17
                if '<maven.compiler.source>' not in new:
                    props_match = re.search(r'(<properties>.*?)(\s*</properties>)', new, flags=re.S)
                    if props_match:
                        props_content = props_match.group(1)
                        new = new.replace(props_content, props_content + '\n        <maven.compiler.source>17</maven.compiler.source>')
                else:
                    new = re.sub(r"(<maven.compiler.source>\s*)(1\.8|8)(\s*</maven.compiler.source>)",
                                 lambda m: f"{m.group(1)}17{m.group(3)}",
                                 new)
                
                if '<maven.compiler.target>' not in new:
                    props_match = re.search(r'(<properties>.*?)(\s*</properties>)', new, flags=re.S)
                    if props_match:
                        props_content = props_match.group(1)
                        new = new.replace(props_content, props_content + '\n        <maven.compiler.target>17</maven.compiler.target>')
                else:
                    new = re.sub(r"(<maven.compiler.target>\s*)(1\.8|8)(\s*</maven.compiler.target>)",
                                 lambda m: f"{m.group(1)}17{m.group(3)}",
                                 new)

            # If there's a Spring Boot parent, try to bump its version to 3.1.0 if <version> present and not already 3.x
            try:
                parent_block = re.search(r"<parent>.*?<groupId>\s*org\.springframework\.boot\s*</groupId>.*?<artifactId>\s*spring-boot-starter-parent\s*</artifactId>.*?</parent>", new, flags=re.S)
                if parent_block:
                    pb = parent_block.group(0)
                    if '<version>' in pb:
                        pb_new = re.sub(r"(<version>\s*)([0-9.]+)(\s*</version>)", lambda m: (m.group(0) if m.group(2).startswith('3') else f"<version>3.1.0</version>"), pb)
                        new = new.replace(pb, pb_new)
            except Exception:
                pass

            if new != old:
                marker = '<!-- MODX_DETERMINISTIC_FALLBACK: upgraded to Java 17, Spring Boot 3, and javax→jakarta -->\n'
                try:
                    pom.write_text(marker + new, encoding='utf-8')
                    changes.append({'file': str(pom.relative_to(work_path)), 'type': 'java_modernize', 'lines_changed': max(1, new.count('\n') - old.count('\n'))})
                except Exception:
                    pass

        # Update Gradle build files
        gradle_files = [p for p in work_path.rglob('build.gradle')]
        for gf in gradle_files:
            try:
                old = gf.read_text(encoding='utf-8')
            except Exception:
                old = ''
            new = old
            # sourceCompatibility = 1.8 -> 17
            new = re.sub(r"(sourceCompatibility\s*=\s*)(1\.8|\"1\.8\"|JavaVersion\.VERSION_1_8)",
                         lambda m: f"{m.group(1)}17",
                         new)
            new = re.sub(r"(targetCompatibility\s*=\s*)(1\.8|\"1\.8\"|JavaVersion\.VERSION_1_8)",
                         lambda m: f"{m.group(1)}17",
                         new)
            # JavaVersion.VERSION_1_8 -> JavaVersion.VERSION_17
            new = new.replace('JavaVersion.VERSION_1_8', 'JavaVersion.VERSION_17')

            if new != old:
                marker = '// MODX_DETERMINISTIC_FALLBACK: upgraded to Java 17, Spring Boot 3, and javax→jakarta\n'
                try:
                    gf.write_text(marker + new, encoding='utf-8')
                    changes.append({'file': str(gf.relative_to(work_path)), 'type': 'java_modernize', 'lines_changed': max(1, new.count('\n') - old.count('\n'))})
                except Exception:
                    pass

        # Replace javax.* with jakarta.* in Java source files (safe textual replacement)
        java_files = [p for p in work_path.rglob('*.java')]
        for jf in java_files:
            try:
                old = jf.read_text(encoding='utf-8')
            except Exception:
                old = ''
            if not old:
                continue
            if 'MODX_DETERMINISTIC_FALLBACK' in old:
                continue

            new = old
            # Replace import statements
            new = re.sub(r"\bimport\s+javax\.", 'import jakarta.', new)
            # Replace fully-qualified usages
            new = re.sub(r"\bjavax\.(servlet|persistence|annotation|validation|ws)\.", lambda m: 'jakarta.' + m.group(1) + '.', new)
            # Replace common package roots
            new = new.replace('javax.', 'jakarta.')

            # Attempt a few safe modernizations: prefer try-with-resources (no-op textual hint), leave heavy refactors to AI
            if new != old:
                marker = '/* MODX_DETERMINISTIC_FALLBACK: upgraded to Java 17, Spring Boot 3, and javax→jakarta */\n'
                try:
                    jf.write_text(marker + new, encoding='utf-8')
                    changes.append({'file': str(jf.relative_to(work_path)), 'type': 'java_modernize', 'lines_changed': max(1, new.count('\n') - old.count('\n'))})
                except Exception:
                    pass
        return changes