"""Real PostgreSQL retrieval behind the existing registered tool and compiled graph."""
import json
import uuid
from .evidence import assemble_evidence
from .langgraph_adapter import make_retrieval_tool
from .graph_executor import GraphToolExecutor
from .query_boundary import query_evidence


class PostgresRetrievalTool:
    def __init__(self, repository):
        self.repository = repository
        self.calls = 0

    def retrieve_evidence(self, query_vector, *, top_k, max_evidence_items, max_context_chars):
        for value, maximum in [(top_k, 10), (max_evidence_items, 10), (max_context_chars, 20000)]:
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError('bounded positive retrieval limits required')
        self.calls += 1
        hits = self.repository.retrieve(query_vector, top_k=top_k)
        return assemble_evidence(hits, max_items=max_evidence_items, max_chars=max_context_chars)


class PersistedQueryService:
    def __init__(self, *, repository, query_provider):
        if query_provider is None:
            raise ValueError('explicit query provider required')
        if not repository.embedding_profile.startswith('synthetic'):
            raise ValueError('this local evidence service requires a labelled synthetic profile')
        self.repository, self.provider = repository, query_provider
        self.retrieval = PostgresRetrievalTool(repository)
        self.sdk_tool = make_retrieval_tool(self.retrieval)
        self.executor = GraphToolExecutor(self.sdk_tool)

    def query(self, query, *, top_k=5):
        if type(top_k) is not int or not 1 <= top_k <= 10:
            raise ValueError('top_k must be integer 1..10')
        message = query_evidence(query, self.provider, self.sdk_tool,
            expected_dimension=self.repository.dimension, max_query_chars=2000,
            top_k=top_k, max_evidence_items=top_k, max_context_chars=20000,
            call_id='query-' + uuid.uuid4().hex, executor=self.executor)
        payload = json.loads(message.content) if isinstance(message.content, str) else message.content
        return {'kind': 'retrieval_evidence', 'generated_answer': False,
                'embedding_profile': self.repository.embedding_profile,
                'synthetic_vectors': True, 'tool_selection': 'explicit_not_model_selected',
                'evidence': payload, 'entry_count': len(message.artifact.entries),
                'omitted_count': message.artifact.omitted_count}
