"""Explicit answer composition over the existing persisted retrieval message."""
from dataclasses import asdict
from .answer_boundary import (AnswerRequest, InvalidAnswerInput, generate_answer,
                              resolve_citations)


class PersistedAnswerService:
    def __init__(self, *, query_service, answer_provider):
        if query_service is None or answer_provider is None:
            raise ValueError('explicit retrieval and answer providers required')
        self.query_service=query_service
        self.answer_provider=answer_provider

    def answer(self, question, *, top_k=5):
        if type(question) is not str or not question.strip() or len(question)>2000 or type(top_k) is not int or not 1<=top_k<=10:
            raise InvalidAnswerInput('invalid_answer_input')
        message=self.query_service.retrieve_message(question,top_k=top_k)
        bundle=message.artifact
        result=generate_answer(AnswerRequest(question,bundle),self.answer_provider)
        citations=[]
        for ref,hit in resolve_citations(result,bundle):
            located=hit.located_chunk
            citations.append({'ref':ref,'citation':asdict(located.chunk.citation),
                              'locator':asdict(located.locator),'located_id':located.located_id})
        return {'kind':'validated_answer_contract','status':result.status,'answer':result.answer,
                'claims':[{'text':c.text,'evidence_refs':list(c.evidence_refs)} for c in result.claims],
                'citations':citations,'used_evidence_refs':list(result.used_evidence_refs),
                'omitted_count':bundle.omitted_count,'citation_integrity_validated':True,
                'factual_entailment_verified':False,'tool_selection':'explicit_not_model_selected',
                'embedding_profile':self.query_service.repository.embedding_profile}
