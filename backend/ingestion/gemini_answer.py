"""Opt-in structured Gemini adapter. Construction never invokes a model."""
import json
import time
from importlib.metadata import version
from google import genai
from google.genai import types


class GeminiAnswerError(Exception):
    def __init__(self, category):
        self.category=category
        super().__init__(category)


ANSWER_SCHEMA={
    'type':'object','additionalProperties':False,
    'properties':{
        'status':{'type':'string','enum':['answered','insufficient_evidence']},
        'answer':{'type':'string'},
        'claims':{'type':'array','items':{'type':'object','additionalProperties':False,
            'properties':{'text':{'type':'string'},'evidence_refs':{'type':'array','items':{'type':'string'}}},
            'required':['text','evidence_refs']}},
        'used_evidence_refs':{'type':'array','items':{'type':'string'}}},
    'required':['status','answer','claims','used_evidence_refs']}
BLOCKED={'SAFETY','RECITATION','BLOCKLIST','PROHIBITED_CONTENT','SPII','IMAGE_SAFETY','IMAGE_PROHIBITED_CONTENT','MODEL_ARMOR'}
KNOWN_FINISH={item.value for item in types.FinishReason}


class GeminiAnswerProvider:
    def __init__(self, *, client, model, max_output_tokens=1024):
        if client is None or type(model) is not str or not model.strip() or len(model)>128:
            raise ValueError('explicit client and model required')
        if type(max_output_tokens) is not int or not 1<=max_output_tokens<=1024:
            raise ValueError('output tokens must be 1..1024')
        self.client,self.model,self.max_output_tokens=client,model,max_output_tokens
        self.last_diagnostic=None
        self._owns_client=False

    @classmethod
    def from_api_key(cls, *, api_key, model, timeout_ms=15000, max_output_tokens=1024):
        if not api_key or type(timeout_ms) is not int or not 1000<=timeout_ms<=60000:
            raise ValueError('explicit key and bounded timeout required')
        client=genai.Client(api_key=api_key,http_options=types.HttpOptions(
            timeout=timeout_ms,retry_options=types.HttpRetryOptions(attempts=1)))
        try:
            provider=cls(client=client,model=model,max_output_tokens=max_output_tokens)
            provider._owns_client=True
            return provider
        except BaseException:
            client.close()
            raise

    def close(self):
        if self._owns_client:
            self._owns_client=False
            self.client.close()

    def generate(self, *, instructions, question, evidence, omitted_count):
        started=time.monotonic()
        diagnostic={'provider':'gemini','sdk_version':version('google-genai'),
                    'category':None,'http_status':None,'finish_reason':None,'elapsed_seconds':None}
        # Do not retain model strings, request IDs, arbitrary error attributes,
        # response bodies, prompts or headers in diagnostics. They are untrusted.
        def fail(category):
            diagnostic['category']=category
            raise GeminiAnswerError(category)
        try:
            contents=json.dumps({'question':question,'evidence':evidence,'omitted_count':omitted_count},ensure_ascii=False,allow_nan=False)
            config=types.GenerateContentConfig(system_instruction=instructions,
                response_mime_type='application/json',response_json_schema=ANSWER_SCHEMA,
                max_output_tokens=self.max_output_tokens,candidate_count=1)
            try:
                response=self.client.models.generate_content(model=self.model,contents=contents,config=config)
            except Exception as error:
                code=getattr(error,'code',None)
                if type(code) is int and 100<=code<=599:diagnostic['http_status']=code
                fail('provider_unavailable')
            if not isinstance(response,types.GenerateContentResponse):fail('response_unexpected')
            feedback=response.prompt_feedback
            if feedback and feedback.block_reason and feedback.block_reason.value!='BLOCKED_REASON_UNSPECIFIED':fail('response_blocked')
            candidates=response.candidates
            if not candidates:fail('response_empty')
            if len(candidates)!=1:fail('response_unexpected')
            reason=candidates[0].finish_reason
            reason=reason.value if reason else None
            if reason in KNOWN_FINISH:diagnostic['finish_reason']=reason
            if reason in BLOCKED:fail('response_blocked')
            if reason!='STOP':fail('response_incomplete')
            if response.parsed is not None:
                if type(response.parsed) is not dict:fail('response_unexpected')
                result=response.parsed
            else:
                text=response.text
                if not text or not text.strip():fail('response_empty')
                if len(text)>64000:fail('response_malformed')
                try:result=json.loads(text)
                except (ValueError,TypeError):fail('response_malformed')
                if type(result) is not dict:fail('response_unexpected')
            diagnostic['category']='success'
            return result  # Application validator remains authoritative.
        except GeminiAnswerError:
            raise
        except Exception:
            fail('response_unexpected')
        finally:
            diagnostic['elapsed_seconds']=round(time.monotonic()-started,3)
            self.last_diagnostic=diagnostic
