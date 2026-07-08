from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fastapi import Request

LANG_SESSION_KEY = "ui_language"
DEFAULT_LANGUAGE = "zh"
SUPPORTED_LANGUAGES = {"zh", "en"}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh": {
        "nav.items": "条目",
        "nav.tags": "标签",
        "nav.creators": "创作者",
        "nav.stats": "统计",
        "nav.import": "导入",
        "nav.backup": "备份",
        "nav.logout": "退出",
        "language.zh": "中文",
        "language.en": "English",
        "common.back": "返回",
        "common.save": "保存",
        "common.delete": "删除",
        "common.none": "无",
        "common.any": "任意",
        "common.file": "文件",
        "common.name": "名称",
        "common.type": "类型",
        "common.category": "分类",
        "common.count": "数量",
        "common.date": "日期",
        "common.status": "状态",
        "common.rating": "评分",
        "common.review": "短评",
        "common.title": "标题",
        "common.summary": "简介",
        "common.tags": "标签",
        "common.creators": "创作者",
        "common.extra": "扩展信息",
        "common.cover_path": "封面路径",
        "common.avatar_path": "头像路径",
        "common.release_date": "发布日期",
        "common.extra_json": "扩展 JSON",
        "common.no_cover": "无封面",
        "common.search": "搜索",
        "login.title": "登录",
        "login.subtitle": "本地单用户媒体记录管理。",
        "login.password": "密码",
        "login.submit": "登录",
        "login.invalid_password": "密码无效。",
        "dashboard.title": "仪表盘",
        "dashboard.summary": "{items} 个条目，{tags} 个标签，{creators} 位创作者",
        "dashboard.new_item": "新建条目",
        "dashboard.import": "导入",
        "dashboard.recent_items": "最近添加",
        "dashboard.empty": "还没有条目。",
        "items.title": "条目",
        "items.new": "新建条目",
        "items.no_matching": "没有匹配的条目。",
        "items.create_title": "新建条目",
        "items.edit_title": "编辑条目",
        "items.placeholder_title": "按标题搜索",
        "items.placeholder_tag": "按标签过滤",
        "items.placeholder_cover": "本地封面路径",
        "items.placeholder_summary": "记录简介",
        "items.placeholder_tags": "标签，用逗号分隔",
        "items.placeholder_creators": "创作者，用逗号分隔",
        "items.placeholder_extra": "JSON 对象，例如 {\"source\":\"manual\"}",
        "items.placeholder_review": "记录你的想法",
        "detail.edit": "编辑",
        "detail.clear_state": "清除状态",
        "tags.title": "标签",
        "tags.add": "添加标签",
        "tags.empty": "没有标签。",
        "creators.title": "创作者",
        "creators.add": "添加创作者",
        "creators.empty": "没有创作者。",
        "creators.items": "作品",
        "stats.title": "统计",
        "stats.items": "条目",
        "stats.tags": "标签",
        "stats.creators": "创作者",
        "stats.states": "状态分布",
        "stats.timeline": "时间线",
        "stats.no_states": "没有状态记录。",
        "stats.no_items": "没有条目。",
        "import.title": "导入",
        "import.result": "已导入 {imported} 条，跳过 {skipped} 条。",
        "import.row": "行",
        "import.error": "错误",
        "import.preview": "预览",
        "import.preview_ready": "{count} 行待导入。最多显示 20 行。",
        "import.confirm": "确认导入",
        "import.preview_csv": "预览 CSV",
        "import.preview_json": "预览 JSON",
        "backup.title": "备份与恢复",
        "backup.description": "导出和恢复仅处理本地 SQLite 数据库中的数据，不会请求任何外部地址。",
        "backup.export_json": "导出 JSON 备份",
        "backup.export_csv": "导出 CSV",
        "backup.restore_title": "恢复 JSON 备份",
        "backup.restore": "上传并恢复",
        "backup.restore_hint": "只支持由 NSFWTrack 导出的 JSON 备份。恢复采用追加 / 合并策略。",
        "backup.restore_success": "恢复完成：新增 {created} 条，更新 {updated} 条，跳过 {skipped} 条。",
        "backup.restore_error": "恢复失败：{error}",
        "backup.error_json_required": "请上传 JSON 备份文件。",
        "backup.error_invalid": "备份文件格式无效，未修改现有数据库。",
        "status.wish": "想看",
        "status.watching": "在看",
        "status.watched": "已看",
        "status.like": "喜欢",
        "status.dislike": "不喜欢",
        "status.ignore": "忽略",
    },
    "en": {
        "nav.items": "Items",
        "nav.tags": "Tags",
        "nav.creators": "Creators",
        "nav.stats": "Stats",
        "nav.import": "Import",
        "nav.backup": "Backup",
        "nav.logout": "Logout",
        "language.zh": "中文",
        "language.en": "English",
        "common.back": "Back",
        "common.save": "Save",
        "common.delete": "Delete",
        "common.none": "None",
        "common.any": "Any",
        "common.file": "File",
        "common.name": "Name",
        "common.type": "Type",
        "common.category": "Category",
        "common.count": "Count",
        "common.date": "Date",
        "common.status": "Status",
        "common.rating": "Rating",
        "common.review": "Review",
        "common.title": "Title",
        "common.summary": "Summary",
        "common.tags": "Tags",
        "common.creators": "Creators",
        "common.extra": "Extra",
        "common.cover_path": "Cover Path",
        "common.avatar_path": "Avatar Path",
        "common.release_date": "Release Date",
        "common.extra_json": "Extra JSON",
        "common.no_cover": "No cover",
        "common.search": "Search",
        "login.title": "Login",
        "login.subtitle": "Local media records for one signed-in user.",
        "login.password": "Password",
        "login.submit": "Login",
        "login.invalid_password": "Invalid password.",
        "dashboard.title": "Dashboard",
        "dashboard.summary": "{items} items, {tags} tags, {creators} creators",
        "dashboard.new_item": "New Item",
        "dashboard.import": "Import",
        "dashboard.recent_items": "Recent Items",
        "dashboard.empty": "No items yet.",
        "items.title": "Items",
        "items.new": "New Item",
        "items.no_matching": "No matching items.",
        "items.create_title": "Create Item",
        "items.edit_title": "Edit Item",
        "items.placeholder_title": "Search by title",
        "items.placeholder_tag": "Filter by tag",
        "items.placeholder_cover": "Local cover path",
        "items.placeholder_summary": "Record summary",
        "items.placeholder_tags": "Tags, comma separated",
        "items.placeholder_creators": "Creators, comma separated",
        "items.placeholder_extra": "JSON object, e.g. {\"source\":\"manual\"}",
        "items.placeholder_review": "Write your notes",
        "detail.edit": "Edit",
        "detail.clear_state": "Clear State",
        "tags.title": "Tags",
        "tags.add": "Add Tag",
        "tags.empty": "No tags.",
        "creators.title": "Creators",
        "creators.add": "Add Creator",
        "creators.empty": "No creators.",
        "creators.items": "Items",
        "stats.title": "Stats",
        "stats.items": "Items",
        "stats.tags": "Tags",
        "stats.creators": "Creators",
        "stats.states": "States",
        "stats.timeline": "Timeline",
        "stats.no_states": "No states.",
        "stats.no_items": "No items.",
        "import.title": "Import",
        "import.result": "Imported {imported}, skipped {skipped}.",
        "import.row": "Row",
        "import.error": "Error",
        "import.preview": "Preview",
        "import.preview_ready": "{count} rows ready. Showing up to 20 rows.",
        "import.confirm": "Confirm Import",
        "import.preview_csv": "Preview CSV",
        "import.preview_json": "Preview JSON",
        "backup.title": "Backup and Restore",
        "backup.description": "Export and restore only use data from the local SQLite database. No external address is requested.",
        "backup.export_json": "Export JSON Backup",
        "backup.export_csv": "Export CSV",
        "backup.restore_title": "Restore JSON Backup",
        "backup.restore": "Upload and Restore",
        "backup.restore_hint": "Only JSON backups exported by NSFWTrack are supported. Restore uses an append / merge strategy.",
        "backup.restore_success": "Restore complete: created {created}, updated {updated}, skipped {skipped}.",
        "backup.restore_error": "Restore failed: {error}",
        "backup.error_json_required": "Please upload a JSON backup file.",
        "backup.error_invalid": "The backup file format is invalid. Existing data was not modified.",
        "status.wish": "Wish",
        "status.watching": "Watching",
        "status.watched": "Watched",
        "status.like": "Like",
        "status.dislike": "Dislike",
        "status.ignore": "Ignore",
    },
}


def normalize_language(language: str | None) -> str:
    if language in SUPPORTED_LANGUAGES:
        return language
    return DEFAULT_LANGUAGE


def get_language(request: Request) -> str:
    return normalize_language(request.session.get(LANG_SESSION_KEY))


def set_language(request: Request, language: str) -> str:
    normalized = normalize_language(language)
    request.session[LANG_SESSION_KEY] = normalized
    return normalized


def translate(language: str, key: str, **values: Any) -> str:
    text = TRANSLATIONS.get(normalize_language(language), {}).get(key)
    if text is None:
        text = TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
    if values:
        return text.format(**values)
    return text


def translator(language: str) -> Callable[..., str]:
    def _translate(key: str, **values: Any) -> str:
        return translate(language, key, **values)

    return _translate


def status_translator(language: str) -> Callable[[str | None], str]:
    def _status_label(status: str | None) -> str:
        if not status:
            return ""
        return translate(language, f"status.{status}")

    return _status_label


def assert_translation_coverage(languages: Mapping[str, Mapping[str, str]]) -> bool:
    expected = set(languages[DEFAULT_LANGUAGE])
    return all(set(values) == expected for values in languages.values())
