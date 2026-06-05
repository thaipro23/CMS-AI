import json
import logging
import re
from typing import Any

import httpx
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.prompt_builder import build_question_prompt
from app.services.runtime_settings import apply_runtime_settings
from app.services.token_counter import count_tokens

logger = logging.getLogger(__name__)

class ModelResponseParseError(RuntimeError):
    """Raised after OpenAI has returned successfully, but output parsing failed.

    The request may already be billed by OpenAI. Carry usage details so the
    worker can reconcile actual cost even when no questions are saved.
    """

    def __init__(
        self,
        message: str,
        *,
        usage: dict[str, Any],
        raw_usage: dict[str, Any],
        raw_output_text: str,
        response_id: str | None,
        model: str,
        provider: str = 'openai_responses',
    ) -> None:
        super().__init__(message)
        self.usage = usage
        self.raw_usage = raw_usage
        self.raw_output_text = raw_output_text
        self.response_id = response_id
        self.model = model
        self.provider = provider


class ModelGateway:
    """Single gateway for all model calls.

    UI/services must not call OpenAI/local model directly. This keeps cost logging,
    retry, provider routing and local fallback centralized.

    v20 mock mode is intentionally rich: it parses Source/ChunkId metadata from
    synced course chunks and returns valid source_chunk_id/source_ref so source
    grounding, review queue, duplicate detection and node coverage can be tested
    without spending API cost.
    """

    async def generate_structured_json(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        schema_name: str,
        instructions: str,
        prompt_cache_key: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Call the real OpenAI Responses API for a custom strict JSON task.

        This is intentionally not available in mock mode. Callers use it for
        decisions that must be clearly marked as AI-generated, then apply their
        own deterministic validation before persisting or publishing results.
        """
        apply_runtime_settings()
        if settings.mock_llm:
            raise RuntimeError('MOCK_LLM=true nên không thể chạy Structured Output task thật.')
        if not settings.openai_api_key:
            raise RuntimeError('OPENAI_API_KEY đang trống nên không thể chạy Structured Output task.')
        if settings.openai_api_mode != 'responses':
            raise RuntimeError('Structured Output task hiện yêu cầu OPENAI_API_MODE=responses.')

        payload: dict[str, Any] = {
            'model': settings.openai_model,
            'instructions': instructions,
            'input': prompt,
            'text': {
                'format': {
                    'type': 'json_schema',
                    'name': schema_name[:64],
                    'schema': schema,
                    'strict': True,
                }
            },
            'store': False,
        }
        if prompt_cache_key:
            payload['prompt_cache_key'] = prompt_cache_key[:256]

        fallback_input_tokens = count_tokens(json.dumps(payload, ensure_ascii=False), settings.openai_model)
        timeout_seconds = max(int(settings.llm_timeout_seconds or 90), 90)
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post('https://api.openai.com/v1/responses', headers=self._auth_headers(), json=payload)
            if response.status_code == 400 and prompt_cache_key and 'prompt_cache_key' in payload:
                logger.warning('Structured Responses API rejected prompt_cache_key, retrying without it: %s', response.text[:800])
                payload.pop('prompt_cache_key', None)
                response = await client.post('https://api.openai.com/v1/responses', headers=self._auth_headers(), json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f'OpenAI Structured Responses API failed {response.status_code}: {response.text[:1200]}')

        data = response.json()
        usage = data.get('usage') or {}
        text = self._extract_responses_output_text(data)
        parsed = self._parse_json_payload(text)
        input_tokens = int(usage.get('input_tokens') or usage.get('prompt_tokens') or fallback_input_tokens)
        cached_input_tokens = int(self._cached_tokens_from_usage(usage) or 0)
        output_tokens = int(usage.get('output_tokens') or usage.get('completion_tokens') or count_tokens(text, settings.openai_model))
        usage_dict = {
            'input_tokens': input_tokens,
            'cached_input_tokens': cached_input_tokens,
            'uncached_input_tokens': max(input_tokens - cached_input_tokens, 0),
            'output_tokens': output_tokens,
            'provider': 'openai_responses',
            'model': settings.openai_model,
            'api_mode': 'responses',
            'response_id': data.get('id'),
            'prompt_cache_key': prompt_cache_key,
        }
        return parsed, usage_dict

    async def generate_questions(
        self,
        *,
        content: str,
        question_count: int,
        scope_title: str | None = None,
        target_difficulty: str | None = None,
        difficulty_counts: dict[str, int] | None = None,
        provider: str = 'auto',
        prompt_cache_key: str | None = None,
    ) -> tuple[list[dict], dict]:
        # Runtime settings can be changed from the admin Settings page.
        # Backend and worker are different containers, so always reload the
        # shared runtime config immediately before a model call.
        apply_runtime_settings()
        prompt = build_question_prompt(content, question_count, scope_title, target_difficulty, difficulty_counts=difficulty_counts)
        input_tokens = count_tokens(prompt, settings.openai_model)
        provider = provider or settings.model_provider

        if settings.mock_llm or (provider != 'local' and not settings.openai_api_key):
            questions = self._mock_questions(question_count, scope_title or 'Nội dung bài học', content, target_difficulty, difficulty_counts)
            output_tokens = count_tokens(json.dumps({'questions': questions}, ensure_ascii=False), settings.openai_model)
            return questions, {'input_tokens': input_tokens, 'cached_input_tokens': 0, 'output_tokens': output_tokens, 'provider': 'mock', 'model': settings.openai_model, 'token_source': 'local_tiktoken', 'prompt_cache_key': prompt_cache_key}

        # Routing policy: API-first in phase 1, hybrid/local-ready in phase 2/3.
        providers = self._provider_order(provider)
        last_error: Exception | None = None
        for selected in providers:
            try:
                return await self._call_openai_compatible(prompt, selected, input_tokens, prompt_cache_key=prompt_cache_key)
            except Exception as exc:
                last_error = exc
                if selected == providers[-1]:
                    raise
        raise RuntimeError(f'Model gateway failed: {last_error}')

    def _provider_order(self, provider: str) -> list[str]:
        if provider == 'auto':
            # Phase 2/3 can put local first by setting MODEL_PROVIDER=local.
            return ['local', 'openai'] if settings.model_provider == 'local' else ['openai', 'local']
        if provider == 'local':
            return ['local', 'openai']
        return ['openai']

    async def _call_openai_compatible(self, prompt: str, provider: str, fallback_input_tokens: int, *, prompt_cache_key: str | None = None) -> tuple[list[dict], dict]:
        """Call the configured real model provider.

        v24.2 defaults OpenAI to the Responses API because it is the newer API
        surface for GPT-5-class text generation and Structured Outputs. Chat
        Completions is kept as a legacy fallback for old projects and local
        OpenAI-compatible servers.
        """
        if provider == 'openai' and not settings.openai_api_key:
            raise RuntimeError('OPENAI_API_KEY is empty. Add API key in Settings or .env, then save.')

        # Local OpenAI-compatible servers usually expose /chat/completions, not
        # /responses. Keep them on the legacy path unless the team later verifies
        # their local gateway supports the Responses API.
        if provider == 'openai' and settings.openai_api_mode == 'responses':
            return await self._call_openai_responses(prompt, fallback_input_tokens, prompt_cache_key=prompt_cache_key)
        return await self._call_chat_legacy(prompt, provider, fallback_input_tokens, prompt_cache_key=prompt_cache_key)

    def _question_json_schema(self) -> dict[str, Any]:
        question = {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'topic': {'type': 'string'},
                'concept_id': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                'concept_title': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                'concept_key': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                'question_family_id': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                'variant_no': {'anyOf': [{'type': 'integer'}, {'type': 'null'}]},
                'source_evidence': {'type': 'string'},
                'difficulty': {'type': 'string', 'enum': ['easy', 'medium', 'hard']},
                'cognitive_level': {'type': 'string', 'enum': ['remember', 'understand', 'recognize_example', 'simple_apply']},
                'learning_objective': {'type': 'string'},
                'question_type': {'type': 'string', 'enum': ['single_choice']},
                'question': {'type': 'string'},
                'options': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {
                        'A': {'type': 'string'},
                        'B': {'type': 'string'},
                        'C': {'type': 'string'},
                        'D': {'type': 'string'},
                    },
                    'required': ['A', 'B', 'C', 'D'],
                },
                'correct_answer': {'type': 'string', 'enum': ['A', 'B', 'C', 'D']},
                'explanation': {'type': 'string'},
                'source_ref': {'type': 'string'},
                'source_type': {'type': 'string'},
                'source_page': {'anyOf': [{'type': 'integer'}, {'type': 'null'}]},
                'source_timestamp_start': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                'source_timestamp_end': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                'source_chunk_id': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                'source_node_id': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                'source_excerpt': {'type': 'string'},
                'tags': {'type': 'array', 'items': {'type': 'string'}},
                'ai_rationale': {'type': 'string'},
            },
            'required': [
                'topic', 'concept_id', 'concept_title', 'concept_key', 'question_family_id', 'variant_no', 'source_evidence', 'difficulty', 'cognitive_level', 'learning_objective', 'question_type',
                'question', 'options', 'correct_answer', 'explanation', 'source_ref', 'source_type',
                'source_page', 'source_timestamp_start', 'source_timestamp_end', 'source_chunk_id',
                'source_node_id', 'source_excerpt', 'tags', 'ai_rationale'
            ],
        }
        return {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'questions': {
                    'type': 'array',
                    'items': question,
                }
            },
            'required': ['questions'],
        }

    def _system_instruction(self) -> str:
        return 'Bạn là AI Learning Check Generator. Trả về đúng JSON theo schema, không markdown.'

    def _structured_output_config(self) -> dict[str, Any]:
        return {
            'format': {
                'type': 'json_schema',
                'name': 'learning_check_questions',
                'schema': self._question_json_schema(),
                'strict': True,
            }
        }

    def _responses_payload(self, prompt: str, prompt_cache_key: str | None = None) -> dict[str, Any]:
        payload = {
            'model': settings.openai_model,
            'instructions': self._system_instruction(),
            'input': prompt,
            'text': self._structured_output_config(),
            'store': False,
        }
        if prompt_cache_key:
            payload['prompt_cache_key'] = prompt_cache_key[:256]
        return payload

    def _responses_input_token_payload(self, prompt: str, *, include_schema: bool = True) -> dict[str, Any]:
        """Payload for POST /v1/responses/input_tokens.

        The token-count endpoint accepts the Responses input shape and returns
        ``response.input_tokens``. It does not create/store a response and it is
        stricter than ``/v1/responses`` on some output-only fields, so we do not
        send ``store`` here. First try includes the structured-output schema so
        estimate tracks the real generation request; if OpenAI rejects that for
        a model/API change, the caller retries with a minimal payload and adds a
        conservative local schema overhead.
        """
        payload: dict[str, Any] = {
            'model': settings.openai_model,
            'instructions': self._system_instruction(),
            'input': prompt,
        }
        if include_schema:
            payload['text'] = self._structured_output_config()
        return payload

    def _local_schema_overhead_tokens(self) -> int:
        return count_tokens(json.dumps({'text': self._structured_output_config()}, ensure_ascii=False), settings.openai_model)

    def _auth_headers(self) -> dict[str, str]:
        return {
            'Authorization': f'Bearer {settings.openai_api_key}',
            'Content-Type': 'application/json',
        }

    def _cached_tokens_from_usage(self, usage: dict[str, Any]) -> int:
        details = usage.get('input_tokens_details') or usage.get('prompt_tokens_details') or {}
        if isinstance(details, dict):
            return int(details.get('cached_tokens') or details.get('cached_input_tokens') or 0)
        return 0

    async def count_responses_input_tokens_for_prompt(self, prompt: str) -> dict[str, Any]:
        """Count input tokens with POST /v1/responses/input_tokens.

        Estimate should call OpenAI's input-token endpoint before enqueueing so
        hard-stop decisions use the same model/input shape as Responses API
        generation. Safety factor is still applied later by CostControlService;
        actual cost from generation usage never uses safety_factor.
        """
        apply_runtime_settings()
        fallback = count_tokens(json.dumps(self._responses_input_token_payload(prompt, include_schema=True), ensure_ascii=False), settings.openai_model)
        if settings.mock_llm:
            return {'input_tokens': fallback, 'cached_input_tokens': 0, 'token_source': 'local_tiktoken_fallback_mock_llm_enabled'}
        if not settings.openai_api_key:
            return {'input_tokens': fallback, 'cached_input_tokens': 0, 'token_source': 'local_tiktoken_fallback_missing_api_key'}
        if settings.openai_api_mode != 'responses':
            return {'input_tokens': fallback, 'cached_input_tokens': 0, 'token_source': f'local_tiktoken_fallback_api_mode_{settings.openai_api_mode}'}

        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            # First try: include structured-output schema, but omit output-only
            # fields such as store. This should be the closest estimate to the
            # real /v1/responses request.
            full_payload = self._responses_input_token_payload(prompt, include_schema=True)
            response = await client.post('https://api.openai.com/v1/responses/input_tokens', headers=self._auth_headers(), json=full_payload)

            if response.status_code == 400:
                # Some model/API combinations have rejected text.format on the
                # token-count endpoint. Retry with the minimal supported input
                # payload; then add local schema overhead so estimate remains
                # conservative for budget hard-stop.
                logger.warning('Responses input_tokens rejected full payload with 400: %s', response.text[:1000])
                minimal_payload = self._responses_input_token_payload(prompt, include_schema=False)
                minimal_response = await client.post('https://api.openai.com/v1/responses/input_tokens', headers=self._auth_headers(), json=minimal_payload)
                if minimal_response.status_code < 400:
                    token_info = self._parse_input_token_response(minimal_response.json(), fallback)
                    schema_overhead = self._local_schema_overhead_tokens()
                    return {
                        'input_tokens': int(token_info['input_tokens']) + schema_overhead,
                        'cached_input_tokens': int(token_info.get('cached_input_tokens') or 0),
                        'token_source': 'responses/input_tokens_minimal_plus_local_schema_overhead_after_400',
                    }
                logger.warning('Responses input_tokens minimal retry failed %s: %s', minimal_response.status_code, minimal_response.text[:1000])
                return {'input_tokens': fallback, 'cached_input_tokens': 0, 'token_source': f'local_tiktoken_fallback_after_input_tokens_400_retry_{minimal_response.status_code}'}

        if response.status_code >= 400:
            logger.warning('Responses input_tokens failed %s: %s', response.status_code, response.text[:1000])
            return {'input_tokens': fallback, 'cached_input_tokens': 0, 'token_source': f'local_tiktoken_fallback_after_input_tokens_{response.status_code}'}

        token_info = self._parse_input_token_response(response.json(), fallback)
        return {
            'input_tokens': int(token_info['input_tokens']),
            'cached_input_tokens': int(token_info.get('cached_input_tokens') or 0),
            'token_source': 'responses/input_tokens',
        }

    def _parse_input_token_response(self, data: dict[str, Any], fallback: int) -> dict[str, int]:
        usage = data.get('usage') if isinstance(data.get('usage'), dict) else data
        if not isinstance(usage, dict):
            usage = {}
        input_tokens = usage.get('input_tokens') or usage.get('prompt_tokens') or data.get('input_tokens') or fallback
        cached_input_tokens = self._cached_tokens_from_usage(usage)
        return {'input_tokens': int(input_tokens), 'cached_input_tokens': int(cached_input_tokens or 0)}

    async def _call_openai_responses(self, prompt: str, fallback_input_tokens: int, *, prompt_cache_key: str | None = None) -> tuple[list[dict], dict]:
        payload = self._responses_payload(prompt, prompt_cache_key)
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post('https://api.openai.com/v1/responses', headers=self._auth_headers(), json=payload)
            if response.status_code == 400 and prompt_cache_key and 'prompt_cache_key' in payload:
                # Keep compatibility with any proxy/local gateway that has not
                # implemented prompt_cache_key yet. OpenAI supports it, but this
                # retry prevents one unsupported field from breaking generation.
                logger.warning('Responses API rejected prompt_cache_key, retrying without it: %s', response.text[:800])
                payload.pop('prompt_cache_key', None)
                response = await client.post('https://api.openai.com/v1/responses', headers=self._auth_headers(), json=payload)
        if response.status_code >= 400:
            # Surface the OpenAI error body so Settings > Test GPT is useful.
            raise RuntimeError(f'OpenAI Responses API failed {response.status_code}: {response.text[:1200]}')

        data = response.json()
        usage = data.get('usage') or {}
        text = self._extract_responses_output_text(data)
        output_tokens = usage.get('output_tokens') or usage.get('completion_tokens') or count_tokens(text)
        input_tokens = usage.get('input_tokens') or usage.get('prompt_tokens') or fallback_input_tokens
        cached_input_tokens = self._cached_tokens_from_usage(usage)
        usage_dict = {
            'input_tokens': int(input_tokens),
            'cached_input_tokens': int(cached_input_tokens),
            'uncached_input_tokens': max(int(input_tokens) - int(cached_input_tokens), 0),
            'output_tokens': int(output_tokens),
            'provider': 'openai_responses',
            'model': settings.openai_model,
            'api_mode': 'responses',
            'token_source': 'responses_usage',
            'raw_usage': usage,
            'response_id': data.get('id'),
            'raw_output_text': text[:12000],
            'prompt_cache_key': prompt_cache_key,
        }

        try:
            payload_json = self._parse_json_payload(text)
        except Exception as exc:
            # Important: OpenAI already completed this request and may charge it.
            # Do not let worker lose actual usage/cost just because parsing failed.
            logger.exception('OpenAI response completed but JSON parse failed. response_id=%s', data.get('id'))
            raise ModelResponseParseError(
                f'Model completed but output parse failed: {exc}',
                usage=usage_dict,
                raw_usage=usage if isinstance(usage, dict) else {},
                raw_output_text=text[:12000],
                response_id=data.get('id'),
                model=settings.openai_model,
            ) from exc

        questions = payload_json.get('questions', [])
        return questions, usage_dict

    def _extract_responses_output_text(self, data: dict[str, Any]) -> str:
        # The official SDK exposes response.output_text. REST JSON exposes the
        # content nested under output[].content[].text for message outputs.
        if isinstance(data.get('output_text'), str) and data['output_text'].strip():
            return data['output_text']
        parts: list[str] = []
        for item in data.get('output') or []:
            for content in item.get('content') or []:
                text = content.get('text')
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(content.get('output_text'), str):
                    parts.append(content['output_text'])
        joined = ''.join(parts).strip()
        if not joined:
            raise RuntimeError(f'OpenAI Responses API returned no output text. Raw response: {json.dumps(data, ensure_ascii=False)[:1200]}')
        return joined

    async def _call_chat_legacy(self, prompt: str, provider: str, fallback_input_tokens: int, *, prompt_cache_key: str | None = None) -> tuple[list[dict], dict]:
        client_kwargs: dict[str, Any] = {'api_key': settings.openai_api_key}
        model_name = settings.openai_model
        if provider == 'local':
            client_kwargs['base_url'] = settings.local_openai_base_url
            client_kwargs['api_key'] = settings.openai_api_key or 'local-key'
            model_name = settings.openai_model

        client = AsyncOpenAI(**client_kwargs, timeout=settings.llm_timeout_seconds)
        request_payload = {
            'model': model_name,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.2,
            'response_format': {'type': 'json_object'},
        }
        try:
            response = await client.chat.completions.create(**request_payload)
        except Exception as exc:
            text = str(exc).lower()
            if any(key in text for key in ['temperature', 'response_format', 'unsupported parameter', 'not supported']):
                minimal_payload = {
                    'model': model_name,
                    'messages': [{'role': 'user', 'content': prompt}],
                }
                response = await client.chat.completions.create(**minimal_payload)
            else:
                raise

        text = response.choices[0].message.content or '{"questions": []}'
        payload_json = self._parse_json_payload(text)
        usage = getattr(response, 'usage', None)
        cached_input_tokens = 0
        if usage:
            details = getattr(usage, 'prompt_tokens_details', None) or getattr(usage, 'input_tokens_details', None)
            cached_input_tokens = getattr(details, 'cached_tokens', 0) if details else 0
        input_tokens = getattr(usage, 'prompt_tokens', fallback_input_tokens) if usage else fallback_input_tokens
        output_tokens = getattr(usage, 'completion_tokens', count_tokens(text)) if usage else count_tokens(text)
        raw_usage = {}
        if usage:
            raw_usage = {
                'prompt_tokens': getattr(usage, 'prompt_tokens', None),
                'completion_tokens': getattr(usage, 'completion_tokens', None),
                'total_tokens': getattr(usage, 'total_tokens', None),
                'cached_tokens': cached_input_tokens,
            }
        return payload_json.get('questions', []), {
            'input_tokens': int(input_tokens),
            'cached_input_tokens': int(cached_input_tokens),
            'uncached_input_tokens': max(int(input_tokens) - int(cached_input_tokens), 0),
            'output_tokens': int(output_tokens),
            'provider': 'openai_chat_legacy' if provider == 'openai' else provider,
            'model': model_name,
            'api_mode': 'chat_legacy',
            'token_source': 'chat_usage',
            'raw_usage': raw_usage,
            'prompt_cache_key': prompt_cache_key,
        }

    def _parse_json_payload(self, text: str) -> dict[str, Any]:
        cleaned = (text or '').strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```$', '', cleaned).strip()

        candidates = [cleaned]
        # Responses API can occasionally return a short prefix/suffix around the
        # JSON when a model/API mode is changed. Try extracting the outer object.
        first_obj = cleaned.find('{')
        last_obj = cleaned.rfind('}')
        if first_obj >= 0 and last_obj > first_obj:
            candidates.append(cleaned[first_obj:last_obj + 1])
        first_arr = cleaned.find('[')
        last_arr = cleaned.rfind(']')
        if first_arr >= 0 and last_arr > first_arr:
            candidates.append('{"questions": ' + cleaned[first_arr:last_arr + 1] + '}')

        last_error: Exception | None = None
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
                if isinstance(payload, list):
                    payload = {'questions': payload}
                if not isinstance(payload, dict):
                    raise RuntimeError('Model JSON output must be an object with a questions array.')
                if 'questions' not in payload or not isinstance(payload.get('questions'), list):
                    raise RuntimeError('Model JSON output must contain a questions array.')
                return payload
            except Exception as exc:  # keep trying recovery candidates
                last_error = exc

        raise RuntimeError(f'Model did not return valid questions JSON. First 500 chars: {cleaned[:500]}') from last_error

    def _mock_questions(self, n: int, scope_title: str, content: str = '', target_difficulty: str | None = None, difficulty_counts: dict[str, int] | None = None) -> list[dict]:
        sources = self._extract_mock_sources(content)
        if not sources:
            sources = [{
                'source_ref': 'mock:fallback#chunk=1',
                'source_type': 'html',
                'source_chunk_id': None,
                'source_excerpt': content[:220] or 'Nội dung bài học mẫu.',
                'content': content or 'REST API dùng HTTP methods GET, POST, PUT, DELETE. DbContext quản lý kết nối database. Cost Control giới hạn quota.',
            }]

        templates = self._question_templates(content)
        difficulties: list[str] = []
        for diff, count in (difficulty_counts or {}).items():
            if diff in {'easy', 'medium', 'hard'}:
                difficulties.extend([diff] * int(count or 0))
        if not difficulties:
            safe = (target_difficulty or '').lower()
            difficulties = [safe if safe in {'easy', 'medium', 'hard'} else 'easy'] * n
        while len(difficulties) < n:
            difficulties.append(difficulties[-1] if difficulties else 'easy')
        questions = []
        for i in range(1, n + 1):
            source = sources[(i - 1) % len(sources)]
            template = templates[(i - 1) % len(templates)]
            local_topic = scope_title if scope_title and scope_title != 'Nội dung bài học' else template['topic']
            questions.append({
                'topic': local_topic,
                'concept_id': None,
                'concept_title': template.get('topic') or local_topic,
                'concept_key': None,
                'question_family_id': None,
                'variant_no': i,
                'source_evidence': source.get('source_excerpt') or '',
                'difficulty': difficulties[i - 1] if i - 1 < len(difficulties) else template.get('difficulty', 'easy'),
                'cognitive_level': template.get('cognitive_level', 'remember'),
                'learning_objective': template['learning_objective'],
                'question_type': 'single_choice',
                'question': template['question'] if i <= len(templates) else f"Câu {i}: Theo nội dung về {local_topic}, nhận định nào đúng?",
                'options': template['options'] if i <= len(templates) else {
                    'A': template['correct_text'],
                    'B': 'Đây là nội dung không được đề cập trong bài học',
                    'C': 'Đây là lựa chọn trái với nội dung bài học',
                    'D': 'Đây là một thao tác không liên quan đến chủ đề',
                },
                'correct_answer': template.get('correct_answer', 'A'),
                'explanation': template['explanation'],
                'source_ref': source['source_ref'],
                'source_type': source['source_type'],
                'source_page': source.get('source_page'),
                'source_timestamp_start': source.get('source_timestamp_start'),
                'source_timestamp_end': source.get('source_timestamp_end'),
                'source_chunk_id': source.get('source_chunk_id'),
                'source_node_id': source.get('source_node_id'),
                'block_id': source.get('source_node_id'),
                'source_excerpt': source['source_excerpt'],
                'tags': template.get('tags', [local_topic]),
                'ai_rationale': 'Mock v20 tạo câu hỏi Learning Check dựa trên Open edX node/chunk đã sync, có source reference hợp lệ để test source grounding.',
            })
        return questions

    def _extract_mock_sources(self, content: str) -> list[dict]:
        """Parse worker content blocks:

        Source: <source_ref>
        Type: <source_type>
        ChunkId: <db_chunk_id>
        BlockId: <component_or_node_id>
        <chunk content>
        """
        parts = re.split(r"\n\s*---\s*\n", content or '')
        sources: list[dict] = []
        for part in parts:
            text = part.strip()
            if not text:
                continue
            source_ref = self._match_line(text, r'^Source:\s*(.+)$') or 'mock:unknown'
            source_type = self._match_line(text, r'^Type:\s*(.+)$') or self._infer_source_type(source_ref)
            chunk_id = self._match_line(text, r'^ChunkId:\s*(.+)$')
            block_id = self._match_line(text, r'^BlockId:\s*(.+)$')
            body = re.sub(r'^(Source|Type|ChunkId|BlockId):\s*.+$', '', text, flags=re.M).strip()
            timestamp_start = None
            timestamp_end = None
            page = None
            time_match = re.search(r'#t=([^#\s]*)-([^#\s]*)', source_ref)
            if time_match:
                timestamp_start = time_match.group(1) or None
                timestamp_end = time_match.group(2) or None
            page_match = re.search(r'#page=(\d+)', source_ref)
            if page_match:
                page = int(page_match.group(1))
            sources.append({
                'source_ref': source_ref,
                'source_type': source_type,
                'source_chunk_id': chunk_id,
                'source_node_id': block_id,
                'source_page': page,
                'source_timestamp_start': timestamp_start,
                'source_timestamp_end': timestamp_end,
                'source_excerpt': body[:260] if body else source_ref,
                'content': body,
            })
        return sources

    def _match_line(self, text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.M)
        return match.group(1).strip() if match else None

    def _infer_source_type(self, source_ref: str) -> str:
        lower = (source_ref or '').lower()
        if 'transcript' in lower or 'video' in lower:
            return 'transcript'
        if '.pdf' in lower:
            return 'pdf'
        if '.ppt' in lower:
            return 'pptx'
        if 'problem' in lower or 'quiz' in lower:
            return 'problem'
        return 'html'

    def _question_templates(self, content: str) -> list[dict]:
        lower = (content or '').lower()
        templates: list[dict] = []

        def add(topic, question, options, answer, explanation, objective, level='remember', difficulty='easy', tags=None):
            templates.append({
                'topic': topic,
                'question': question,
                'options': options,
                'correct_answer': answer,
                'correct_text': options[answer],
                'explanation': explanation,
                'learning_objective': objective,
                'cognitive_level': level,
                'difficulty': difficulty,
                'tags': tags or [topic],
            })

        if any(k in lower for k in ['rest api', 'http', 'get', 'post', 'put', 'delete', 'endpoint']):
            add('REST API', 'REST API thường tổ chức dữ liệu theo thành phần nào?', {'A': 'Tài nguyên', 'B': 'Màu giao diện', 'C': 'Tên máy tính', 'D': 'File ảnh nền'}, 'A', 'REST API thường thiết kế endpoint theo tài nguyên như products hoặc orders.', 'Sinh viên nhận biết khái niệm tài nguyên trong REST API.', 'remember', 'easy', ['REST API', 'resource'])
            add('HTTP Methods', 'Phương thức HTTP nào thường được dùng để lấy dữ liệu từ server?', {'A': 'GET', 'B': 'POST', 'C': 'DELETE', 'D': 'PATCH'}, 'A', 'GET thường được dùng để yêu cầu server trả về dữ liệu mà không làm thay đổi dữ liệu.', 'Sinh viên nhận biết chức năng của HTTP GET.', 'remember', 'easy', ['HTTP Methods', 'GET'])
            add('HTTP Methods', 'POST thường được dùng trong trường hợp nào?', {'A': 'Tạo mới tài nguyên', 'B': 'Xóa tài nguyên', 'C': 'Tắt server', 'D': 'Đổi màu giao diện'}, 'A', 'POST thường dùng để gửi dữ liệu lên server nhằm tạo mới tài nguyên.', 'Sinh viên hiểu mục đích của POST trong REST API.', 'understand', 'easy', ['HTTP Methods', 'POST'])
            add('HTTP Methods', 'PUT thường phù hợp nhất với thao tác nào?', {'A': 'Cập nhật tài nguyên', 'B': 'Lấy danh sách dữ liệu', 'C': 'Xóa tài khoản khỏi hệ thống', 'D': 'Tạo file CSS'}, 'A', 'PUT thường được dùng để cập nhật toàn bộ tài nguyên theo dữ liệu gửi lên.', 'Sinh viên phân biệt PUT với GET/POST/DELETE.', 'understand', 'medium', ['HTTP Methods', 'PUT'])
            add('REST API', 'Khi một API cần vừa lấy dữ liệu vừa không làm thay đổi trạng thái tài nguyên, lựa chọn nào phù hợp nhất theo REST?', {'A': 'Dùng GET cho thao tác đọc dữ liệu', 'B': 'Dùng POST vì mọi request đều phải tạo mới', 'C': 'Dùng DELETE để server trả dữ liệu nhanh hơn', 'D': 'Dùng PUT để lấy danh sách dữ liệu'}, 'A', 'GET phù hợp cho thao tác đọc dữ liệu và không làm thay đổi trạng thái tài nguyên.', 'Sinh viên áp dụng đúng HTTP method trong tình huống cụ thể.', 'simple_apply', 'hard', ['REST API', 'HTTP Methods'])
            add('HTTP Methods', 'DELETE thường được dùng để làm gì trong REST API?', {'A': 'Xóa tài nguyên', 'B': 'Tạo mới tài nguyên', 'C': 'Lấy dữ liệu', 'D': 'Biên dịch project'}, 'A', 'DELETE thường được dùng để xóa một tài nguyên trên server.', 'Sinh viên nhận biết chức năng của DELETE.', 'remember', 'easy', ['HTTP Methods', 'DELETE'])

        if any(k in lower for k in ['entity framework', 'ef core', 'dbcontext', 'dbset', 'migration', 'savechanges']):
            add('Entity Framework Core', 'Entity Framework Core trong .NET có vai trò chính là gì?', {'A': 'ORM ánh xạ object với bảng database', 'B': 'Thư viện thiết kế icon', 'C': 'Công cụ nén ảnh', 'D': 'Trình duyệt web'}, 'A', 'EF Core là ORM giúp ánh xạ object trong code với bảng trong database.', 'Sinh viên nhận biết vai trò EF Core.', 'remember', 'easy', ['EF Core', 'ORM'])
            add('DbContext', 'DbContext trong EF Core dùng để làm gì?', {'A': 'Quản lý kết nối database và entity', 'B': 'Thiết kế giao diện người dùng', 'C': 'Chạy Docker container', 'D': 'Tạo file video'}, 'A', 'DbContext quản lý kết nối database, DbSet và theo dõi thay đổi entity.', 'Sinh viên hiểu vai trò DbContext.', 'understand', 'easy', ['EF Core', 'DbContext'])
            add('DbSet', 'DbSet thường đại diện cho thành phần nào?', {'A': 'Một tập entity, thường tương ứng với bảng dữ liệu', 'B': 'Một file cấu hình Docker', 'C': 'Một route trong React', 'D': 'Một cổng mạng'}, 'A', 'DbSet đại diện cho một tập entity và thường tương ứng với một bảng trong database.', 'Sinh viên nhận biết ý nghĩa DbSet.', 'remember', 'easy', ['EF Core', 'DbSet'])
            add('Migration', 'Migration trong EF Core dùng để làm gì?', {'A': 'Quản lý lịch sử thay đổi schema database', 'B': 'Gửi email cho sinh viên', 'C': 'Tạo màu cho button', 'D': 'Chạy unit test frontend'}, 'A', 'Migration tạo lịch sử thay đổi schema database theo thay đổi của model.', 'Sinh viên nhận biết vai trò Migration.', 'remember', 'easy', ['EF Core', 'Migration'])
            add('Migration', 'Lệnh Update-Database thường dùng để làm gì?', {'A': 'Áp dụng migration để cập nhật schema database', 'B': 'Xóa toàn bộ source code', 'C': 'Tạo component React', 'D': 'Đăng nhập vào Open edX'}, 'A', 'Update-Database áp dụng migration vào database.', 'Sinh viên hiểu bước cập nhật database sau khi tạo migration.', 'understand', 'medium', ['EF Core', 'Migration'])
            add('SaveChanges', 'Khi gọi SaveChanges trong EF Core, điều gì xảy ra?', {'A': 'Các thay đổi đang theo dõi được ghi xuống database', 'B': 'Trang web tự đổi giao diện', 'C': 'Docker image được build lại', 'D': 'Transcript video được tạo tự động'}, 'A', 'SaveChanges ghi các thay đổi mà DbContext đang theo dõi xuống database.', 'Sinh viên hiểu tác dụng SaveChanges.', 'understand', 'easy', ['EF Core', 'SaveChanges'])
            add('DbContext', 'Nếu entity đã được DbContext theo dõi nhưng chưa gọi SaveChanges, nhận định nào đúng nhất?', {'A': 'Thay đổi mới ở bộ nhớ ứng dụng, chưa chắc đã ghi xuống database', 'B': 'Database đã tự cập nhật ngay khi gán thuộc tính', 'C': 'Migration sẽ tự chạy thay cho SaveChanges', 'D': 'DbSet sẽ bị xóa khỏi model'}, 'A', 'DbContext theo dõi thay đổi, còn SaveChanges mới ghi các thay đổi đó xuống database.', 'Sinh viên kết hợp vai trò tracking của DbContext với SaveChanges.', 'simple_apply', 'hard', ['EF Core', 'DbContext', 'SaveChanges'])

        if any(k in lower for k in ['ai server', 'course sync', 'question bank', 'teacher review', 'learning check', 'olx', 'source grounding']):
            add('Course Sync', 'AI Server lấy dữ liệu khóa học từ đâu trong MVP?', {'A': 'Từ course đã có trong Open edX', 'B': 'Từ việc giáo viên upload lại thủ công', 'C': 'Từ mạng xã hội', 'D': 'Từ file bất kỳ không liên quan'}, 'A', 'MVP lấy nội dung trực tiếp từ course Open edX, không yêu cầu upload lại tài liệu.', 'Sinh viên/người dùng hiểu nguồn dữ liệu của AI Server.', 'understand', 'easy', ['Open edX', 'Course Sync'])
            add('Source Grounding', 'Vì sao mỗi câu hỏi cần source reference?', {'A': 'Để chứng minh câu hỏi bám sát tài liệu khóa học', 'B': 'Để làm câu hỏi khó hơn', 'C': 'Để ẩn đáp án đúng', 'D': 'Để tăng màu sắc giao diện'}, 'A', 'Source reference giúp giáo viên kiểm tra câu hỏi dựa trên slide, transcript hoặc component nào.', 'Sinh viên/người dùng hiểu lý do cần source grounding.', 'understand', 'medium', ['Source Grounding', 'Quality'])
            add('Question Bank', 'Nếu một Unit muốn random đúng câu hỏi sinh từ chính Unit đó, metadata nào quan trọng nhất?', {'A': 'source_node_id', 'B': 'Màu của button', 'C': 'Tên máy đang chạy Docker', 'D': 'Số ký tự trong đáp án'}, 'A', 'source_node_id cho biết node/component gốc tạo câu hỏi để Problem Bank filter/random đúng phạm vi.', 'Sinh viên/người dùng hiểu cách metadata hỗ trợ random/filter trong Open edX.', 'simple_apply', 'hard', ['Question Bank', 'source_node_id'])
            add('Teacher Review', 'AI-generated question có được publish trực tiếp cho sinh viên không?', {'A': 'Không, cần giáo viên review trước', 'B': 'Có, luôn publish ngay', 'C': 'Có, nếu câu hỏi có 4 đáp án', 'D': 'Có, nếu chi phí thấp'}, 'A', 'Câu hỏi AI mặc định cần qua Teacher Review để approve/reject/edit trước khi publish.', 'Sinh viên/người dùng hiểu state machine review.', 'remember', 'easy', ['Teacher Review', 'Question Bank'])
            add('Question Bank', 'Question Bank lưu câu hỏi theo những thông tin nào?', {'A': 'Course, node, difficulty, source và trạng thái', 'B': 'Chỉ lưu màu giao diện', 'C': 'Chỉ lưu mật khẩu user', 'D': 'Chỉ lưu tên server'}, 'A', 'Question Bank lưu câu hỏi kèm node/source metadata để filter, review và publish.', 'Sinh viên/người dùng nhận biết vai trò Question Bank.', 'remember', 'easy', ['Question Bank', 'Metadata'])
            add('Open edX Export', 'Câu hỏi approved có thể được export sang định dạng nào để đưa vào Open edX?', {'A': 'OLX XML', 'B': 'MP3', 'C': 'PNG', 'D': 'EXE'}, 'A', 'Open edX problem component có thể biểu diễn bằng OLX/XML.', 'Sinh viên/người dùng biết output publish sang Open edX.', 'remember', 'easy', ['Open edX', 'OLX'])

        if any(k in lower for k in ['cost control', 'quota', 'hard stop', 'usage log', 'tokens', 'budget']):
            add('Cost Control', 'Mọi request AI phải đi qua thành phần nào trước khi gọi model?', {'A': 'Cost Control Layer và Model Gateway', 'B': 'Trình phát nhạc', 'C': 'File ảnh nền', 'D': 'Bảng điểm sinh viên'}, 'A', 'Cost Control Layer và Model Gateway kiểm tra quota, estimate chi phí và ghi log trước khi gọi model.', 'Sinh viên/người dùng hiểu luồng kiểm soát chi phí.', 'understand', 'easy', ['Cost Control', 'Model Gateway'])
            add('Quota', 'Quota Phase 1 đề xuất cho mỗi lần generate là bao nhiêu câu?', {'A': '20-50 câu', 'B': '1.000-2.000 câu', 'C': 'Không giới hạn', 'D': 'Chỉ 1 câu duy nhất'}, 'A', 'Mỗi lần generate giới hạn 20-50 câu để dễ review và kiểm soát token.', 'Sinh viên/người dùng hiểu quota mỗi job.', 'remember', 'easy', ['Quota', 'Cost Control'])
            add('Hard Stop', 'Hard stop có tác dụng gì?', {'A': 'Chặn job vượt ngân sách hoặc quota trước khi gọi model', 'B': 'Tự động tăng chi phí', 'C': 'Bỏ qua bước review', 'D': 'Xóa toàn bộ question bank'}, 'A', 'Hard stop ngăn hệ thống gọi API nếu vượt ngân sách/quota.', 'Sinh viên/người dùng hiểu cơ chế chống AI chạy thả rông.', 'understand', 'medium', ['Hard Stop', 'Budget'])
            add('Cost Control', 'Vì sao actual cost không nên nhân safety_factor?', {'A': 'Vì actual cost phải phản ánh usage thật model trả về', 'B': 'Vì safety_factor dùng để làm đáp án khó hơn', 'C': 'Vì output token không cần tính tiền', 'D': 'Vì usage log chỉ dùng cho giao diện'}, 'A', 'Safety factor dùng cho estimate/hard stop; actual cost phải dựa trên usage thật và không nhân thêm.', 'Sinh viên/người dùng phân biệt estimate cost và actual cost.', 'simple_apply', 'hard', ['Cost Control', 'Actual Usage'])
            add('Usage Log', 'Usage log dùng để ghi lại thông tin gì?', {'A': 'Model, tokens, chi phí và người gọi', 'B': 'Màu nền dashboard', 'C': 'Tên bài hát', 'D': 'Mật khẩu người dùng'}, 'A', 'Usage log phục vụ dashboard chi phí theo course, teacher, feature và model.', 'Sinh viên/người dùng hiểu dữ liệu cost dashboard.', 'remember', 'easy', ['Usage Log', 'Cost Dashboard'])

        if not templates:
            add('Nội dung bài học', 'Theo nội dung bài học, mục tiêu của Learning Check là gì?', {'A': 'Kiểm tra sinh viên đã học và hiểu nội dung cơ bản', 'B': 'Đánh đố sinh viên bằng câu hỏi mẹo', 'C': 'Thay thế hoàn toàn giáo viên', 'D': 'Tạo câu hỏi ngoài tài liệu'}, 'A', 'Learning Check dùng để kiểm tra mức độ theo dõi bài học, không đánh đố.', 'Sinh viên hiểu mục tiêu Learning Check.', 'understand', 'easy', ['Learning Check'])
        return templates
