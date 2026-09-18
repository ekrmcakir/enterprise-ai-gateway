"""OpenAI-compatible /v1/chat/completions endpoint."""

import time
import json
from typing import Optional
from fastapi import APIRouter, Header, Depends, Request, Response
from fastapi.responses import StreamingResponse

from app.config import settings
from app.models.schemas import ChatCompletionRequest, ChatCompletionResponse, ChatMessage, Usage, ChatCompletionChoice, ChoiceMessage
from app.models.db_models import audit_store, AuditLogRecord
from app.core.exceptions import (
    AuthenticationError,
    SecurityFirewallBlockedException,
    GatewayException,
)
from app.core.logging import logger
from app.core.telemetry import (
    tracer,
    REQUESTS_TOTAL,
    LATENCY_HISTOGRAM,
    PROMPT_TOKENS_TOTAL,
    COMPLETION_TOKENS_TOTAL,
    ESTIMATED_COST_USD,
    FIREWALL_BLOCKED_TOTAL,
    COST_SAVINGS_USD_TOTAL,
)
from app.firewall.injection_detector import injection_detector
from app.firewall.pii_sanitizer import pii_sanitizer
from app.firewall.output_guard import output_guard
from app.cache.semantic_cache import semantic_cache
from app.finops.rate_limiter import rate_limiter
from app.finops.budget_manager import budget_manager
from app.finops.pricing_catalog import calculate_cost
from app.routing.router import router

chat_router = APIRouter(tags=["Chat Completions"])


def authenticate_client(authorization: Optional[str] = Header(None)) -> str:
    """Validates Authorization header against allowed API keys."""
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing or invalid Authorization header. Expected 'Bearer <key>'.")

    api_key = authorization[7:].strip()
    if api_key not in settings.allowed_api_keys and api_key != settings.master_api_key:
        raise AuthenticationError("Invalid API key provided.")

    return api_key


@chat_router.post("/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(
    request: ChatCompletionRequest,
    client_id: str = Depends(authenticate_client),
):
    start_time = time.time()

    with tracer.start_as_current_span("ai_gateway.process_completion") as span:
        span.set_attribute("gen_ai.request.model", request.model)
        span.set_attribute("client_id", client_id)

        # 1. FinOps Rate Limiting & Pre-flight Budget Check
        with tracer.start_as_current_span("finops.preflight_check"):
            est_tokens = sum(len(m.content.split()) * 2 for m in request.messages)
            rate_limiter.check_and_record(client_id, estimated_tokens=est_tokens)
            budget_manager.check_budget_preflight(client_id)

        # 2. Semantic Firewall: Prompt Injection & Jailbreak Detection
        with tracer.start_as_current_span("firewall.injection_scan"):
            all_user_content = " ".join(m.content for m in request.messages if m.role == "user")
            is_threat, score, threats = injection_detector.scan_text(all_user_content)
            
            if is_threat and (request.enable_firewall and settings.block_prompt_injections):
                FIREWALL_BLOCKED_TOTAL.labels(threat_type="prompt_injection", client_id=client_id).inc()
                latency_ms = (time.time() - start_time) * 1000.0
                
                # Record to Audit Log
                audit_store.add_record(AuditLogRecord(
                    client_id=client_id,
                    model_requested=request.model,
                    model_used=request.model,
                    status="blocked_firewall",
                    latency_ms=latency_ms,
                    prompt_tokens=est_tokens,
                    completion_tokens=0,
                    cost_usd=0.0,
                    firewall_triggered=True,
                    threat_details={"score": score, "threats": threats},
                    prompt_preview=all_user_content[:150],
                ))
                
                raise SecurityFirewallBlockedException(
                    message="Security Firewall: Prompt injection or jailbreak payload detected.",
                    threat_type="prompt_injection",
                    risk_score=score,
                    detected_patterns=threats,
                )

        # 3. Reversible PII Masking
        pii_mappings = {}
        masked_messages = []
        all_pii_entities = []

        with tracer.start_as_current_span("firewall.pii_masking"):
            if request.enable_firewall and settings.pii_masking_enabled:
                for msg in request.messages:
                    masked_txt, mapping, entities = pii_sanitizer.mask(msg.content)
                    pii_mappings.update(mapping)
                    all_pii_entities.extend(entities)
                    masked_messages.append(ChatMessage(role=msg.role, content=masked_txt, name=msg.name))
            else:
                masked_messages = request.messages

        sanitized_request = request.model_copy(update={"messages": masked_messages})

        # 4. Semantic Caching Fast Path
        with tracer.start_as_current_span("cache.semantic_lookup") as cache_span:
            if request.enable_cache and not request.stream:
                is_hit, cached_val, hit_type, sim_score = await semantic_cache.lookup(
                    model=sanitized_request.model,
                    messages=[m.model_dump() for m in sanitized_request.messages],
                    temperature=sanitized_request.temperature,
                )
                if is_hit and cached_val:
                    cache_span.set_attribute("cache.hit", True)
                    cache_span.set_attribute("cache.type", hit_type)
                    cache_span.set_attribute("cache.similarity", sim_score)

                    latency_ms = (time.time() - start_time) * 1000.0
                    LATENCY_HISTOGRAM.labels(model=request.model, source="cache_hit").observe(latency_ms / 1000.0)
                    REQUESTS_TOTAL.labels(model=request.model, client_id=client_id, status="cached").inc()

                    # Unmask cached content if needed
                    cached_content = cached_val["choices"][0]["message"]["content"]
                    restored_content = pii_sanitizer.unmask(cached_content, pii_mappings)
                    
                    saved_cost = cached_val.get("usage", {}).get("estimated_cost_usd", 0.0)
                    COST_SAVINGS_USD_TOTAL.labels(model=request.model).inc(saved_cost)

                    response_obj = ChatCompletionResponse(
                        id=cached_val.get("id"),
                        model=cached_val.get("model", request.model),
                        created=cached_val.get("created"),
                        choices=[
                            ChatCompletionChoice(
                                index=0,
                                message=ChoiceMessage(role="assistant", content=restored_content),
                                finish_reason="stop",
                            )
                        ],
                        usage=Usage(
                            prompt_tokens=cached_val.get("usage", {}).get("prompt_tokens", 0),
                            completion_tokens=cached_val.get("usage", {}).get("completion_tokens", 0),
                            total_tokens=cached_val.get("usage", {}).get("total_tokens", 0),
                            estimated_cost_usd=0.0,  # Zero dollar spend for cache hit
                        ),
                        gateway_metadata={
                            "cache_hit": True,
                            "cache_type": hit_type,
                            "similarity_score": sim_score,
                            "latency_ms": round(latency_ms, 2),
                            "cost_saved_usd": saved_cost,
                            "pii_entities_sanitized": list(set(all_pii_entities)),
                        }
                    )

                    audit_store.add_record(AuditLogRecord(
                        client_id=client_id,
                        model_requested=request.model,
                        model_used=response_obj.model,
                        status="cached",
                        latency_ms=latency_ms,
                        prompt_tokens=response_obj.usage.prompt_tokens,
                        completion_tokens=response_obj.usage.completion_tokens,
                        cost_usd=saved_cost,
                        cache_hit=True,
                        cache_type=hit_type,
                        pii_entities_masked=list(set(all_pii_entities)),
                        prompt_preview=all_user_content[:150],
                        completion_preview=restored_content[:150],
                    ))

                    return response_obj

        # 5. Handle Streaming Request
        if request.stream:
            async def sse_generator():
                async for chunk, prov_used, model_used in router.route_stream(sanitized_request):
                    data_str = f"data: {chunk.model_dump_json()}\n\n"
                    yield data_str.encode("utf-8")
                yield b"data: [DONE]\n\n"

            return StreamingResponse(sse_generator(), media_type="text/event-stream")

        # 6. Dispatch to Router & Upstream LLMs (with fallback cascade)
        with tracer.start_as_current_span("router.dispatch_upstream") as router_span:
            upstream_resp, provider_used, model_used = await router.route_completion(sanitized_request)
            router_span.set_attribute("upstream.provider", provider_used)
            router_span.set_attribute("upstream.model", model_used)

        # 7. Response Processing: Unmask PII and Output Guardrail Check
        with tracer.start_as_current_span("firewall.post_process"):
            raw_assistant_text = upstream_resp.choices[0].message.content
            # Restore PII
            restored_text = pii_sanitizer.unmask(raw_assistant_text, pii_mappings)
            # Inspect output guard
            is_clean, clean_text, violations = output_guard.inspect_output(restored_text)
            
            # Replace content
            upstream_resp.choices[0].message.content = clean_text

        # 8. Store in Semantic Cache
        if request.enable_cache:
            with tracer.start_as_current_span("cache.store"):
                await semantic_cache.store(
                    model=sanitized_request.model,
                    messages=[m.model_dump() for m in sanitized_request.messages],
                    response_data=upstream_resp.model_dump(),
                    temperature=sanitized_request.temperature,
                )

        # 9. FinOps & Metrics Accounting
        latency_ms = (time.time() - start_time) * 1000.0
        p_toks = upstream_resp.usage.prompt_tokens
        c_toks = upstream_resp.usage.completion_tokens
        cost_usd = calculate_cost(upstream_resp.model, p_toks, c_toks)
        upstream_resp.usage.estimated_cost_usd = cost_usd

        # Record spend in FinOps manager
        budget_manager.record_usage(client_id, cost_usd, p_toks + c_toks)

        # Update OTel / Prometheus metrics
        REQUESTS_TOTAL.labels(model=upstream_resp.model, client_id=client_id, status="success").inc()
        LATENCY_HISTOGRAM.labels(model=upstream_resp.model, source="upstream_call").observe(latency_ms / 1000.0)
        PROMPT_TOKENS_TOTAL.labels(model=upstream_resp.model, client_id=client_id).inc(p_toks)
        COMPLETION_TOKENS_TOTAL.labels(model=upstream_resp.model, client_id=client_id).inc(c_toks)
        ESTIMATED_COST_USD.labels(model=upstream_resp.model, client_id=client_id).inc(cost_usd)

        # Attach gateway metadata
        upstream_resp.gateway_metadata = {
            "cache_hit": False,
            "provider_used": provider_used,
            "model_used": model_used,
            "latency_ms": round(latency_ms, 2),
            "cost_usd": cost_usd,
            "pii_entities_sanitized": list(set(all_pii_entities)),
            "output_guard_clean": is_clean,
        }

        # Record to Audit Log
        audit_store.add_record(AuditLogRecord(
            client_id=client_id,
            model_requested=request.model,
            model_used=upstream_resp.model,
            status="success",
            latency_ms=latency_ms,
            prompt_tokens=p_toks,
            completion_tokens=c_toks,
            cost_usd=cost_usd,
            cache_hit=False,
            pii_entities_masked=list(set(all_pii_entities)),
            prompt_preview=all_user_content[:150],
            completion_preview=clean_text[:150],
        ))

        return upstream_resp
