"""Tenant-only document lifecycle. No raw bytes, model calls, schema or policy changes."""
from .postgres_repository import PostgresDocumentRepository


class DocumentManagementService:
    def __init__(self, repository):
        if not isinstance(repository, PostgresDocumentRepository) or not repository.source_prefix:
            raise ValueError('tenant-scoped PostgreSQL repository required')
        self.repository = repository

    @staticmethod
    def validate_id(document_id):
        if type(document_id) is not str or len(document_id) != 64 or any(c not in '0123456789abcdef' for c in document_id):
            raise ValueError('invalid document ID')
        return document_id

    def list_documents(self):
        return {'documents': self.repository.list_documents(), 'retention': {
            'automatic_expiry': False,
            'logout_deletes_documents': False,
            'deletion_scope': 'application_database_only',
            'backup_erasure_guaranteed': False}}

    def document_details(self, document_id):
        return self.repository.document_details(self.validate_id(document_id))

    def delete_document(self, document_id):
        return self.repository.delete_document(self.validate_id(document_id))
