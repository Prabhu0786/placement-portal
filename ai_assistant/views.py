import json
import logging
import os

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.db.models import Q
from urllib.parse import urlsplit
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from google import genai
from google.genai import types

from .models import Conversation, Message
from content.models import ContentStatus, Resource

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 6000
MAX_CONTEXT_MESSAGES = 8

SYSTEM_INSTRUCTIONS = """
You are the AI Placement Assistant in a university placement preparation portal.
Help students with programming, DSA, computer science subjects, aptitude,
interview preparation, resumes, career planning and professional communication.

Be accurate, friendly, practical and clear. Explain concepts step by step for
beginners when needed. For code, give readable code and explain important parts.
For practice or mock interviews, ask one question at a time and wait for the
student's answer. Never invent job openings, deadlines, company policies,
student grades or personal records. Be honest when uncertain. Reply in the
language requested by the student, or follow the language they use.
Use Markdown headings, lists and fenced code blocks where useful.
"""



# ---------------------------------------------------------------------------
# Placement Resource Hub retrieval
# Only published resources with valid HTTPS links are eligible for AI context.
# ---------------------------------------------------------------------------
RESOURCE_STOP_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "what", "how",
    "can", "you", "your", "about", "please", "give", "show", "tell",
    "explain", "help", "want", "need", "make", "create", "prepare",
    "should", "would", "could", "into", "are", "is", "was", "were",
    "a", "an", "to", "of", "in", "on", "at", "by", "or", "as", "my",
    "me", "i", "we", "it", "be", "do", "does", "did", "learn", "study",
}


def retrieve_portal_resources(question, limit=5):
    """Return relevant, published Resource Hub entries for a student's question."""
    words = {
        word.lower()
        for word in __import__("re").findall(r"[A-Za-z0-9+#.]{2,}", question)
        if word.lower() not in RESOURCE_STOP_WORDS
    }
    if not words:
        return []

    query = Q()
    for word in words:
        query |= (
            Q(title__icontains=word)
            | Q(topic__name__icontains=word)
            | Q(topic__subject__icontains=word)
            | Q(source__icontains=word)
        )

    candidates = (
        Resource.objects.filter(status=ContentStatus.PUBLISHED)
        .exclude(url="")
        .filter(query)
        .select_related("topic")
        .only(
            "id", "title", "url", "type", "language", "source",
            "topic__name", "topic__subject",
        )[:100]
    )

    ranked = []
    for resource in candidates:
        parsed = urlsplit(resource.url)
        if parsed.scheme != "https" or not parsed.netloc:
            continue

        title = (resource.title or "").lower()
        topic_name = (resource.topic.name or "").lower()
        subject = (resource.topic.subject or "").lower()
        source = (resource.source or "").lower()

        score = 0
        for word in words:
            if word in title:
                score += 4
            if word in topic_name:
                score += 3
            if word in subject:
                score += 2
            if word in source:
                score += 1

        if score:
            ranked.append((score, resource))

    ranked.sort(key=lambda item: (-item[0], item[1].title.lower()))
    return [resource for _, resource in ranked[:limit]]


def build_resource_context(resources):
    if not resources:
        return "", ""
    lines = []
    for index, resource in enumerate(resources, start=1):
        lines.append(
            f"{index}. {resource.title} | "
            f"Topic: {resource.topic.subject} / {resource.topic.name} | "
            f"Type: {resource.get_type_display()} | "
            f"Language: {resource.get_language_display()} | "
            f"URL: {resource.url}"
        )
    context = (
        "\n\nVERIFIED PORTAL RESOURCE RECORDS (from the student's Resource Hub):\n"
        + "\n".join(lines)
        + "\nUse these records only when relevant. Never invent additional portal "
          "resources, descriptions, ratings, or availability. If none is relevant, "
          "say so. Distinguish your general explanation from what the portal records show."
    )
    footer = (
        "\n\n---\n**Related resources from this portal**\n"
        + "\n".join(
            f"- [{resource.title}]({resource.url}) — "
            f"{resource.topic.subject} / {resource.topic.name} "
            f"({resource.get_language_display()})"
            for resource in resources
        )
    )
    return context, footer



def _owned_conversation(user, conversation_id):
    return get_object_or_404(Conversation, pk=conversation_id, user=user)


@login_required
def chat(request):
    conversations = Conversation.objects.filter(user=request.user)[:60]
    active_id = request.GET.get("conversation")
    active_conversation = None
    messages = []

    if active_id:
        try:
            active_conversation = _owned_conversation(request.user, int(active_id))
            messages = list(active_conversation.messages.all())
        except (ValueError, TypeError):
            active_conversation = None

    return render(request, "ai_assistant/chat.html", {
        "conversations": conversations,
        "active_conversation": active_conversation,
        "messages": messages,
    })


@login_required
@require_POST
def new_conversation(request):
    conversation = Conversation.objects.create(user=request.user)
    return JsonResponse({
        "id": conversation.id,
        "url": f"/ai-assistant/conversation/{conversation.id}/",
    })


@login_required
@require_POST
def send_message(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)

    message_text = str(data.get("message", "")).strip()
    conversation_id = data.get("conversation_id")
    language = str(data.get("language", "auto"))
    mode = str(data.get("mode", "general"))

    if not message_text:
        return JsonResponse({"error": "Please type a message."}, status=400)
    if len(message_text) > MAX_MESSAGE_LENGTH:
        return JsonResponse({"error": f"Message must be under {MAX_MESSAGE_LENGTH} characters."}, status=400)

    if language not in {"auto", "english", "hindi", "hinglish"}:
        language = "auto"
    if mode not in {"general", "explain", "practice", "interview", "resume"}:
        mode = "general"

    if conversation_id:
        conversation = _owned_conversation(request.user, conversation_id)
    else:
        conversation = Conversation.objects.create(user=request.user)

    is_first_message = not conversation.messages.exists()
    user_message = Message.objects.create(
        conversation=conversation,
        role=Message.Role.USER,
        content=message_text,
    )
    if is_first_message:
        conversation.title = message_text[:68].strip() or "New chat"
        if len(message_text) > 68:
            conversation.title = conversation.title.rstrip() + "…"
    conversation.save()

    api_key = os.getenv("GEMINI_API_KEY")
    # Flash-Lite is optimized for low-latency, high-throughput chat.
    # Vercel environment variables can override these defaults.
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
    if not api_key:
        return JsonResponse({"error": "AI service is not configured. Please contact the administrator."}, status=503)

    previous = list(
        conversation.messages.exclude(pk=user_message.pk)
        .order_by("-created_at")[:MAX_CONTEXT_MESSAGES]
    )
    previous.reverse()

    mode_text = {
        "general": "Answer directly and helpfully.",
        "explain": "Teach from basics, with a simple example and short recap.",
        "practice": "Ask one practice question at a time. Wait for the student's answer before evaluating.",
        "interview": "Conduct a realistic fresher mock interview, one question at a time. Give constructive feedback after each answer.",
        "resume": "Review only resume details provided. Do not invent achievements or experience.",
    }[mode]
    language_text = {
        "auto": "Use the student's language.",
        "english": "Use clear, simple English.",
        "hindi": "Use simple Hindi, retaining technical terms in English where useful.",
        "hinglish": "Use natural, simple Hinglish.",
    }[language]

    matched_resources = retrieve_portal_resources(message_text)
    resource_context, resource_footer = build_resource_context(matched_resources)

    prompt_parts = [
        SYSTEM_INSTRUCTIONS,
        f"\nCurrent mode: {mode_text}\nResponse language: {language_text}\n",
        resource_context,
    ]
    for item in previous:
        speaker = "Student" if item.role == Message.Role.USER else "Assistant"
        prompt_parts.append(f"{speaker}: {item.content}")
    prompt_parts.append(f"Student: {message_text}\nAssistant:")
    prompt = "\n\n".join(prompt_parts)

    def stream_answer():
        client = None
        collected = []
        last_error = None
        try:
            retry_options = types.HttpRetryOptions(
                attempts=2,
                initial_delay=0.5,
                max_delay=2.0,
                exp_base=2.0,
                jitter=0.25,
                http_status_codes=[408, 429, 500, 502, 503, 504],
            )
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=45000,
                    retry_options=retry_options,
                ),
            )

            model_candidates = [model_name]
            if fallback_model and fallback_model != model_name:
                model_candidates.append(fallback_model)

            generated = False
            for candidate in model_candidates:
                try:
                    stream = client.models.generate_content_stream(
                        model=candidate,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            max_output_tokens=1400,
                            temperature=0.4,
                        ),
                    )
                    for chunk in stream:
                        piece = getattr(chunk, "text", None)
                        if piece:
                            collected.append(piece)
                            yield piece

                    generated = True
                    if candidate != model_name:
                        logger.warning("AI response completed using fallback model %s", candidate)
                    break

                except Exception as exc:
                    last_error = exc
                    status_code = (
                        getattr(exc, "code", None)
                        or getattr(exc, "status_code", None)
                    )
                    logger.warning(
                        "Gemini model %s failed before completion (status=%s): %s",
                        candidate, status_code, str(exc)[:500],
                        exc_info=True,
                    )
                    if collected:
                        raise
                    if status_code not in {408, 429, 500, 502, 503, 504}:
                        raise
                    continue

            if not generated and not collected:
                raise last_error or RuntimeError("No Gemini model produced a response.")

            final_text = "".join(collected).strip()
            if final_text:
                if resource_footer:
                    final_text += resource_footer
                    yield resource_footer
                Message.objects.create(
                    conversation=conversation,
                    role=Message.Role.ASSISTANT,
                    content=final_text,
                )
                conversation.save()
            else:
                fallback_text = "I couldn't generate a response. Please try again."
                Message.objects.create(
                    conversation=conversation,
                    role=Message.Role.ASSISTANT,
                    content=fallback_text,
                )
                yield fallback_text

        except Exception as exc:
            logger.exception("Gemini streaming request failed.")
            if collected:
                partial = "".join(collected)
                Message.objects.create(
                    conversation=conversation,
                    role=Message.Role.ASSISTANT,
                    content=partial,
                )
                yield "\n\n[The response was interrupted. Please try again if anything is missing.]"
            else:
                status_code = (
                    getattr(exc, "code", None)
                    or getattr(exc, "status_code", None)
                )
                if status_code == 429:
                    error_text = (
                        "The AI service has reached its current usage limit. "
                        "Please try again later."
                    )
                elif status_code in {500, 502, 503, 504, 408}:
                    error_text = (
                        "The AI service is temporarily busy. Please try again in a moment."
                    )
                else:
                    error_text = (
                        "The AI service could not complete this request. "
                        "Please try again or contact the portal administrator."
                    )
                Message.objects.create(
                    conversation=conversation,
                    role=Message.Role.ASSISTANT,
                    content=error_text,
                )
                yield error_text
        finally:
            if client is not None:
                client.close()

    response = StreamingHttpResponse(stream_answer(), content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    response["X-Conversation-Id"] = str(conversation.id)
    return response


@login_required
@require_POST
def rename_conversation(request, conversation_id):
    conversation = _owned_conversation(request.user, conversation_id)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)
    title = str(data.get("title", "")).strip()
    if not title:
        return JsonResponse({"error": "Chat title cannot be empty."}, status=400)
    conversation.title = title[:120]
    conversation.save(update_fields=["title", "updated_at"])
    return JsonResponse({"title": conversation.title})


@login_required
@require_POST
def delete_conversation(request, conversation_id):
    conversation = _owned_conversation(request.user, conversation_id)
    conversation.delete()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def clear_chat(request):
    Conversation.objects.filter(user=request.user).delete()
    return redirect("ai_chat")


@login_required
def open_conversation(request, conversation_id):
    _owned_conversation(request.user, conversation_id)
    return redirect(f"/ai-assistant/?conversation={conversation_id}")
