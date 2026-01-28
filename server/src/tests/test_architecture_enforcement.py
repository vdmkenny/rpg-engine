"""
Architecture Enforcement Tests

These tests enforce the GSM architecture patterns defined in GSM_ARCHITECTURE_PATTERNS.md.
They prevent regression of architectural violations in the service layer.

Key Principles Enforced:
- Services MUST NOT import ORM models directly
- Services MUST NOT access database sessions directly  
- API endpoints MUST use services, not GSM directly
- GSM SHOULD BE the single source of truth for game state
"""

import ast
import os
from pathlib import Path
from typing import Set, List, Tuple

# Only import pytest if available (for proper test execution)
try:
    import pytest
    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False
    
    # Create a dummy decorator for standalone execution
    def pytest_mark_integration(func):
        return func
    
    class pytest:
        class mark:
            integration = pytest_mark_integration


class ArchitectureViolationError(Exception):
    """Raised when architecture patterns are violated."""
    pass


def get_python_files_in_directory(directory: Path) -> List[Path]:
    """Get all Python files in a directory recursively."""
    python_files = []
    if directory.exists() and directory.is_dir():
        for file_path in directory.rglob("*.py"):
            # Skip __pycache__ and test files for service analysis
            if "__pycache__" not in str(file_path):
                python_files.append(file_path)
    return python_files


def extract_imports_from_file(file_path: Path) -> Set[str]:
    """Extract all imports from a Python file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        imports = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        imports.add(f"{node.module}.{alias.name}")
        
        return imports
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError):
        # Skip files that can't be parsed (e.g., non-Python files)
        return set()


def check_service_model_imports() -> List[str]:
    """Check that services don't import ORM models directly."""
    violations = []
    
    # Get project root
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent
    services_dir = project_root / "server" / "src" / "services"
    
    # Banned model imports for services
    banned_imports = {
        "server.src.models.player.Player",
        "server.src.models.item.Item", 
        "server.src.models.item.PlayerInventory",
        "server.src.models.item.PlayerEquipment",
        "server.src.models.item.GroundItem",
        "server.src.models.skill.Skill",
        "server.src.models.skill.PlayerSkill",
    }
    
    service_files = get_python_files_in_directory(services_dir)
    
    for service_file in service_files:
        # Skip GSM files (they have known violations documented separately)
        if "game_state_manager" in str(service_file):
            continue
            
        imports = extract_imports_from_file(service_file)
        
        for banned_import in banned_imports:
            if banned_import in imports:
                relative_path = service_file.relative_to(project_root)
                violations.append(
                    f"{relative_path} imports banned model: {banned_import}"
                )
    
    return violations


def check_api_database_imports() -> List[str]:
    """Check that API endpoints don't import database sessions or ORM models."""
    violations = []
    
    # Get project root  
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent
    api_dir = project_root / "server" / "src" / "api"
    
    # Banned imports for API layer
    banned_imports = {
        "server.src.core.database.get_db",
        "sqlalchemy.ext.asyncio.AsyncSession",
        "server.src.models.player.Player",
        "server.src.models.item.Item",
        "server.src.models.item.PlayerInventory", 
        "server.src.models.item.PlayerEquipment",
        "server.src.models.item.GroundItem",
        "server.src.models.skill.Skill",
        "server.src.models.skill.PlayerSkill",
    }
    
    api_files = get_python_files_in_directory(api_dir)
    
    for api_file in api_files:
        imports = extract_imports_from_file(api_file)
        
        for banned_import in banned_imports:
            if banned_import in imports:
                relative_path = api_file.relative_to(project_root)
                violations.append(
                    f"{relative_path} imports banned database/model: {banned_import}"
                )
    
    return violations


def check_service_database_sessions() -> List[str]:
    """Check that services don't create database sessions directly."""
    violations = []
    
    # Get project root
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent
    services_dir = project_root / "server" / "src" / "services"
    
    # Patterns that indicate direct database session usage
    banned_patterns = [
        "AsyncSession", 
        "get_db",
        "sessionmaker",
        "_db_session",
    ]
    
    service_files = get_python_files_in_directory(services_dir)
    
    for service_file in service_files:
        # Skip GSM files (they legitimately need database access)
        if "game_state_manager" in str(service_file):
            continue
            
        try:
            with open(service_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            for pattern in banned_patterns:
                if pattern in content:
                    relative_path = service_file.relative_to(project_root)
                    violations.append(
                        f"{relative_path} contains banned database pattern: {pattern}"
                    )
        except (UnicodeDecodeError, FileNotFoundError):
            continue
    
    return violations


# =============================================================================
# TEST CASES
# =============================================================================

def test_services_no_model_imports():
    """
    CRITICAL: Services must not import ORM models directly.
    
    This enforces the GSM architecture where services work with pure data
    structures and delegate all data operations to GSM.
    """
    violations = check_service_model_imports()
    
    if violations:
        error_msg = "\n".join([
            "ARCHITECTURE VIOLATION: Services importing ORM models directly!",
            "",
            "Services must use GSM and dataclasses instead of ORM models.",
            "This violates the GSM architecture patterns.",
            "",
            "Violations found:",
        ] + [f"  - {v}" for v in violations] + [
            "", 
            "Fix: Replace model imports with GSM calls and dataclasses.",
            "See: GSM_ARCHITECTURE_PATTERNS.md"
        ])
        raise ArchitectureViolationError(error_msg)


def test_api_no_database_imports():
    """
    CRITICAL: API endpoints must not import database sessions or ORM models.
    
    This enforces proper layering where API -> Services -> GSM -> Database.
    """
    violations = check_api_database_imports()
    
    if violations:
        error_msg = "\n".join([
            "ARCHITECTURE VIOLATION: API endpoints importing database/models directly!",
            "",
            "API endpoints must use services only, not database or GSM directly.",
            "This violates proper layered architecture.",
            "",
            "Violations found:",
        ] + [f"  - {v}" for v in violations] + [
            "",
            "Fix: Use service layer methods instead of direct database access.",
            "See: GSM_ARCHITECTURE_PATTERNS.md"
        ])
        raise ArchitectureViolationError(error_msg)


def test_services_no_database_sessions():
    """
    HIGH: Services should not create database sessions directly.
    
    This enforces GSM as the single data access layer.
    """
    violations = check_service_database_sessions()
    
    if violations:
        error_msg = "\n".join([
            "ARCHITECTURE VIOLATION: Services using database sessions directly!",
            "",
            "Services should use GSM singleton, not create database sessions.",
            "This violates the single source of truth principle.",
            "",
            "Violations found:",
        ] + [f"  - {v}" for v in violations] + [
            "",
            "Fix: Use get_game_state_manager() singleton instead.",
            "See: GSM_ARCHITECTURE_PATTERNS.md"
        ])
        raise ArchitectureViolationError(error_msg)


def test_gsm_architectural_debt_documentation():
    """
    MEDIUM: Document known GSM architectural violations.
    
    The GSM itself has 45+ model imports which is a fundamental
    architectural issue. This test documents the current state
    and serves as a reminder for future refactoring.
    """
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent
    gsm_init = project_root / "server" / "src" / "services" / "game_state_manager" / "__init__.py"
    
    # Count model imports in GSM (this is expected to be high currently)
    violations = []
    if gsm_init.exists():
        with open(gsm_init, 'r') as f:
            content = f.read()
            
        # Count lines with model imports
        import_lines = [line for line in content.split('\n') if 'from server.src.models' in line]
        violation_count = len(import_lines)
        
        # Document the current state
        print(f"\n📊 GSM ARCHITECTURAL DEBT METRICS:")
        print(f"   Model imports in GSM: {violation_count}")
        print(f"   Status: KNOWN ARCHITECTURAL DEBT")
        print(f"   Action Required: Future GSM refactoring")
        print(f"   Priority: Major refactoring project")
        
        # This test passes but documents the debt
        if violation_count > 40:
            print(f"   🚨 GSM model violations: {violation_count} (expected ~45)")
        
        # Validate expected legacy violations remain during migration
        assert violation_count > 0, "GSM refactoring completed - update this test"


@pytest.mark.integration
def test_service_layer_compliance_integration():
    """
    Integration test: Verify all service layers comply with GSM architecture.
    
    This test combines all architecture checks to ensure the service layer
    maintains proper separation of concerns.
    """
    print("\n🔍 RUNNING COMPREHENSIVE ARCHITECTURE AUDIT...")
    
    # Collect all violations
    all_violations = []
    
    service_model_violations = check_service_model_imports()  
    api_db_violations = check_api_database_imports()
    service_db_violations = check_service_database_sessions()
    
    if service_model_violations:
        all_violations.extend([f"SERVICE-MODEL: {v}" for v in service_model_violations])
        
    if api_db_violations:
        all_violations.extend([f"API-DATABASE: {v}" for v in api_db_violations])
        
    if service_db_violations:
        all_violations.extend([f"SERVICE-DB: {v}" for v in service_db_violations])
    
    # Report results
    if not all_violations:
        print("   ✅ All service layer architecture checks passed!")
        print("   📋 Service layer complies with GSM patterns")
    else:
        error_msg = "\n".join([
            "🚨 MULTIPLE ARCHITECTURE VIOLATIONS DETECTED:",
            "",
        ] + [f"  - {v}" for v in all_violations] + [
            "",
            "These violations break GSM architecture patterns.",
            "Fix all violations before proceeding with further development.",
            "",
            "Architecture Guide: GSM_ARCHITECTURE_PATTERNS.md"
        ])
        raise ArchitectureViolationError(error_msg)


if __name__ == "__main__":
    # Allow running this test file directly for architecture auditing
    print("🏗️  ARCHITECTURE ENFORCEMENT AUDIT")
    print("="*50)
    
    try:
        test_services_no_model_imports()
        print("✅ Services model import check: PASSED")
    except ArchitectureViolationError as e:
        print(f"❌ Services model import check: FAILED\n{e}")
    
    try:
        test_api_no_database_imports() 
        print("✅ API database import check: PASSED")
    except ArchitectureViolationError as e:
        print(f"❌ API database import check: FAILED\n{e}")
    
    try:
        test_services_no_database_sessions()
        print("✅ Services database session check: PASSED")  
    except ArchitectureViolationError as e:
        print(f"❌ Services database session check: FAILED\n{e}")
        
    try:
        test_gsm_architectural_debt_documentation()
        print("✅ GSM architectural debt documentation: PASSED")
    except Exception as e:
        print(f"❌ GSM debt documentation: FAILED\n{e}")
        
    print("\n📋 Architecture audit complete.")