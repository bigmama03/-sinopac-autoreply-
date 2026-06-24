"""Template management — CRUD operations and file import."""

from typing import Optional

from src.data.database import Database
from src.data.repository import Repository
from src.data.models import Template
from src.utils.csv_parser import parse_file


class TemplateManager:
    """Manages reply templates (CRUD + CSV/Excel import)."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def import_from_file(self, file_path: str) -> tuple[int, int, Optional[str]]:
        """Import templates from CSV/Excel.
        Returns (imported_count, skipped_count, error_message).
        """
        templates, error = parse_file(file_path)
        if error:
            return 0, 0, error

        import sqlite3

        imported = 0
        skipped = 0
        errors = []

        for t in templates:
            try:
                self.repo.insert_template(t)
                imported += 1
            except sqlite3.IntegrityError:
                # Duplicate template_code — skip
                skipped += 1
            except Exception as e:
                errors.append(f"文案 {t.template_code}: {e}")

        if errors:
            return imported, skipped, f"部分匯入失敗: {'; '.join(errors[:5])}"

        if imported > 0:
            self.repo.log_audit("TEMPLATE_IMPORTED", {
                "file": file_path,
                "imported": imported,
                "skipped": skipped,
            })

        return imported, skipped, None

    def get_all(self, active_only: bool = True) -> list[Template]:
        return self.repo.get_all_templates(active_only)

    def get_by_category(self, category: str) -> list[Template]:
        return self.repo.get_templates_by_category(category)

    def get_by_id(self, template_id: int) -> Optional[Template]:
        return self.repo.get_template_by_id(template_id)

    def delete(self, template_id: int):
        template = self.repo.get_template_by_id(template_id)
        if template:
            self.repo.delete_template(template_id)
            self.repo.log_audit("TEMPLATE_DELETED", {
                "template_id": template_id,
                "template_code": template.template_code,
            })

    def clear_all(self):
        count = self.repo.count_templates()
        self.repo.clear_all_templates()
        self.repo.log_audit("TEMPLATES_CLEARED", {"count": count})

    def count(self) -> int:
        return self.repo.count_templates()

    def get_categories(self) -> list[str]:
        """Get distinct active template categories."""
        templates = self.repo.get_all_templates(active_only=True)
        return sorted(set(t.category for t in templates if t.category))
