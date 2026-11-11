import sys
from types import ModuleType, SimpleNamespace

from app.config import Settings
from app.repositories import FirestoreWorkSessionRepository


def test_settings_uses_firebase_project_id(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "firebase-project-id")
    monkeypatch.setenv("FIRESTORE_PROJECT_ID", "legacy-project-id")

    settings = Settings(_env_file=None)

    assert settings.firebase_project_id == "firebase-project-id"


def test_firestore_repository_uses_firebase_project_and_database_id(monkeypatch):
    calls = {}
    app = object()
    collection = object()

    firebase_admin = ModuleType("firebase_admin")

    def get_app():
        raise ValueError

    def initialize_app(*, options):
        calls["options"] = options
        return app

    def client(*, app, database_id):
        calls["app"] = app
        calls["database_id"] = database_id
        return SimpleNamespace(
            collection=lambda name: calls.setdefault("collection", (name, collection))[1]
        )

    firebase_admin.get_app = get_app
    firebase_admin.initialize_app = initialize_app
    firebase_admin.firestore = SimpleNamespace(client=client)
    monkeypatch.setitem(sys.modules, "firebase_admin", firebase_admin)

    repository = FirestoreWorkSessionRepository(
        "firebase-project-id",
        "(default)",
        "work_sessions",
    )

    assert calls == {
        "options": {"projectId": "firebase-project-id"},
        "app": app,
        "database_id": "(default)",
        "collection": ("work_sessions", collection),
    }
    assert repository._collection is collection
